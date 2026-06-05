"""
backtest_pinnacle.py — Backtest Walk-Forward con cuotas Pinnacle
================================================================
Metodología:
  - Entrena con partidos ANTERIORES a cada partido de test
  - Predice 1X2 con Dixon-Coles + Monte Carlo
  - Compara vs cuotas de cierre Pinnacle (PSCH/PSCD/PSCA)
  - Mide ROI, Brier Score, calibración y edge real

Uso:
    python backtest_pinnacle.py

Resultado:
    backtest_report.html — reporte visual completo
    backtest_results.csv — todos los partidos con predicciones
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
import os, sys, warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────
BASE        = r"D:\MODELO DE PREDICCION\Codigo"
CSV_FILE    = "JPN.csv"
OUTPUT_HTML = os.path.join(BASE, "backtest_report.html")
OUTPUT_CSV  = os.path.join(BASE, "backtest_results.csv")

# Años de entrenamiento inicial y test
TRAIN_UNTIL = 2022   # entrena con datos hasta este año (inclusive)
TEST_FROM   = 2023   # testea desde este año
XI          = 0.006    # time decay más agresivo — más peso a datos recientes
MIN_TRAIN   = 500    # mínimo partidos para entrenar
N_SIM       = 50_000 # simulaciones MC (50k para velocidad en backtest)
VALUE_THRESH = 0.06  # umbral de value bet subido a 6%

# ─────────────────────────────────────────────────────────────
# BLOQUE 1: CARGA DE DATOS
# ─────────────────────────────────────────────────────────────
def load_csv(path):
    df = pd.read_csv(path, encoding='utf-8-sig', on_bad_lines='skip', low_memory=False)

    rename = {}
    for c in df.columns:
        cl = c.strip().lower()
        if   cl == 'home':     rename[c] = 'home_team'
        elif cl == 'away':     rename[c] = 'away_team'
        elif cl == 'hg':       rename[c] = 'home_goals'
        elif cl == 'ag':       rename[c] = 'away_goals'
        elif cl == 'res':      rename[c] = 'result'
        elif cl == 'psch':     rename[c] = 'ps_home'
        elif cl == 'pscd':     rename[c] = 'ps_draw'
        elif cl == 'psca':     rename[c] = 'ps_away'
        elif cl == 'date':     rename[c] = 'date_raw'
    df.rename(columns=rename, inplace=True)

    required = ['home_team','away_team','home_goals','away_goals','date_raw']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}")

    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df.dropna(subset=['home_goals','away_goals'], inplace=True)
    df['home_goals'] = df['home_goals'].astype(int)
    df['away_goals'] = df['away_goals'].astype(int)

    # Parseo de fecha robusto
    best = None
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y']:
        parsed = pd.to_datetime(df['date_raw'], format=fmt, errors='coerce')
        if best is None or parsed.notna().sum() > best.notna().sum():
            best = parsed
    df['match_date'] = pd.to_datetime(best, errors='coerce')
    df.dropna(subset=['match_date'], inplace=True)
    df['year'] = df['match_date'].dt.year

    # Cuotas Pinnacle (numéricas)
    for col in ['ps_home','ps_draw','ps_away']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            df[col] = np.nan

    df = df.sort_values('match_date').reset_index(drop=True)
    print(f"  ✓ {len(df)} partidos cargados ({df['year'].min()}–{df['year'].max()})")
    print(f"  ✓ Partidos con cuotas Pinnacle: {df['ps_home'].notna().sum()}")
    return df

# ─────────────────────────────────────────────────────────────
# BLOQUE 2: DIXON-COLES
# ─────────────────────────────────────────────────────────────
def rho_correction(hg, ag, lam, mu, rho):
    if   hg == 0 and ag == 0: return max(1e-10, 1 - lam * mu * rho)
    elif hg == 0 and ag == 1: return max(1e-10, 1 + lam * rho)
    elif hg == 1 and ag == 0: return max(1e-10, 1 + mu  * rho)
    elif hg == 1 and ag == 1: return max(1e-10, 1 - rho)
    return 1.0

def dc_log_likelihood(params, df, teams, xi):
    n   = len(teams)
    atk = params[:n]
    dfc = params[n:2*n]
    rho = params[2*n]
    gam = params[2*n+1]

    hidx = np.array([teams.index(t) for t in df['home_team']])
    aidx = np.array([teams.index(t) for t in df['away_team']])

    lam = np.exp(atk[hidx] + dfc[aidx] + gam)
    mu  = np.exp(atk[aidx] + dfc[hidx])

    hg = df['home_goals'].values
    ag = df['away_goals'].values
    w  = np.exp(-xi * df['time_diff_days'].values)

    rc = np.array([rho_correction(h,a,l,m,rho) for h,a,l,m in zip(hg,ag,lam,mu)])
    ll = w * (poisson.logpmf(hg,lam) + poisson.logpmf(ag,mu) + np.log(rc))
    return -np.sum(ll)

def fit_dixon_coles(df_train, xi=XI):
    ref   = df_train['match_date'].max()
    df_t  = df_train.copy()
    df_t['time_diff_days'] = (ref - df_t['match_date']).dt.days

    teams = sorted(set(df_t['home_team']) | set(df_t['away_team']))
    n     = len(teams)
    x0    = np.zeros(2*n+2)
    x0[2*n+1] = 0.1
    bounds = [(-3,3)]*n + [(-3,3)]*n + [(-0.99,0.99)] + [(0,2)]

    res = minimize(
        dc_log_likelihood, x0,
        args=(df_t, teams, xi),
        method='SLSQP', bounds=bounds,
        options={'maxiter':500,'ftol':1e-6}
    )
    return {
        'attack':  dict(zip(teams, res.x[:n])),
        'defence': dict(zip(teams, res.x[n:2*n])),
        'rho':     res.x[2*n],
        'gamma':   res.x[2*n+1],
        'teams':   teams,
        'success': res.success
    }

def predict_match(home, away, params, n_sim=N_SIM):
    atk   = params['attack']
    dfc   = params['defence']
    rho   = params['rho']
    gamma = params['gamma']

    avg_a = np.mean(list(atk.values()))
    avg_d = np.mean(list(dfc.values()))

    lam_h = np.exp(atk.get(home, avg_a) + dfc.get(away, avg_d) + gamma)
    lam_a = np.exp(atk.get(away, avg_a) + dfc.get(home, avg_d))

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
    n = max(len(hg), 1)

    return {
        'p_home': np.sum(hg > ag) / n,
        'p_draw': np.sum(hg == ag) / n,
        'p_away': np.sum(ag > hg) / n,
        'lam_h': lam_h, 'lam_a': lam_a
    }

# ─────────────────────────────────────────────────────────────
# BLOQUE 3: BACKTEST WALK-FORWARD
# ─────────────────────────────────────────────────────────────
def run_backtest(df):
    test_df = df[df['year'] >= TEST_FROM].reset_index(drop=True)
    print(f"\n  📋 Partidos de test ({TEST_FROM}+): {len(test_df)}")
    print(f"  📋 Con cuotas Pinnacle: {test_df['ps_home'].notna().sum()}")

    results = []
    # Cache del modelo: re-entrenamos mensualmente para velocidad
    last_trained_month = None
    params = None

    total = len(test_df)
    for i, row in test_df.iterrows():
        pct = (i+1) / total * 100
        if (i+1) % 50 == 0 or i == 0:
            print(f"  ⏳ Progreso: {i+1}/{total} ({pct:.0f}%)...", end='\r')

        match_date = row['match_date']
        month_key  = (match_date.year, match_date.month)

        # Re-entrenar al inicio de cada mes
        if month_key != last_trained_month:
            train_data = df[df['match_date'] < match_date].copy()
            if len(train_data) < MIN_TRAIN:
                continue
            params = fit_dixon_coles(train_data)
            last_trained_month = month_key

        if params is None:
            continue

        pred = predict_match(row['home_team'], row['away_team'], params)

        # Resultado real
        actual = row.get('result', '')
        if pd.isna(actual) or actual == '':
            hg = row['home_goals']
            ag = row['away_goals']
            actual = 'H' if hg > ag else ('A' if ag > hg else 'D')

        ps_h = row['ps_home']
        ps_d = row['ps_draw']
        ps_a = row['ps_away']
        has_pinnacle = not (pd.isna(ps_h) or pd.isna(ps_d) or pd.isna(ps_a))

        # Value vs Pinnacle
        value_home = value_draw = value_away = np.nan
        if has_pinnacle:
            value_home = pred['p_home'] - (1/ps_h)
            value_draw = pred['p_draw'] - (1/ps_d)
            value_away = pred['p_away'] - (1/ps_a)

        # Brier Score (modelo)
        ind_h = 1 if actual == 'H' else 0
        ind_d = 1 if actual == 'D' else 0
        ind_a = 1 if actual == 'A' else 0
        brier = (pred['p_home']-ind_h)**2 + (pred['p_draw']-ind_d)**2 + (pred['p_away']-ind_a)**2

        # Brier Score (Pinnacle — benchmark)
        brier_ps = np.nan
        if has_pinnacle:
            # Normalizar cuotas Pinnacle a probabilidades
            margin = 1/ps_h + 1/ps_d + 1/ps_a
            pp_h = (1/ps_h) / margin
            pp_d = (1/ps_d) / margin
            pp_a = (1/ps_a) / margin
            brier_ps = (pp_h-ind_h)**2 + (pp_d-ind_d)**2 + (pp_a-ind_a)**2

        results.append({
            'date':       match_date.strftime('%Y-%m-%d'),
            'year':       match_date.year,
            'home':       row['home_team'],
            'away':       row['away_team'],
            'hg':         row['home_goals'],
            'ag':         row['away_goals'],
            'result':     actual,
            'p_home':     round(pred['p_home'],4),
            'p_draw':     round(pred['p_draw'],4),
            'p_away':     round(pred['p_away'],4),
            'lam_h':      round(pred['lam_h'],3),
            'lam_a':      round(pred['lam_a'],3),
            'ps_home':    ps_h,
            'ps_draw':    ps_d,
            'ps_away':    ps_a,
            'value_home': round(value_home,4) if not np.isnan(value_home) else np.nan,
            'value_draw': round(value_draw,4) if not np.isnan(value_draw) else np.nan,
            'value_away': round(value_away,4) if not np.isnan(value_away) else np.nan,
            'brier':      round(brier,4),
            'brier_ps':   round(brier_ps,4) if not np.isnan(brier_ps) else np.nan,
        })

    print(f"\n  ✓ Backtest completo: {len(results)} partidos analizados")
    return pd.DataFrame(results)

# ─────────────────────────────────────────────────────────────
# BLOQUE 4: MÉTRICAS
# ─────────────────────────────────────────────────────────────
def compute_metrics(res):
    r = res.copy()
    m = {}

    # — Brier Score —
    m['brier_model']    = r['brier'].mean()
    m['brier_pinnacle'] = r['brier_ps'].dropna().mean()
    m['brier_diff']     = m['brier_pinnacle'] - m['brier_model']  # positivo = modelo mejor

    # — Value bets simuladas (flat stake 1u) —
    rp = r[r['ps_home'].notna()].copy()
    if len(rp) == 0:
        m['n_with_pinnacle'] = 0
        return m

    m['n_with_pinnacle'] = len(rp)

    for outcome, prob_col, odd_col, result_val in [
        ('home', 'p_home', 'ps_home', 'H'),
        ('draw', 'p_draw', 'ps_draw', 'D'),
        ('away', 'p_away', 'ps_away', 'A'),
    ]:
        val_col = f'value_{outcome}'
        vb = rp[rp[val_col] > VALUE_THRESH].copy()
        if len(vb) == 0:
            m[f'n_vb_{outcome}']  = 0
            m[f'roi_{outcome}']   = np.nan
            m[f'win_{outcome}']   = np.nan
            continue

        won  = (vb['result'] == result_val)
        pnl  = np.where(won, vb[odd_col] - 1, -1)
        roi  = pnl.sum() / len(vb)
        m[f'n_vb_{outcome}']   = len(vb)
        m[f'roi_{outcome}']    = round(roi, 4)
        m[f'win_{outcome}']    = round(won.mean(), 4)
        m[f'avg_odd_{outcome}']= round(vb[odd_col].mean(), 2)
        m[f'avg_val_{outcome}']= round(vb[val_col].mean()*100, 2)

    # Total value bets combinadas
    all_vb_roi = []
    for o in ['home','draw','away']:
        if m.get(f'n_vb_{o}', 0) > 0 and not np.isnan(m.get(f'roi_{o}', np.nan)):
            all_vb_roi.append((m[f'n_vb_{o}'], m[f'roi_{o}']))
    if all_vb_roi:
        total_bets = sum(n for n,_ in all_vb_roi)
        m['roi_total'] = sum(n*r for n,r in all_vb_roi) / total_bets
        m['n_vb_total'] = total_bets
    else:
        m['roi_total'] = np.nan
        m['n_vb_total'] = 0

    # — Calibración —
    bins = np.linspace(0, 1, 11)
    cal = {'prob_center':[], 'freq_home':[], 'freq_draw':[], 'freq_away':[], 'count':[]}
    for lo, hi in zip(bins[:-1], bins[1:]):
        mid = (lo+hi)/2
        mask = (rp['p_home'] >= lo) & (rp['p_home'] < hi)
        sub  = rp[mask]
        if len(sub) >= 5:
            cal['prob_center'].append(round(mid,2))
            cal['freq_home'].append(round((sub['result']=='H').mean(),3))
            cal['freq_draw'].append(round((sub['result']=='D').mean(),3))
            cal['freq_away'].append(round((sub['result']=='A').mean(),3))
            cal['count'].append(len(sub))
    m['calibration'] = cal

    # — ROI por año —
    roi_yr = {}
    for yr in sorted(rp['year'].unique()):
        ydf = rp[rp['year']==yr]
        yr_roi = []
        for o, rv, oc in [('home','H','ps_home'),('draw','D','ps_draw'),('away','A','ps_away')]:
            vc = f'value_{o}'
            vb = ydf[ydf[vc] > VALUE_THRESH]
            if len(vb) == 0: continue
            won = vb['result'] == rv
            pnl = np.where(won, vb[oc]-1, -1)
            yr_roi.append((len(vb), pnl.sum()/len(vb)))
        if yr_roi:
            tot = sum(n for n,_ in yr_roi)
            roi_yr[yr] = round(sum(n*r for n,r in yr_roi)/tot*100, 1)
        else:
            roi_yr[yr] = 0.0
    m['roi_by_year'] = roi_yr

    return m

# ─────────────────────────────────────────────────────────────
# BLOQUE 5: REPORTE HTML
# ─────────────────────────────────────────────────────────────
def generate_html(res, m, output_path):

    def fmt_roi(v):
        if np.isnan(v): return '—'
        color = '#48bb78' if v > 0 else '#fc8181'
        sign  = '+' if v > 0 else ''
        return f'<span style="color:{color};font-weight:600">{sign}{v*100:.1f}%</span>'

    def fmt_brier(v):
        if np.isnan(v): return '—'
        return f'{v:.4f}'

    # Tabla de los últimos 30 partidos de test con value bets
    rp = res[res['ps_home'].notna()].copy()
    value_rows = ""
    shown = 0
    for _, row in rp.sort_values('date', ascending=False).iterrows():
        if shown >= 100: break
        vb_found = False
        cells = ""
        for o, label, prob_col, odd_col, result_val in [
            ('home','1','p_home','ps_home','H'),
            ('draw','X','p_draw','ps_draw','D'),
            ('away','2','p_away','ps_away','A'),
        ]:
            vc  = f'value_{o}'
            val = row[vc]
            odd = row[odd_col]
            prob = row[prob_col]
            if pd.isna(val):
                cells += f'<td>—</td>'
            elif val > VALUE_THRESH:
                won = row['result'] == result_val
                cls = 'vb-win' if won else 'vb-loss'
                pnl = f"+{odd-1:.2f}u" if won else "-1u"
                cells += f'<td class="{cls}">🟢 {label} {val*100:+.1f}% @ {odd:.2f} ({pnl})</td>'
                vb_found = True
            else:
                cells += f'<td class="no-val">{label} {val*100:+.1f}%</td>'

        if vb_found:
            res_cls = {'H':'res-h','D':'res-d','A':'res-a'}.get(row['result'],'')
            value_rows += f"""
            <tr>
              <td>{row['date']}</td>
              <td>{row['home']} vs {row['away']}</td>
              <td>{row['hg']}-{row['ag']}</td>
              <td class="{res_cls}">{row['result']}</td>
              {cells}
            </tr>"""
            shown += 1

    # Gráfico ROI por año (barras inline SVG)
    roi_yr = m.get('roi_by_year', {})
    max_abs = max(abs(v) for v in roi_yr.values()) if roi_yr else 1
    bar_html = ""
    for yr, val in roi_yr.items():
        w   = int(abs(val) / max(max_abs,1) * 200)
        col = '#48bb78' if val >= 0 else '#fc8181'
        sign = '+' if val >= 0 else ''
        bar_html += f"""
        <div class="bar-row">
          <span class="bar-yr">{yr}</span>
          <div class="bar-wrap">
            <div class="bar-fill" style="width:{w}px;background:{col}"></div>
          </div>
          <span class="bar-val" style="color:{col}">{sign}{val:.1f}%</span>
        </div>"""

    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    n_total = len(res)
    n_pin   = m.get('n_with_pinnacle', 0)
    brier_m = m.get('brier_model', np.nan)
    brier_p = m.get('brier_pinnacle', np.nan)
    roi_tot = m.get('roi_total', np.nan)
    n_vb    = m.get('n_vb_total', 0)

    verdict_color = '#48bb78' if (not np.isnan(roi_tot) and roi_tot > 0) else '#fc8181'
    verdict_text  = '✅ EDGE POSITIVO — el modelo gana dinero históricamente' if (not np.isnan(roi_tot) and roi_tot > 0) \
                    else '⚠ SIN EDGE POSITIVO — el modelo necesita ajustes antes de apostar'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Backtest J-League — Pinnacle</title>
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
.card h2{{font-family:'IBM Plex Mono',monospace;font-size:.9rem;color:var(--acc);letter-spacing:2px;margin-bottom:1rem;text-transform:uppercase;}}
.verdict{{background:var(--card);border:2px solid {verdict_color};border-radius:14px;padding:1.5rem;text-align:center;margin-bottom:1.5rem;}}
.verdict p{{font-family:'IBM Plex Mono',monospace;font-size:1.1rem;color:{verdict_color};}}
.metric{{display:flex;justify-content:space-between;align-items:center;padding:.5rem 0;border-bottom:1px solid var(--bord);}}
.metric:last-child{{border-bottom:none;}}
.ml{{color:var(--mut);font-size:.82rem;}}
.mv{{font-family:'IBM Plex Mono',monospace;font-size:1rem;}}
.big-stat{{text-align:center;padding:1rem 0;}}
.big-stat .bs-val{{font-family:'IBM Plex Mono',monospace;font-size:2rem;}}
.big-stat .bs-lbl{{color:var(--mut);font-size:.72rem;text-transform:uppercase;letter-spacing:1.5px;margin-top:.3rem;}}
table{{width:100%;border-collapse:collapse;font-size:.78rem;}}
th{{text-align:left;padding:.5rem .6rem;color:var(--mut);font-size:.68rem;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid var(--bord);}}
td{{padding:.45rem .6rem;border-bottom:1px solid rgba(26,34,53,.6);}}
.vb-win{{color:var(--grn);}}
.vb-loss{{color:var(--red);}}
.no-val{{color:var(--mut);font-size:.72rem;}}
.res-h{{color:var(--acc);font-weight:600;}}
.res-d{{color:var(--ylw);font-weight:600;}}
.res-a{{color:#b794f4;font-weight:600;}}
.bar-row{{display:flex;align-items:center;gap:.7rem;margin-bottom:.5rem;}}
.bar-yr{{font-family:'IBM Plex Mono',monospace;font-size:.8rem;color:var(--mut);width:2.5rem;}}
.bar-wrap{{flex:1;background:rgba(255,255,255,.04);border-radius:4px;height:18px;overflow:hidden;max-width:220px;}}
.bar-fill{{height:100%;border-radius:4px;}}
.bar-val{{font-family:'IBM Plex Mono',monospace;font-size:.8rem;width:4rem;}}
footer{{text-align:center;padding:2rem;color:var(--mut);font-size:.72rem;border-top:1px solid var(--bord);margin-top:2rem;}}
.table-wrap{{overflow-x:auto;}}
</style>
</head>
<body>
<header>
  <h1>📈 BACKTEST J-LEAGUE — PINNACLE</h1>
  <p>Walk-forward · Dixon-Coles · Entrenamiento hasta {TRAIN_UNTIL} · Test desde {TEST_FROM} · Generado {now_str}</p>
</header>
<div class="container">

  <div class="verdict">
    <p>{verdict_text}</p>
  </div>

  <div class="grid3">
    <div class="card">
      <div class="big-stat">
        <div class="bs-val" style="color:{'var(--grn)' if not np.isnan(roi_tot) and roi_tot>0 else 'var(--red)'}">
          {f"+{roi_tot*100:.1f}%" if not np.isnan(roi_tot) and roi_tot>=0 else (f"{roi_tot*100:.1f}%" if not np.isnan(roi_tot) else "N/A")}
        </div>
        <div class="bs-lbl">ROI total value bets</div>
      </div>
    </div>
    <div class="card">
      <div class="big-stat">
        <div class="bs-val" style="color:var(--acc)">{n_vb}</div>
        <div class="bs-lbl">Value bets detectadas (>{VALUE_THRESH*100:.0f}%)</div>
      </div>
    </div>
    <div class="card">
      <div class="big-stat">
        <div class="bs-val" style="color:var(--ylw)">{n_total}</div>
        <div class="bs-lbl">Partidos totales de test</div>
      </div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>📊 Brier Score (calibración)</h2>
      <div class="metric"><span class="ml">Modelo Dixon-Coles</span><span class="mv">{fmt_brier(brier_m)}</span></div>
      <div class="metric"><span class="ml">Pinnacle (benchmark)</span><span class="mv">{fmt_brier(brier_p)}</span></div>
      <div class="metric">
        <span class="ml">Diferencia (+ = modelo mejor)</span>
        <span class="mv" style="color:{'var(--grn)' if not np.isnan(m.get('brier_diff',np.nan)) and m.get('brier_diff',0)>0 else 'var(--red)'}">
          {f"{m.get('brier_diff',0)*100:+.2f}%" if not np.isnan(m.get('brier_diff',np.nan)) else '—'}
        </span>
      </div>
      <p style="color:var(--mut);font-size:.72rem;margin-top:.8rem">
        Brier Score mide calibración (menor es mejor). Un buen modelo está por debajo de 0.65.
      </p>
    </div>

    <div class="card">
      <h2>💰 ROI por resultado</h2>
      <div class="metric"><span class="ml">Value bets 1 (local)</span>
        <span class="mv">{fmt_roi(m.get('roi_home',np.nan))} ({m.get('n_vb_home',0)} apuestas)</span></div>
      <div class="metric"><span class="ml">Value bets X (empate)</span>
        <span class="mv">{fmt_roi(m.get('roi_draw',np.nan))} ({m.get('n_vb_draw',0)} apuestas)</span></div>
      <div class="metric"><span class="ml">Value bets 2 (visitante)</span>
        <span class="mv">{fmt_roi(m.get('roi_away',np.nan))} ({m.get('n_vb_away',0)} apuestas)</span></div>
      <div class="metric" style="margin-top:.5rem"><span class="ml"><strong>Cobertura Pinnacle</strong></span>
        <span class="mv" style="color:var(--acc)">{n_pin} / {n_total} partidos</span></div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>📅 ROI por temporada</h2>
      {bar_html if bar_html else '<p style="color:var(--mut)">Sin datos suficientes</p>'}
    </div>

    <div class="card">
      <h2>🎯 Resumen por mercado</h2>
      <table>
        <thead><tr><th>Mercado</th><th>Apuestas</th><th>Win%</th><th>Odd media</th><th>Value medio</th><th>ROI</th></tr></thead>
        <tbody>
          <tr>
            <td>1 (local)</td>
            <td>{m.get('n_vb_home',0)}</td>
            <td>{f"{m.get('win_home',0)*100:.1f}%" if m.get('n_vb_home',0)>0 else '—'}</td>
            <td>{m.get('avg_odd_home','—')}</td>
            <td>{f"+{m.get('avg_val_home',0):.1f}%" if m.get('n_vb_home',0)>0 else '—'}</td>
            <td>{fmt_roi(m.get('roi_home',np.nan))}</td>
          </tr>
          <tr>
            <td>X (empate)</td>
            <td>{m.get('n_vb_draw',0)}</td>
            <td>{f"{m.get('win_draw',0)*100:.1f}%" if m.get('n_vb_draw',0)>0 else '—'}</td>
            <td>{m.get('avg_odd_draw','—')}</td>
            <td>{f"+{m.get('avg_val_draw',0):.1f}%" if m.get('n_vb_draw',0)>0 else '—'}</td>
            <td>{fmt_roi(m.get('roi_draw',np.nan))}</td>
          </tr>
          <tr>
            <td>2 (visitante)</td>
            <td>{m.get('n_vb_away',0)}</td>
            <td>{f"{m.get('win_away',0)*100:.1f}%" if m.get('n_vb_away',0)>0 else '—'}</td>
            <td>{m.get('avg_odd_away','—')}</td>
            <td>{f"+{m.get('avg_val_away',0):.1f}%" if m.get('n_vb_away',0)>0 else '—'}</td>
            <td>{fmt_roi(m.get('roi_away',np.nan))}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="card" style="margin-bottom:1.5rem">
    <h2>🟢 Partidos con value bets detectadas (últimas 100)</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Fecha</th><th>Partido</th><th>Resultado</th><th>Res</th>
            <th>1 (local)</th><th>X (empate)</th><th>2 (visit)</th>
          </tr>
        </thead>
        <tbody>
          {value_rows if value_rows else '<tr><td colspan="7" style="text-align:center;color:var(--mut);padding:2rem">Sin value bets en los datos de test</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

</div>
<footer>Backtest estadístico. No garantiza resultados futuros. Apuesta con responsabilidad.</footer>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ Reporte HTML: {output_path}")

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("  BACKTEST WALK-FORWARD — Dixon-Coles + Pinnacle")
    print("=" * 60)

    csv_path = os.path.join(BASE, CSV_FILE)
    if not os.path.exists(csv_path):
        print(f"❌ No encontrado: {csv_path}")
        sys.exit(1)

    print(f"\n📂 Cargando {CSV_FILE}...")
    df = load_csv(csv_path)

    print(f"\n⏳ Ejecutando backtest walk-forward...")
    print(f"   Entrenamiento inicial: hasta {TRAIN_UNTIL}")
    print(f"   Período de test:       {TEST_FROM} en adelante")
    print(f"   Re-entrena: 1x por mes | Simulaciones MC: {N_SIM:,}")
    print(f"   Umbral value bet: >{VALUE_THRESH*100:.0f}%\n")

    res = run_backtest(df)

    if len(res) == 0:
        print("❌ Sin resultados. Verifica que el CSV tiene datos del año de test.")
        sys.exit(1)

    # Guardar CSV de resultados
    res.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"✅ Resultados CSV: {OUTPUT_CSV}")

    print("\n📊 Calculando métricas...")
    m = compute_metrics(res)

    # Imprimir resumen en consola
    print("\n" + "=" * 60)
    print("  RESUMEN DE RESULTADOS")
    print("=" * 60)
    print(f"  Partidos de test:          {len(res)}")
    print(f"  Con cuotas Pinnacle:       {m.get('n_with_pinnacle',0)}")
    print(f"  Value bets detectadas:     {m.get('n_vb_total',0)}")
    roi = m.get('roi_total', np.nan)
    if not np.isnan(roi):
        sign = '+' if roi >= 0 else ''
        print(f"  ROI total value bets:      {sign}{roi*100:.1f}%")
    print(f"\n  Brier Score modelo:        {m.get('brier_model',0):.4f}")
    print(f"  Brier Score Pinnacle:      {m.get('brier_pinnacle',0):.4f}")
    bd = m.get('brier_diff', 0)
    print(f"  Diferencia Brier:          {bd*100:+.3f}% ({'modelo mejor' if bd>0 else 'Pinnacle mejor'})")

    print(f"\n  ROI por mercado:")
    for o in ['home','draw','away']:
        r   = m.get(f'roi_{o}', np.nan)
        n   = m.get(f'n_vb_{o}', 0)
        lbl = {'home':'1 (local)','draw':'X (empate)','away':'2 (visit)'}[o]
        if not np.isnan(r):
            sign = '+' if r >= 0 else ''
            print(f"    {lbl:<15} {sign}{r*100:.1f}%  ({n} apuestas)")

    print(f"\n  ROI por año:")
    for yr, r in m.get('roi_by_year', {}).items():
        sign = '+' if r >= 0 else ''
        bar  = '█' * min(int(abs(r)/2), 20)
        print(f"    {yr}: {sign}{r:.1f}%  {bar}")

    if not np.isnan(roi) and roi > 0:
        print("\n  ✅ VEREDICTO: El modelo tiene EDGE POSITIVO sobre Pinnacle.")
        print("     Puedes apostar con confianza en las value bets detectadas.")
    else:
        print("\n  ⚠  VEREDICTO: Edge negativo o neutro sobre Pinnacle.")
        print("     Aplica las mejoras (forma reciente, filtros) antes de apostar.")

    print("\n⏳ Generando reporte HTML...")
    generate_html(res, m, OUTPUT_HTML)
    print("=" * 60)
