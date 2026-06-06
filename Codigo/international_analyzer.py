"""
international_analyzer.py — Sistema de predicción para Selecciones Nacionales
==============================================================================
Basado en Dixon-Coles adaptado para fútbol internacional con:
  ✅ Pesos por tipo de torneo (Mundial=1.0, Clasificatoria=0.85, Amistoso=0.4)
  ✅ Factor sede neutral (sin ventaja local cuando neutral=True)
  ✅ Ranking FIFA como prior para equipos con poco historial reciente
  ✅ Time decay — más peso a partidos recientes (últimos 3 años)
  ✅ Monte Carlo 100k simulaciones
  ✅ Comparación vs cuotas Pinnacle (The Odds API)
  ✅ Filtros: visitante >4% value + forma reciente ≥1.2 pts/j
  ✅ Reporte HTML visual completo

Datos necesarios (en la misma carpeta):
  - results.csv         ← Kaggle: martj42/international-football-results
  - goalscorers.csv     ← mismo dataset
  - former_names.csv    ← mismo dataset (nombres históricos de selecciones)

Uso:
    python international_analyzer.py
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
import json, os, sys, warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings('ignore')

# ══════════════════════════════════════════════════════════════
# ── CONFIGURACIÓN ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════
BASE         = r"D:\MODELO DE PREDICCION\Codigo"
RESULTS_CSV  = "results.csv"
NAMES_CSV    = "former_names.csv"
OUTPUT_HTML  = os.path.join(BASE, "international_report.html")

API_KEY_ODDS     = "07fed81a038a0eb0b8c6c4abedcdcd35"  # The Odds API → cuotas Pinnacle
API_KEY_FOOTBALL = "f7de0f5bd4e48491c6e02aefa322d67a"  # API-Football  → convocados/lesionados

# Parámetros del modelo
XI              = 0.00180   # time decay más suave (selecciones juegan menos)
TRAIN_FROM_YEAR = 2010      # solo usar datos desde 2010 (fútbol moderno)
MIN_MATCHES     = 10        # mínimo partidos (respaldo para equipos no en TEAM_WHITELIST)

# Lista fija de selecciones a modelar (las que el usuario quiere cubrir)
TEAM_WHITELIST = {
    # Europa
    'Albania', 'Germany', 'Andorra', 'Austria', 'Belarus', 'Belgium',
    'Bosnia and Herzegovina', 'Bulgaria', 'Croatia', 'Czech Republic',
    'Czechia', 'Denmark', 'England', 'Scotland', 'Northern Ireland',
    'Finland', 'France', 'Georgia', 'Greece', 'Hungary', 'Iceland',
    'Israel', 'Italy', 'Kosovo', 'Luxembourg', 'Moldova', 'Montenegro',
    'Netherlands', 'North Macedonia', 'Norway', 'Poland', 'Portugal',
    'Romania', 'Russia', 'Serbia', 'Slovakia', 'Slovenia', 'Spain',
    'Sweden', 'Switzerland', 'Turkey', 'Ukraine', 'Wales',
    # América
    'Argentina', 'Bolivia', 'Brazil', 'Canada', 'Chile', 'Colombia',
    'Costa Rica', 'Cuba', 'Curacao', 'Ecuador', 'El Salvador', 'Guatemala',
    'Haiti', 'Honduras', 'Jamaica', 'Mexico', 'Nicaragua', 'Panama',
    'Paraguay', 'Peru', 'Puerto Rico', 'United States', 'Uruguay',
    'Venezuela', 'Bermuda', 'Aruba',
    # África
    'Algeria', 'Angola', 'Benin', 'Burkina Faso', 'Cameroon',
    'Cape Verde', 'Congo DR', 'DR Congo', 'Ivory Coast', "Cote d'Ivoire",
    "Côte d'Ivoire", 'Egypt', 'Gabon', 'Ghana', 'Guinea', 'Mali',
    'Mauritania', 'Morocco', 'Niger', 'Nigeria', 'Senegal', 'South Africa',
    'Tunisia', 'Uganda', 'Zambia',
    # Asia / Oceanía
    'Australia', 'Bahrain', 'China', 'China PR', 'Indonesia', 'Iran',
    'Iraq', 'Japan', 'Jordan', 'Kuwait', 'Kyrgyzstan', 'New Zealand',
    'Oman', 'Palestine', 'Qatar', 'Saudi Arabia', 'Singapore', 'South Korea',
    'Korea Republic', 'Syria', 'Tajikistan', 'Thailand', 'UAE',
    'United Arab Emirates', 'Uzbekistan', 'Vietnam',
}
N_SIM           = 100_000   # simulaciones Monte Carlo

# Filtros value bet (calibrados para selecciones)
VALUE_THRESH_HOME = 0.07    # local más estricto
VALUE_THRESH_AWAY = 0.04    # visitante estándar
DRAW_ENABLED      = False   # empates desactivados igual que J-League
FORM_MATCHES      = 8       # últimos 8 partidos (selecciones juegan menos)
FORM_MIN_PTS_HOME = 1.3
FORM_MIN_PTS_AWAY = 1.0

# Pesos por tipo de torneo
TOURNAMENT_WEIGHTS = {
    # Alta competición oficial
    'fifa world cup':                   1.00,
    'uefa euro':                        1.00,
    'copa america':                     1.00,
    'africa cup of nations':            1.00,
    'afc asian cup':                    1.00,
    'gold cup':                         0.95,
    # Clasificatorias
    'fifa world cup qualification':     0.85,
    'uefa euro qualification':          0.85,
    'conmebol world cup qualification': 0.85,
    'caf world cup qualification':      0.85,
    'afc world cup qualification':      0.85,
    'concacaf world cup qualification': 0.85,
    # Nations League y similares
    'uefa nations league':              0.80,
    'conmebol-uefa finalissima':        0.90,
    # Copas regionales menores
    'concacaf nations league':          0.75,
    'aff championship':                 0.70,
    # Amistosos — menos peso (rotación de plantilla)
    'friendly':                         0.40,
}

def get_tournament_weight(tournament_name):
    """Retorna el peso del torneo. Si no está en la lista, 0.6 por defecto."""
    t = tournament_name.lower().strip()
    for key, w in TOURNAMENT_WEIGHTS.items():
        if key in t:
            return w
    # Clasificatorias genéricas
    if 'qualif' in t or 'qualifier' in t:
        return 0.82
    if 'friendly' in t or 'amistoso' in t:
        return 0.40
    if 'nations' in t:
        return 0.78
    return 0.60  # torneo desconocido


# ══════════════════════════════════════════════════════════════
# BLOQUE 1 — CARGA Y PREPARACIÓN DE DATOS
# ══════════════════════════════════════════════════════════════
def load_results(base_path):
    path = os.path.join(base_path, RESULTS_CSV)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No encontrado: {path}\n"
                                f"Descarga results.csv de:\n"
                                f"https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017")

    df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)

    # Normalizar columnas
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    # Columnas esperadas: date, home_team, away_team, home_score, away_score,
    #                     tournament, city, country, neutral
    rename = {}
    for c in df.columns:
        if 'home_score' in c or (c == 'home_score'): rename[c] = 'home_goals'
        if 'away_score' in c or (c == 'away_score'): rename[c] = 'away_goals'
    df.rename(columns=rename, inplace=True)

    # Asegurar nombres de columnas estándar
    col_map = {}
    for c in df.columns:
        if 'home_team' in c:    col_map[c] = 'home_team'
        elif 'away_team' in c:  col_map[c] = 'away_team'
        elif 'home_goal' in c or 'home_score' in c: col_map[c] = 'home_goals'
        elif 'away_goal' in c or 'away_score' in c: col_map[c] = 'away_goals'
        elif c == 'date':       col_map[c] = 'date'
        elif 'tournament' in c: col_map[c] = 'tournament'
        elif 'neutral' in c:    col_map[c] = 'neutral'
    df.rename(columns=col_map, inplace=True)

    required = ['date', 'home_team', 'away_team', 'home_goals', 'away_goals']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en results.csv: {missing}\n"
                         f"Columnas disponibles: {list(df.columns)}")

    # Tipos
    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df.dropna(subset=['home_goals', 'away_goals'], inplace=True)
    df['home_goals'] = df['home_goals'].astype(int)
    df['away_goals'] = df['away_goals'].astype(int)

    # Fecha
    df['match_date'] = pd.to_datetime(df['date'], errors='coerce')
    df.dropna(subset=['match_date'], inplace=True)
    df['year'] = df['match_date'].dt.year

    # Neutral
    if 'neutral' not in df.columns:
        df['neutral'] = False
    df['neutral'] = df['neutral'].astype(str).str.lower().isin(['true', '1', 'yes'])

    # Torneo
    if 'tournament' not in df.columns:
        df['tournament'] = 'Friendly'

    # Filtrar desde TRAIN_FROM_YEAR
    df = df[df['year'] >= TRAIN_FROM_YEAR].copy()

    # ── Filtrar SOLO selecciones de la whitelist ──
    df = df[df['home_team'].isin(TEAM_WHITELIST) & df['away_team'].isin(TEAM_WHITELIST)].copy()
    df = df.reset_index(drop=True)
    df = df.sort_values('match_date').reset_index(drop=True)

    # Peso por torneo + time decay
    ref = df['match_date'].max()
    df['time_diff_days'] = (ref - df['match_date']).dt.days
    df['t_weight']  = df['tournament'].apply(get_tournament_weight)
    df['td_weight'] = np.exp(-XI * df['time_diff_days'].values)
    df['weight']    = df['t_weight'] * df['td_weight']

    print(f"  ✓ {len(df):,} partidos cargados ({df['year'].min()}–{df['year'].max()})")
    print(f"  ✓ {df['home_team'].nunique()} selecciones modeladas ({len(TEAM_WHITELIST)} en whitelist)")
    print(f"  ✓ Amistosos: {(df['tournament'].str.lower().str.contains('friendly')).sum():,} | "
          f"Oficiales: {(~df['tournament'].str.lower().str.contains('friendly')).sum():,}")
    return df


# ══════════════════════════════════════════════════════════════
# BLOQUE 2 — RANKING FIFA (prior para equipos con poco historial)
# ══════════════════════════════════════════════════════════════
# Ranking FIFA aproximado (junio 2026) — top 50 selecciones
# Fuente: fifa.com/fifa-world-ranking
FIFA_RANKING = {
    'Argentina': 1, 'France': 2, 'England': 3, 'Spain': 4,
    'Brazil': 5, 'Belgium': 6, 'Portugal': 7, 'Netherlands': 8,
    'Germany': 9, 'Italy': 10, 'Croatia': 11, 'Morocco': 12,
    'Japan': 13, 'United States': 14, 'Mexico': 15, 'Switzerland': 16,
    'Senegal': 17, 'Iran': 18, 'Colombia': 19, 'Denmark': 20,
    'Uruguay': 21, 'South Korea': 22, 'Ecuador': 23, 'Canada': 24,
    'Austria': 25, 'Hungary': 26, 'Turkey': 27, 'Australia': 28,
    'Wales': 29, 'Poland': 30, 'Serbia': 31, 'Ukraine': 32,
    'Chile': 33, 'Peru': 34, 'Nigeria': 35, 'Sweden': 36,
    'Czechia': 37, 'Czech Republic': 37, 'Scotland': 38, 'Greece': 39,
    'Egypt': 40, 'Algeria': 41, 'Ivory Coast': 42, 'Costa Rica': 43,
    'Russia': 44, 'Romania': 45, 'Slovakia': 46, 'Ghana': 47,
    'South Africa': 48, 'Cameroon': 49, 'Tunisia': 50,
    'Saudi Arabia': 51, 'Qatar': 52, 'New Zealand': 53,
    'Bolivia': 55, 'Venezuela': 56, 'Paraguay': 57,
    'Jamaica': 60, 'Panama': 62, 'Honduras': 65,
    'Guatemala': 70, 'El Salvador': 72,
}

def get_fifa_prior(team, n_teams_in_model):
    """
    Devuelve un prior de ataque basado en el ranking FIFA.
    Top 10 → +0.15, posición 50+ → -0.15
    """
    rank = FIFA_RANKING.get(team, 80)
    # Normalizar: rank 1 → +0.15, rank 80+ → -0.15
    prior = 0.15 - (rank - 1) * (0.30 / 79)
    return np.clip(prior, -0.20, 0.20)


# ══════════════════════════════════════════════════════════════
# BLOQUE 3 — DIXON-COLES PARA SELECCIONES
# ══════════════════════════════════════════════════════════════
def rho_correction(hg, ag, lam, mu, rho):
    if   hg == 0 and ag == 0: return max(1e-10, 1 - lam * mu * rho)
    elif hg == 0 and ag == 1: return max(1e-10, 1 + lam * rho)
    elif hg == 1 and ag == 0: return max(1e-10, 1 + mu  * rho)
    elif hg == 1 and ag == 1: return max(1e-10, 1 - rho)
    return 1.0

def dc_log_likelihood(params, df, teams, neutral_idx):
    """
    Log-verosimilitud Dixon-Coles.
    gamma (ventaja local) se aplica solo cuando neutral=False.
    """
    n   = len(teams)
    atk = params[:n]
    dfc = params[n:2*n]
    rho = params[2*n]
    gam = params[2*n + 1]   # ventaja local

    hidx = np.array([teams.index(t) for t in df['home_team']])
    aidx = np.array([teams.index(t) for t in df['away_team']])

    # gamma solo para partidos NO neutrales
    home_adv = np.where(neutral_idx, 0.0, gam)

    lam = np.exp(atk[hidx] + dfc[aidx] + home_adv)
    mu  = np.exp(atk[aidx] + dfc[hidx])

    hg = df['home_goals'].values
    ag = df['away_goals'].values
    w  = df['weight'].values

    rc = np.array([rho_correction(h, a, l, m, rho)
                   for h, a, l, m in zip(hg, ag, lam, mu)])
    ll = w * (poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu) + np.log(rc))
    return -np.sum(ll)

def fit_model(df, verbose=True):
    # Usar SOLO la whitelist — ya filtrado en load_results()
    df_fit = df.copy()

    teams  = sorted(set(df_fit['home_team']) | set(df_fit['away_team']))
    n      = len(teams)

    # Inicialización con prior FIFA
    x0 = np.zeros(2 * n + 2)
    for i, team in enumerate(teams):
        x0[i]     = get_fifa_prior(team, n)   # ataque
        x0[n + i] = -get_fifa_prior(team, n) * 0.5  # defensa (inverso suave)
    x0[2*n + 1] = 0.25  # gamma inicial (ventaja local)

    bounds = [(-2.5, 2.5)] * n + [(-2.5, 2.5)] * n + [(-0.99, 0.99)] + [(0, 1.5)]

    neutral_idx = df_fit['neutral'].values.astype(float)

    res = minimize(
        dc_log_likelihood, x0,
        args=(df_fit, teams, neutral_idx),
        method='SLSQP', bounds=bounds,
        options={'maxiter': 1000, 'ftol': 1e-8}
    )

    if verbose:
        print(f"  ✓ Convergencia: {res.success} | Equipos modelados: {len(teams)}")
        print(f"  rho   = {res.x[2*n]:.4f}  (ideal: -0.05 a -0.20)")
        print(f"  gamma = {res.x[2*n+1]:.4f}  (ventaja local, ~0.20-0.35 esperado)")

    return {
        'attack':  dict(zip(teams, res.x[:n])),
        'defence': dict(zip(teams, res.x[n:2*n])),
        'rho':     res.x[2*n],
        'gamma':   res.x[2*n + 1],
        'success': res.success,
        'teams':   teams,
    }


# ══════════════════════════════════════════════════════════════
# BLOQUE 4 — PREDICCIÓN MONTE CARLO
# ══════════════════════════════════════════════════════════════
def predict_match(home, away, params, neutral=False, n_sim=N_SIM):
    atk   = params['attack']
    dfc   = params['defence']
    rho   = params['rho']
    gamma = params['gamma'] if not neutral else 0.0  # sin ventaja en sede neutral

    avg_a = np.mean(list(atk.values()))
    avg_d = np.mean(list(dfc.values()))

    # Si el equipo no está en el modelo, usar prior FIFA
    atk_h = atk.get(home, get_fifa_prior(home, len(atk)))
    dfc_a = dfc.get(away, -get_fifa_prior(away, len(dfc)) * 0.5)
    atk_a = atk.get(away, get_fifa_prior(away, len(atk)))
    dfc_h = dfc.get(home, -get_fifa_prior(home, len(dfc)) * 0.5)

    lam_h = np.exp(atk_h + dfc_a + gamma)
    lam_a = np.exp(atk_a + dfc_h)

    hg = np.random.poisson(lam_h, n_sim)
    ag = np.random.poisson(lam_a, n_sim)

    r  = np.random.random(n_sim)
    ok = np.ones(n_sim, dtype=bool)
    for mask, thresh in [
        ((hg==0)&(ag==0), max(0, 1 - lam_h*lam_a*rho)),
        ((hg==1)&(ag==0), max(0, 1 + lam_a*rho)),
        ((hg==0)&(ag==1), max(0, 1 + lam_h*rho)),
        ((hg==1)&(ag==1), max(0, 1 - rho)),
    ]:
        ok[mask] &= r[mask] < thresh

    hg, ag = hg[ok], ag[ok]
    nv = max(len(hg), 1)

    scores = {}
    for h, a in zip(hg, ag):
        k = (int(h), int(a))
        scores[k] = scores.get(k, 0) + 1

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
        'neutral':    neutral,
        'known_home': home in params['teams'],
        'known_away': away in params['teams'],
    }


# ══════════════════════════════════════════════════════════════
# BLOQUE 5 — FORMA RECIENTE
# ══════════════════════════════════════════════════════════════
def get_team_form(df, team, n=FORM_MATCHES):
    mask   = (df['home_team'] == team) | (df['away_team'] == team)
    recent = df[mask].tail(n)
    if len(recent) == 0:
        return {'form': [], 'pts_pg': None, 'avg_gf': 0, 'avg_ga': 0, 'tournaments': []}

    form, gf_l, ga_l, tourn_l = [], [], [], []
    for _, row in recent.iterrows():
        is_home = row['home_team'] == team
        gf = row['home_goals'] if is_home else row['away_goals']
        ga = row['away_goals'] if is_home else row['home_goals']
        gf_l.append(gf); ga_l.append(ga)
        if   gf > ga: form.append('W')
        elif gf < ga: form.append('L')
        else:          form.append('D')
        tourn_l.append(row.get('tournament', ''))

    form.reverse(); gf_l.reverse(); ga_l.reverse(); tourn_l.reverse()
    pts = sum({'W':3,'D':1,'L':0}[r] for r in form)
    return {
        'form':        form,
        'pts_pg':      round(pts / max(len(form), 1), 2),
        'avg_gf':      round(np.mean(gf_l), 2),
        'avg_ga':      round(np.mean(ga_l), 2),
        'tournaments': tourn_l,
    }


# ══════════════════════════════════════════════════════════════
# BLOQUE 6b — API-FOOTBALL: CONVOCADOS, LESIONADOS, HEAD2HEAD
# ══════════════════════════════════════════════════════════════
AF_BASE = "https://v3.football.api-sports.io"

def _af_get(endpoint, params, api_key):
    """Llamada genérica a API-Football. Devuelve lista 'response' o []."""
    import time
    try:
        import urllib.request, urllib.parse
        qs  = urllib.parse.urlencode(params)
        url = f"{AF_BASE}/{endpoint}?{qs}"
        req = urllib.request.Request(url, headers={"x-apisports-key": api_key})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        time.sleep(0.5)  # evitar rate limit (100 req/día, ~1 req/seg máx)
        return data.get("response", [])
    except Exception as e:
        print(f"  ⚠ API-Football [{endpoint}]: {e}")
        return []

def get_team_id(team_name, api_key):
    """Busca el ID de una selección por nombre."""
    res = _af_get("teams", {"name": team_name, "type": "National"}, api_key)
    if not res:
        # Intentar búsqueda más amplia
        res = _af_get("teams", {"search": team_name[:6]}, api_key)
    if res:
        return res[0]["team"]["id"], res[0]["team"]["name"]
    return None, None

def get_injuries(team_id, api_key):
    """Devuelve lista de lesionados/suspendidos del equipo."""
    res = _af_get("injuries", {"team": team_id, "league": 1}, api_key)
    players = []
    for p in res:
        players.append({
            "name":   p["player"]["name"],
            "reason": p["player"].get("reason", "Lesión"),
            "status": p["player"].get("type", "?"),
        })
    return players

def get_squad(team_id, api_key):
    """Devuelve plantilla con posiciones."""
    res = _af_get("players/squads", {"team": team_id}, api_key)
    if not res:
        return []
    players = []
    for p in res[0].get("players", []):
        players.append({
            "name":     p["name"],
            "position": p["position"],
            "age":      p.get("age", "?"),
            "number":   p.get("number", "?"),
        })
    return players

def get_head_to_head(team_id_home, team_id_away, api_key, last=5):
    """Devuelve últimos N enfrentamientos entre los dos equipos."""
    res = _af_get("fixtures/headtohead",
                  {"h2h": f"{team_id_home}-{team_id_away}", "last": last},
                  api_key)
    matches = []
    for m in res:
        fix  = m.get("fixture", {})
        tms  = m.get("teams", {})
        goal = m.get("goals", {})
        matches.append({
            "date":       fix.get("date", "")[:10],
            "home":       tms.get("home", {}).get("name", "?"),
            "away":       tms.get("away", {}).get("name", "?"),
            "home_goals": goal.get("home"),
            "away_goals": goal.get("away"),
        })
    return matches

def get_team_last_matches(team_id, api_key, last=5):
    """Últimos N partidos del equipo."""
    res = _af_get("fixtures", {"team": team_id, "last": last}, api_key)
    matches = []
    for m in res:
        fix  = m.get("fixture", {})
        tms  = m.get("teams", {})
        goal = m.get("goals", {})
        league = m.get("league", {})
        is_home = tms.get("home", {}).get("id") == team_id
        gf = goal.get("home") if is_home else goal.get("away")
        ga = goal.get("away") if is_home else goal.get("home")
        if gf is None or ga is None:
            continue
        result = "W" if gf > ga else ("L" if gf < ga else "D")
        matches.append({
            "date":       fix.get("date", "")[:10],
            "opponent":   tms.get("away" if is_home else "home", {}).get("name", "?"),
            "home_away":  "H" if is_home else "A",
            "gf": gf, "ga": ga, "result": result,
            "tournament": league.get("name", ""),
        })
    return matches

def fetch_pre_match_info(home_name, away_name, api_key):
    """
    Recopila toda la info pre-partido de API-Football:
    - IDs de ambos equipos
    - Lesionados/suspendidos
    - Plantilla (posiciones clave)
    - Últimos 5 partidos de cada equipo
    - Head to Head últimos 5
    Devuelve un dict con todo.
    """
    print(f"  📡 Consultando API-Football: {home_name} vs {away_name}...")

    # IDs
    home_id, home_official = get_team_id(home_name, api_key)
    away_id, away_official = get_team_id(away_name, api_key)

    if not home_id or not away_id:
        print(f"  ⚠ No se encontraron IDs para {home_name} o {away_name}")
        return None

    print(f"  ✓ {home_name} → ID {home_id} ({home_official})")
    print(f"  ✓ {away_name} → ID {away_id} ({away_official})")

    # Últimos partidos
    home_last = get_team_last_matches(home_id, api_key, last=5)
    away_last = get_team_last_matches(away_id, api_key, last=5)

    # Head to Head
    h2h = get_head_to_head(home_id, away_id, api_key, last=5)

    # Lesionados
    home_injuries = get_injuries(home_id, api_key)
    away_injuries = get_injuries(away_id, api_key)

    # Plantilla
    home_squad = get_squad(home_id, api_key)
    away_squad = get_squad(away_id, api_key)

    return {
        "home_id": home_id, "away_id": away_id,
        "home_official": home_official, "away_official": away_official,
        "home_last": home_last, "away_last": away_last,
        "h2h": h2h,
        "home_injuries": home_injuries, "away_injuries": away_injuries,
        "home_squad": home_squad, "away_squad": away_squad,
    }


def pre_match_html(info, home_name, away_name):
    """Genera el bloque HTML con la info pre-partido."""
    if not info:
        return '<div class="warn">⚠ No se pudo obtener info pre-partido de API-Football</div>'

    # Lesionados
    def injury_list(injuries):
        if not injuries:
            return '<span style="color:var(--grn)">Sin bajas confirmadas ✅</span>'
        items = "".join(
            f'<div style="font-size:.78rem;padding:.2rem 0;color:var(--red)">'
            f'❌ {p["name"]} <span style="color:var(--mut)">({p["reason"]})</span></div>'
            for p in injuries[:6]
        )
        return items

    # Últimos partidos
    def last_matches_html(matches):
        if not matches:
            return '<span style="color:var(--mut)">Sin datos</span>'
        rows = ""
        for m in matches:
            col = {'W':'#48bb78','D':'#f6e05e','L':'#fc8181'}[m['result']]
            rows += (f'<div style="display:flex;gap:.5rem;align-items:center;font-size:.75rem;padding:.2rem 0">'
                     f'<span style="width:18px;height:18px;border-radius:50%;background:{col};'
                     f'display:inline-flex;align-items:center;justify-content:center;'
                     f'font-weight:700;font-size:.6rem;color:#000">{m["result"]}</span>'
                     f'<span style="color:var(--mut)">{m["date"][:10]}</span>'
                     f'<span style="color:var(--txt)">{m["home_away"]} vs {m["opponent"][:18]}</span>'
                     f'<span style="color:var(--acc);font-family:IBM Plex Mono,monospace">'
                     f'{m["gf"]}-{m["ga"]}</span>'
                     f'<span style="color:var(--mut);font-size:.65rem">{m["tournament"][:20]}</span>'
                     f'</div>')
        return rows

    # Head to Head
    def h2h_html(matches):
        if not matches:
            return '<span style="color:var(--mut)">Sin enfrentamientos recientes</span>'
        rows = ""
        for m in matches:
            hg = m['home_goals'] if m['home_goals'] is not None else '?'
            ag = m['away_goals'] if m['away_goals'] is not None else '?'
            rows += (f'<div style="font-size:.75rem;padding:.2rem 0;'
                     f'display:flex;gap:.8rem;align-items:center">'
                     f'<span style="color:var(--mut)">{m["date"]}</span>'
                     f'<span style="color:var(--txt)">{m["home"]}</span>'
                     f'<span style="font-family:IBM Plex Mono,monospace;color:var(--ylw)">{hg}-{ag}</span>'
                     f'<span style="color:var(--txt)">{m["away"]}</span></div>')
        return rows

    # Plantilla highlights (solo porteros y delanteros)
    def squad_highlights(squad):
        if not squad:
            return '<span style="color:var(--mut)">Sin datos de plantilla</span>'
        by_pos = {}
        for p in squad:
            pos = p['position']
            by_pos.setdefault(pos, []).append(p['name'])
        html = ""
        for pos, players in by_pos.items():
            names = ", ".join(players[:4])
            html += (f'<div style="font-size:.75rem;padding:.15rem 0">'
                     f'<span style="color:var(--mut);width:90px;display:inline-block">{pos}:</span>'
                     f'<span style="color:var(--txt)">{names}</span></div>')
        return html if html else '<span style="color:var(--mut)">Sin datos</span>'

    return f"""
    <div style="border:1px solid var(--bord);border-radius:10px;padding:1rem;margin:.8rem 0;background:rgba(15,22,35,.5)">
      <div style="font-family:IBM Plex Mono,monospace;font-size:.72rem;color:var(--acc);
                  text-transform:uppercase;letter-spacing:1.5px;margin-bottom:.8rem">
        📡 Info Pre-Partido — API-Football
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem">
        <div>
          <div style="font-size:.72rem;color:var(--ylw);margin-bottom:.4rem">
            ⚕ Bajas — {home_name}
          </div>
          {injury_list(info['home_injuries'])}
        </div>
        <div>
          <div style="font-size:.72rem;color:var(--ylw);margin-bottom:.4rem">
            ⚕ Bajas — {away_name}
          </div>
          {injury_list(info['away_injuries'])}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem">
        <div>
          <div style="font-size:.72rem;color:var(--acc);margin-bottom:.4rem">
            🕐 Últimos 5 — {home_name}
          </div>
          {last_matches_html(info['home_last'])}
        </div>
        <div>
          <div style="font-size:.72rem;color:#b794f4;margin-bottom:.4rem">
            🕐 Últimos 5 — {away_name}
          </div>
          {last_matches_html(info['away_last'])}
        </div>
      </div>

      <div style="margin-bottom:1rem">
        <div style="font-size:.72rem;color:var(--ylw);margin-bottom:.4rem">
          🔄 Head to Head (últimos 5 enfrentamientos)
        </div>
        {h2h_html(info['h2h'])}
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
        <div>
          <div style="font-size:.72rem;color:var(--acc);margin-bottom:.4rem">
            👥 Plantilla — {home_name}
          </div>
          {squad_highlights(info['home_squad'])}
        </div>
        <div>
          <div style="font-size:.72rem;color:#b794f4;margin-bottom:.4rem">
            👥 Plantilla — {away_name}
          </div>
          {squad_highlights(info['away_squad'])}
        </div>
      </div>
    </div>"""


# ══════════════════════════════════════════════════════════════
# BLOQUE 7 — THE ODDS API (selecciones)
# ══════════════════════════════════════════════════════════════
INTL_SPORT_KEYS = [
    'soccer_fifa_world_cup',
    'soccer_fifa_world_cup_winner',
    'soccer_international_friendlies',
    'soccer_conmebol_copa_america',
    'soccer_uefa_european_championship',
    'soccer_uefa_nations_league',
    'soccer_concacaf_nations_league',
]

def get_active_intl_sports(api_key):
    """Consulta qué sports internacionales tienen partidos activos ahora."""
    try:
        import urllib.request
        url = f"https://api.the-odds-api.com/v4/sports/?apiKey={api_key}"
        with urllib.request.urlopen(url, timeout=10) as r:
            all_sports = json.loads(r.read())
        # Filtrar solo internacionales activos
        intl_keys = []
        for s in all_sports:
            k = s['key']
            if not s.get('active', False):
                continue
            if any(x in k for x in ['world_cup','international','copa_america',
                                      'european_championship','nations_league',
                                      'concacaf','conmebol','uefa_euro']):
                intl_keys.append(k)
        return intl_keys
    except Exception as e:
        print(f"  ⚠ No se pudo consultar sports activos: {e}")
        return INTL_SPORT_KEYS  # fallback a la lista hardcodeada

def fetch_international_fixtures(api_key, hours_ahead=240):
    """Consulta The Odds API para todos los deportes de selecciones.
    hours_ahead=240 (10 días) para capturar amistosos + primeros partidos del Mundial.
    """
    try:
        import urllib.request

        # Primero descubrir qué sports tienen cuotas activas
        print("  🔍 Descubriendo sports internacionales con cuotas...")
        active_keys = get_active_intl_sports(api_key)
        if active_keys:
            print(f"  ✓ Sports activos: {', '.join(active_keys)}")
        else:
            active_keys = INTL_SPORT_KEYS

        now    = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)
        all_fixtures = []

        for sport_key in active_keys:
            url = (f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
                   f"?apiKey={api_key}&regions=eu&markets=h2h&oddsFormat=decimal"
                   f"&bookmakers=pinnacle,betfair_ex_eu,bet365,unibet,williamhill")
            try:
                with urllib.request.urlopen(url, timeout=8) as resp:
                    data = json.loads(resp.read())
                if data:
                    print(f"  ✓ {sport_key}: {len(data)} partidos con cuotas")
            except Exception as e:
                print(f"  ⚠ {sport_key}: {e}")
                continue

            for g in data:
                t = datetime.fromisoformat(g['commence_time'].replace('Z', '+00:00'))
                if t > cutoff:
                    continue

                home_api = g['home_team']
                away_api = g['away_team']

                odds_by_book = {}
                for book in g.get('bookmakers', []):
                    for mkt in book.get('markets', []):
                        if mkt['key'] == 'h2h':
                            o = {'home': None, 'draw': None, 'away': None}
                            for outcome in mkt['outcomes']:
                                nm = outcome['name']
                                if nm == home_api:   o['home'] = outcome['price']
                                elif nm == 'Draw':   o['draw'] = outcome['price']
                                elif nm == away_api: o['away'] = outcome['price']
                            if o['home']:
                                odds_by_book[book['key']] = o
                            break

                odds   = None
                source = 'N/A'
                for pref in ['pinnacle', 'betfair_ex_eu', 'bet365']:
                    if pref in odds_by_book:
                        odds   = odds_by_book[pref]
                        source = pref
                        break
                if odds is None and odds_by_book:
                    source, odds = next(iter(odds_by_book.items()))
                if odds is None:
                    odds = {'home': None, 'draw': None, 'away': None}

                margin = None
                if odds['home'] and odds['draw'] and odds['away']:
                    margin = round((1/odds['home'] + 1/odds['draw'] + 1/odds['away'] - 1) * 100, 2)

                # Detectar si es sede neutral (Copa del Mundo, Copa América
                # suelen jugarse en país anfitrión que no es ninguno de los 2)
                neutral_detected = sport_key in [
                    'soccer_fifa_world_cup',
                    'soccer_conmebol_copa_america',
                    'soccer_uefa_european_championship',
                ]

                all_fixtures.append({
                    'commence':    t,
                    'home_api':    home_api,
                    'away_api':    away_api,
                    'home_csv':    home_api,
                    'away_csv':    away_api,
                    'odds':        odds,
                    'odds_source': source,
                    'margin':      margin,
                    'sport_key':   sport_key,
                    'neutral':     neutral_detected,
                    'tournament':  sport_key.replace('soccer_','').replace('_',' ').title(),
                })

        # Eliminar duplicados (mismo partido en varios sport_keys)
        seen = set()
        unique = []
        for fx in all_fixtures:
            key = (fx['home_api'], fx['away_api'], fx['commence'].date())
            if key not in seen:
                seen.add(key)
                unique.append(fx)

        return sorted(unique, key=lambda x: x['commence'])[:20]  # máx 20 partidos

    except Exception as e:
        print(f"  ⚠ Error API: {e}")
        return []


# ══════════════════════════════════════════════════════════════
# BLOQUE 7 — CÁLCULO VALUE BET
# ══════════════════════════════════════════════════════════════
def calc_value(pred, odds, form_home=None, form_away=None):
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

        # Empates desactivados
        if outcome == 'draw' and not DRAW_ENABLED:
            res[outcome] = {
                'prob_model': model_p, 'prob_implied': implied,
                'odd': odd, 'value': value, 'edge_rel': edge_rel,
                'has_value': False, 'strong_value': False,
                'blocked_reason': '⛔ Empates desactivados',
            }
            continue

        # Umbral y forma diferenciados
        thresh   = VALUE_THRESH_HOME if outcome == 'home' else VALUE_THRESH_AWAY
        form_min = FORM_MIN_PTS_HOME if outcome == 'home' else FORM_MIN_PTS_AWAY
        form_pts = form_home if outcome == 'home' else form_away

        form_ok   = True
        form_warn = None
        if value > thresh and form_pts is not None:
            if form_pts < form_min:
                form_ok   = False
                form_warn = f'⚠ Forma baja: {form_pts} pts/j (mín {form_min})'

        has_value    = value > thresh and form_ok
        strong_value = has_value and edge_rel > 0.09

        res[outcome] = {
            'prob_model':    model_p,
            'prob_implied':  implied,
            'odd':           odd,
            'value':         value,
            'edge_rel':      edge_rel,
            'has_value':     has_value,
            'strong_value':  strong_value,
            'blocked_reason': form_warn,
        }
    return res


# ══════════════════════════════════════════════════════════════
# BLOQUE 8 — REPORTE HTML
# ══════════════════════════════════════════════════════════════
def generate_html(analyses, output_path):

    def form_html(fd):
        if not fd or not fd.get('form'):
            return '<span style="color:var(--mut)">Sin historial reciente</span>'
        dots = ""
        for r in fd['form']:
            c = {'W':'#48bb78','D':'#f6e05e','L':'#fc8181'}[r]
            dots += f'<span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:{c};font-size:.6rem;line-height:18px;text-align:center;color:#000;font-weight:700;margin-right:2px">{r}</span>'
        stats = f"Últ.{len(fd['form'])} → {fd['pts_pg']} pts/j · GF:{fd['avg_gf']} GA:{fd['avg_ga']}"
        return f'<div style="margin:.3rem 0">{dots}</div><div style="font-size:.7rem;color:var(--mut)">{stats}</div>'

    def badge(outcome, label, val_dict):
        v = val_dict.get(outcome)
        if not v:
            return f'<span class="badge no-data">{label} —</span>'
        pct  = f"{v['prob_model']*100:.1f}%"
        odd  = f"{v['odd']:.2f}"
        tip  = f"+{v['value']*100:.1f}%" if v['value'] > 0 else f"{v['value']*100:.1f}%"

        if outcome == 'draw' and not DRAW_ENABLED:
            return f'<span class="badge badge-blocked">⛔ X: {pct} @ {odd}</span>'
        if v.get('blocked_reason') and not v['has_value']:
            return f'<span class="badge badge-blocked">⚠ {label}: {pct} @ {odd} <em>({tip})</em></span>'
        if v['strong_value']:   cls, icon = 'value-strong', '🔥'
        elif v['has_value']:    cls, icon = 'value-yes',    '🟢'
        else:                   cls, icon = 'value-no',     '🔴'
        return f'<span class="badge {cls}">{icon} {label}: {pct} @ {odd} <em>({tip})</em></span>'

    cards = ""
    for a in analyses:
        pred     = a['pred']
        val      = a['value']
        fix      = a['fixture']
        f_home   = a.get('form_home', {})
        f_away   = a.get('form_away', {})
        pre_info = a.get('pre_info')

        hora  = fix['commence'].astimezone().strftime('%H:%M')
        fecha = fix['commence'].astimezone().strftime('%d/%m/%Y')

        src       = fix.get('odds_source', 'N/A')
        src_color = '#48bb78' if src == 'pinnacle' else ('#63b3ed' if src == 'betfair_ex_eu' else '#f6e05e')
        margin_txt = f" · margen {fix['margin']}%" if fix.get('margin') else ""
        src_badge  = (f'<span style="font-size:.68rem;background:rgba(255,255,255,.05);'
                      f'border:1px solid {src_color};color:{src_color};padding:.2rem .5rem;'
                      f'border-radius:10px">{src}{margin_txt}</span>')

        neutral_badge = ""
        if fix.get('neutral'):
            neutral_badge = (' <span style="font-size:.65rem;background:rgba(183,148,244,.1);'
                             'border:1px solid #b794f4;color:#b794f4;padding:.2rem .4rem;'
                             'border-radius:8px">⚖ Sede neutral</span>')

        tourn_badge = (f'<span style="font-size:.65rem;background:rgba(99,179,237,.08);'
                       f'border:1px solid #63b3ed44;color:var(--acc);padding:.2rem .4rem;'
                       f'border-radius:8px">{fix.get("tournament","")}</span>')

        warn = ""
        if not pred['known_home'] or not pred['known_away']:
            unk = []
            if not pred['known_home']: unk.append(fix['home_csv'])
            if not pred['known_away']: unk.append(fix['away_csv'])
            warn = (f'<div class="warn">⚠ Equipo nuevo en modelo: {", ".join(unk)} '
                    f'— usa prior FIFA (ranking estimado)</div>')

        # Ranking FIFA
        rank_h = FIFA_RANKING.get(fix['home_csv'], '?')
        rank_a = FIFA_RANKING.get(fix['away_csv'], '?')
        rank_html = (f'<div style="font-size:.72rem;color:var(--mut);margin-bottom:.6rem">'
                     f'Ranking FIFA → {fix["home_csv"]} #{rank_h} &nbsp;·&nbsp; '
                     f'{fix["away_csv"]} #{rank_a}</div>')

        # Top marcadores
        top_html = ""
        for h, ag_s, p in pred['top_scores']:
            w = min(int(p * 500), 260)
            top_html += (f'<div class="score-row">'
                         f'<span class="slabel">{h}-{ag_s}</span>'
                         f'<div class="bwrap"><div class="bbar" style="width:{w}px"></div></div>'
                         f'<span class="spct">{p*100:.1f}%</span></div>')

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

        # Confianza
        max_p    = max(pred['p_home'], pred['p_draw'], pred['p_away'])
        conf_pct = int(max_p * 100)
        conf_col = '#48bb78' if conf_pct >= 55 else ('#f6e05e' if conf_pct >= 45 else '#fc8181')
        conf_lbl = 'Alta' if conf_pct >= 55 else ('Media' if conf_pct >= 45 else 'Baja')
        conf_bar = (f'<div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.8rem">'
                    f'<span style="font-size:.7rem;color:var(--mut)">Confianza:</span>'
                    f'<div style="flex:1;max-width:120px;background:rgba(255,255,255,.05);'
                    f'border-radius:3px;height:6px"><div style="width:{conf_pct}%;height:100%;'
                    f'background:{conf_col};border-radius:3px"></div></div>'
                    f'<span style="font-size:.75rem;color:{conf_col}">{conf_lbl} ({conf_pct}%)</span></div>')

        cards += f"""
        <div class="card">
          <div class="mh">
            <div>
              <div class="teams">{fix['home_api']} <span class="vs">vs</span> {fix['away_api']}</div>
              <div style="margin-top:.4rem;display:flex;gap:.4rem;flex-wrap:wrap">
                {tourn_badge}{neutral_badge}{src_badge}
              </div>
            </div>
            <div class="mtime">⏰ {fecha} {hora}</div>
          </div>
          {warn}
          {rank_html}
          {conf_bar}
          <div class="lam">λ local <strong>{pred['lambda_home']:.2f}</strong> &nbsp;·&nbsp; λ visitante <strong>{pred['lambda_away']:.2f}</strong>
            {'&nbsp;·&nbsp; <em style="color:#b794f4">Sede neutral</em>' if fix.get('neutral') else ''}
          </div>
          <div class="badges">
            {badge('home','1',val)}
            {badge('draw','X',val)}
            {badge('away','2',val)}
          </div>
          <div class="stitle">📈 Forma reciente (últimos {FORM_MATCHES} partidos)</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin-bottom:.5rem">
            <div>
              <div style="font-size:.72rem;color:var(--acc);margin-bottom:.3rem">{fix['home_api']}</div>
              {form_html(f_home)}
            </div>
            <div>
              <div style="font-size:.72rem;color:#b794f4;margin-bottom:.3rem">{fix['away_api']}</div>
              {form_html(f_away)}
            </div>
          </div>
          {pre_match_html(pre_info, fix['home_api'], fix['away_api']) if pre_info else ''}
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

    n_value    = sum(1 for a in analyses for v in a['value'].values() if v.get('has_value'))
    n_strong   = sum(1 for a in analyses for v in a['value'].values() if v.get('strong_value'))
    n_filtered = sum(1 for a in analyses for v in a['value'].values()
                     if v.get('blocked_reason') and not v.get('has_value'))
    now_str    = datetime.now().strftime('%d/%m/%Y %H:%M')

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>⚽ International Analyzer</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@300;500;700&display=swap');
:root{{--bg:#080d18;--card:#0f1623;--bord:#1a2235;--acc:#63b3ed;--grn:#48bb78;--red:#fc8181;--ylw:#f6e05e;--txt:#dde3ee;--mut:#4a5568;--purp:#b794f4;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--txt);font-family:'Inter',sans-serif;}}
header{{background:linear-gradient(135deg,#050a14 0%,#0a1a35 50%,#14082a 100%);border-bottom:1px solid var(--bord);padding:2.5rem 1rem;text-align:center;}}
header h1{{font-family:'IBM Plex Mono',monospace;font-size:2rem;color:var(--acc);letter-spacing:3px;}}
header p{{color:var(--mut);margin-top:.5rem;font-size:.82rem;}}
.statsbar{{display:flex;flex-wrap:wrap;gap:2rem;background:var(--card);border:1px solid var(--bord);border-radius:12px;padding:1.2rem 1.5rem;}}
.stat .sl{{font-size:.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--mut);}}
.stat .sv{{font-family:'IBM Plex Mono',monospace;font-size:1.2rem;color:var(--acc);margin-top:.2rem;}}
.stat .sv.strong{{color:var(--ylw);}}
.grid{{max-width:1000px;margin:0 auto;padding:2rem 1rem;display:grid;gap:1.5rem;}}
.card{{background:var(--card);border:1px solid var(--bord);border-radius:14px;padding:1.5rem;}}
.mh{{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:.5rem;margin-bottom:.9rem;}}
.teams{{font-family:'IBM Plex Mono',monospace;font-size:1.1rem;color:#fff;}}
.vs{{color:var(--mut);font-size:.8rem;margin:0 .4rem;}}
.mtime{{font-size:.82rem;color:var(--acc);white-space:nowrap;}}
.lam{{font-size:.8rem;color:var(--mut);margin-bottom:.9rem;}}
.lam strong{{color:var(--txt);}}
.warn{{background:rgba(246,224,94,.08);border:1px solid var(--ylw);color:var(--ylw);padding:.45rem .8rem;border-radius:8px;font-size:.78rem;margin-bottom:.9rem;}}
.badges{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1rem;}}
.badge{{padding:.35rem .75rem;border-radius:20px;font-family:'IBM Plex Mono',monospace;font-size:.75rem;}}
.value-strong{{background:rgba(246,224,94,.12);border:1px solid var(--ylw);color:var(--ylw);}}
.value-yes{{background:rgba(72,187,120,.12);border:1px solid var(--grn);color:var(--grn);}}
.value-no{{background:rgba(252,129,129,.08);border:1px solid var(--red);color:var(--red);}}
.no-data{{background:rgba(74,85,104,.15);border:1px solid var(--mut);color:var(--mut);}}
.badge-blocked{{background:rgba(74,85,104,.12);border:1px solid #2d3748;color:#718096;}}
.badge em{{font-style:normal;opacity:.75;}}
.stitle{{font-size:.68rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--mut);margin:1rem 0 .5rem;}}
.scores{{display:flex;flex-direction:column;gap:.3rem;margin-bottom:.5rem;}}
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
.legend{{display:flex;gap:.8rem;flex-wrap:wrap;padding:.8rem 0;}}
.legend span{{font-size:.68rem;color:var(--mut);}}
footer{{text-align:center;padding:2rem;color:var(--mut);font-size:.72rem;border-top:1px solid var(--bord);margin-top:2rem;}}
.no-fix{{text-align:center;padding:4rem;color:var(--mut);font-family:'IBM Plex Mono',monospace;font-size:.9rem;}}
</style>
</head>
<body>
<header>
  <h1>🌍 INTERNATIONAL ANALYZER</h1>
  <p>Dixon-Coles · Pesos torneo · Sede neutral · Ranking FIFA · Monte Carlo 100k · {now_str}</p>
</header>
<div class="grid">
  <div class="statsbar">
    <div class="stat"><div class="sl">Partidos</div><div class="sv">{len(analyses)}</div></div>
    <div class="stat"><div class="sl">Value bets</div><div class="sv">{n_value}</div></div>
    <div class="stat"><div class="sl">🔥 Value sólido</div><div class="sv strong">{n_strong}</div></div>
    <div class="stat"><div class="sl">⛔ Filtradas</div><div class="sv" style="color:var(--mut)">{n_filtered}</div></div>
    <div class="stat"><div class="sl">Actualizado</div><div class="sv">{now_str}</div></div>
  </div>
  <div class="legend">
    <span>🔥 Value sólido: &gt;umbral + edge relativo &gt;9% + forma OK</span>
    <span>🟢 Value: &gt;umbral + forma OK</span>
    <span>⚠ Filtrado: value existe pero forma baja</span>
    <span>⛔ Empates: desactivados</span>
    <span>⚖ Sede neutral: sin ventaja local en el modelo</span>
  </div>
  {"<div class='no-fix'>No hay partidos disponibles en las próximas 96h con cuotas.<br><br>Vuelve cuando haya jornada de amistosos o el Mundial arranque.</div>" if not analyses else cards}
</div>
<footer>Modelo estadístico — Dixon-Coles adaptado para selecciones. No garantiza resultados. Apuesta con responsabilidad.</footer>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ Reporte HTML: {output_path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 65)
    print("  INTERNATIONAL ANALYZER — Dixon-Coles para Selecciones")
    print("=" * 65)

    # 1. Cargar datos
    print(f"\n📂 Cargando {RESULTS_CSV}...")
    df = load_results(BASE)

    # 2. Entrenar modelo
    print(f"\n⏳ Ajustando Dixon-Coles ({df['year'].min()}–{df['year'].max()})...")
    print(f"   Pesos: Mundial=1.0 | Clasif=0.85 | Amistoso=0.4")
    print(f"   Time decay: xi={XI} | Sede neutral: gamma=0 cuando neutral=True")
    params = fit_model(df, verbose=True)

    # 3. Top selecciones
    print(f"\n📊 Top 10 ataques (selecciones):")
    for team, v in sorted(params['attack'].items(), key=lambda x: -x[1])[:10]:
        rank = FIFA_RANKING.get(team, '?')
        print(f"   #{str(rank):<3} {team:<25} {v:+.3f}")

    print(f"\n📊 Top 10 defensas (menor = mejor):")
    for team, v in sorted(params['defence'].items(), key=lambda x: x[1])[:10]:
        rank = FIFA_RANKING.get(team, '?')
        print(f"   #{str(rank):<3} {team:<25} {v:+.3f}")

    # 4. Obtener partidos
    print(f"\n🔍 Buscando partidos internacionales próximos (10 días)...")
    fixtures = fetch_international_fixtures(API_KEY_ODDS)

    if fixtures:
        print(f"   ✓ {len(fixtures)} partidos encontrados:")
        for fx in fixtures:
            h  = fx['commence'].astimezone().strftime('%d/%m %H:%M')
            mg = f" margen={fx['margin']}%" if fx.get('margin') else ""
            print(f"   [{h}] {fx['home_api']} vs {fx['away_api']}  "
                  f"[{fx['tournament']}] [{fx['odds_source']}{mg}]")
    else:
        print("   Sin partidos disponibles. Generando demo...")
        demo_pairs = [
            ('Argentina', 'France', False),
            ('Spain', 'Brazil', False),
            ('Germany', 'England', False),
        ]
        fixtures = []

    # ── PARTIDOS MANUALES (amistosos que The Odds API no cubre) ──────────
    # Edita esta lista con los partidos del día.
    # Formato: (local, visitante, neutral, hora_h, hora_m, odds_1, odds_X, odds_2)
    # Si no tienes cuotas escribe None.
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    MANUAL_FIXTURES = [
        # SAB 6 junio — amistosos
        ("Portugal",         "Chile",                    True,  20, 0,  None, None, None),
        ("Romania",          "Wales",                    False, 19, 0,  None, None, None),
        ("United States",    "Germany",                  True,  20, 30, None, None, None),
        ("Panama",           "Bosnia and Herzegovina",   True,  21, 0,  None, None, None),
        ("Switzerland",      "Australia",                True,  21, 0,  None, None, None),
        ("Bolivia",          "Scotland",                 True,  22, 0,  None, None, None),
        ("Qatar",            "El Salvador",              True,  22, 0,  None, None, None),
        ("England",          "New Zealand",              True,  22, 0,  None, None, None),
        ("Brazil",           "Egypt",                    True,  0,  0,  None, None, None),
        ("Venezuela",        "Turkey",                   True,  0,  0,  None, None, None),
        ("Argentina",        "Honduras",                 True,  2,  0,  None, None, None),
        # DOM 7 junio
        ("Denmark",          "Ukraine",                  False, 18, 30, None, None, None),
        ("Kosovo",           "Andorra",                  False, 20, 0,  None, None, None),
        ("Croatia",          "Slovenia",                 False, 20, 45, None, None, None),
        ("Greece",           "Italy",                    False, 21, 0,  None, None, None),
        ("Morocco",          "Norway",                   True,  21, 0,  None, None, None),
        ("Ecuador",          "Guatemala",                True,  22, 0,  None, None, None),
        ("Colombia",         "Jordan",                   True,  1,  0,  None, None, None),
        # LUN 8 junio
        ("Netherlands",      "Uzbekistan",               True,  20, 45, None, None, None),
        ("France",           "Northern Ireland",         False, 21, 10, None, None, None),
        ("Peru",             "Spain",                    True,  4,  0,  None, None, None),
        # MAR 9 junio
        ("Bahrain",          "Syria",                    True,  16, 0,  None, None, None),
        ("Armenia",          "Moldova",                  False, 17, 0,  None, None, None),
        ("Hungary",          "Kazakhstan",               False, 19, 0,  None, None, None),
        ("Saudi Arabia",     "Senegal",                  True,  1,  0,  None, None, None),
        ("Argentina",        "Iceland",                  True,  3,  0,  None, None, None),
        ("Iraq",             "Venezuela",                True,  3,  0,  None, None, None),
    ]

    manual = []
    now_utc = datetime.now(timezone.utc)
    for row in MANUAL_FIXTURES:
        local, visit, neutral, hh, mm = row[0], row[1], row[2], row[3], row[4]
        o1, ox, o2 = row[5], row[6], row[7]
        commence = today.replace(hour=hh, minute=mm)
        # Si ya pasó hoy, mover al día siguiente
        if commence < now_utc - timedelta(hours=3):
            commence += timedelta(days=1)
        manual.append({
            'commence':    commence,
            'home_api': local, 'away_api':  visit,
            'home_csv': local, 'away_csv':  visit,
            'odds':     {'home': o1, 'draw': ox, 'away': o2},
            'odds_source': 'manual', 'margin': None,
            'sport_key':   'friendly',
            'neutral':     neutral,
            'tournament':  'Amistoso Internacional',
        })

    if fixtures:
        # Combinar API + manual sin duplicados
        api_pairs = {(f['home_api'], f['away_api']) for f in fixtures}
        for m in manual:
            if (m['home_api'], m['away_api']) not in api_pairs:
                fixtures.append(m)
        fixtures = sorted(fixtures, key=lambda x: x['commence'])[:25]
        print(f"   Total partidos (API + manuales): {len(fixtures)}")
    else:
        fixtures = sorted(manual, key=lambda x: x['commence'])
        print(f"   Usando {len(fixtures)} partidos manuales de amistosos")

    # 5. Analizar cada partido
    analyses = []
    print()
    for fix in fixtures:
        pred   = predict_match(fix['home_csv'], fix['away_csv'], params,
                               neutral=fix.get('neutral', False))
        f_home = get_team_form(df, fix['home_csv'], FORM_MATCHES)
        f_away = get_team_form(df, fix['away_csv'], FORM_MATCHES)
        value  = calc_value(pred, fix['odds'],
                            form_home=f_home.get('pts_pg'),
                            form_away=f_away.get('pts_pg'))

    # Info pre-partido de API-Football (solo el primer partido para no gastar requests)
        pre_info = None
        if API_KEY_FOOTBALL and analyses == []:  # solo el primer partido
            pre_info = fetch_pre_match_info(fix['home_api'], fix['away_api'], API_KEY_FOOTBALL)

        analyses.append({
            'fixture':   fix,
            'pred':      pred,
            'value':     value,
            'form_home': f_home,
            'form_away': f_away,
            'pre_info':  pre_info,
        })

        hora = fix['commence'].astimezone().strftime('%H:%M')
        neu  = " [NEUTRAL]" if fix.get('neutral') else ""
        print(f"  [{hora}] {fix['home_api']} vs {fix['away_api']}{neu}")
        print(f"    Forma {fix['home_api'][:15]}: {''.join(f_home['form'])} ({f_home.get('pts_pg','?')} pts/j)")
        print(f"    Forma {fix['away_api'][:15]}: {''.join(f_away['form'])} ({f_away.get('pts_pg','?')} pts/j)")
        print(f"    Modelo → 1:{pred['p_home']*100:.1f}%  X:{pred['p_draw']*100:.1f}%  2:{pred['p_away']*100:.1f}%")
        if fix['odds']['home']:
            print(f"    Cuotas ({fix['odds_source']}) → 1:{fix['odds']['home']}  "
                  f"X:{fix['odds']['draw']}  2:{fix['odds']['away']}")
        for out, v in value.items():
            if v.get('strong_value'):
                print(f"    🔥 VALUE SÓLIDO: {out.upper()}  "
                      f"value={v['value']*100:+.1f}%  edge_rel={v['edge_rel']*100:+.1f}%  odd={v['odd']}")
            elif v.get('has_value'):
                print(f"    ✅ VALUE BET: {out.upper()}  "
                      f"value={v['value']*100:+.1f}%  odd={v['odd']}")
            elif v.get('blocked_reason'):
                print(f"    ⛔ FILTRADO: {out.upper()} — {v['blocked_reason']}")

    # 6. HTML
    print("\n⏳ Generando reporte HTML...")
    generate_html(analyses, OUTPUT_HTML)
    print("=" * 65)
    print("\n  📌 Para el Mundial:")
    print("     python international_analyzer.py")
    print("  📌 Para J-League (cuando vuelva):")
    print("     python jleague_analyzer.py")
    print("=" * 65)
