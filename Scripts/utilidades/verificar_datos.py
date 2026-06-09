import pandas as pd
import os
import sys

# Añadir la ruta de configuración
config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Config'))
if config_dir not in sys.path:
    sys.path.insert(0, config_dir)
from config import RESULTS_CSV, PATCH_2026_CSV, PARTIDOS_CONV_CSV

# ── Lista de equipos a verificar ──────────────────────────────
# Puedes cambiar esta lista con cualquier selección
EQUIPOS = [
    # Grupo A
    'Mexico', 'South Africa', 'South Korea', 'Czech Republic',
    # Grupo B
    'Canada', 'Bosnia and Herzegovina', 'United States', 'Paraguay',
    # Grupo C
    'Qatar', 'Switzerland', 'Brazil', 'Morocco',
    # Grupo D
    'Haiti', 'Scotland', 'Australia', 'Turkey',
    # Grupo E
    'Germany', 'Ivory Coast', 'Netherlands', 'Japan',
    # Grupo F
    'Spain', 'Cape Verde', 'Belgium', 'Egypt',
    # Grupo G
    'Saudi Arabia', 'Uruguay', 'Iran', 'New Zealand',
    # Grupo H
    'France', 'Senegal', 'Iraq', 'Norway',
    # Grupo I
    'Argentina', 'Algeria', 'Austria', 'Jordan',
    # Grupo J
    'Portugal', 'DR Congo', 'Colombia', 'Uzbekistan',
    # Grupo K
    'England', 'Croatia', 'Ghana', 'Panama',
    # Grupo L
    'Sweden', 'Tunisia', 'Italy', 'Ecuador',
]

def cargar_todos_los_datos():
    """Carga y combina todas las fuentes de datos disponibles."""
    fuentes = []
    nombres = []

    # 1. results.csv — Kaggle (base histórica)
    if os.path.exists(RESULTS_CSV):
        df1 = pd.read_csv(RESULTS_CSV, encoding='utf-8-sig', low_memory=False)
        fuentes.append(df1)
        nombres.append(f'Kaggle (results.csv) — {len(df1)} partidos')
    else:
        print(f"⚠ No encontrado: {RESULTS_CSV}")

    # 2. partidos_convertidos.csv — Scraper soccerway jun 2025-actualidad
    if os.path.exists(PARTIDOS_CONV_CSV):
        df2 = pd.read_csv(PARTIDOS_CONV_CSV, encoding='utf-8-sig', low_memory=False)
        fuentes.append(df2)
        nombres.append(f'Scraper (partidos_convertidos.csv) — {len(df2)} partidos')
    else:
        print(f"⚠ No encontrado: {PARTIDOS_CONV_CSV}")

    # 3. results_2026_patch.csv — Parche manual
    if os.path.exists(PATCH_2026_CSV):
        df3 = pd.read_csv(PATCH_2026_CSV, encoding='utf-8-sig', low_memory=False)
        fuentes.append(df3)
        nombres.append(f'Parche manual (results_2026_patch.csv) — {len(df3)} partidos')
    else:
        print(f"⚠ No encontrado: {PATCH_2026_CSV}")

    if not fuentes:
        print("❌ No se encontró ninguna fuente de datos.")
        sys.exit(1)

    print(f"\n📂 Fuentes cargadas:")
    for n in nombres:
        print(f"   ✓ {n}")

    # Normalizar y combinar
    dfs_norm = []
    for df in fuentes:
        df = df.copy()
        df.columns = [c.strip().lower() for c in df.columns]
        renames = {}
        for c in df.columns:
            if c == 'home_score': renames[c] = 'home_goals'
            if c == 'away_score': renames[c] = 'away_goals'
        df.rename(columns=renames, inplace=True)
        if 'tournament' not in df.columns:
            df['tournament'] = 'Unknown'
        dfs_norm.append(df)

    df_total = pd.concat(dfs_norm, ignore_index=True)
    df_total['date'] = pd.to_datetime(df_total['date'], errors='coerce')
    df_total = df_total.dropna(subset=['date'])
    df_total = df_total.sort_values('date').reset_index(drop=True)

    # Eliminar duplicados (mismo partido en varias fuentes — mantener el más reciente/completo)
    df_total = df_total.drop_duplicates(
        subset=['date', 'home_team', 'away_team'], keep='last'
    ).reset_index(drop=True)

    print(f"\n✅ Total combinado: {len(df_total)} partidos únicos")
    print(f"   Rango: {df_total['date'].min().date()} → {df_total['date'].max().date()}")
    return df_total


def verificar_equipo(df, equipo, n=10):
    """Muestra los últimos N partidos de un equipo con W/D/L."""
    mask = (df['home_team'] == equipo) | (df['away_team'] == equipo)
    sub  = df[mask].tail(n).copy()

    if len(sub) == 0:
        print(f"\n  ⚠ '{equipo}' — SIN DATOS en ninguna fuente")
        return

    # Calcular W/D/L para el equipo
    resultados = []
    for _, row in sub.iterrows():
        es_local = row['home_team'] == equipo
        gf_col = 'home_goals' if 'home_goals' in row.index else 'home_score'
        ga_col = 'away_goals' if 'away_goals' in row.index else 'away_score'
        try:
            gf = float(row[gf_col]) if es_local else float(row[ga_col])
            ga = float(row[ga_col]) if es_local else float(row[gf_col])
            if pd.isna(gf) or pd.isna(ga):
                res = '?'
            elif gf > ga:
                res = 'W'
            elif gf < ga:
                res = 'L'
            else:
                res = 'D'
        except Exception:
            res = '?'
        resultados.append(res)

    sub = sub.copy()
    sub['res'] = resultados

    # Calcular forma
    forma  = ''.join(resultados)
    pts    = sum({'W': 3, 'D': 1, 'L': 0}.get(r, 0) for r in resultados)
    pts_pg = round(pts / max(len(resultados), 1), 2)
    icons  = {'W': '✅', 'D': '➖', 'L': '❌', '?': '❓'}

    print(f"\n{'─'*72}")
    print(f"  {equipo:<22} Forma: {forma}  |  {pts_pg} pts/j  |  últimos {len(sub)} partidos")
    print(f"{'─'*72}")

    gf_col = 'home_goals' if 'home_goals' in sub.columns else 'home_score'
    ga_col = 'away_goals' if 'away_goals' in sub.columns else 'away_score'

    for _, row in sub.iterrows():
        fecha  = str(row['date'].date())
        local  = str(row['home_team'])[:22]
        visit  = str(row['away_team'])[:22]
        tourn  = str(row.get('tournament', ''))[:24]
        try:
            marcador = f"{int(row[gf_col])}-{int(row[ga_col])}"
        except Exception:
            marcador = "?-?"
        icon = icons.get(row['res'], '❓')
        print(f"  {fecha}  {local:<23} {marcador:<6} {visit:<23} {icon}  {tourn}")


def main():
    print("=" * 72)
    print("  VERIFICADOR DE DATOS — Todas las fuentes combinadas")
    print("  Equipos del Mundial 2026 — últimos 10 partidos por selección")
    print("=" * 72)

    df = cargar_todos_los_datos()

    print(f"\n\n{'='*72}")
    print(f"  VERIFICANDO {len(EQUIPOS)} SELECCIONES DEL MUNDIAL 2026")
    print(f"{'='*72}")

    for equipo in EQUIPOS:
        verificar_equipo(df, equipo, n=10)

    print(f"\n\n{'='*72}")
    print(f"  ✅ Verificación completada — {len(EQUIPOS)} selecciones")
    print(f"  Si faltan partidos o hay errores, agrégalos a:")
    print(f"  Datos\\internacional\\results_2026_patch.csv")
    print(f"{'='*72}")


if __name__ == '__main__':
    main()
