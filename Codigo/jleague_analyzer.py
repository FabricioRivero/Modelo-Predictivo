"""
jleague_analyzer.py — Sistema completo de análisis de apuestas J-League
Flujo: JPN.csv (football-data.co.uk) → Dixon-Coles → The Odds API → reporte HTML
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
import json, os, sys
from datetime import datetime, timedelta, timezone

# ─────────────────────────────────────────────────────────────
# BLOQUE 1: CORRECCIÓN DIXON-COLES
# ─────────────────────────────────────────────────────────────
def rho_correction(home_g, away_g, lam_h, lam_a, rho):
    if   home_g == 0 and away_g == 0: return max(1e-10, 1 - lam_h * lam_a * rho)
    elif home_g == 0 and away_g == 1: return max(1e-10, 1 + lam_h * rho)
    elif home_g == 1 and away_g == 0: return max(1e-10, 1 + lam_a * rho)
    elif home_g == 1 and away_g == 1: return max(1e-10, 1 - rho)
    return 1.0

# ─────────────────────────────────────────────────────────────
# BLOQUE 2: LOG-VEROSIMILITUD CON TIME DECAY
# ─────────────────────────────────────────────────────────────
def dc_log_likelihood(params, df, teams, xi=0.00325):
    n = len(teams)
    atk_vals = params[:n]
    def_vals = params[n:2*n]
    rho   = params[2*n]
    gamma = params[2*n + 1]

    home_idx = np.array([teams.index(t) for t in df['home_team']])
    away_idx = np.array([teams.index(t) for t in df['away_team']])

    atk_h = atk_vals[home_idx]
    def_a = def_vals[away_idx]
    atk_a = atk_vals[away_idx]
    def_h = def_vals[home_idx]

    lam = np.exp(atk_h + def_a + gamma)
    mu  = np.exp(atk_a + def_h)

    hg = df['home_goals'].values
    ag = df['away_goals'].values
    weights = np.exp(-xi * df['time_diff_days'].values)

    rho_corr = np.array([
        rho_correction(h, a, l, m, rho)
        for h, a, l, m in zip(hg, ag, lam, mu)
    ])

    log_lik = weights * (
        poisson.logpmf(hg, lam) +
        poisson.logpmf(ag, mu) +
        np.log(rho_corr)
    )
    return -np.sum(log_lik)

# ─────────────────────────────────────────────────────────────
# BLOQUE 3: MLE DIXON-COLES
# ─────────────────────────────────────────────────────────────
def fit_dixon_coles(df, xi=0.00325):
    teams = sorted(set(df['home_team']) | set(df['away_team']))
    n = len(teams)
    x0 = np.zeros(2 * n + 2)
    x0[2*n + 1] = 0.1  # gamma inicial

    bounds = [(-3, 3)] * n + [(-3, 3)] * n + [(-0.99, 0.99)] + [(0, 2)]

    result = minimize(
        dc_log_likelihood, x0,
        args=(df, teams, xi),
        method='SLSQP',
        bounds=bounds,
        options={'maxiter': 1000, 'ftol': 1e-8}
    )
    return {
        'attack':  dict(zip(teams, result.x[:n])),
        'defence': dict(zip(teams, result.x[n:2*n])),
        'rho':     result.x[2*n],
        'gamma':   result.x[2*n + 1],
        'success': result.success,
        'teams':   teams
    }

# ─────────────────────────────────────────────────────────────
# BLOQUE 4: PREDICCIÓN MONTE CARLO
# ─────────────────────────────────────────────────────────────
def predict_match(home, away, params, n_sim=100_000):
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

    # Corrección Dixon-Coles en simulaciones
    r = np.random.random(n_sim)
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

    p_home = np.sum(hg > ag) / nv
    p_draw = np.sum(hg == ag) / nv
    p_away = np.sum(ag > hg) / nv

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
        'p_home': p_home, 'p_draw': p_draw, 'p_away': p_away,
        'top_scores': top5,
        'score_matrix': matrix.tolist(),
        'known_home': home in params['teams'],
        'known_away': away in params['teams'],
    }

# ─────────────────────────────────────────────────────────────
# BLOQUE 5: CARGA CSV — formato football-data.co.uk JPN.csv
# ─────────────────────────────────────────────────────────────
def load_jleague_csv(path, verbose=True):
    df = pd.read_csv(path, encoding='utf-8', on_bad_lines='skip', low_memory=False)

    # Mapeo flexible de columnas
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
    df.rename(columns=rename, inplace=True)

    missing = [c for c in ['home_team','away_team','home_goals','away_goals','date_raw']
               if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}. Disponibles: {list(df.columns)}")

    df = df[['home_team','away_team','home_goals','away_goals','date_raw']].copy()
    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df.dropna(inplace=True)
    df['home_goals'] = df['home_goals'].astype(int)
    df['away_goals'] = df['away_goals'].astype(int)

    # Parseo de fecha — intenta cada formato y usa el que parsea más filas
    best = None
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y']:
        parsed = pd.to_datetime(df['date_raw'], format=fmt, errors='coerce')
        if best is None or parsed.notna().sum() > best.notna().sum():
            best = parsed
    # fallback dayfirst
    fallback = pd.to_datetime(df['date_raw'], dayfirst=True, errors='coerce')
    df['match_date'] = best.where(best.notna(), fallback)
    # Forzar dtype datetime64 (necesario para .dt)
    df['match_date'] = pd.to_datetime(df['match_date'], errors='coerce')

    df.dropna(subset=['match_date'], inplace=True)
    ref = df['match_date'].max()
    df['time_diff_days'] = (ref - df['match_date']).dt.days
    df = df.drop(columns=['date_raw']).reset_index(drop=True)

    if verbose:
        print(f"  ✓ {os.path.basename(path):<20} → {len(df):>4} partidos  "
              f"({df['match_date'].min().date()} → {df['match_date'].max().date()})")
    return df

# ─────────────────────────────────────────────────────────────
# BLOQUE 6: MAPEO NOMBRES API → CSV
# ─────────────────────────────────────────────────────────────
NAME_MAP = {
    # The Odds API name              → football-data.co.uk name
    "Kashima Antlers":               "Kashima Antlers",
    "Gamba Osaka":                   "Gamba Osaka",
    "Urawa Red Diamonds":            "Urawa Reds",
    "Urawa Reds":                    "Urawa Reds",
    "Yokohama F Marinos":            "Yokohama F. Marinos",
    "Yokohama F. Marinos":           "Yokohama F. Marinos",
    "FC Tokyo":                      "FC Tokyo",
    "Cerezo Osaka":                  "Cerezo Osaka",
    "Vissel Kobe":                   "Vissel Kobe",
    "Kawasaki Frontale":             "Kawasaki Frontale",
    "Nagoya Grampus":                "Nagoya Grampus",
    "Sanfrecce Hiroshima":           "Sanfrecce Hiroshima",
    "Hiroshima Sanfrecce FC":        "Sanfrecce Hiroshima",
    "Avispa Fukuoka":                "Avispa Fukuoka",
    "JEF United Chiba":              "JEF United",
    "FC Machida Zelvia":             "Machida",
    "Machida Zelvia":                "Machida",
    "Tokyo Verdy":                   "Verdy",
    "Shimizu S Pulse":               "Shimizu S-Pulse",
    "Shimizu S-Pulse":               "Shimizu S-Pulse",
    "Kashiwa Reysol":                "Kashiwa Reysol",
    "Kyoto Purple Sanga":            "Kyoto",
    "Kyoto Sanga":                   "Kyoto",
    "Fagiano Okayama":               "Okayama",
    "Mito HollyHock":                "Mito HollyHock",
    "V-Varen Nagasaki":              "V-Varen Nagasaki",
    "Shonan Bellmare":               "Shonan Bellmare",
    "Albirex Niigata":               "Albirex Niigata",
    "Yokohama FC":                   "Yokohama FC",
}

def normalize_name(name):
    return NAME_MAP.get(name, name)

# ─────────────────────────────────────────────────────────────
# BLOQUE 7: OBTENER PARTIDOS DE THE ODDS API
# ─────────────────────────────────────────────────────────────
def fetch_fixtures(api_key, hours_ahead=48):
    try:
        import urllib.request
        url = (f"https://api.the-odds-api.com/v4/sports/soccer_japan_j_league/odds/"
               f"?apiKey={api_key}&regions=eu&markets=h2h&oddsFormat=decimal")
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)
        fixtures = []

        for g in data:
            t = datetime.fromisoformat(g['commence_time'].replace('Z', '+00:00'))
            if t > cutoff:
                continue
            home_api = g['home_team']
            away_api = g['away_team']
            odds = {'home': None, 'draw': None, 'away': None}

            for book in g.get('bookmakers', []):
                for mkt in book.get('markets', []):
                    if mkt['key'] == 'h2h':
                        for o in mkt['outcomes']:
                            n = o['name']
                            if n == home_api:  odds['home'] = o['price']
                            elif n == 'Draw':  odds['draw'] = o['price']
                            elif n == away_api: odds['away'] = o['price']
                        break
                if odds['home']:
                    break

            fixtures.append({
                'commence': t,
                'home_api': home_api,
                'away_api': away_api,
                'home_csv': normalize_name(home_api),
                'away_csv': normalize_name(away_api),
                'odds': odds,
            })
        return fixtures
    except Exception as e:
        print(f"  ⚠ API error: {e}")
        return []

# ─────────────────────────────────────────────────────────────
# BLOQUE 8: VALUE BET
# ─────────────────────────────────────────────────────────────
def calc_value(pred, odds):
    res = {}
    for outcome, prob_key, odd in [
        ('home', 'p_home', odds.get('home')),
        ('draw', 'p_draw', odds.get('draw')),
        ('away', 'p_away', odds.get('away')),
    ]:
        if odd and odd > 1:
            implied   = 1 / odd
            model_p   = pred[prob_key]
            value     = model_p - implied
            res[outcome] = {
                'prob_model':   model_p,
                'prob_implied': implied,
                'odd':          odd,
                'value':        value,
                'has_value':    value > 0.03,
            }
    return res

# ─────────────────────────────────────────────────────────────
# BLOQUE 9: REPORTE HTML
# ─────────────────────────────────────────────────────────────
def generate_html_report(analyses, output_path):

    def badge(outcome, label, val_dict):
        v = val_dict.get(outcome)
        if not v:
            return f'<span class="badge no-data">{label} —</span>'
        pct  = f"{v['prob_model']*100:.1f}%"
        odd  = f"{v['odd']:.2f}"
        vval = v['value']
        cls  = 'value-yes' if v['has_value'] else 'value-no'
        icon = '🟢' if v['has_value'] else '🔴'
        tip  = f"+{vval*100:.1f}%" if vval > 0 else f"{vval*100:.1f}%"
        return f'<span class="badge {cls}">{icon} {label}: {pct} @ {odd} <em>({tip})</em></span>'

    cards = ""
    for a in analyses:
        pred = a['pred']
        val  = a['value']
        fix  = a['fixture']

        hora  = fix['commence'].astimezone().strftime('%H:%M')
        fecha = fix['commence'].astimezone().strftime('%d/%m/%Y')

        # Marcadores
        top_html = ""
        for h, ag, p in pred['top_scores']:
            w = min(int(p * 500), 280)
            top_html += f"""
            <div class="score-row">
              <span class="slabel">{h}-{ag}</span>
              <div class="bwrap"><div class="bbar" style="width:{w}px"></div></div>
              <span class="spct">{p*100:.1f}%</span>
            </div>"""

        # Heatmap
        hm = pred['score_matrix']
        hm_rows = ""
        for hg in range(6):
            row = "".join(
                f'<td style="background:rgba(99,179,237,{hm[hg][ag]*5:.2f})">'
                f'{hm[hg][ag]*100:.1f}%</td>'
                for ag in range(6)
            )
            hm_rows += f"<tr><td class='ax'>{hg}</td>{row}</tr>"

        warn = ""
        if not pred['known_home'] or not pred['known_away']:
            unk = []
            if not pred['known_home']: unk.append(fix['home_csv'])
            if not pred['known_away']: unk.append(fix['away_csv'])
            warn = f'<div class="warn">⚠ Equipo nuevo en modelo: {", ".join(unk)} — usa promedio de liga</div>'

        cards += f"""
        <div class="card">
          <div class="mh">
            <div class="teams">{fix['home_api']} <span class="vs">vs</span> {fix['away_api']}</div>
            <div class="mtime">⏰ {fecha} {hora}</div>
          </div>
          {warn}
          <div class="lam">λ local <strong>{pred['lambda_home']:.2f}</strong> &nbsp;·&nbsp; λ visitante <strong>{pred['lambda_away']:.2f}</strong></div>
          <div class="badges">
            {badge('home','1',val)}
            {badge('draw','X',val)}
            {badge('away','2',val)}
          </div>
          <div class="stitle">📊 Top marcadores</div>
          <div class="scores">{top_html}</div>
          <div class="stitle">🔥 Heatmap de marcadores (local↓ / visitante→)</div>
          <div class="hmwrap">
            <table class="hm">
              <thead><tr><th></th>{"".join(f'<th>{i}</th>' for i in range(6))}</tr></thead>
              <tbody>{hm_rows}</tbody>
            </table>
          </div>
        </div>"""

    n_value = sum(1 for a in analyses for v in a['value'].values() if v.get('has_value'))
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>J-League Analyzer</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@300;500;700&display=swap');
:root{{--bg:#080d18;--card:#0f1623;--bord:#1a2235;--acc:#63b3ed;--grn:#48bb78;--red:#fc8181;--ylw:#f6e05e;--txt:#dde3ee;--mut:#4a5568;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--txt);font-family:'Inter',sans-serif;}}
header{{background:linear-gradient(135deg,#050a14 0%,#0d2240 100%);border-bottom:1px solid var(--bord);padding:2.5rem 1rem;text-align:center;}}
header h1{{font-family:'IBM Plex Mono',monospace;font-size:2rem;color:var(--acc);letter-spacing:3px;}}
header p{{color:var(--mut);margin-top:.5rem;font-size:.85rem;}}
.statsbar{{display:flex;flex-wrap:wrap;gap:2rem;background:var(--card);border:1px solid var(--bord);border-radius:12px;padding:1.2rem 1.5rem;}}
.stat .sl{{font-size:.68rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--mut);}}
.stat .sv{{font-family:'IBM Plex Mono',monospace;font-size:1.2rem;color:var(--acc);margin-top:.2rem;}}
.grid{{max-width:960px;margin:0 auto;padding:2rem 1rem;display:grid;gap:1.5rem;}}
.card{{background:var(--card);border:1px solid var(--bord);border-radius:14px;padding:1.5rem;}}
.mh{{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:.5rem;margin-bottom:.8rem;}}
.teams{{font-family:'IBM Plex Mono',monospace;font-size:1.05rem;color:#fff;}}
.vs{{color:var(--mut);font-size:.8rem;margin:0 .3rem;}}
.mtime{{font-size:.82rem;color:var(--acc);}}
.lam{{font-size:.8rem;color:var(--mut);margin-bottom:.9rem;}}
.lam strong{{color:var(--txt);}}
.warn{{background:rgba(246,224,94,.08);border:1px solid var(--ylw);color:var(--ylw);padding:.45rem .8rem;border-radius:8px;font-size:.78rem;margin-bottom:.9rem;}}
.badges{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1.1rem;}}
.badge{{padding:.35rem .75rem;border-radius:20px;font-family:'IBM Plex Mono',monospace;font-size:.75rem;}}
.value-yes{{background:rgba(72,187,120,.12);border:1px solid var(--grn);color:var(--grn);}}
.value-no{{background:rgba(252,129,129,.08);border:1px solid var(--red);color:var(--red);}}
.no-data{{background:rgba(74,85,104,.15);border:1px solid var(--mut);color:var(--mut);}}
.badge em{{font-style:normal;opacity:.75;}}
.stitle{{font-size:.7rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--mut);margin:1rem 0 .5rem;}}
.scores{{display:flex;flex-direction:column;gap:.3rem;}}
.score-row{{display:flex;align-items:center;gap:.7rem;}}
.slabel{{font-family:'IBM Plex Mono',monospace;font-size:.82rem;color:var(--acc);width:2.5rem;}}
.bwrap{{flex:1;max-width:280px;background:rgba(255,255,255,.05);border-radius:3px;height:5px;overflow:hidden;}}
.bbar{{height:100%;background:linear-gradient(90deg,var(--acc),#9f7aea);border-radius:3px;}}
.spct{{font-size:.75rem;color:var(--mut);width:3rem;text-align:right;}}
.hmwrap{{overflow-x:auto;margin-top:.4rem;}}
.hm{{border-collapse:collapse;font-family:'IBM Plex Mono',monospace;font-size:.7rem;}}
.hm th,.hm td{{width:50px;height:32px;text-align:center;border:1px solid var(--bord);}}
.hm th{{background:var(--bg);color:var(--mut);}}
.hm .ax{{background:var(--bg);color:var(--mut);font-weight:600;}}
footer{{text-align:center;padding:2rem;color:var(--mut);font-size:.72rem;border-top:1px solid var(--bord);margin-top:2rem;}}
.no-fix{{text-align:center;padding:3rem;color:var(--mut);font-family:'IBM Plex Mono',monospace;}}
</style>
</head>
<body>
<header>
  <h1>⚽ J-LEAGUE ANALYZER</h1>
  <p>Dixon-Coles · Monte Carlo 100k · The Odds API · Actualizado {now_str}</p>
</header>
<div class="grid">
  <div class="statsbar">
    <div class="stat"><div class="sl">Partidos</div><div class="sv">{len(analyses)}</div></div>
    <div class="stat"><div class="sl">Value bets</div><div class="sv">{n_value}</div></div>
    <div class="stat"><div class="sl">Generado</div><div class="sv">{now_str}</div></div>
  </div>
  {"".join([f'<div class="no-fix">No hay partidos en las próximas 48h con cuotas disponibles.</div>']) if not analyses else cards}
</div>
<footer>Modelo estadístico basado en datos históricos. No garantiza resultados. Apuesta con responsabilidad.</footer>
</body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ Reporte HTML guardado en: {output_path}")
    print("   Abre ese archivo en tu navegador.")

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  J-LEAGUE ANALYZER — Dixon-Coles + Value Bets")
    print("=" * 60)

    # ── CONFIGURACIÓN ──────────────────────────────────────
    BASE    = r"D:\MODELO DE PREDICCION\Codigo"
    API_KEY = "07fed81a038a0eb0b8c6c4abedcdcd35"
    CSV_FILE = "JPN.csv"          # ← tu archivo (ya confirmado que funciona)
    OUTPUT_HTML = os.path.join(BASE, "jleague_report.html")
    # ───────────────────────────────────────────────────────

    # 1. Cargar CSV
    csv_path = os.path.join(BASE, CSV_FILE)
    print(f"\n📂 Cargando {CSV_FILE}...")
    if not os.path.exists(csv_path):
        print(f"❌ No encontrado: {csv_path}")
        sys.exit(1)

    df = load_jleague_csv(csv_path, verbose=True)
    print(f"   Equipos: {df['home_team'].nunique()} | Temporadas: {sorted(df['match_date'].dt.year.unique())[-3:]}")

    # 2. Entrenar modelo
    print("\n⏳ Ajustando Dixon-Coles (puede tardar ~15s)...")
    params = fit_dixon_coles(df, xi=0.00325)
    print(f"✓ Convergencia: {params['success']}")
    print(f"  rho   = {params['rho']:.4f}  (esperado -0.05 a -0.20)")
    print(f"  gamma = {params['gamma']:.4f}  (esperado  0.15 a 0.40)")

    print("\n📊 Top 8 ataques (J-League):")
    for team, v in sorted(params['attack'].items(), key=lambda x: -x[1])[:8]:
        print(f"   {team:<28} {v:+.3f}")

    # 3. Obtener partidos
    print("\n🔍 Buscando partidos próximos (48h)...")
    fixtures = fetch_fixtures(API_KEY)
    if fixtures:
        print(f"   {len(fixtures)} partidos encontrados con cuotas.")
    else:
        print("   Sin partidos disponibles. Generando demo con equipos top...")
        # Demo automático si no hay partidos
        top_teams = sorted(params['attack'].items(), key=lambda x: -x[1])
        fixtures = [{
            'commence': datetime.now(timezone.utc) + timedelta(hours=2),
            'home_api': top_teams[0][0], 'away_api': top_teams[1][0],
            'home_csv': top_teams[0][0], 'away_csv': top_teams[1][0],
            'odds': {'home': None, 'draw': None, 'away': None},
        }]

    # 4. Analizar
    analyses = []
    print()
    for fix in fixtures:
        pred  = predict_match(fix['home_csv'], fix['away_csv'], params)
        value = calc_value(pred, fix['odds'])

        analyses.append({'fixture': fix, 'pred': pred, 'value': value})

        hora = fix['commence'].astimezone().strftime('%H:%M')
        print(f"  [{hora}] {fix['home_api']} vs {fix['away_api']}")
        print(f"    Modelo → 1:{pred['p_home']*100:.1f}%  X:{pred['p_draw']*100:.1f}%  2:{pred['p_away']*100:.1f}%")
        if fix['odds']['home']:
            print(f"    Cuotas → 1:{fix['odds']['home']}  X:{fix['odds']['draw']}  2:{fix['odds']['away']}")
        for out, v in value.items():
            if v.get('has_value'):
                print(f"    ✅ VALUE BET: {out.upper()}  value={v['value']*100:+.1f}%  odd={v['odd']}")

    # 5. Reporte HTML
    generate_html_report(analyses, OUTPUT_HTML)
    print("=" * 60)
