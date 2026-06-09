"""
estadisticas_dataset.py — Cuántos partidos tenemos por selección
================================================================
Muestra para cada una de las 48 selecciones del Mundial 2026:
  - Total de partidos en la base completa
  - Desglose por período (2010-2022, 2023-2024, 2025-2026)
  - Último partido registrado
  - Alerta si tiene menos de 20 partidos desde 2020

Uso:
    python Scripts/utilidades/estadisticas_dataset.py
"""

import pandas as pd
import os
import sys

config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Config'))
if config_dir not in sys.path:
    sys.path.insert(0, config_dir)
from config import PATCH_2026_CSV, PARTIDOS_CONV_CSV, INTL_DIR

MASTER_CSV = os.path.join(INTL_DIR, 'base_datos_maestra.csv')

# 48 selecciones del Mundial 2026
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


def cargar_datos():
    dfs = []
    for ruta in [MASTER_CSV, PARTIDOS_CONV_CSV, PATCH_2026_CSV]:
        if os.path.exists(ruta):
            df = pd.read_csv(ruta, encoding='utf-8-sig', low_memory=False)
            df.columns = [c.strip().lower() for c in df.columns]
            for old, new in [('home_score','home_goals'),('away_score','away_goals')]:
                if old in df.columns: df.rename(columns={old:new}, inplace=True)
            dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df = df.drop_duplicates(subset=['date','home_team','away_team'], keep='last')
    df = df.sort_values('date').reset_index(drop=True)
    df['year'] = df['date'].dt.year
    return df


def stats_equipo(df, equipo):
    mask = (df['home_team']==equipo) | (df['away_team']==equipo)
    sub  = df[mask]
    if len(sub) == 0:
        return None

    total    = len(sub)
    desde_2020 = len(sub[sub['year'] >= 2020])
    desde_2023 = len(sub[sub['year'] >= 2023])
    desde_2025 = len(sub[sub['year'] >= 2025])
    ultimo   = sub['date'].max().strftime('%Y-%m-%d')
    ultimo_rival = sub[sub['date'] == sub['date'].max()].iloc[0]
    rival = (ultimo_rival['away_team'] if ultimo_rival['home_team']==equipo
             else ultimo_rival['home_team'])

    # Goles
    gf_col = 'home_goals' if 'home_goals' in sub.columns else 'home_score'
    ga_col = 'away_goals' if 'away_goals' in sub.columns else 'away_score'

    alerta = '⚠️' if desde_2020 < 20 else '✅'

    return {
        'equipo':      equipo,
        'total':       total,
        'desde_2020':  desde_2020,
        'desde_2023':  desde_2023,
        'desde_2025':  desde_2025,
        'ultimo':      ultimo,
        'rival':       rival[:18],
        'alerta':      alerta,
    }


def main():
    print("=" * 80)
    print("  ESTADÍSTICAS DE DATOS — 48 Selecciones del Mundial 2026")
    print("  Cuántos partidos tenemos de cada equipo en nuestra base de datos")
    print("=" * 80)

    df = cargar_datos()
    print(f"\n  Base total: {len(df):,} partidos | {df['year'].min()}-{df['year'].max()}\n")

    # Cabecera
    print(f"  {'Grupo':<6} {'Selección':<25} {'Total':>6} {'≥2020':>6} {'≥2023':>6} {'≥2025':>6} {'Último partido':<12} {'vs':<20} {'OK'}")
    print(f"  {'-'*6} {'-'*25} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*12} {'-'*20} {'-'*3}")

    alertas = []
    for grupo, equipos in GRUPOS.items():
        for equipo in equipos:
            s = stats_equipo(df, equipo)
            if s is None:
                print(f"  {'G'+grupo:<6} {equipo:<25} {'SIN DATOS':>6}")
                alertas.append(equipo)
                continue
            print(f"  {'G'+grupo:<6} {s['equipo']:<25} "
                  f"{s['total']:>6,} "
                  f"{s['desde_2020']:>6} "
                  f"{s['desde_2023']:>6} "
                  f"{s['desde_2025']:>6} "
                  f"{s['ultimo']:<12} "
                  f"vs {s['rival']:<18} "
                  f"{s['alerta']}")
            if s['alerta'] == '⚠️':
                alertas.append(equipo)
        print()

    print(f"\n{'='*80}")
    if alertas:
        print(f"  ⚠️  Equipos con pocos datos (< 20 partidos desde 2020):")
        for e in alertas:
            print(f"     → {e}")
        print(f"\n  Estos equipos usan el Ranking FIFA como prior adicional.")
    else:
        print(f"  ✅ Todos los equipos tienen datos suficientes (≥ 20 partidos desde 2020)")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
