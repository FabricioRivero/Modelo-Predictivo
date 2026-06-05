"""
jleague_analyzer.py — Sistema completo de análisis de apuestas J-League
==========================================================================
MEJORAS v2:
  ✅ Cuotas Pinnacle como referencia principal (+ The Odds API como backup)
  ✅ Forma reciente: doble peso a los últimos 6 partidos de cada equipo
  ✅ Stats de jugadores: goles por equipo ajustan las lambdas del modelo
  ✅ Reporte HTML mejorado: confianza, forma reciente, indicador Pinnacle

Flujo:
  JPN.csv → Dixon-Coles + Forma → The Odds API → Comparar vs Pinnacle → HTML
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
import json, os, sys
from datetime import datetime, timedelta, timezone

# ══════════════════════════════════════════════════════════════
# ── CONFIGURACIÓN ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════
BASE         = r"D:\MODELO DE PREDICCION\Codigo"
API_KEY      = "07fed81a038a0eb0b8c6c4abedcdcd35"
CSV_FILE     = "JPN.csv"
PLAYERS_CSV  = "J1_League_Player_Stats_2022_2025.csv"
OUTPUT_HTML  = os.path.join(BASE, "jleague_report.html")

XI            = 0.00325   # time decay estándar Dixon-Coles
FORM_MATCHES  = 6         # partidos recientes con peso extra
FORM_BOOST    = 2.5       # multiplicador de peso para forma reciente
VALUE_THRESH  = 0.04      # umbral value bet: 4%
DRAW_ENABLED  = False     # ⛔ empates desactivados — ROI histórico -46%, no fiable
FORM_MIN_PTS  = 1.2       # pts/partido mínimos del equipo favorecido para activar value bet
N_SIM         = 100_000   # simulaciones Monte Carlo


# ══════════════════════════════════════════════════════════════
# BLOQUE 1 — CARGA CSV (JPN.csv con columnas Pinnacle)
# ══════════════════════════════════════════════════════════════
def load_jleague_csv(path, verbose=True):
    df = pd.read_csv(path, encoding='utf-8-sig', on_bad_lines='skip', low_memory=False)

    rename = {}
    for c in df.columns:
        cl = c.strip().lower()
        if   cl == 'home':     rename[c] = 'home_team'
        elif cl == 'away':     rename[c] = 'away_team'
        elif cl == 'hg':       rename[c] = 'home_goals'
        elif cl == 'ag':       rename[c] = 'away_goals'
        elif cl == 'hometeam': rename[c] = 'home_team'
        elif cl == 'awayteam': rename[c] = 'away_team'
        elif cl == 'fthg':     rename[c] = 'home_goals'
        elif cl == 'ftag':     rename[c] = 'away_goals'
        elif cl == 'date':     rename[c] = 'date_raw'
        elif cl == 'psch':     rename[c] = 'ps_home'
        elif cl == 'pscd':     rename[c] = 'ps_draw'
        elif cl == 'psca':     rename[c] = 'ps_away'
        elif cl == 'res':      rename[c] = 'result'
    df.rename(columns=rename, inplace=True)

    required = ['home_team', 'away_team', 'home_goals', 'away_goals', 'date_raw']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}. Disponibles: {list(df.columns)}")

    # Mantener columnas Pinnacle si existen
    keep = required[:]
    for col in ['ps_home', 'ps_draw', 'ps_away', 'result']:
        if col in df.columns:
            keep.append(col)

    df = df[keep].copy()
    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df.dropna(subset=['home_goals', 'away_goals'], inplace=True)
    df['home_goals'] = df['home_goals'].astype(int)
    df['away_goals'] = df['away_goals'].astype(int)

    # Parseo de fecha robusto
    best = None
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y']:
        parsed = pd.to_datetime(df['date_raw'], format=fmt, errors='coerce')
        if best is None or parsed.notna().sum() > best.notna().sum():
            best = parsed
    fallback = pd.to_datetime(df['date_raw'], dayfirst=True, errors='coerce')
    df['match_date'] = pd.to_datetime(best.where(best.notna(), fallback), errors='coerce')
    df.dropna(subset=['match_date'], inplace=True)
    df = df.sort_values('match_date').reset_index(drop=True)

    # Pinnacle numéricas
    for col in ['ps_home', 'ps_draw', 'ps_away']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            df[col] = np.nan

    if verbose:
        n_ps = df['ps_home'].notna().sum()
        print(f"  ✓ {len(df):,} partidos  ({df['match_date'].min().date()} → {df['match_date'].max().date()})")
        print(f"  ✓ {df['home_team'].nunique()} equipos distintos")
        print(f"  ✓ Cuotas Pinnacle disponibles: {n_ps:,} partidos ({n_ps/len(df)*100:.0f}%)")
    return df


# ══════════════════════════════════════════════════════════════
# BLOQUE 2 — STATS DE JUGADORES (ajuste de lambda por plantilla)
# ══════════════════════════════════════════════════════════════
def load_player_stats(path):
    """
    Carga J1_League_Player_Stats_2022_2025.csv y calcula
    un índice de potencial ofensivo por equipo (goles/90 agregados).
    Devuelve dict: team_name → offensive_index (float, normalizado ~1.0)
    """
    try:
        df = pd.read_csv(path, encoding='utf-8-sig', on_bad_lines='skip', low_memory=False)
        # Columnas: Squad, Gls, Min, Season
        # Usar solo última temporada disponible
        if 'Season' in df.columns:
            last_season = df['Season'].max()
            df = df[df['Season'] == last_season]

        if 'Squad' not in df.columns or 'Gls' not in df.columns:
            return {}

        df['Gls'] = pd.to_numeric(df['Gls'], errors='coerce').fillna(0)
        df['Min'] = pd.to_numeric(str(df['Min']).replace(',',''), errors='coerce') if 'Min' in df.columns else 90

        # Goles totales por equipo en la temporada
        team_goals = df.groupby('Squad')['Gls'].sum()

        # Normalizar: media = 1.0
        mean_g = team_goals.mean()
        if mean_g > 0:
            team_index = (team_goals / mean_g).to_dict()
        else:
            team_index = {}

        return team_index
    except Exception as e:
        print(f"  ⚠ No se pudo cargar stats de jugadores: {e}")
        return {}


# ══════════════════════════════════════════════════════════════
# BLOQUE 3 — FORMA RECIENTE (últimos N partidos, más peso)
# ══════════════════════════════════════════════════════════════
def compute_form_weights(df, form_matches=FORM_MATCHES, form_boost=FORM_BOOST):
    """
    Retorna un array de pesos del mismo tamaño que df.
    Los últimos FORM_MATCHES partidos de cada equipo reciben
    un peso multiplicado por FORM_BOOST sobre el time decay normal.
    """
    ref   = df['match_date'].max()
    days  = (ref - df['match_date']).dt.days.values
    base_w = np.exp(-XI * days)  # time decay estándar

    # Identificar últimos N partidos de cada equipo
    boost_mask = np.zeros(len(df), dtype=bool)
    teams = set(df['home_team']) | set(df['away_team'])
    for team in teams:
        mask = (df['home_team'] == team) | (df['away_team'] == team)
        idxs = df[mask].index.tolist()[-form_matches:]  # últimos N
        boost_mask[idxs] = True

    weights = np.where(boost_mask, base_w * form_boost, base_w)
    return weights


# ══════════════════════════════════════════════════════════════
# BLOQUE 4 — DIXON-COLES CON PESOS EXTERNOS
# ══════════════════════════════════════════════════════════════
def rho_correction(hg, ag, lam, mu, rho):
    if   hg == 0 and ag == 0: return max(1e-10, 1 - lam * mu * rho)
    elif hg == 0 and ag == 1: return max(1e-10, 1 + lam * rho)
    elif hg == 1 and ag == 0: return max(1e-10, 1 + mu  * rho)
    elif hg == 1 and ag == 1: return max(1e-10, 1 - rho)
    return 1.0

def dc_log_likelihood(params, df, teams, weights):
    n   = len(teams)
    atk = params[:n]
    dfc = params[n:2*n]
    rho = params[2*n]
    gam = params[2*n + 1]

    hidx = np.array([teams.index(t) for t in df['home_team']])
    aidx = np.array([teams.index(t) for t in df['away_team']])

    lam  = np.exp(atk[hidx] + dfc[aidx] + gam)
    mu   = np.exp(atk[aidx] + dfc[hidx])
    hg   = df['home_goals'].values
    ag   = df['away_goals'].values

    rc = np.array([rho_correction(h, a, l, m, rho)
                   for h, a, l, m in zip(hg, ag, lam, mu)])
    ll = weights * (poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu) + np.log(rc))
    return -np.sum(ll)

def fit_dixon_coles(df, player_index=None, verbose=True):
    """
    Ajusta Dixon-Coles con:
    - Time decay + boost de forma reciente en los pesos
    - Ajuste opcional por stats de jugadores (player_index)
    """
    weights = compute_form_weights(df)
    teams   = sorted(set(df['home_team']) | set(df['away_team']))
    n       = len(teams)
    x0      = np.zeros(2 * n + 2)
    x0[2*n + 1] = 0.15  # gamma inicial

    bounds = [(-3, 3)] * n + [(-3, 3)] * n + [(-0.99, 0.99)] + [(0, 2)]

    result = minimize(
        dc_log_likelihood, x0,
        args=(df, teams, weights),
        method='SLSQP',
        bounds=bounds,
        options={'maxiter': 1000, 'ftol': 1e-8}
    )

    attack_raw  = dict(zip(teams, result.x[:n]))
    defence_raw = dict(zip(teams, result.x[n:2*n]))

    # ── Ajuste por stats de jugadores (si está disponible) ──
    # Si el índice ofensivo del equipo es mayor al promedio,
    # se suma un pequeño boost logarítmico al ataque (máx ±0.15)
    if player_index:
        for team in teams:
            if team in player_index:
                idx = player_index[team]
                boost = np.clip(np.log(idx) * 0.15, -0.15, 0.15)
                attack_raw[team] = attack_raw[team] + boost

    if verbose:
        print(f"  ✓ Convergencia: {result.success}")
        print(f"  rho   = {result.x[2*n]:.4f}  (ideal: -0.05 a -0.20)")
        print(f"  gamma = {result.x[2*n+1]:.4f}  (ideal:  0.15 a 0.40)")

    return {
        'attack':  attack_raw,
        'defence': defence_raw,
        'rho':     result.x[2*n],
        'gamma':   result.x[2*n + 1],
        'success': result.success,
        'teams':   teams
    }


# ══════════════════════════════════════════════════════════════
# BLOQUE 5 — FORMA RECIENTE VISIBLE (para el reporte)
# ══════════════════════════════════════════════════════════════
def get_team_form(df, team, n=6):
    """
    Devuelve los últimos N resultados de un equipo como lista:
    ['W','D','L','W','W','D']  (desde más reciente a más antiguo)
    y métricas: goles marcados, goles recibidos, puntos/partido
    """
    mask = (df['home_team'] == team) | (df['away_team'] == team)
    recent = df[mask].tail(n)

    form = []
    gf_list, ga_list = [], []
    for _, row in recent.iterrows():
        is_home = row['home_team'] == team
        gf = row['home_goals'] if is_home else row['away_goals']
        ga = row['away_goals'] if is_home else row['home_goals']
        gf_list.append(gf)
        ga_list.append(ga)
        if   gf > ga: form.append('W')
        elif gf < ga: form.append('L')
        else:          form.append('D')

    form.reverse()  # más reciente primero
    gf_list.reverse()
    ga_list.reverse()

    pts = sum({'W':3,'D':1,'L':0}[r] for r in form)
    return {
        'form':   form,
        'gf':     gf_list,
        'ga':     ga_list,
        'pts_pg': round(pts / max(len(form), 1), 2),
        'avg_gf': round(np.mean(gf_list) if gf_list else 0, 2),
        'avg_ga': round(np.mean(ga_list) if ga_list else 0, 2),
    }


# ══════════════════════════════════════════════════════════════
# BLOQUE 6 — PREDICCIÓN MONTE CARLO
# ══════════════════════════════════════════════════════════════
def predict_match(home, away, params, n_sim=N_SIM):
    atk   = params['attack']
    dfc   = params['defence']
    rho   = params['rho']
    gamma = params['gamma']

    avg_atk = np.mean(list(atk.values()))
    avg_def = np.mean(list(dfc.values()))

    lam_h = np.exp(atk.get(home, avg_atk) + dfc.get(away, avg_def) + gamma)
    lam_a = np.exp(atk.get(away, avg_atk) + dfc.get(home, avg_def))

    hg = np.random.poisson(lam_h, n_sim)
    ag = np.random.poisson(lam_a, n_sim)

    r     = np.random.random(n_sim)
    valid = np.ones(n_sim, dtype=bool)
    for mask, thresh in [
        ((hg==0)&(ag==0), max(0, 1 - lam_h*lam_a*rho)),
        ((hg==1)&(ag==0), max(0, 1 + lam_a*rho)),
        ((hg==0)&(ag==1), max(0, 1 + lam_h*rho)),
        ((hg==1)&(ag==1), max(0, 1 - rho)),
    ]:
        valid[mask] &= r[mask] < thresh

    hg, ag = hg[valid], ag[valid]
    nv = max(len(hg), 1)

    scores = {}
    for h, a in zip(hg, ag):
        scores[(int(h), int(a))] = scores.get((int(h), int(a)), 0) + 1

    top5 = sorted(scores.items(), key=lambda x: -x[1])[:5]
    top5 = [(h, a, cnt/nv) for (h, a), cnt in top5]

    matrix = np.zeros((6, 6))
    for (h, a), cnt in scores.items():
        if h <= 5 and a <= 5:
            matrix[h, a] = cnt / nv

    return {
        'home': home, 'away': away,
        'lambda_home': lam_h, 'lambda_away': lam_a,
        'p_home': np.sum(hg > ag) / nv,
        'p_draw': np.sum(hg == ag) / nv,
        'p_away': np.sum(ag > hg) / nv,
        'top_scores': top5,
        'score_matrix': matrix.tolist(),
        'known_home': home in params['teams'],
        'known_away': away in params['teams'],
    }


# ══════════════════════════════════════════════════════════════
# BLOQUE 7 — MAPEO DE NOMBRES API → CSV
# ══════════════════════════════════════════════════════════════
NAME_MAP = {
    "Kashima Antlers":        "Kashima Antlers",
    "Gamba Osaka":            "Gamba Osaka",
    "Urawa Red Diamonds":     "Urawa Reds",
    "Urawa Reds":             "Urawa Reds",
    "Yokohama F Marinos":     "Yokohama F. Marinos",
    "Yokohama F. Marinos":    "Yokohama F. Marinos",
    "FC Tokyo":               "FC Tokyo",
    "Cerezo Osaka":           "Cerezo Osaka",
    "Vissel Kobe":            "Vissel Kobe",
    "Kawasaki Frontale":      "Kawasaki Frontale",
    "Nagoya Grampus":         "Nagoya Grampus",
    "Sanfrecce Hiroshima":    "Sanfrecce Hiroshima",
    "Hiroshima Sanfrecce FC": "Sanfrecce Hiroshima",
    "Avispa Fukuoka":         "Avispa Fukuoka",
    "JEF United Chiba":       "JEF United",
    "FC Machida Zelvia":      "Machida",
    "Machida Zelvia":         "Machida",
    "Tokyo Verdy":            "Verdy",
    "Shimizu S Pulse":        "Shimizu S-Pulse",
    "Shimizu S-Pulse":        "Shimizu S-Pulse",
    "Kashiwa Reysol":         "Kashiwa Reysol",
    "Kyoto Purple Sanga":     "Kyoto",
    "Kyoto Sanga":            "Kyoto",
    "Fagiano Okayama":        "Okayama",
    "Mito HollyHock":         "Mito HollyHock",
    "V-Varen Nagasaki":       "V-Varen Nagasaki",
    "Shonan Bellmare":        "Shonan Bellmare",
    "Albirex Niigata":        "Albirex Niigata",
    "Yokohama FC":            "Yokohama FC",
    "Sagan Tosu":             "Sagan Tosu",
    "Consadole Sapporo":      "Hokkaido Consadole Sapporo",
    "Consa Sapporo":          "Hokkaido Consadole Sapporo",
    "Grampus":                "Nagoya Grampus",
}

def normalize_name(name):
    return NAME_MAP.get(name, name)


# ══════════════════════════════════════════════════════════════
# BLOQUE 8 — OBTENER PARTIDOS (The Odds API + Pinnacle del CSV)
# ══════════════════════════════════════════════════════════════
def fetch_fixtures(api_key, hours_ahead=72):
    """
    Consulta The Odds API. Para cada partido incluye:
    - Cuotas de mercado (The Odds API) → para detectar value bets en tiempo real
    - Las cuotas Pinnacle del CSV son el benchmark histórico (backtest)
    """
    try:
        import urllib.request
        url = (f"https://api.the-odds-api.com/v4/sports/soccer_japan_j_league/odds/"
               f"?apiKey={api_key}&regions=eu&markets=h2h&oddsFormat=decimal"
               f"&bookmakers=pinnacle,betfair_ex_eu,bet365,unibet")
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())

        now     = datetime.now(timezone.utc)
        cutoff  = now + timedelta(hours=hours_ahead)
        fixtures = []

        for g in data:
            t = datetime.fromisoformat(g['commence_time'].replace('Z', '+00:00'))
            if t > cutoff:
                continue

            home_api = g['home_team']
            away_api = g['away_team']

            # Intentar obtener Pinnacle primero, luego mejor disponible
            odds_by_book = {}
            for book in g.get('bookmakers', []):
                bkey = book['key']
                for mkt in book.get('markets', []):
                    if mkt['key'] == 'h2h':
                        o = {'home': None, 'draw': None, 'away': None}
                        for outcome in mkt['outcomes']:
                            n = outcome['name']
                            if n == home_api:   o['home'] = outcome['price']
                            elif n == 'Draw':   o['draw'] = outcome['price']
                            elif n == away_api: o['away'] = outcome['price']
                        if o['home']:
                            odds_by_book[bkey] = o
                        break

            # Prioridad: pinnacle > betfair > bet365 > cualquiera
            odds = None
            source = 'N/A'
            for pref in ['pinnacle', 'betfair_ex_eu', 'bet365', 'unibet']:
                if pref in odds_by_book:
                    odds  = odds_by_book[pref]
                    source = pref
                    break
            if odds is None and odds_by_book:
                source, odds = next(iter(odds_by_book.items()))

            if odds is None:
                odds = {'home': None, 'draw': None, 'away': None}

            # Margen de la casa (overround)
            margin = None
            if odds['home'] and odds['draw'] and odds['away']:
                margin = round((1/odds['home'] + 1/odds['draw'] + 1/odds['away'] - 1) * 100, 2)

            fixtures.append({
                'commence':   t,
                'home_api':   home_api,
                'away_api':   away_api,
                'home_csv':   normalize_name(home_api),
                'away_csv':   normalize_name(away_api),
                'odds':       odds,
                'odds_source': source,
                'margin':     margin,
            })
        return fixtures

    except Exception as e:
        print(f"  ⚠ API error: {e}")
        return []


# ══════════════════════════════════════════════════════════════
# BLOQUE 9 — CÁLCULO DE VALUE BET (con filtros)
# ══════════════════════════════════════════════════════════════
def calc_value(pred, odds, form_home=None, form_away=None, threshold=VALUE_THRESH):
    """
    Calcula value bets aplicando dos filtros:
      1. Empates desactivados (DRAW_ENABLED=False) — ROI histórico -46%
      2. Forma reciente: solo activar value si el equipo favorecido
         tiene >= FORM_MIN_PTS pts/partido en los últimos 6 partidos
    """
    res = {}
    for outcome, prob_key, odd in [
        ('home', 'p_home', odds.get('home')),
        ('draw', 'p_draw', odds.get('draw')),
        ('away', 'p_away', odds.get('away')),
    ]:
        if not (odd and odd > 1.0):
            continue

        implied  = 1.0 / odd
        model_p  = pred[prob_key]
        value    = model_p - implied
        edge_rel = value / implied if implied > 0 else 0

        # ── Filtro 1: empates desactivados ──
        if outcome == 'draw' and not DRAW_ENABLED:
            res[outcome] = {
                'prob_model': model_p, 'prob_implied': implied,
                'odd': odd, 'value': value, 'edge_rel': edge_rel,
                'has_value': False, 'strong_value': False,
                'blocked_reason': '⛔ Empates desactivados (ROI histórico -46%)',
            }
            continue

        # ── Filtro 2: forma reciente del equipo favorecido ──
        form_pts = form_home if outcome == 'home' else form_away
        form_ok  = True
        form_warn = None
        if value > threshold and form_pts is not None:
            if form_pts < FORM_MIN_PTS:
                form_ok   = False
                form_warn = f'⚠ Forma insuficiente: {form_pts} pts/j (mín {FORM_MIN_PTS})'

        has_value    = value > threshold and form_ok
        strong_value = has_value and edge_rel > 0.08

        res[outcome] = {
            'prob_model':    model_p,
            'prob_implied':  implied,
            'odd':           odd,
            'value':         value,
            'edge_rel':      edge_rel,
            'has_value':     has_value,
            'strong_value':  strong_value,
            'blocked_reason': form_warn,   # None si no hay bloqueo
        }
    return res


# ══════════════════════════════════════════════════════════════
# BLOQUE 10 — REPORTE HTML MEJORADO
# ══════════════════════════════════════════════════════════════
def generate_html_report(analyses, output_path):

    def form_html(form_data, color):
        dots = ""
        for r in form_data['form']:
            c = {'W': '#48bb78', 'D': '#f6e05e', 'L': '#fc8181'}[r]
            dots += f'<span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:{c};font-size:.6rem;line-height:18px;text-align:center;color:#000;font-weight:700">{r}</span> '
        stats = (f"Últ.{len(form_data['form'])} → "
                 f"{form_data['pts_pg']} pts/j · "
                 f"GF:{form_data['avg_gf']} GA:{form_data['avg_ga']}")
        return f'<div style="margin:.3rem 0">{dots}</div><div style="font-size:.7rem;color:var(--mut)">{stats}</div>'

    def badge(outcome, label, val_dict):
        v = val_dict.get(outcome)
        if not v:
            return f'<span class="badge no-data">{label} —</span>'
        pct  = f"{v['prob_model']*100:.1f}%"
        odd  = f"{v['odd']:.2f}"
        vval = v['value']
        tip  = f"+{vval*100:.1f}%" if vval > 0 else f"{vval*100:.1f}%"

        # Empate desactivado
        if outcome == 'draw' and not DRAW_ENABLED:
            return f'<span class="badge badge-blocked">⛔ X: {pct} @ {odd} <em>(empates off)</em></span>'

        # Bloqueado por forma
        if v.get('blocked_reason') and not v['has_value']:
            return f'<span class="badge badge-blocked">⚠ {label}: {pct} @ {odd} <em>({tip} — forma baja)</em></span>'

        if v['strong_value']:
            cls, icon = 'value-strong', '🔥'
        elif v['has_value']:
            cls, icon = 'value-yes', '🟢'
        else:
            cls, icon = 'value-no', '🔴'
        return f'<span class="badge {cls}">{icon} {label}: {pct} @ {odd} <em>({tip})</em></span>'

    cards = ""
    for a in analyses:
        pred  = a['pred']
        val   = a['value']
        fix   = a['fixture']
        f_home = a.get('form_home', {})
        f_away = a.get('form_away', {})

        hora  = fix['commence'].astimezone().strftime('%H:%M')
        fecha = fix['commence'].astimezone().strftime('%d/%m/%Y')

        # Fuente de cuotas badge
        src   = fix.get('odds_source', 'N/A')
        src_color = '#48bb78' if src == 'pinnacle' else ('#63b3ed' if src == 'betfair_ex_eu' else '#f6e05e')
        margin_txt = f" · margen {fix['margin']}%" if fix.get('margin') else ""
        src_badge = f'<span style="font-size:.68rem;background:rgba(255,255,255,.05);border:1px solid {src_color};color:{src_color};padding:.2rem .5rem;border-radius:10px">{src}{margin_txt}</span>'

        # Marcadores top
        top_html = ""
        for h, ag_s, p in pred['top_scores']:
            w = min(int(p * 500), 260)
            top_html += f"""
            <div class="score-row">
              <span class="slabel">{h}-{ag_s}</span>
              <div class="bwrap"><div class="bbar" style="width:{w}px"></div></div>
              <span class="spct">{p*100:.1f}%</span>
            </div>"""

        # Heatmap
        hm = pred['score_matrix']
        hm_rows = ""
        for hg_i in range(6):
            row = "".join(
                f'<td style="background:rgba(99,179,237,{hm[hg_i][ag_i]*5:.2f})">'
                f'{hm[hg_i][ag_i]*100:.1f}%</td>'
                for ag_i in range(6)
            )
            hm_rows += f"<tr><td class='ax'>{hg_i}</td>{row}</tr>"

        # Advertencia equipo nuevo
        warn = ""
        if not pred['known_home'] or not pred['known_away']:
            unk = []
            if not pred['known_home']: unk.append(fix['home_csv'])
            if not pred['known_away']: unk.append(fix['away_csv'])
            warn = f'<div class="warn">⚠ Equipo nuevo en modelo: {", ".join(unk)} — usa promedio de liga</div>'

        # Confianza del modelo
        max_prob = max(pred['p_home'], pred['p_draw'], pred['p_away'])
        conf_pct = int(max_prob * 100)
        conf_color = '#48bb78' if conf_pct >= 55 else ('#f6e05e' if conf_pct >= 45 else '#fc8181')
        conf_label = 'Alta' if conf_pct >= 55 else ('Media' if conf_pct >= 45 else 'Baja')
        conf_bar = f'<div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.8rem"><span style="font-size:.7rem;color:var(--mut)">Confianza:</span><div style="flex:1;max-width:120px;background:rgba(255,255,255,.05);border-radius:3px;height:6px"><div style="width:{conf_pct}%;height:100%;background:{conf_color};border-radius:3px"></div></div><span style="font-size:.75rem;color:{conf_color}">{conf_label} ({conf_pct}%)</span></div>'

        # Forma reciente
        form_section = ""
        if f_home or f_away:
            fh_html = form_html(f_home, '#63b3ed') if f_home else '—'
            fa_html = form_html(f_away, '#b794f4') if f_away else '—'
            form_section = f"""
            <div class="stitle">📈 Forma reciente (últimos {FORM_MATCHES} partidos)</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin-bottom:.5rem">
              <div>
                <div style="font-size:.72rem;color:var(--acc);margin-bottom:.3rem">{fix['home_api']}</div>
                {fh_html}
              </div>
              <div>
                <div style="font-size:.72rem;color:#b794f4;margin-bottom:.3rem">{fix['away_api']}</div>
                {fa_html}
              </div>
            </div>"""

        cards += f"""
        <div class="card">
          <div class="mh">
            <div>
              <div class="teams">{fix['home_api']} <span class="vs">vs</span> {fix['away_api']}</div>
              <div style="margin-top:.3rem">{src_badge}</div>
            </div>
            <div class="mtime">⏰ {fecha} {hora}</div>
          </div>
          {warn}
          {conf_bar}
          <div class="lam">λ local <strong>{pred['lambda_home']:.2f}</strong> &nbsp;·&nbsp; λ visitante <strong>{pred['lambda_away']:.2f}</strong></div>
          <div class="badges">
            {badge('home','1',val)}
            {badge('draw','X',val)}
            {badge('away','2',val)}
          </div>
          {form_section}
          <div class="stitle">📊 Top marcadores</div>
          <div class="scores">{top_html}</div>
          <div class="stitle">🔥 Heatmap (local↓ / visitante→)</div>
          <div class="hmwrap">
            <table class="hm">
              <thead><tr><th></th>{"".join(f'<th>{i}</th>' for i in range(6))}</tr></thead>
              <tbody>{hm_rows}</tbody>
            </table>
          </div>
        </div>"""

    n_value  = sum(1 for a in analyses for v in a['value'].values() if v.get('has_value'))
    n_strong = sum(1 for a in analyses for v in a['value'].values() if v.get('strong_value'))
    n_filtered = sum(1 for a in analyses for v in a['value'].values() if v.get('blocked_reason') and not v.get('has_value'))
    now_str  = datetime.now().strftime('%d/%m/%Y %H:%M')

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>J-League Analyzer v2</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@300;500;700&display=swap');
:root{{--bg:#080d18;--card:#0f1623;--bord:#1a2235;--acc:#63b3ed;--grn:#48bb78;--red:#fc8181;--ylw:#f6e05e;--txt:#dde3ee;--mut:#4a5568;--purp:#b794f4;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--txt);font-family:'Inter',sans-serif;}}
header{{background:linear-gradient(135deg,#050a14 0%,#0d2240 100%);border-bottom:1px solid var(--bord);padding:2.5rem 1rem;text-align:center;}}
header h1{{font-family:'IBM Plex Mono',monospace;font-size:2rem;color:var(--acc);letter-spacing:3px;}}
header p{{color:var(--mut);margin-top:.5rem;font-size:.82rem;}}
.statsbar{{display:flex;flex-wrap:wrap;gap:2rem;background:var(--card);border:1px solid var(--bord);border-radius:12px;padding:1.2rem 1.5rem;}}
.stat .sl{{font-size:.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--mut);}}
.stat .sv{{font-family:'IBM Plex Mono',monospace;font-size:1.2rem;color:var(--acc);margin-top:.2rem;}}
.stat .sv.strong{{color:var(--ylw);}}
.grid{{max-width:980px;margin:0 auto;padding:2rem 1rem;display:grid;gap:1.5rem;}}
.card{{background:var(--card);border:1px solid var(--bord);border-radius:14px;padding:1.5rem;}}
.mh{{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:.5rem;margin-bottom:.9rem;}}
.teams{{font-family:'IBM Plex Mono',monospace;font-size:1.05rem;color:#fff;}}
.vs{{color:var(--mut);font-size:.8rem;margin:0 .3rem;}}
.mtime{{font-size:.82rem;color:var(--acc);}}
.lam{{font-size:.8rem;color:var(--mut);margin-bottom:.9rem;}}
.lam strong{{color:var(--txt);}}
.warn{{background:rgba(246,224,94,.08);border:1px solid var(--ylw);color:var(--ylw);padding:.45rem .8rem;border-radius:8px;font-size:.78rem;margin-bottom:.9rem;}}
.badges{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1rem;}}
.badge{{padding:.35rem .75rem;border-radius:20px;font-family:'IBM Plex Mono',monospace;font-size:.75rem;}}
.value-strong{{background:rgba(246,224,94,.12);border:1px solid var(--ylw);color:var(--ylw);}}
.value-yes{{background:rgba(72,187,120,.12);border:1px solid var(--grn);color:var(--grn);}}
.value-no{{background:rgba(252,129,129,.08);border:1px solid var(--red);color:var(--red);}}
.no-data{{background:rgba(74,85,104,.15);border:1px solid var(--mut);color:var(--mut);}}
.badge-blocked{{background:rgba(74,85,104,.12);border:1px solid #2d3748;color:#4a5568;}}
.badge em{{font-style:normal;opacity:.75;}}
.stitle{{font-size:.68rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--mut);margin:1rem 0 .5rem;}}
.scores{{display:flex;flex-direction:column;gap:.3rem;}}
.score-row{{display:flex;align-items:center;gap:.7rem;}}
.slabel{{font-family:'IBM Plex Mono',monospace;font-size:.82rem;color:var(--acc);width:2.5rem;}}
.bwrap{{flex:1;max-width:260px;background:rgba(255,255,255,.05);border-radius:3px;height:5px;overflow:hidden;}}
.bbar{{height:100%;background:linear-gradient(90deg,var(--acc),var(--purp));border-radius:3px;}}
.spct{{font-size:.75rem;color:var(--mut);width:3rem;text-align:right;}}
.hmwrap{{overflow-x:auto;margin-top:.4rem;}}
.hm{{border-collapse:collapse;font-family:'IBM Plex Mono',monospace;font-size:.7rem;}}
.hm th,.hm td{{width:50px;height:32px;text-align:center;border:1px solid var(--bord);}}
.hm th{{background:var(--bg);color:var(--mut);}}
.hm .ax{{background:var(--bg);color:var(--mut);font-weight:600;}}
.legend{{display:flex;gap:1rem;flex-wrap:wrap;margin-top:.5rem;}}
.legend span{{font-size:.68rem;color:var(--mut);}}
footer{{text-align:center;padding:2rem;color:var(--mut);font-size:.72rem;border-top:1px solid var(--bord);margin-top:2rem;}}
.no-fix{{text-align:center;padding:3rem;color:var(--mut);font-family:'IBM Plex Mono',monospace;}}
</style>
</head>
<body>
<header>
  <h1>⚽ J-LEAGUE ANALYZER v2</h1>
  <p>Dixon-Coles · Forma reciente · Stats jugadores · Monte Carlo 100k · Actualizado {now_str}</p>
</header>
<div class="grid">
  <div class="statsbar">
    <div class="stat"><div class="sl">Partidos</div><div class="sv">{len(analyses)}</div></div>
    <div class="stat"><div class="sl">Value bets</div><div class="sv">{n_value}</div></div>
    <div class="stat"><div class="sl">🔥 Value sólido</div><div class="sv strong">{n_strong}</div></div>
    <div class="stat"><div class="sl">⛔ Filtradas</div><div class="sv" style="color:var(--mut)">{n_filtered}</div></div>
    <div class="stat"><div class="sl">Generado</div><div class="sv">{now_str}</div></div>
  </div>
  <div class="legend">
    <span>🔥 Value sólido: &gt;4% value Y &gt;8% edge relativo + forma OK</span>
    <span>🟢 Value detectado: &gt;4% ventaja + forma OK</span>
    <span>⚠ Filtrado por forma: value existe pero equipo con mala racha (&lt;1.2 pts/j)</span>
    <span>⛔ Empates desactivados (ROI histórico -46%)</span>
    <span>🔴 Sin value: la casa tiene ventaja</span>
  </div>
  {"".join(['<div class="no-fix">No hay partidos en las próximas 72h con cuotas disponibles.</div>']) if not analyses else cards}
</div>
<footer>Modelo estadístico v2 — Dixon-Coles + Forma reciente + Stats jugadores. No garantiza resultados. Apuesta con responsabilidad.</footer>
</body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ Reporte HTML: {output_path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 62)
    print("  J-LEAGUE ANALYZER v2 — Dixon-Coles + Forma + Jugadores")
    print("=" * 62)

    # ── 1. Cargar CSV principal ────────────────────────────
    csv_path = os.path.join(BASE, CSV_FILE)
    print(f"\n📂 Cargando {CSV_FILE}...")
    if not os.path.exists(csv_path):
        print(f"❌ No encontrado: {csv_path}")
        sys.exit(1)
    df = load_jleague_csv(csv_path, verbose=True)

    # ── 2. Cargar stats de jugadores (opcional) ───────────
    player_index = {}
    players_path = os.path.join(BASE, PLAYERS_CSV)
    if os.path.exists(players_path):
        print(f"\n📋 Cargando stats de jugadores...")
        player_index = load_player_stats(players_path)
        if player_index:
            top3 = sorted(player_index.items(), key=lambda x: -x[1])[:3]
            print(f"  ✓ {len(player_index)} equipos con índice ofensivo")
            print(f"  Top equipos ofensivos: " + ", ".join(f"{t}({v:.2f})" for t,v in top3))
        else:
            print("  ⚠ Sin índice — el ajuste por jugadores se omite")
    else:
        print(f"\n  ⚠ {PLAYERS_CSV} no encontrado — continuando sin stats de jugadores")

    # ── 3. Entrenar modelo ────────────────────────────────
    print(f"\n⏳ Ajustando Dixon-Coles con forma reciente (últimos {FORM_MATCHES} partidos ×{FORM_BOOST}x)...")
    params = fit_dixon_coles(df, player_index=player_index if player_index else None)

    print(f"\n📊 Top 8 ataques (J-League):")
    for team, v in sorted(params['attack'].items(), key=lambda x: -x[1])[:8]:
        print(f"   {team:<30} {v:+.3f}")

    print(f"\n📊 Top 8 defensas (menor = mejor):")
    for team, v in sorted(params['defence'].items(), key=lambda x: x[1])[:8]:
        print(f"   {team:<30} {v:+.3f}")

    # ── 4. Obtener partidos con cuotas ────────────────────
    print(f"\n🔍 Buscando partidos próximos (72h)...")
    fixtures = fetch_fixtures(API_KEY)

    if fixtures:
        print(f"   ✓ {len(fixtures)} partidos encontrados")
        for fx in fixtures:
            src = fx.get('odds_source', '?')
            mg  = f"  margen={fx['margin']}%" if fx.get('margin') else ""
            print(f"   [{fx['commence'].astimezone().strftime('%d/%m %H:%M')}] "
                  f"{fx['home_api']} vs {fx['away_api']}  [{src}{mg}]")
    else:
        print("   Sin partidos disponibles. Generando demo con equipos top...")
        top_teams = sorted(params['attack'].items(), key=lambda x: -x[1])
        fixtures = [{
            'commence':    datetime.now(timezone.utc) + timedelta(hours=2),
            'home_api':    top_teams[0][0], 'away_api':    top_teams[1][0],
            'home_csv':    top_teams[0][0], 'away_csv':    top_teams[1][0],
            'odds':        {'home': None, 'draw': None, 'away': None},
            'odds_source': 'demo', 'margin': None,
        }]

    # ── 5. Analizar cada partido ──────────────────────────
    analyses = []
    print()
    for fix in fixtures:
        pred   = predict_match(fix['home_csv'], fix['away_csv'], params)
        f_home = get_team_form(df, fix['home_csv'], FORM_MATCHES)
        f_away = get_team_form(df, fix['away_csv'], FORM_MATCHES)
        value  = calc_value(pred, fix['odds'],
                            form_home=f_home.get('pts_pg'),
                            form_away=f_away.get('pts_pg'))

        analyses.append({
            'fixture':   fix,
            'pred':      pred,
            'value':     value,
            'form_home': f_home,
            'form_away': f_away,
        })

        hora = fix['commence'].astimezone().strftime('%H:%M')
        print(f"  [{hora}] {fix['home_api']} vs {fix['away_api']}")
        print(f"    Forma local:    {''.join(f_home['form'])} ({f_home['pts_pg']} pts/j)")
        print(f"    Forma visitante:{''.join(f_away['form'])} ({f_away['pts_pg']} pts/j)")
        print(f"    Modelo → 1:{pred['p_home']*100:.1f}%  X:{pred['p_draw']*100:.1f}%  2:{pred['p_away']*100:.1f}%")
        if fix['odds']['home']:
            print(f"    Cuotas ({fix['odds_source']}) → 1:{fix['odds']['home']}  X:{fix['odds']['draw']}  2:{fix['odds']['away']}")
        for out, v in value.items():
            if v.get('strong_value'):
                print(f"    🔥 VALUE SÓLIDO: {out.upper()}  value={v['value']*100:+.1f}%  edge_rel={v['edge_rel']*100:+.1f}%  odd={v['odd']}")
            elif v.get('has_value'):
                print(f"    ✅ VALUE BET: {out.upper()}  value={v['value']*100:+.1f}%  odd={v['odd']}")
            elif v.get('blocked_reason'):
                print(f"    ⛔ FILTRADO: {out.upper()}  value={v['value']*100:+.1f}% — {v['blocked_reason']}")

    # ── 6. Reporte HTML ───────────────────────────────────
    print("\n⏳ Generando reporte HTML...")
    generate_html_report(analyses, OUTPUT_HTML)
    print("=" * 62)
    print(f"\n  Ejecuta también: python backtest_pinnacle.py")
    print(f"  → Verifica si el modelo tiene edge real antes de apostar")
    print("=" * 62)
