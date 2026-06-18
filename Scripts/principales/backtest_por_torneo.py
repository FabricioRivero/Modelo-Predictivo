"""
backtest_por_torneo.py — Backtest segmentado por tipo de torneo
================================================================
Analiza si el edge del modelo varía según el tipo de competición:
  - FIFA World Cup (fase final)
  - Clasificatorias mundiales
  - Copa continental (Euro, Copa América, AFCON, etc.)
  - UEFA Nations League
  - Amistosos

Objetivo: Determinar si hay edge visitante en el Mundial específicamente
(actualmente desactivado por ROI -12.3% global).

Uso:
    python Scripts/principales/backtest_por_torneo.py
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
import os, sys, warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# ── Configuración ─────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'Config'))
from config import (
    RESULTS_CSV, PATCH_2026_CSV, PARTIDOS_CONV_CSV, INTL_DIR,
    FIFA_RANKING_CANDIDATES, REPORTES_DIR,
    XI_INTL, N_SIM_INTL, TRAIN_FROM_INTL,
    VT_HOME_INTL, VT_AWAY_INTL,
    FORM_MIN_HOME_INTL, FORM_MIN_AWAY_INTL,
    ensure_dirs,
)
ensure_dirs()

OUTPUT_CSV  = os.path.join(REPORTES_DIR, "backtest_por_torneo.csv")

# Períodos
TRAIN_FROM = 2010
TEST_FROM  = 2022
XI         = XI_INTL
MIN_TRAIN  = 300
N_SIM      = 30_000

# Categorías de torneo para segmentar
CATEGORIAS = {
    'Mundial':        ['FIFA World Cup'],
    'Clasificatoria': ['FIFA World Cup qualification'],
    'Continental':    ['UEFA Euro', 'Copa America', 'African Cup of Nations',
                       'AFC Asian Cup', 'Gold Cup'],
    'Nations League': ['UEFA Nations League', 'CONCACAF Nations League'],
    'Amistoso':       ['Friendly'],
}

def categorizar_torneo(tournament):
    t = str(tournament).lower().strip()
    if 'world cup' in t and 'qualif' not in t:
        return 'Mundial'
    if 'qualif' in t or 'qualification' in t:
        return 'Clasificatoria'
    if any(x.lower() in t for x in ['euro', 'copa america', 'african cup',
                                      'afc asian', 'gold cup', 'concacaf']):
        return 'Continental'
    if 'nations league' in t:
        return 'Nations League'
    if 'friendly' in t:
        return 'Amistoso'
    return 'Otro'

# ── Whitelist de selecciones ──────────────────────────────────
TEAM_WHITELIST = {
    'Albania','Germany','Austria','Belarus','Belgium','Bosnia and Herzegovina',
    'Bulgaria','Croatia','Czech Republic','Denmark','England','Scotland',
    'Northern Ireland','Finland','France','Georgia','Greece','Hungary',
    'Iceland','Israel','Italy','Kosovo','Luxembourg','Moldova','Montenegro',
    'Netherlands','North Macedonia','Norway','Poland','Portugal','Romania',
    'Russia','Serbia','Slovakia','Slovenia','Spain','Sweden','Switzerland',
    'Turkey','Ukraine','Wales',
    'Argentina','Bolivia','Brazil','Canada','Chile','Colombia','Costa Rica',
    'Curacao','Ecuador','El Salvador','Guatemala','Haiti','Honduras','Jamaica',
    'Mexico','Panama','Paraguay','Peru','United States','Uruguay','Venezuela',
    'Algeria','Angola','Burkina Faso','Cameroon','Cape Verde','DR Congo',
    'Ivory Coast','Egypt','Gabon','Ghana','Guinea','Mali','Mauritania',
    'Morocco','Niger','Nigeria','Senegal','South Africa','Tunisia','Uganda','Zambia',
    'Australia','Bahrain','China PR','Indonesia','Iran','Iraq','Japan','Jordan',
    'Kuwait','Kyrgyzstan','New Zealand','Oman','Palestine','Qatar',
    'Saudi Arabia','South Korea','Syria','Tajikistan','Thailand',
    'United Arab Emirates','Uzbekistan','Vietnam',
}

TOURNAMENT_WEIGHTS = {
    'fifa world cup': 1.00, 'uefa euro': 1.00, 'copa america': 1.00,
    'african cup of nations': 1.00, 'afc asian cup': 1.00, 'gold cup': 0.95,
    'fifa world cup qualification': 0.85, 'uefa euro qualification': 0.85,
    'uefa nations league': 0.80, 'friendly': 0.40,
}

def get_tournament_weight(t):
    tl = str(t).lower().strip()
    for k, w in TOURNAMENT_WEIGHTS.items():
        if k in tl: return w
    if 'qualif' in tl: return 0.82
    if 'friendly' in tl: return 0.40
    if 'nations' in tl: return 0.78
    return 0.60

# ── Ranking FIFA ──────────────────────────────────────────────
FIFA_NAME_MAP = {
    'España':'Spain','Francia':'France','Inglaterra':'England','Brasil':'Brazil',
    'Marruecos':'Morocco','Países Bajos':'Netherlands','Bélgica':'Belgium',
    'Alemania':'Germany','Croacia':'Croatia','Italia':'Italy','México':'Mexico',
    'EEUU':'United States','Japón':'Japan','Suiza':'Switzerland',
    'Dinamarca':'Denmark','RI de Irán':'Iran','Turquía':'Turkey',
    'República de Corea':'South Korea','Korea Republic':'South Korea',
    'USA':'United States','Czechia':'Czech Republic',
    "Côte d'Ivoire":'Ivory Coast','Congo DR':'DR Congo',
    'RD del Congo':'DR Congo','IR Iran':'Iran','Türkiye':'Turkey',
}

FIFA_RANKING = {}

def load_fifa_ranking():
    for path in FIFA_RANKING_CANDIDATES:
        if not os.path.exists(path): continue
        try:
            df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
            df.columns = [c.strip().lower().replace('.','_').replace(' ','_') for c in df.columns]
            if 'team' in df.columns and 'semester' in df.columns:
                latest = df[df['date'] == df['date'].max()]
                latest = latest[latest['semester'] == latest['semester'].max()]
                for _, row in latest.iterrows():
                    name = FIFA_NAME_MAP.get(str(row['team']).strip(), str(row['team']).strip())
                    FIFA_RANKING[name] = int(row['rank'])
                return
            if 'country_full' in df.columns:
                latest = df[df['rank_date'] == df['rank_date'].max()]
                for _, row in latest.iterrows():
                    name = FIFA_NAME_MAP.get(str(row['country_full']).strip(), str(row['country_full']).strip())
                    FIFA_RANKING[name] = int(row['rank'])
                return
        except Exception:
            pass

def get_fifa_prior(team):
    rank = FIFA_RANKING.get(team, 80)
    return float(np.clip(0.20 - (rank - 1) * (0.40 / 79), -0.25, 0.25))

# ── Carga de datos ────────────────────────────────────────────
def load_data():
    path = os.path.join(INTL_DIR, 'base_datos_maestra.csv')
    if not os.path.exists(path):
        path = RESULTS_CSV
    df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]
    for old, new in [('home_score','home_goals'),('away_score','away_goals')]:
        if old in df.columns: df.rename(columns={old:new}, inplace=True)
    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df.dropna(subset=['home_goals','away_goals'], inplace=True)
    df['home_goals'] = df['home_goals'].astype(int)
    df['away_goals'] = df['away_goals'].astype(int)
    df['match_date'] = pd.to_datetime(df['date'], errors='coerce')
    df.dropna(subset=['match_date'], inplace=True)
    df['year'] = df['match_date'].dt.year
    if 'neutral' not in df.columns: df['neutral'] = False
    df['neutral'] = df['neutral'].astype(str).str.lower().isin(['true','1','yes'])
    if 'tournament' not in df.columns: df['tournament'] = 'Friendly'
    df = df[df['year'] >= TRAIN_FROM].copy()
    df = df[df['home_team'].isin(TEAM_WHITELIST) & df['away_team'].isin(TEAM_WHITELIST)]
    df = df.sort_values('match_date').reset_index(drop=True)
    # Agregar categoría
    df['categoria'] = df['tournament'].apply(categorizar_torneo)
    return df

# ── Dixon-Coles ───────────────────────────────────────────────
def rho_correction(hg, ag, lam, mu, rho):
    if hg==0 and ag==0: return max(1e-10, 1 - lam*mu*rho)
    elif hg==0 and ag==1: return max(1e-10, 1 + lam*rho)
    elif hg==1 and ag==0: return max(1e-10, 1 + mu*rho)
    elif hg==1 and ag==1: return max(1e-10, 1 - rho)
    return 1.0

def dc_log_likelihood(params, df, teams, neutral_idx, weights):
    n = len(teams)
    atk = params[:n]; dfc = params[n:2*n]
    rho = params[2*n]; gam = params[2*n+1]
    hidx = np.array([teams.index(t) for t in df['home_team']])
    aidx = np.array([teams.index(t) for t in df['away_team']])
    home_adv = np.where(neutral_idx, 0.0, gam)
    lam = np.exp(atk[hidx] + dfc[aidx] + home_adv)
    mu = np.exp(atk[aidx] + dfc[hidx])
    hg = df['home_goals'].values; ag = df['away_goals'].values
    rc = np.array([rho_correction(h,a,l,m,rho) for h,a,l,m in zip(hg,ag,lam,mu)])
    ll = weights * (poisson.logpmf(hg,lam) + poisson.logpmf(ag,mu) + np.log(rc))
    return -np.sum(ll)

def fit_model(df_train):
    ref = df_train['match_date'].max()
    td = (ref - df_train['match_date']).dt.days.values
    tw = df_train['tournament'].apply(get_tournament_weight).values
    w = np.exp(-XI * td) * tw
    teams = sorted(set(df_train['home_team']) | set(df_train['away_team']))
    n = len(teams)
    x0 = np.zeros(2*n+2)
    for i,t in enumerate(teams):
        p = get_fifa_prior(t)
        x0[i] = p; x0[n+i] = -p*0.5
    x0[2*n+1] = 0.25
    bounds = [(-2.5,2.5)]*n + [(-2.5,2.5)]*n + [(-0.99,0.99)] + [(0,1.5)]
    neutral_idx = df_train['neutral'].values.astype(float)
    res = minimize(dc_log_likelihood, x0, args=(df_train, teams, neutral_idx, w),
                   method='SLSQP', bounds=bounds, options={'maxiter':400,'ftol':1e-6})
    return {
        'attack': dict(zip(teams, res.x[:n])),
        'defence': dict(zip(teams, res.x[n:2*n])),
        'rho': res.x[2*n], 'gamma': res.x[2*n+1], 'teams': teams,
    }

def predict(home, away, params, neutral=False):
    atk = params['attack']; dfc = params['defence']
    rho = params['rho']
    gam = params['gamma'] if not neutral else 0.0
    ah = get_fifa_prior(home); ad = get_fifa_prior(away)
    lam_h = np.exp(atk.get(home, ah) + dfc.get(away, -ad*0.5) + gam)
    lam_a = np.exp(atk.get(away, ad) + dfc.get(home, -ah*0.5))
    hg = np.random.poisson(lam_h, N_SIM)
    ag = np.random.poisson(lam_a, N_SIM)
    r = np.random.random(N_SIM); ok = np.ones(N_SIM, dtype=bool)
    for mask, thresh in [
        ((hg==0)&(ag==0), max(0, 1-lam_h*lam_a*rho)),
        ((hg==1)&(ag==0), max(0, 1+lam_a*rho)),
        ((hg==0)&(ag==1), max(0, 1+lam_h*rho)),
        ((hg==1)&(ag==1), max(0, 1-rho)),
    ]:
        ok[mask] &= r[mask] < thresh
    hg, ag = hg[ok], ag[ok]
    nv = max(len(hg), 1)
    return np.sum(hg>ag)/nv, np.sum(hg==ag)/nv, np.sum(ag>hg)/nv

# ── Backtest principal ────────────────────────────────────────
def run_backtest(df):
    test_df = df[df['year'] >= TEST_FROM].copy()
    test_df = test_df[test_df['categoria'] != 'Otro'].reset_index(drop=True)
    print(f"  Partidos de test ({TEST_FROM}+): {len(test_df)}")
    print(f"  Desglose por categoría:")
    for cat, n in test_df['categoria'].value_counts().items():
        print(f"    {cat:<20} {n:>5} partidos")

    results = []
    last_month = None; params = None
    total = len(test_df)

    for i, row in test_df.iterrows():
        if (i+1) % 100 == 0:
            print(f"  ⏳ {i+1}/{total} ({(i+1)/total*100:.0f}%)...", end='\r')
        match_date = row['match_date']
        month_key = (match_date.year, match_date.month)
        if month_key != last_month:
            train = df[df['match_date'] < match_date].copy()
            if len(train) < MIN_TRAIN: continue
            try:
                params = fit_model(train)
                last_month = month_key
            except: continue
        if params is None: continue

        neutral = bool(row.get('neutral', False))
        ph, pd_, pa = predict(row['home_team'], row['away_team'], params, neutral)
        hg = row['home_goals']; ag = row['away_goals']
        actual = 'H' if hg > ag else ('A' if ag > hg else 'D')

        results.append({
            'date': match_date.strftime('%Y-%m-%d'),
            'year': match_date.year,
            'tournament': row['tournament'],
            'categoria': row['categoria'],
            'home': row['home_team'], 'away': row['away_team'],
            'hg': hg, 'ag': ag, 'result': actual,
            'neutral': neutral,
            'p_home': round(ph,4), 'p_draw': round(pd_,4), 'p_away': round(pa,4),
        })

    print(f"\n  ✓ Backtest completo: {len(results)} partidos")
    return pd.DataFrame(results)

# ── Métricas segmentadas ──────────────────────────────────────
def compute_roi_by_category(res):
    print(f"\n{'='*75}")
    print(f"  RESULTADOS SEGMENTADOS POR TORNEO")
    print(f"{'='*75}")

    # Umbrales a probar
    UMBRALES = [0.03, 0.04, 0.05, 0.06, 0.07]

    for cat in ['Mundial', 'Clasificatoria', 'Continental', 'Nations League', 'Amistoso']:
        sub = res[res['categoria'] == cat]
        if len(sub) < 10:
            print(f"\n  {cat}: Solo {len(sub)} partidos — insuficiente")
            continue

        print(f"\n{'─'*75}")
        print(f"  📊 {cat.upper()} — {len(sub)} partidos de test")
        print(f"{'─'*75}")

        # Accuracy
        sub_copy = sub.copy()
        sub_copy['predicted'] = sub_copy[['p_home','p_draw','p_away']].idxmax(axis=1).map(
            {'p_home':'H','p_draw':'D','p_away':'A'})
        acc = (sub_copy['predicted'] == sub_copy['result']).mean()
        print(f"  Precisión general: {acc*100:.1f}%")

        # ROI por mercado y umbral
        print(f"\n  {'Mercado':<12} {'Umbral':<8} {'Apuestas':<10} {'Win%':<8} {'ROI':<10} {'Status'}")
        print(f"  {'-'*60}")

        best_home = {'roi': -999, 'thresh': 0, 'n': 0}
        best_away = {'roi': -999, 'thresh': 0, 'n': 0}

        for thresh in UMBRALES:
            for mercado, prob_col, result_val in [
                ('LOCAL (1)', 'p_home', 'H'),
                ('VISIT (2)', 'p_away', 'A'),
            ]:
                vb = sub[sub[prob_col] > thresh]
                if len(vb) < 3: continue
                # ROI vs cuota justa (1/probabilidad)
                fair_odd = 1.0 / vb[prob_col]
                won = (vb['result'] == result_val)
                pnl = np.where(won, fair_odd - 1, -1.0)
                roi = pnl.sum() / len(vb)
                win_pct = won.mean()
                status = '✅' if roi > 0 else '❌'

                print(f"  {mercado:<12} >{thresh*100:.0f}%     "
                      f"{len(vb):<10} {win_pct*100:.1f}%   "
                      f"{'+' if roi>=0 else ''}{roi*100:.1f}%     {status}")

                if mercado == 'LOCAL (1)' and roi > best_home['roi']:
                    best_home = {'roi': roi, 'thresh': thresh, 'n': len(vb)}
                if mercado == 'VISIT (2)' and roi > best_away['roi']:
                    best_away = {'roi': roi, 'thresh': thresh, 'n': len(vb)}

        # Resumen
        print(f"\n  → Mejor LOCAL:    umbral >{best_home['thresh']*100:.0f}%  "
              f"ROI {'+' if best_home['roi']>=0 else ''}{best_home['roi']*100:.1f}%  "
              f"({best_home['n']} apuestas)")
        print(f"  → Mejor VISIT:    umbral >{best_away['thresh']*100:.0f}%  "
              f"ROI {'+' if best_away['roi']>=0 else ''}{best_away['roi']*100:.1f}%  "
              f"({best_away['n']} apuestas)")

    # Tabla final resumen
    print(f"\n\n{'='*75}")
    print(f"  RESUMEN EJECUTIVO — ¿Dónde hay edge?")
    print(f"{'='*75}")
    print(f"  {'Categoría':<18} {'Mejor mercado':<15} {'Umbral':<10} {'ROI':<10} {'N':<6} {'Recomendación'}")
    print(f"  {'-'*70}")

    for cat in ['Mundial', 'Clasificatoria', 'Continental', 'Nations League', 'Amistoso']:
        sub = res[res['categoria'] == cat]
        if len(sub) < 10: continue
        best_roi = -999; best_info = ''
        for thresh in UMBRALES:
            for mercado, prob_col, result_val, label in [
                ('LOCAL','p_home','H','Local'),
                ('VISIT','p_away','A','Visitante'),
            ]:
                vb = sub[sub[prob_col] > thresh]
                if len(vb) < 5: continue
                fair_odd = 1.0 / vb[prob_col]
                won = (vb['result'] == result_val)
                pnl = np.where(won, fair_odd - 1, -1.0)
                roi = pnl.sum() / len(vb)
                if roi > best_roi:
                    best_roi = roi
                    best_info = f"{label:<15} >{thresh*100:.0f}%      " \
                               f"{'+' if roi>=0 else ''}{roi*100:.1f}%     {len(vb):<6}"

        recom = '✅ APOSTAR' if best_roi > 0.02 else ('🟡 MARGINAL' if best_roi > 0 else '⛔ NO APOSTAR')
        print(f"  {cat:<18} {best_info} {recom}")


def main():
    print("=" * 75)
    print("  BACKTEST SEGMENTADO POR TORNEO — Selecciones Nacionales")
    print("  ¿Hay edge visitante en el Mundial?")
    print("=" * 75)

    print("\n🏆 Cargando ranking FIFA...")
    load_fifa_ranking()
    print(f"  ✓ {len(FIFA_RANKING)} selecciones")

    print(f"\n📂 Cargando datos...")
    df = load_data()
    print(f"  ✓ {len(df):,} partidos ({df['year'].min()}-{df['year'].max()})")

    print(f"\n⏳ Ejecutando backtest walk-forward...")
    print(f"   Train: {TRAIN_FROM}-{TEST_FROM-1} | Test: {TEST_FROM}-2026")
    print(f"   Re-entrena: mensual | MC: {N_SIM:,} sim/partido\n")

    res = run_backtest(df)
    if len(res) == 0:
        print("❌ Sin resultados."); return

    res.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"\n✅ CSV guardado: {OUTPUT_CSV}")

    compute_roi_by_category(res)

    print(f"\n{'='*75}")
    print(f"  Si el ROI visitante en 'Mundial' es >0% con umbral razonable,")
    print(f"  podemos reactivar apuestas visitante SOLO para el Mundial 2026.")
    print(f"{'='*75}")


if __name__ == '__main__':
    main()
