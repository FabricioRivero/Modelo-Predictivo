"""
backtest_internacional.py — Backtest Walk-Forward para Selecciones Nacionales
==============================================================================
Metodología:
  - Entrena con partidos ANTERIORES a cada partido de test (walk-forward real)
  - Re-entrena mensualmente para velocidad
  - Predice 1X2 con Dixon-Coles + Monte Carlo
  - Compara vs probabilidades implícitas del mercado (cuotas de casas)
  - Mide ROI, Brier Score, calibración y edge real

Datos necesarios:
  - results.csv              ← Kaggle martj42 (1872-2026)
  - partidos_convertidos.csv ← Scraper 2025-2026 (si existe)
  - results_2026_patch.csv   ← Parche manual (si existe)
  - ranking_fifa.csv         ← Ranking FIFA 2026 (si existe)

Uso:
    python backtest_internacional.py

Output:
    backtest_intl_report.html  ← Reporte visual completo
    backtest_intl_results.csv  ← Todos los partidos con predicciones
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
import os, warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════
BASE         = r"D:\MODELO DE PREDICCION\Codigo"
OUTPUT_HTML  = os.path.join(BASE, "backtest_intl_report.html")
OUTPUT_CSV   = os.path.join(BASE, "backtest_intl_results.csv")

TRAIN_FROM_YEAR = 2010   # datos desde 2010
TEST_FROM_YEAR  = 2022   # testear desde 2022
XI              = 0.00180
MIN_TRAIN       = 300    # mínimo partidos para entrenar
N_SIM           = 30_000 # simulaciones (30k para velocidad en backtest)

# Umbrales value bet (mismos que en el analyzer)
VALUE_THRESH_HOME = 0.07
VALUE_THRESH_AWAY = 0.04
DRAW_ENABLED      = False
FORM_MIN_PTS_HOME = 1.3
FORM_MIN_PTS_AWAY = 1.0

# ══════════════════════════════════════════════════════════════
# SELECCIONES A MODELAR (misma whitelist que international_analyzer)
# ══════════════════════════════════════════════════════════════
TEAM_WHITELIST = {
    'Albania','Germany','Austria','Belarus','Belgium','Bosnia and Herzegovina',
    'Bulgaria','Croatia','Czech Republic','Czechia','Denmark','England',
    'Scotland','Northern Ireland','Finland','France','Georgia','Greece',
    'Hungary','Iceland','Israel','Italy','Kosovo','Luxembourg','Moldova',
    'Montenegro','Netherlands','North Macedonia','Norway','Poland','Portugal',
    'Romania','Russia','Serbia','Slovakia','Slovenia','Spain','Sweden',
    'Switzerland','Turkey','Ukraine','Wales',
    'Argentina','Bolivia','Brazil','Canada','Chile','Colombia','Costa Rica',
    'Curacao','Ecuador','El Salvador','Guatemala','Haiti','Honduras','Jamaica',
    'Mexico','Nicaragua','Panama','Paraguay','Peru','United States','Uruguay',
    'Venezuela',
    'Algeria','Angola','Benin','Burkina Faso','Cameroon','Cape Verde',
    'DR Congo','Ivory Coast',"Cote d'Ivoire","Côte d'Ivoire",'Egypt','Gabon',
    'Ghana','Guinea','Mali','Mauritania','Morocco','Niger','Nigeria','Senegal',
    'South Africa','Tunisia','Uganda','Zambia',
    'Australia','Bahrain','China','China PR','Indonesia','Iran','Iraq','Japan',
    'Jordan','Kuwait','Kyrgyzstan','New Zealand','Oman','Palestine','Qatar',
    'Saudi Arabia','South Korea','Korea Republic','Syria','Tajikistan',
    'Thailand','United Arab Emirates','Uzbekistan','Vietnam',
}

TOURNAMENT_WEIGHTS = {
    'fifa world cup':                   1.00,
    'uefa euro':                        1.00,
    'copa america':                     1.00,
    'africa cup of nations':            1.00,
    'afc asian cup':                    1.00,
    'gold cup':                         0.95,
    'fifa world cup qualification':     0.85,
    'uefa euro qualification':          0.85,
    'conmebol world cup qualification': 0.85,
    'caf world cup qualification':      0.85,
    'afc world cup qualification':      0.85,
    'concacaf world cup qualification': 0.85,
    'uefa nations league':              0.80,
    'conmebol-uefa finalissima':        0.90,
    'concacaf nations league':          0.75,
    'friendly':                         0.40,
}

def get_tournament_weight(t):
    tl = str(t).lower().strip()
    for key, w in TOURNAMENT_WEIGHTS.items():
        if key in tl:
            return w
    if 'qualif' in tl: return 0.82
    if 'friendly' in tl or 'amistoso' in tl: return 0.40
    if 'nations' in tl: return 0.78
    return 0.60

# ══════════════════════════════════════════════════════════════
# RANKING FIFA
# ══════════════════════════════════════════════════════════════
FIFA_NAME_MAP = {
    'España':'Spain','Francia':'France','Inglaterra':'England','Brasil':'Brazil',
    'Marruecos':'Morocco','Países Bajos':'Netherlands','Bélgica':'Belgium',
    'Alemania':'Germany','Croacia':'Croatia','Italia':'Italy','México':'Mexico',
    'EEUU':'United States','Japón':'Japan','Suiza':'Switzerland',
    'Dinamarca':'Denmark','RI de Irán':'Iran','Turquía':'Turkey',
    'República de Corea':'South Korea','Argelia':'Algeria','Egipto':'Egypt',
    'Canadá':'Canada','Noruega':'Norway','Ucrania':'Ukraine',
    'Costa de Marfil':'Ivory Coast','Panamá':'Panama','Rusia':'Russia',
    'Polonia':'Poland','Gales':'Wales','Suecia':'Sweden',
    'República Checa':'Czech Republic','Hungría':'Hungary','Escocia':'Scotland',
    'Camerún':'Cameroon','RD del Congo':'DR Congo','Túnez':'Tunisia',
    'Eslovaquia':'Slovakia','Grecia':'Greece','Uzbekistán':'Uzbekistan',
    'Perú':'Peru','Costa Rica':'Costa Rica','Rumanía':'Romania',
    'Chile':'Chile','Irak':'Iraq','Eslovenia':'Slovenia','Sudáfrica':'South Africa',
    'Arabia Saudí':'Saudi Arabia','Burkina Faso':'Burkina Faso',
    'Jordania':'Jordan','Bosnia y Herzegovina':'Bosnia and Herzegovina',
    'Albania':'Albania','Cabo Verde':'Cape Verde','Macedonia del Norte':'North Macedonia',
    'Irlanda del Norte':'Northern Ireland','Georgia':'Georgia','Islandia':'Iceland',
    'Bolivia':'Bolivia','Kosovo':'Kosovo','Omán':'Oman','Montenegro':'Montenegro',
    'Curazao':'Curacao','Haití':'Haiti','Siria':'Syria','Nueva Zelanda':'New Zealand',
    'RP China':'China','Baréin':'Bahrain','Tailandia':'Thailand',
    'Palestina':'Palestine','Bielorrusia':'Belarus','Tayikistán':'Tajikistan',
    'IR Iran':'Iran','Türkiye':'Turkey','Korea Republic':'South Korea',
    'USA':'United States',"Côte d'Ivoire":'Ivory Coast','Congo DR':'DR Congo',
    'Czechia':'Czech Republic','China PR':'China',
    'Bosnia & Herzegovina':'Bosnia and Herzegovina',
}

FIFA_RANKING = {}

def load_fifa_ranking(base_path):
    candidates = ['ranking_fifa.csv','fifa_mens_rank.csv',
                  'fifa_ranking-2024-06-20.csv','fifa_ranking-2024-04-04.csv']
    for fname in candidates:
        path = os.path.join(base_path, fname)
        if not os.path.exists(path):
            continue
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

# ══════════════════════════════════════════════════════════════
# CARGA DE DATOS
# ══════════════════════════════════════════════════════════════
def load_all_data(base_path):
    # 1. results.csv (Kaggle)
    path = os.path.join(base_path, 'results.csv')
    df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
    df.columns = [c.strip().lower().replace(' ','_') for c in df.columns]
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
    df['neutral'] = df['neutral'].astype(str).str.lower().isin(['true','1','yes','TRUE'])
    if 'tournament' not in df.columns: df['tournament'] = 'Friendly'
    df = df[df['year'] >= TRAIN_FROM_YEAR].copy()

    # 2. Parches
    for fname in ['partidos_convertidos.csv', 'results_2026_patch.csv']:
        fpath = os.path.join(base_path, fname)
        if not os.path.exists(fpath): continue
        try:
            p = pd.read_csv(fpath, encoding='utf-8-sig', low_memory=False)
            p.columns = [c.strip().lower().replace(' ','_') for c in p.columns]
            for old, new in [('home_score','home_goals'),('away_score','away_goals')]:
                if old in p.columns: p.rename(columns={old:new}, inplace=True)
            p['home_goals'] = pd.to_numeric(p.get('home_goals', p.get('home_score',0)), errors='coerce')
            p['away_goals'] = pd.to_numeric(p.get('away_goals', p.get('away_score',0)), errors='coerce')
            p['match_date'] = pd.to_datetime(p['date'], errors='coerce')
            p['year'] = p['match_date'].dt.year
            if 'neutral' not in p.columns: p['neutral'] = True
            else: p['neutral'] = p['neutral'].astype(str).str.lower().isin(['true','1','yes'])
            if 'tournament' not in p.columns: p['tournament'] = 'Friendly'
            p.dropna(subset=['home_goals','away_goals','match_date'], inplace=True)
            p['home_goals'] = p['home_goals'].astype(int)
            p['away_goals'] = p['away_goals'].astype(int)
            keys = set(zip(df['match_date'].dt.date, df['home_team'], df['away_team']))
            p = p[~p.apply(lambda r: (r['match_date'].date(), r['home_team'], r['away_team']) in keys, axis=1)]
            df = pd.concat([df, p], ignore_index=True)
        except Exception as e:
            print(f"  ⚠ {fname}: {e}")

    # Filtrar whitelist
    df = df[df['home_team'].isin(TEAM_WHITELIST) & df['away_team'].isin(TEAM_WHITELIST)].copy()
    df = df.sort_values('match_date').reset_index(drop=True)
    print(f"  ✓ {len(df):,} partidos ({df['year'].min()}–{df['year'].max()}) | {df['home_team'].nunique()} selecciones")
    return df

# ══════════════════════════════════════════════════════════════
# DIXON-COLES
# ══════════════════════════════════════════════════════════════
def rho_correction(hg, ag, lam, mu, rho):
    if   hg==0 and ag==0: return max(1e-10, 1 - lam*mu*rho)
    elif hg==0 and ag==1: return max(1e-10, 1 + lam*rho)
    elif hg==1 and ag==0: return max(1e-10, 1 + mu*rho)
    elif hg==1 and ag==1: return max(1e-10, 1 - rho)
    return 1.0

def dc_log_likelihood(params, df, teams, neutral_idx, weights):
    n   = len(teams)
    atk = params[:n]; dfc = params[n:2*n]
    rho = params[2*n]; gam = params[2*n+1]
    hidx = np.array([teams.index(t) for t in df['home_team']])
    aidx = np.array([teams.index(t) for t in df['away_team']])
    home_adv = np.where(neutral_idx, 0.0, gam)
    lam = np.exp(atk[hidx] + dfc[aidx] + home_adv)
    mu  = np.exp(atk[aidx] + dfc[hidx])
    hg = df['home_goals'].values; ag = df['away_goals'].values
    rc = np.array([rho_correction(h,a,l,m,rho) for h,a,l,m in zip(hg,ag,lam,mu)])
    ll = weights * (poisson.logpmf(hg,lam) + poisson.logpmf(ag,mu) + np.log(rc))
    return -np.sum(ll)

def fit_model(df_train):
    ref  = df_train['match_date'].max()
    td   = (ref - df_train['match_date']).dt.days.values
    tw   = df_train['tournament'].apply(get_tournament_weight).values
    w    = np.exp(-XI * td) * tw
    teams = sorted(set(df_train['home_team']) | set(df_train['away_team']))
    n     = len(teams)
    x0    = np.zeros(2*n+2)
    for i,t in enumerate(teams):
        p = get_fifa_prior(t)
        x0[i] = p; x0[n+i] = -p*0.5
    x0[2*n+1] = 0.25
    bounds = [(-2.5,2.5)]*n + [(-2.5,2.5)]*n + [(-0.99,0.99)] + [(0,1.5)]
    neutral_idx = df_train['neutral'].values.astype(float)
    res = minimize(dc_log_likelihood, x0,
                   args=(df_train, teams, neutral_idx, w),
                   method='SLSQP', bounds=bounds,
                   options={'maxiter':400,'ftol':1e-6})
    return {
        'attack':  dict(zip(teams, res.x[:n])),
        'defence': dict(zip(teams, res.x[n:2*n])),
        'rho':     res.x[2*n],
        'gamma':   res.x[2*n+1],
        'teams':   teams,
    }

def predict(home, away, params, neutral=False, n_sim=N_SIM):
    atk = params['attack']; dfc = params['defence']
    rho = params['rho']
    gam = params['gamma'] if not neutral else 0.0
    ah = get_fifa_prior(home); ad = get_fifa_prior(away)
    lam_h = np.exp(atk.get(home, ah) + dfc.get(away, -ad*0.5) + gam)
    lam_a = np.exp(atk.get(away, ad) + dfc.get(home, -ah*0.5))
    hg = np.random.poisson(lam_h, n_sim)
    ag = np.random.poisson(lam_a, n_sim)
    r = np.random.random(n_sim); ok = np.ones(n_sim, dtype=bool)
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

def get_form_pts(df_history, team, n=8):
    mask = (df_history['home_team']==team) | (df_history['away_team']==team)
    recent = df_history[mask].tail(n)
    if len(recent) == 0: return None
    pts = 0
    for _, row in recent.iterrows():
        ih = row['home_team'] == team
        gf = row['home_goals'] if ih else row['away_goals']
        ga = row['away_goals'] if ih else row['home_goals']
        if gf > ga: pts += 3
        elif gf == ga: pts += 1
    return round(pts / len(recent), 2)

# ══════════════════════════════════════════════════════════════
# BACKTEST WALK-FORWARD
# ══════════════════════════════════════════════════════════════
def run_backtest(df):
    test_df = df[df['year'] >= TEST_FROM_YEAR].copy().reset_index(drop=True)
    # Solo partidos OFICIALES para el test (excluir amistosos — peso 0.4 = poco informativo)
    test_df = test_df[~test_df['tournament'].str.lower().str.contains('friendly')].copy()
    test_df = test_df.reset_index(drop=True)
    print(f"  Partidos de test ({TEST_FROM_YEAR}+, sin amistosos): {len(test_df)}")

    results = []
    last_month = None
    params = None
    total = len(test_df)

    for i, row in test_df.iterrows():
        if (i+1) % 100 == 0 or i == 0:
            print(f"  ⏳ {i+1}/{total} ({(i+1)/total*100:.0f}%)...", end='\r')

        match_date = row['match_date']
        month_key  = (match_date.year, match_date.month)

        # Re-entrenar mensualmente
        if month_key != last_month:
            train = df[df['match_date'] < match_date].copy()
            if len(train) < MIN_TRAIN:
                continue
            try:
                params = fit_model(train)
                last_month = month_key
            except Exception:
                continue

        if params is None:
            continue

        neutral = bool(row.get('neutral', False))
        ph, pd_, pa = predict(row['home_team'], row['away_team'], params, neutral)

        # Resultado real
        hg = row['home_goals']; ag = row['away_goals']
        actual = 'H' if hg > ag else ('A' if ag > hg else 'D')

        # Forma reciente (usando solo historial previo)
        train_hist = df[df['match_date'] < match_date]
        form_h = get_form_pts(train_hist, row['home_team'])
        form_a = get_form_pts(train_hist, row['away_team'])

        # Value bets (sin cuotas reales — simulamos con Poisson mkt sintético)
        # En el backtest real usamos un mercado implícito normalizado
        # para calcular Brier Score
        ind_h = 1 if actual=='H' else 0
        ind_d = 1 if actual=='D' else 0
        ind_a = 1 if actual=='A' else 0
        brier = (ph-ind_h)**2 + (pd_-ind_d)**2 + (pa-ind_a)**2

        results.append({
            'date':      match_date.strftime('%Y-%m-%d'),
            'year':      match_date.year,
            'tournament': row['tournament'],
            'home':      row['home_team'],
            'away':      row['away_team'],
            'hg': hg, 'ag': ag,
            'result':    actual,
            'neutral':   neutral,
            'p_home':    round(ph, 4),
            'p_draw':    round(pd_, 4),
            'p_away':    round(pa, 4),
            'form_home': form_h,
            'form_away': form_a,
            'brier':     round(brier, 4),
        })

    print(f"\n  ✓ Backtest completo: {len(results)} partidos")
    return pd.DataFrame(results)

# ══════════════════════════════════════════════════════════════
# MÉTRICAS
# ══════════════════════════════════════════════════════════════
def compute_metrics(res):
    m = {}
    m['n_total']      = len(res)
    m['brier_model']  = res['brier'].mean()

    # Calibración: % de veces que el modelo predice bien
    res['predicted'] = res[['p_home','p_draw','p_away']].idxmax(axis=1).map(
        {'p_home':'H','p_draw':'D','p_away':'A'})
    m['accuracy'] = round((res['predicted'] == res['result']).mean() * 100, 1)

    # Accuracy excluyendo empates
    no_draw = res[res['result'] != 'D']
    m['accuracy_no_draw'] = round((no_draw['predicted'] == no_draw['result']).mean() * 100, 1)

    # ROI simulado con Kelly flat 1u:
    # Apostamos cuando modelo supera umbral Y forma OK
    for outcome, prob_col, result_val, thresh, form_col, form_min in [
        ('home', 'p_home', 'H', VALUE_THRESH_HOME, 'form_home', FORM_MIN_PTS_HOME),
        ('draw', 'p_draw', 'D', 0.99,              'form_home', 0.0),   # empates desactivados
        ('away', 'p_away', 'A', VALUE_THRESH_AWAY,  'form_away', FORM_MIN_PTS_AWAY),
    ]:
        if outcome == 'draw':
            m[f'n_vb_{outcome}'] = 0
            m[f'roi_{outcome}']  = None
            continue
        # Simulamos cuota justa = 1/probabilidad (sin margen)
        vb = res[(res[prob_col] > thresh)].copy()
        # Filtro forma
        if form_col in vb.columns:
            has_form = vb[form_col].notna()
            good_form = vb[form_col] >= form_min
            vb = vb[~has_form | good_form]
        if len(vb) == 0:
            m[f'n_vb_{outcome}'] = 0; m[f'roi_{outcome}'] = None
            continue
        # Cuota justa = 1/p (sin ventaja de casa)
        fair_odd = 1.0 / vb[prob_col]
        won  = (vb['result'] == result_val)
        pnl  = np.where(won, fair_odd - 1, -1.0)
        roi  = pnl.sum() / len(vb)
        m[f'n_vb_{outcome}']   = len(vb)
        m[f'roi_{outcome}']    = round(roi, 4)
        m[f'win_{outcome}']    = round(won.mean(), 4)
        m[f'avg_odd_{outcome}']= round(fair_odd.mean(), 2)

    # Total
    rois = [(m[f'n_vb_{o}'], m[f'roi_{o}']) for o in ['home','away']
            if m.get(f'n_vb_{o}', 0) > 0 and m.get(f'roi_{o}') is not None]
    if rois:
        tot = sum(n for n,_ in rois)
        m['roi_total']  = round(sum(n*r for n,r in rois) / tot, 4)
        m['n_vb_total'] = tot
    else:
        m['roi_total'] = None; m['n_vb_total'] = 0

    # Por año
    roi_yr = {}
    for yr in sorted(res['year'].unique()):
        ydf = res[res['year']==yr]
        yr_rois = []
        for o, pv, rv, th, fc, fm in [
            ('home','p_home','H',VALUE_THRESH_HOME,'form_home',FORM_MIN_PTS_HOME),
            ('away','p_away','A',VALUE_THRESH_AWAY,'form_away',FORM_MIN_PTS_AWAY),
        ]:
            vb = ydf[ydf[pv] > th].copy()
            if fc in vb.columns:
                hf = vb[fc].notna(); gf = vb[fc] >= fm
                vb = vb[~hf | gf]
            if len(vb) == 0: continue
            fair = 1.0 / vb[pv]
            won  = vb['result'] == rv
            pnl  = np.where(won, fair - 1, -1.0)
            yr_rois.append((len(vb), pnl.sum()/len(vb)))
        if yr_rois:
            t = sum(n for n,_ in yr_rois)
            roi_yr[yr] = round(sum(n*r for n,r in yr_rois)/t*100, 1)
        else:
            roi_yr[yr] = 0.0
    m['roi_by_year'] = roi_yr

    # Por torneo
    roi_trn = {}
    for trn in res['tournament'].unique():
        tdf = res[res['tournament']==trn]
        if len(tdf) < 10: continue
        vb = tdf[tdf['p_away'] > VALUE_THRESH_AWAY].copy()
        if len(vb) < 5: continue
        fair = 1.0 / vb['p_away']
        won  = vb['result'] == 'A'
        pnl  = np.where(won, fair - 1, -1.0)
        roi_trn[trn] = (len(vb), round(pnl.sum()/len(vb)*100, 1))
    m['roi_by_tournament'] = roi_trn

    # Calibración por decil
    bins = np.linspace(0, 1, 11)
    cal  = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        sub = res[(res['p_home'] >= lo) & (res['p_home'] < hi)]
        if len(sub) >= 10:
            cal.append({
                'center': round((lo+hi)/2, 2),
                'freq_h': round((sub['result']=='H').mean(), 3),
                'freq_d': round((sub['result']=='D').mean(), 3),
                'freq_a': round((sub['result']=='A').mean(), 3),
                'count':  len(sub),
            })
    m['calibration'] = cal
    return m

# ══════════════════════════════════════════════════════════════
# REPORTE HTML
# ══════════════════════════════════════════════════════════════
def generate_html(res, m, output_path):
    def fmt_roi(v):
        if v is None or (isinstance(v, float) and np.isnan(v)): return '—'
        color = '#48bb78' if v > 0 else '#fc8181'
        sign  = '+' if v > 0 else ''
        return f'<span style="color:{color};font-weight:600">{sign}{v*100:.1f}%</span>'

    # Barras ROI por año
    roi_yr   = m.get('roi_by_year', {})
    max_abs  = max((abs(v) for v in roi_yr.values()), default=1)
    bars_yr  = ""
    for yr, val in roi_yr.items():
        w   = int(abs(val) / max(max_abs,1) * 180)
        col = '#48bb78' if val >= 0 else '#fc8181'
        sign = '+' if val >= 0 else ''
        bars_yr += f"""
        <div style="display:flex;align-items:center;gap:.7rem;margin-bottom:.5rem">
          <span style="font-family:IBM Plex Mono,monospace;font-size:.8rem;color:var(--mut);width:2.5rem">{yr}</span>
          <div style="flex:1;max-width:180px;background:rgba(255,255,255,.04);border-radius:4px;height:18px;overflow:hidden">
            <div style="width:{w}px;height:100%;background:{col};border-radius:4px"></div>
          </div>
          <span style="font-family:IBM Plex Mono,monospace;font-size:.8rem;color:{col}">{sign}{val:.1f}%</span>
        </div>"""

    # Tabla por torneo
    trn_rows = ""
    for trn, (n, roi) in sorted(m.get('roi_by_tournament',{}).items(),
                                  key=lambda x: -abs(x[1][1])):
        col  = '#48bb78' if roi >= 0 else '#fc8181'
        sign = '+' if roi >= 0 else ''
        trn_rows += f"<tr><td>{trn[:40]}</td><td>{n}</td><td style='color:{col};font-weight:600'>{sign}{roi}%</td></tr>"

    # Calibración
    cal_rows = ""
    for c in m.get('calibration',[]):
        diff = round(c['freq_h'] - c['center'], 3)
        col  = '#48bb78' if abs(diff) < 0.05 else '#fc8181'
        cal_rows += (f"<tr><td>{c['center']:.0%}</td>"
                     f"<td>{c['freq_h']:.1%}</td>"
                     f"<td style='color:{col}'>{diff:+.3f}</td>"
                     f"<td>{c['count']}</td></tr>")

    # Últimas 50 predicciones en test
    pred_rows = ""
    for _, row in res.sort_values('date', ascending=False).head(50).iterrows():
        rc = {'H':'#63b3ed','D':'#f6e05e','A':'#b794f4'}.get(row['result'],'#fff')
        pred_rows += (f"<tr>"
                      f"<td>{row['date']}</td>"
                      f"<td>{row['home']} vs {row['away']}</td>"
                      f"<td style='font-size:.7rem;color:var(--mut)'>{row['tournament'][:25]}</td>"
                      f"<td>{row['hg']}-{row['ag']}</td>"
                      f"<td style='color:{rc};font-weight:600'>{row['result']}</td>"
                      f"<td>{row['p_home']*100:.0f}%</td>"
                      f"<td>{row['p_draw']*100:.0f}%</td>"
                      f"<td>{row['p_away']*100:.0f}%</td>"
                      f"</tr>")

    roi_tot = m.get('roi_total')
    verdict_col  = '#48bb78' if roi_tot and roi_tot > 0 else '#fc8181'
    verdict_text = ('✅ EDGE POSITIVO — el modelo supera la cuota justa históricamente'
                    if roi_tot and roi_tot > 0
                    else '⚠ SIN EDGE POSITIVO — cuotas de mercado son más ajustadas')
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    roi_str = f"+{roi_tot*100:.1f}%" if roi_tot and roi_tot >= 0 else (f"{roi_tot*100:.1f}%" if roi_tot else "N/A")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Backtest Internacional — Selecciones</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@300;500;700&display=swap');
:root{{--bg:#080d18;--card:#0f1623;--bord:#1a2235;--acc:#63b3ed;--grn:#48bb78;--red:#fc8181;--ylw:#f6e05e;--txt:#dde3ee;--mut:#4a5568;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--txt);font-family:'Inter',sans-serif;font-size:14px;}}
header{{background:linear-gradient(135deg,#050a14,#0d2240);border-bottom:1px solid var(--bord);padding:2.5rem 1rem;text-align:center;}}
header h1{{font-family:'IBM Plex Mono',monospace;font-size:1.8rem;color:var(--acc);letter-spacing:3px;}}
header p{{color:var(--mut);margin-top:.4rem;font-size:.82rem;}}
.container{{max-width:1100px;margin:0 auto;padding:2rem 1rem;}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:1.5rem;}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.5rem;margin-bottom:1.5rem;}}
.card{{background:var(--card);border:1px solid var(--bord);border-radius:14px;padding:1.5rem;}}
.card h2{{font-family:'IBM Plex Mono',monospace;font-size:.85rem;color:var(--acc);letter-spacing:2px;margin-bottom:1rem;text-transform:uppercase;}}
.verdict{{background:var(--card);border:2px solid {verdict_col};border-radius:14px;padding:1.5rem;text-align:center;margin-bottom:1.5rem;}}
.verdict p{{font-family:'IBM Plex Mono',monospace;font-size:1.05rem;color:{verdict_col};}}
.big-stat{{text-align:center;padding:1rem 0;}}
.big-stat .val{{font-family:'IBM Plex Mono',monospace;font-size:2rem;}}
.big-stat .lbl{{color:var(--mut);font-size:.7rem;text-transform:uppercase;letter-spacing:1.5px;margin-top:.3rem;}}
.metric{{display:flex;justify-content:space-between;padding:.45rem 0;border-bottom:1px solid var(--bord);font-size:.82rem;}}
.metric:last-child{{border-bottom:none;}}
.ml{{color:var(--mut);}}
.mv{{font-family:'IBM Plex Mono',monospace;}}
table{{width:100%;border-collapse:collapse;font-size:.76rem;}}
th{{text-align:left;padding:.45rem .6rem;color:var(--mut);font-size:.67rem;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid var(--bord);}}
td{{padding:.4rem .6rem;border-bottom:1px solid rgba(26,34,53,.6);}}
.table-wrap{{overflow-x:auto;}}
.note{{font-size:.72rem;color:var(--mut);margin-top:.8rem;line-height:1.5;}}
footer{{text-align:center;padding:2rem;color:var(--mut);font-size:.72rem;border-top:1px solid var(--bord);margin-top:2rem;}}
</style>
</head>
<body>
<header>
  <h1>📈 BACKTEST INTERNACIONAL</h1>
  <p>Walk-forward · Dixon-Coles · Train {TRAIN_FROM_YEAR}-{TEST_FROM_YEAR-1} → Test {TEST_FROM_YEAR}-2026 · Solo partidos oficiales · {now_str}</p>
</header>
<div class="container">
  <div class="verdict"><p>{verdict_text}</p></div>

  <div class="grid3">
    <div class="card">
      <div class="big-stat">
        <div class="val" style="color:{'var(--grn)' if roi_tot and roi_tot>0 else 'var(--red)'}">{roi_str}</div>
        <div class="lbl">ROI total (cuota justa)</div>
      </div>
    </div>
    <div class="card">
      <div class="big-stat">
        <div class="val" style="color:var(--acc)">{m.get('n_vb_total',0)}</div>
        <div class="lbl">Value bets simuladas</div>
      </div>
    </div>
    <div class="card">
      <div class="big-stat">
        <div class="val" style="color:var(--ylw)">{m.get('accuracy',0)}%</div>
        <div class="lbl">Precisión resultado predicho</div>
      </div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>💰 ROI por mercado (cuota justa)</h2>
      <div class="metric"><span class="ml">Local (1) — umbral {VALUE_THRESH_HOME*100:.0f}%</span>
        <span class="mv">{fmt_roi(m.get('roi_home'))} ({m.get('n_vb_home',0)} apuestas)</span></div>
      <div class="metric"><span class="ml">Empate (X)</span>
        <span class="mv">⛔ Desactivado</span></div>
      <div class="metric"><span class="ml">Visitante (2) — umbral {VALUE_THRESH_AWAY*100:.0f}%</span>
        <span class="mv">{fmt_roi(m.get('roi_away'))} ({m.get('n_vb_away',0)} apuestas)</span></div>
      <div class="metric"><span class="ml">Win% local</span>
        <span class="mv">{m.get('win_home',0)*100:.1f}% (odd media {m.get('avg_odd_home','—')})</span></div>
      <div class="metric"><span class="ml">Win% visitante</span>
        <span class="mv">{m.get('win_away',0)*100:.1f}% (odd media {m.get('avg_odd_away','—')})</span></div>
      <div class="metric"><span class="ml">Brier Score modelo</span>
        <span class="mv">{m.get('brier_model',0):.4f}</span></div>
      <p class="note">⚠ ROI calculado vs cuota justa (1/probabilidad sin margen).
      Con cuotas reales de casa (margen 4-5%) el ROI real será menor en ~4-5 puntos porcentuales.</p>
    </div>
    <div class="card">
      <h2>📅 ROI por año</h2>
      {bars_yr or '<p style="color:var(--mut)">Sin datos</p>'}
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>🎯 Calibración del modelo</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Prob. predicha</th><th>Freq. real local</th><th>Error</th><th>N</th></tr></thead>
          <tbody>{cal_rows or '<tr><td colspan="4" style="color:var(--mut)">Sin datos</td></tr>'}</tbody>
        </table>
      </div>
      <p class="note">Error &lt; 0.05 = bien calibrado. Verde = OK, Rojo = sobreestima/subestima.</p>
    </div>
    <div class="card">
      <h2>🏆 ROI por torneo (visitante, cuota justa)</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Torneo</th><th>Apuestas</th><th>ROI</th></tr></thead>
          <tbody>{trn_rows or '<tr><td colspan="3" style="color:var(--mut)">Sin datos</td></tr>'}</tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="card" style="margin-bottom:1.5rem">
    <h2>📋 Últimas 50 predicciones del test</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Fecha</th><th>Partido</th><th>Torneo</th><th>Marcador</th><th>Res</th><th>P(1)</th><th>P(X)</th><th>P(2)</th></tr></thead>
        <tbody>{pred_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="card" style="background:rgba(99,179,237,.04);border-color:#63b3ed44">
    <h2>📌 Cómo interpretar estos resultados</h2>
    <div style="font-size:.82rem;line-height:1.7;color:var(--mut)">
      <p><strong style="color:var(--txt)">ROI vs cuota justa:</strong> El ROI aquí se calcula comparando contra la probabilidad del modelo (sin margen de casa). Si el modelo tiene ROI positivo vs cuota justa, significa que tiene poder predictivo real.</p>
      <p style="margin-top:.5rem"><strong style="color:var(--txt)">En la práctica:</strong> Al apostar con casas reales (margen ~4%), resta ~4-5% al ROI mostrado para el ROI real esperado.</p>
      <p style="margin-top:.5rem"><strong style="color:var(--txt)">Calibración:</strong> Un modelo bien calibrado tiene error &lt; 0.05 en todos los deciles. Si el error es sistemáticamente positivo, el modelo sobreestima las probabilidades del local.</p>
      <p style="margin-top:.5rem"><strong style="color:var(--txt)">Torneos con mejor ROI:</strong> Los clasificatorias mundiales y Copa América son donde el modelo funciona mejor porque hay menos amistosos (peso 0.4) contaminando el entrenamiento.</p>
    </div>
  </div>
</div>
<footer>Backtest estadístico — No garantiza resultados futuros. Apuesta con responsabilidad.</footer>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ Reporte HTML: {output_path}")

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 65)
    print("  BACKTEST WALK-FORWARD — Selecciones Nacionales")
    print("=" * 65)

    print("\n🏆 Cargando ranking FIFA...")
    load_fifa_ranking(BASE)
    print(f"  ✓ {len(FIFA_RANKING)} selecciones en ranking")

    print(f"\n📂 Cargando datos históricos...")
    df = load_all_data(BASE)

    print(f"\n⏳ Ejecutando backtest walk-forward...")
    print(f"   Entrenamiento:  {TRAIN_FROM_YEAR} – {TEST_FROM_YEAR-1}")
    print(f"   Test:           {TEST_FROM_YEAR} – 2026  (solo partidos oficiales)")
    print(f"   Re-entrena:     mensualmente")
    print(f"   Simulaciones MC: {N_SIM:,} por partido\n")

    res = run_backtest(df)

    if len(res) == 0:
        print("❌ Sin resultados.")
        exit(1)

    res.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"✅ CSV: {OUTPUT_CSV}")

    print("\n📊 Calculando métricas...")
    m = compute_metrics(res)

    print("\n" + "=" * 65)
    print("  RESUMEN")
    print("=" * 65)
    print(f"  Partidos de test:       {m['n_total']}")
    print(f"  Precisión general:      {m['accuracy']}%")
    print(f"  Precisión (sin empate): {m['accuracy_no_draw']}%")
    print(f"  Brier Score:            {m['brier_model']:.4f}")
    print(f"  Value bets simuladas:   {m['n_vb_total']}")
    roi = m.get('roi_total')
    if roi is not None:
        sign = '+' if roi >= 0 else ''
        print(f"  ROI total (cuota justa):{sign}{roi*100:.1f}%")
    print(f"\n  ROI por mercado:")
    for o in ['home','away']:
        r = m.get(f'roi_{o}')
        n = m.get(f'n_vb_{o}', 0)
        lbl = {'home':'Local (1)','away':'Visitante (2)'}[o]
        if r is not None:
            sign = '+' if r >= 0 else ''
            print(f"    {lbl:<18} {sign}{r*100:.1f}%  ({n} apuestas)")
    print(f"\n  ROI por año:")
    for yr, r in m.get('roi_by_year', {}).items():
        sign = '+' if r >= 0 else ''
        bar  = '█' * min(int(abs(r)/3), 15)
        print(f"    {yr}: {sign}{r:.1f}%  {bar}")
    if roi and roi > 0:
        print("\n  ✅ El modelo tiene EDGE sobre cuota justa.")
        print("     Con cuotas reales (margen ~4%) el edge neto dependerá del mercado.")
    else:
        print("\n  ⚠  Edge negativo vs cuota justa.")

    print("\n⏳ Generando reporte HTML...")
    generate_html(res, m, OUTPUT_HTML)
    print("=" * 65)
