"""
check_ligas.py — Partidos 2018-2026 por año y último partido de las 48 selecciones del Mundial
================================================================================================
Muestra por cada selección:
  - Total partidos 2018-2026
  - Desglose por año (2018, 2019, ..., 2026)
  - Último partido jugado con resultado

Uso:
    python Scripts/utilidades/check_ligas.py
"""

import pandas as pd
import os
import sys

config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Config'))
if config_dir not in sys.path:
    sys.path.insert(0, config_dir)
from config import PATCH_2026_CSV, PARTIDOS_CONV_CSV, INTL_DIR

MASTER_CSV = os.path.join(INTL_DIR, 'base_datos_maestra.csv')
ANOS = list(range(2018, 2027))

GRUPOS = {
    'A': ['Mexico',        'South Africa',          'South Korea',  'Czech Republic'],
    'B': ['Canada',        'Bosnia and Herzegovina', 'Qatar',        'Switzerland'],
    'C': ['Brazil',        'Morocco',               'Haiti',        'Scotland'],
    'D': ['United States', 'Paraguay',              'Australia',    'Turkey'],
    'E': ['Germany',       'Curaçao',               'Ivory Coast',  'Ecuador'],
    'F': ['Netherlands',   'Japan',                 'Sweden',       'Tunisia'],
    'G': ['Belgium',       'Egypt',                 'Iran',         'New Zealand'],
    'H': ['Spain',         'Cape Verde',            'Saudi Arabia', 'Uruguay'],
    'I': ['France',        'Senegal',               'Iraq',         'Norway'],
    'J': ['Argentina',     'Algeria',               'Austria',      'Jordan'],
    'K': ['Portugal',      'DR Congo',              'Uzbekistan',   'Colombia'],
    'L': ['England',       'Croatia',               'Ghana',        'Panama'],
}


def cargar_datos():
    dfs = []
    for ruta in [MASTER_CSV, PARTIDOS_CONV_CSV, PATCH_2026_CSV]:
        if os.path.exists(ruta):
            df = pd.read_csv(ruta, encoding='utf-8-sig', low_memory=False)
            df.columns = [c.strip().lower() for c in df.columns]
            for old, new in [('home_score', 'home_goals'), ('away_score', 'away_goals')]:
                if old in df.columns:
                    df.rename(columns={old: new}, inplace=True)
            dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df = df.drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
    df = df[df['date'] >= '2018-01-01']
    df = df[df['date'] <= '2026-06-09']
    df = df.sort_values('date').reset_index(drop=True)
    df['year'] = df['date'].dt.year
    return df


def buscar_equipo(df, equipo):
    """Busca partidos de un equipo con nombre flexible (ignora tildes y mayúsculas)."""
    import unicodedata
    def normalizar(s):
        s = str(s).strip().lower()
        return ''.join(c for c in unicodedata.normalize('NFD', s)
                       if unicodedata.category(c) != 'Mn')
    equipo_norm = normalizar(equipo)
    mask = (df['home_team'].apply(normalizar) == equipo_norm) | \
           (df['away_team'].apply(normalizar) == equipo_norm)
    return df[mask]


def stats_equipo(df, equipo):
    sub = buscar_equipo(df, equipo)
    if len(sub) == 0:
        return None

    por_ano = {}
    for a in ANOS:
        por_ano[a] = len(sub[sub['year'] == a])

    total = len(sub)
    ultimo_row = sub.iloc[-1]
    es_local = ultimo_row['home_team'] == equipo
    rival    = ultimo_row['away_team'] if es_local else ultimo_row['home_team']
    gf_col   = 'home_goals' if 'home_goals' in sub.columns else 'home_score'
    ga_col   = 'away_goals' if 'away_goals' in sub.columns else 'away_score'
    try:
        gf = int(ultimo_row[gf_col]) if es_local else int(ultimo_row[ga_col])
        ga = int(ultimo_row[ga_col]) if es_local else int(ultimo_row[gf_col])
        marcador = f"{gf}-{ga}"
        res = 'W' if gf > ga else ('L' if gf < ga else 'D')
    except Exception:
        marcador = '?-?'
        res = '?'

    tourn  = str(ultimo_row.get('tournament', ''))[:22]
    fecha  = ultimo_row['date'].strftime('%Y-%m-%d')
    icono  = {'W': 'W', 'D': 'D', 'L': 'L'}.get(res, '?')
    alerta = 'BAJO' if total < 20 else ('MED' if total < 35 else 'OK ')

    return {
        'equipo':   equipo,
        'total':    total,
        'por_ano':  por_ano,
        'fecha':    fecha,
        'rival':    rival[:20],
        'marcador': marcador,
        'res':      res,
        'icono':    icono,
        'tourn':    tourn,
        'alerta':   alerta,
    }


def main():
    print("=" * 130)
    print("  PARTIDOS 2018 → 09/06/2026 POR AÑO — 48 Selecciones del Mundial 2026")
    print("=" * 130)

    df = cargar_datos()
    print(f"\n  Base filtrada: {len(df):,} partidos (2018-2026)\n")

    header_anos = ' '.join(f"{a}" for a in ANOS)
    print(f"  {'Gr':<3} {'Seleccion':<25} {'TOT':>4}  {'2018':>4} {'2019':>4} {'2020':>4} {'2021':>4} {'2022':>4} {'2023':>4} {'2024':>4} {'2025':>4} {'2026':>4}  {'Ultimo':>10}  {'vs':<22}  {'Mar':<6} {'Res'}  {'Estado'}")
    sep = "-" * 130
    print(f"  {sep}")

    alertas_bajo = []
    alertas_med  = []

    for grupo, equipos in GRUPOS.items():
        for equipo in equipos:
            s = stats_equipo(df, equipo)
            if s is None:
                print(f"  G{grupo:<2} {equipo:<25}  SIN DATOS")
                alertas_bajo.append(equipo)
                continue

            anos_str = ' '.join(
                f"{s['por_ano'][a]:>4}" for a in ANOS
            )
            print(f"  G{grupo:<2} {s['equipo']:<25} {s['total']:>4}  {anos_str}  "
                  f"{s['fecha']:>10}  {s['rival']:<22}  {s['marcador']:<6} {s['icono']}  {s['alerta']}")

            if s['alerta'] == 'BAJO':
                alertas_bajo.append(equipo)
            elif s['alerta'] == 'MED':
                alertas_med.append(equipo)

        print(f"  {'-'*130}")

    print(f"\n{'='*130}")
    print(f"  RESUMEN — Estado de datos")
    print(f"{'='*130}")
    print(f"  OK   = 35+ partidos 2018-2026  (datos muy confiables)")
    print(f"  MED  = 20-34 partidos          (datos aceptables)")
    print(f"  BAJO = < 20 partidos           (modelo usa ranking FIFA como apoyo)")

    if alertas_bajo:
        print(f"\n  BAJO — Necesitan refuerzo urgente:")
        for e in alertas_bajo:
            s = stats_equipo(df, e)
            n = s['total'] if s else 0
            print(f"    -> {e:<25} {n} partidos")

    if alertas_med:
        print(f"\n  MED — Aceptables pero mejorables:")
        for e in alertas_med:
            s = stats_equipo(df, e)
            n = s['total'] if s else 0
            print(f"    -> {e:<25} {n} partidos")

    if not alertas_bajo and not alertas_med:
        print(f"\n  Todos los equipos tienen 35+ partidos desde 2018")
    print(f"{'='*130}")


if __name__ == '__main__':
    main()
