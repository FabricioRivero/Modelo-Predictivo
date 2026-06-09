"""
construir_dataset.py — Construye el dataset maestro limpio
============================================================
Une las 3 fuentes de datos, limpia y exporta un CSV único
listo para usar en el modelo Dixon-Coles.

Fuentes:
  1. results.csv              ← Kaggle martj42 (1872-2026)
  2. partidos_convertidos.csv ← Scraper soccerway (jun 2025-hoy)
  3. results_2026_patch.csv   ← Parche manual

Output:
  Datos/internacional/base_datos_limpia.csv ← Dataset maestro

Uso:
    python Scripts/utilidades/construir_dataset.py
"""

import pandas as pd
import os
import sys

# ── Configuración ─────────────────────────────────────────────
config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Config'))
if config_dir not in sys.path:
    sys.path.insert(0, config_dir)
from config import RESULTS_CSV, PATCH_2026_CSV, PARTIDOS_CONV_CSV, INTL_DIR

OUTPUT_CSV = os.path.join(INTL_DIR, 'base_datos_limpia.csv')

# Palabras que indican selecciones NO mayores masculinas
PALABRAS_EXCLUIR = [
    'U17', 'U20', 'U21', 'U23', 'U15', 'U16', 'U18', 'U19',
    'Sub-17', 'Sub-20', 'Sub-21', 'Sub-23',
    'Women', 'Femenino', 'Femenina', 'Female',
    'Olympic', 'Olympics',
    'B team', 'B-team', 'Reserva',
    # Equipos de clubes que se coló el scraper
    'Lecce', 'Udinese', 'Metalist', 'Urartu', 'Zanzíbar',
]


def cargar_fuentes():
    fuentes = {}
    for nombre, ruta in [
        ('Kaggle (results.csv)',                RESULTS_CSV),
        ('Scraper (partidos_convertidos.csv)',  PARTIDOS_CONV_CSV),
        ('Parche manual (results_2026_patch)',  PATCH_2026_CSV),
    ]:
        if os.path.exists(ruta):
            df = pd.read_csv(ruta, encoding='utf-8-sig', low_memory=False)
            fuentes[nombre] = df
            print(f"  ✓ {nombre}: {len(df):,} partidos")
        else:
            print(f"  ⚠ No encontrado: {ruta}")
    return fuentes


def normalizar(df):
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    renames = {}
    for c in df.columns:
        if c == 'home_score': renames[c] = 'home_goals'
        if c == 'away_score': renames[c] = 'away_goals'
    df.rename(columns=renames, inplace=True)
    for col in ['home_goals', 'away_goals', 'tournament', 'neutral']:
        if col not in df.columns:
            df[col] = None
    for col in ['home_team', 'away_team']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


def limpiar(df):
    n_inicial = len(df)

    # 1. Fechas
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    print(f"  Después de parsear fechas:     {len(df):,}")

    # 2. Filtrar no-mayores masculinos
    patron = '|'.join(PALABRAS_EXCLUIR)
    mask_home  = df['home_team'].str.contains(patron, case=False, na=False)
    mask_away  = df['away_team'].str.contains(patron, case=False, na=False)
    mask_tourn = df['tournament'].astype(str).str.contains(patron, case=False, na=False)
    df = df[~(mask_home | mask_away | mask_tourn)]
    print(f"  Después de filtrar no-mayores: {len(df):,}")

    # 3. Goles válidos
    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df = df.dropna(subset=['home_goals', 'away_goals'])
    df = df[(df['home_goals'] >= 0) & (df['away_goals'] >= 0)]
    df = df[(df['home_goals'] <= 30) & (df['away_goals'] <= 30)]
    print(f"  Después de validar goles:      {len(df):,}")

    # 4. Deduplicar — patch al final = tiene prioridad
    df = df.sort_values('date')
    df = df.drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
    df = df.reset_index(drop=True)
    print(f"  Después de deduplicar:         {len(df):,}")
    print(f"\n  Eliminados en total: {n_inicial - len(df):,}")
    return df


def estadisticas(df):
    print(f"\n{'='*60}")
    print(f"  ESTADÍSTICAS DEL DATASET FINAL")
    print(f"{'='*60}")
    print(f"  Total partidos:     {len(df):,}")
    print(f"  Rango fechas:       {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"  Selecciones únicas: {pd.concat([df['home_team'], df['away_team']]).nunique()}")
    df['year'] = df['date'].dt.year
    print(f"\n  Por período:")
    for periodo, desde, hasta in [
        ('Antes 2010', 1872, 2009),
        ('2010-2018',  2010, 2018),
        ('2019-2022',  2019, 2022),
        ('2023-2024',  2023, 2024),
        ('2025-2026',  2025, 2026),
    ]:
        n = len(df[(df['year'] >= desde) & (df['year'] <= hasta)])
        print(f"    {periodo:<15} {n:>6,} partidos")
    print(f"\n  Top 8 torneos:")
    for tourn, count in df['tournament'].value_counts().head(8).items():
        print(f"    {str(tourn):<35} {count:>5,}")


def main():
    print("=" * 60)
    print("  CONSTRUIR DATASET MAESTRO")
    print("  Fuentes: Kaggle + Scraper + Parche manual")
    print("=" * 60)

    print(f"\n📂 Cargando fuentes...")
    fuentes = cargar_fuentes()
    if not fuentes:
        print("❌ Sin fuentes.")
        return

    print(f"\n🔧 Normalizando...")
    dfs = [normalizar(df) for df in fuentes.values()]
    df_total = pd.concat(dfs, ignore_index=True)
    print(f"  Total antes de limpiar: {len(df_total):,}")

    print(f"\n🧹 Limpiando...")
    df_clean = limpiar(df_total)

    estadisticas(df_clean)

    df_clean.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"\n✅ Dataset guardado en: {OUTPUT_CSV}")
    print(f"   {len(df_clean):,} partidos listos para el modelo")


if __name__ == '__main__':
    main()
