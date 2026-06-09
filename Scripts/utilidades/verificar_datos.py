"""
verificar_datos.py — Verifica los últimos N partidos de las 48 selecciones del Mundial 2026
=============================================================================================
Muestra: fecha, local, visitante, marcador, W/D/L, torneo y forma reciente.
Combina las 3 fuentes: base_datos_maestra.csv + partidos_convertidos.csv + results_2026_patch.csv

Uso:
    python Scripts/utilidades/verificar_datos.py
"""

import pandas as pd
import os
import sys

# ── Configuración ─────────────────────────────────────────────
config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Config'))
if config_dir not in sys.path:
    sys.path.insert(0, config_dir)
from config import RESULTS_CSV, PATCH_2026_CSV, PARTIDOS_CONV_CSV, INTL_DIR

# Usar dataset maestro si existe, si no usar results.csv
MASTER_CSV = os.path.join(INTL_DIR, 'base_datos_maestra.csv')
if os.path.exists(MASTER_CSV):
    BASE_CSV = MASTER_CSV
else:
    BASE_CSV = RESULTS_CSV

# ══════════════════════════════════════════════════════════════
# 48 SELECCIONES DEL MUNDIAL 2026 — GRUPOS REALES
# ══════════════════════════════════════════════════════════════
GRUPOS = {
    'A': ['Mexico',        'South Africa',          'South Korea',  'Czech Republic'],
    'B': ['Canada',        'Bosnia and Herzegovina', 'Qatar',        'Switzerland'],
    'C': ['Brazil',        'Morocco',               'Haiti',        'Scotland'],
    'D': ['United States', 'Paraguay',              'Australia',    'Turkey'],
    'E': ['Germany',       'Curacao',               'Ivory Coast',  'Ecuador'],
    'F': ['Netherlands',   'Japan',                 'Sweden',       'Tunisia'],
    'G': ['Belgium',       'Egypt',                 'Iran',         'New Zealand'],
    'H': ['Spain',         'Cape Verde',            'Saudi Arabia', 'Uruguay'],
    'I': ['France',        'Senegal',               'Iraq',         'Norway'],
    'J': ['Argentina',     'Algeria',               'Austria',      'Jordan'],
    'K': ['Portugal',      'DR Congo',              'Uzbekistan',   'Colombia'],
    'L': ['England',       'Croatia',               'Ghana',        'Panama'],
}
EQUIPOS = [e for g in GRUPOS.values() for e in g]


def cargar_todos_los_datos():
    fuentes = []
    nombres = []

    # 1. Dataset maestro (base_datos_maestra.csv) — prioridad
    if os.path.exists(BASE_CSV):
        df1 = pd.read_csv(BASE_CSV, encoding='utf-8-sig', low_memory=False)
        fuentes.append(df1)
        nombres.append(f'Dataset maestro ({os.path.basename(BASE_CSV)}) — {len(df1):,}')
    else:
        print(f"⚠ No encontrado: {BASE_CSV}")

    # 2. partidos_convertidos.csv — scraper jun 2025-actualidad
    if os.path.exists(PARTIDOS_CONV_CSV):
        df2 = pd.read_csv(PARTIDOS_CONV_CSV, encoding='utf-8-sig', low_memory=False)
        fuentes.append(df2)
        nombres.append(f'Scraper (partidos_convertidos.csv) — {len(df2):,}')
    else:
        print(f"⚠ No encontrado: {PARTIDOS_CONV_CSV}")

    # 3. results_2026_patch.csv — parche manual (máxima prioridad)
    if os.path.exists(PATCH_2026_CSV):
        df3 = pd.read_csv(PATCH_2026_CSV, encoding='utf-8-sig', low_memory=False)
        fuentes.append(df3)
        nombres.append(f'Parche manual (results_2026_patch.csv) — {len(df3):,}')
    else:
        print(f"⚠ No encontrado: {PATCH_2026_CSV}")

    if not fuentes:
        print("❌ Sin fuentes de datos.")
        sys.exit(1)

    print(f"\n📂 Fuentes cargadas:")
    for n in nombres:
        print(f"   ✓ {n}")

    # Normalizar y combinar
    dfs_norm = []
    for df in fuentes:
        df = df.copy()
        df.columns = [c.strip().lower() for c in df.columns]
        for old, new in [('home_score', 'home_goals'), ('away_score', 'away_goals')]:
            if old in df.columns:
                df.rename(columns={old: new}, inplace=True)
        if 'tournament' not in df.columns:
            df['tournament'] = 'Unknown'
        dfs_norm.append(df)

    df_total = pd.concat(dfs_norm, ignore_index=True)
    df_total['date'] = pd.to_datetime(df_total['date'], errors='coerce')
    df_total = df_total.dropna(subset=['date'])
    df_total = df_total.sort_values('date').reset_index(drop=True)
    df_total = df_total.drop_duplicates(
        subset=['date', 'home_team', 'away_team'], keep='last'
    ).reset_index(drop=True)

    print(f"\n✅ Total combinado: {len(df_total):,} partidos únicos")
    print(f"   Rango: {df_total['date'].min().date()} → {df_total['date'].max().date()}")
    return df_total


def verificar_equipo(df, equipo, n=10):
    mask = (df['home_team'] == equipo) | (df['away_team'] == equipo)
    sub  = df[mask].tail(n).copy()

    if len(sub) == 0:
        print(f"\n  ⚠ '{equipo}' — SIN DATOS")
        return

    resultados = []
    gf_col = 'home_goals' if 'home_goals' in sub.columns else 'home_score'
    ga_col = 'away_goals' if 'away_goals' in sub.columns else 'away_score'

    for _, row in sub.iterrows():
        es_local = row['home_team'] == equipo
        try:
            gf = float(row[gf_col]) if es_local else float(row[ga_col])
            ga = float(row[ga_col]) if es_local else float(row[gf_col])
            if pd.isna(gf) or pd.isna(ga):
                res = '?'
            elif gf > ga:   res = 'W'
            elif gf < ga:   res = 'L'
            else:           res = 'D'
        except Exception:
            res = '?'
        resultados.append(res)

    sub['res'] = resultados
    forma  = ''.join(resultados)
    pts    = sum({'W': 3, 'D': 1, 'L': 0}.get(r, 0) for r in resultados)
    pts_pg = round(pts / max(len(resultados), 1), 2)
    icons  = {'W': '✅', 'D': '➖', 'L': '❌', '?': '❓'}

    print(f"\n{'─'*72}")
    print(f"  {equipo:<22} Forma: {forma}  |  {pts_pg} pts/j  |  últimos {len(sub)} partidos")
    print(f"{'─'*72}")

    for _, row in sub.iterrows():
        fecha    = str(row['date'].date())
        local    = str(row['home_team'])[:22]
        visit    = str(row['away_team'])[:22]
        tourn    = str(row.get('tournament', ''))[:24]
        try:
            marcador = f"{int(row[gf_col])}-{int(row[ga_col])}"
        except Exception:
            marcador = '?-?'
        icon = icons.get(row['res'], '❓')
        print(f"  {fecha}  {local:<23} {marcador:<6} {visit:<23} {icon}  {tourn}")


def main():
    print("=" * 72)
    print("  VERIFICADOR DE DATOS — Mundial 2026")
    print("  48 selecciones · últimos 10 partidos por equipo")
    print("=" * 72)

    df = cargar_todos_los_datos()

    for grupo, equipos in GRUPOS.items():
        print(f"\n\n{'='*72}")
        print(f"  GRUPO {grupo}: {' · '.join(equipos)}")
        print(f"{'='*72}")
        for equipo in equipos:
            verificar_equipo(df, equipo, n=10)

    print(f"\n\n{'='*72}")
    print(f"  ✅ Verificación completada — {len(EQUIPOS)} selecciones")
    print(f"  Si faltan datos, agrega a:")
    print(f"  Datos\\internacional\\results_2026_patch.csv")
    print(f"{'='*72}")


if __name__ == '__main__':
    main()
