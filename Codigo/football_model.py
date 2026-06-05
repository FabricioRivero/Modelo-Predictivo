"""
Motor Predictivo de Fútbol - Dixon-Coles + Time Decay + Monte Carlo
Python 3.10+ | pip install numpy pandas scipy
"""

import numpy as np
import pandas as pd
from scipy.stats import poisson
from scipy.optimize import minimize


# ─────────────────────────────────────────────
# [BLOQUE 1] CORRECCIÓN DIXON-COLES
# ─────────────────────────────────────────────
def rho_correction(x, y, lam, mu, rho):
    if x == 0 and y == 0:
        return 1 - (lam * mu * rho)
    elif x == 0 and y == 1:
        return 1 + (lam * rho)
    elif x == 1 and y == 0:
        return 1 + (mu * rho)
    elif x == 1 and y == 1:
        return 1 - rho
    return 1.0


# ─────────────────────────────────────────────
# [BLOQUE 2] LOG-VEROSIMILITUD (vectorizada)
# ─────────────────────────────────────────────
def dc_log_likelihood(params, df, teams, team_idx, xi=0.00325):
    n       = len(teams)
    attack  = params[:n]
    defence = params[n:2*n]
    gamma   = params[2*n]
    rho     = params[2*n + 1]

    hi = np.array([team_idx[t] for t in df['home_team']], dtype=int)
    ai = np.array([team_idx[t] for t in df['away_team']], dtype=int)
    hg = df['home_goals'].values.astype(int)
    ag = df['away_goals'].values.astype(int)
    td = df['time_diff_days'].values.astype(float)

    weights = np.exp(-xi * td)
    lam     = np.exp(attack[hi] + defence[ai] + gamma)
    mu      = np.exp(attack[ai] + defence[hi])

    log_p_hg = poisson.logpmf(hg, lam)
    log_p_ag = poisson.logpmf(ag, mu)

    rho_f        = np.ones(len(df))
    m00          = (hg == 0) & (ag == 0)
    m01          = (hg == 0) & (ag == 1)
    m10          = (hg == 1) & (ag == 0)
    m11          = (hg == 1) & (ag == 1)
    rho_f[m00]   = 1 - lam[m00] * mu[m00] * rho
    rho_f[m01]   = 1 + lam[m01] * rho
    rho_f[m10]   = 1 + mu[m10] * rho
    rho_f[m11]   = 1 - rho
    rho_f        = np.clip(rho_f, 1e-10, None)

    ll = weights * (np.log(rho_f) + log_p_hg + log_p_ag)
    return -np.sum(ll)


# ─────────────────────────────────────────────
# [BLOQUE 3] AJUSTE MLE
# ─────────────────────────────────────────────
def fit_dixon_coles(df, xi=0.00325):
    teams    = np.sort(df['home_team'].unique())
    n        = len(teams)
    team_idx = {t: i for i, t in enumerate(teams)}

    x0          = np.zeros(2 * n + 2)
    x0[2*n + 1] = -0.13

    constraints = [{'type': 'eq', 'fun': lambda p: np.sum(p[:n])}]
    bounds      = [(None, None)] * (2 * n + 1) + [(-0.5, 0.5)]

    result = minimize(
        dc_log_likelihood,
        x0,
        args=(df, teams, team_idx, xi),
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 1000, 'ftol': 1e-8}
    )

    return {
        'attack':  {t: result.x[i]     for i, t in enumerate(teams)},
        'defence': {t: result.x[n + i] for i, t in enumerate(teams)},
        'gamma':   result.x[2*n],
        'rho':     result.x[2*n + 1],
        'success': result.success,
        'teams':   teams
    }


# ─────────────────────────────────────────────
# [BLOQUE 4] MONTE CARLO + 1X2
# ─────────────────────────────────────────────
def predict_match(home, away, params, n_sim=100_000, max_goals=10):
    lam = np.exp(params['attack'][home] + params['defence'][away] + params['gamma'])
    mu  = np.exp(params['attack'][away] + params['defence'][home])

    sim_h = np.random.poisson(lam, n_sim)
    sim_a = np.random.poisson(mu,  n_sim)

    g_range     = np.arange(max_goals + 1)
    score_matrix = np.outer(poisson.pmf(g_range, lam), poisson.pmf(g_range, mu))
    rho         = params['rho']
    for hg in range(2):
        for ag in range(2):
            score_matrix[hg, ag] *= rho_correction(hg, ag, lam, mu, rho)
    score_matrix /= score_matrix.sum()

    flat = sorted(
        [(i, j, score_matrix[i, j]) for i in range(max_goals+1) for j in range(max_goals+1)],
        key=lambda x: -x[2]
    )

    return {
        'p_home':       float(np.mean(sim_h > sim_a)),
        'p_draw':       float(np.mean(sim_h == sim_a)),
        'p_away':       float(np.mean(sim_h < sim_a)),
        'lambda_home':  lam,
        'lambda_away':  mu,
        'score_matrix': score_matrix,
        'top_scores':   flat[:5]
    }


# ─────────────────────────────────────────────
# [BLOQUE 5] BRIER SCORE
# ─────────────────────────────────────────────
def brier_score(pred_probs, outcomes):
    return float(np.mean((np.array(pred_probs) - np.array(outcomes)) ** 2))


# ─────────────────────────────────────────────
# [BLOQUE 6] CARGA DE DATOS - ROBUSTO
# ─────────────────────────────────────────────
def load_football_data(csv_path, prediction_date=None, verbose=True):
    """
    Compatible con football-data.co.uk (con o sin columna Time).
    prediction_date: 'YYYY-MM-DD'. Default: fecha del último partido del CSV.
    """
    df_raw = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip')

    if verbose:
        print(f"  Columnas detectadas: {df_raw.columns.tolist()}")
        print(f"  Filas brutas: {len(df_raw)}")

    # Renombrar columnas estándar
    rename = {'HomeTeam': 'home_team', 'AwayTeam': 'away_team',
              'FTHG': 'home_goals', 'FTAG': 'away_goals', 'Date': 'match_date'}
    df = df_raw.rename(columns=rename)

    required = ['home_team', 'away_team', 'home_goals', 'away_goals', 'match_date']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}. Tienes: {df.columns.tolist()}")

    df = df[required].dropna()
    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df = df.dropna()
    df['home_goals'] = df['home_goals'].astype(int)
    df['away_goals'] = df['away_goals'].astype(int)

    # Parseo de fecha flexible
    df['match_date'] = pd.to_datetime(df['match_date'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['match_date'])

    if verbose:
        print(f"  Rango de fechas: {df['match_date'].min().date()} → {df['match_date'].max().date()}")

    # Si no se especifica fecha, usar hoy (o la fecha máxima + 1 día si hay partidos futuros)
    if prediction_date:
        ref = pd.Timestamp(prediction_date)
    else:
        ref = pd.Timestamp.today().normalize()

    df['time_diff_days'] = (ref - df['match_date']).dt.days

    # Solo partidos ya jugados (time_diff >= 0)
    df_filtered = df[df['time_diff_days'] >= 0].reset_index(drop=True)

    if verbose:
        print(f"  Partidos con resultado: {len(df_filtered)}")
        if len(df_filtered) == 0:
            print("\n  ⚠️  PROBLEMA: 0 partidos cargados.")
            print(f"     Fecha de referencia usada: {ref.date()}")
            print(f"     Fecha máx en CSV:          {df['match_date'].max().date()}")
            print("     → Si la fecha del CSV es FUTURA, especifica prediction_date manualmente.")

    return df_filtered


# ─────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    print("=" * 55)
    print("  MODELO DIXON-COLES + MONTE CARLO")
    print("=" * 55)

    base = r"D:\MODELO DE PREDICCION\Codigo"
    archivos = [
        "E0 (3).csv",
        "E0 (2).csv",
        "E0 (1).csv",
        "E0.csv",
    ]

    print("\n📂 Cargando temporadas...")
    frames = []
    for f in archivos:
        path = os.path.join(base, f)
        try:
            df_temp = load_football_data(path, verbose=False)
            print(f"  ✓ {f:<20} → {len(df_temp):>3} partidos "
                  f"({df_temp['match_date'].min().date()} → "
                  f"{df_temp['match_date'].max().date()})")
            frames.append(df_temp)
        except Exception as e:
            print(f"  ✗ {f}: {e}")

    # ── AQUÍ ES EL CAMBIO CLAVE: concat FUERA del loop ──
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=['home_team', 'away_team', 'match_date'])
    df = df.sort_values('match_date').reset_index(drop=True)

    print(f"\n✓ Dataset combinado: {len(df)} partidos | "
          f"{df['home_team'].nunique()} equipos | "
          f"{df['match_date'].min().date()} → {df['match_date'].max().date()}")

    if len(df) < 20:
        print("❌ Muy pocos partidos.")
        sys.exit(1)

    # Ajustar modelo UNA SOLA VEZ con todo el dataset
    print("\n⏳ Ajustando MLE Dixon-Coles (4 temporadas)...")
    params = fit_dixon_coles(df, xi=0.00325)
    print(f"✓ Convergencia: {params['success']}")
    print(f"  rho   = {params['rho']:.4f}  (esperado entre -0.05 y -0.20)")
    print(f"  gamma = {params['gamma']:.4f} (esperado entre 0.20 y 0.40)")

    print("\n📊 Top 5 ataques (4 temporadas combinadas):")
    atk_sorted = sorted(params['attack'].items(), key=lambda x: -x[1])[:5]
    for team, val in atk_sorted:
        print(f"   {team:<20} {val:+.3f}")

    # Predecir — usa los 2 mejores del ranking automáticamente
    home, away = atk_sorted[0][0], atk_sorted[1][0]
    print(f"\n🔮 Predicción: {home} vs {away}")
    pred = predict_match(home, away, params, n_sim=100_000)
    print(f"  λ_home={pred['lambda_home']:.3f} | λ_away={pred['lambda_away']:.3f}")
    print(f"  P(Home) = {pred['p_home']:.3f} ({pred['p_home']*100:.1f}%)")
    print(f"  P(Draw) = {pred['p_draw']:.3f} ({pred['p_draw']*100:.1f}%)")
    print(f"  P(Away) = {pred['p_away']:.3f} ({pred['p_away']*100:.1f}%)")
    print("\n  Top 5 marcadores exactos:")
    for hg, ag, prob in pred['top_scores']:
        print(f"    {hg}-{ag}  →  {prob*100:.2f}%")

    print("\n✅ Modelo con 4 temporadas listo.")
    print("=" * 55)