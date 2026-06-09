"""
construir_dataset.py — Construye el dataset maestro limpio (ETL completo)
=========================================================================
Proceso ETL de calidad de producción:
  1. Une 4 fuentes de datos
  2. Estandariza nombres de países (español/inglés/variantes → inglés estándar)
  3. Estandariza torneos (Amistosos Internacionales → Friendly, etc.)
  4. Convierte goles a enteros
  5. Limpia nulos en city/country/neutral
  6. Deduplica — parche tiene prioridad
  7. Exporta base_datos_maestra.csv

Fuentes (menor → mayor prioridad):
  1. base_datos_selecciones_limpia2.csv ← Dataset externo (50,314 filas)
  2. results.csv                        ← Kaggle martj42
  3. partidos_convertidos.csv           ← Scraper soccerway
  4. results_2026_patch.csv             ← Parche manual (máxima prioridad)

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

LIMPIA2_CSV = os.path.join(INTL_DIR, 'base_datos_selecciones_limpia2.csv')
OUTPUT_CSV  = os.path.join(INTL_DIR, 'base_datos_maestra.csv')

# ══════════════════════════════════════════════════════════════
# 1. DICCIONARIO DE NOMBRES ESTÁNDAR (todo → inglés estándar)
# ══════════════════════════════════════════════════════════════
NOMBRES_ESTANDAR = {
    # Español → Inglés
    'Alemania':'Germany','España':'Spain','Francia':'France',
    'Italia':'Italy','Países Bajos':'Netherlands','Bélgica':'Belgium',
    'Brasil':'Brazil','México':'Mexico','Japón':'Japan',
    'Corea del Sur':'South Korea','República de Corea':'South Korea',
    'China':'China PR','RP China':'China PR',
    'Irán':'Iran','RI de Irán':'Iran','IR Iran':'Iran',
    'Irak':'Iraq','Turquía':'Turkey','Türkiye':'Turkey',
    'Marruecos':'Morocco','Argelia':'Algeria','Túnez':'Tunisia',
    'Egipto':'Egypt','Camerún':'Cameroon','Sudáfrica':'South Africa',
    'Costa de Marfil':'Ivory Coast',
    "Côte d'Ivoire":'Ivory Coast',"Cote d'Ivoire":'Ivory Coast',
    'RD del Congo':'DR Congo','Congo DR':'DR Congo',
    'Jordania':'Jordan','Baréin':'Bahrain','Bahréin':'Bahrain',
    'Omán':'Oman','Catar':'Qatar','Arabia Saudí':'Saudi Arabia',
    'Arabia Saudita':'Saudi Arabia','Arabia Saudí':'Saudi Arabia',
    'Canadá':'Canada','EE. UU.':'United States','EE.UU.':'United States',
    'EEUU':'United States','Estados Unidos':'United States',
    'Perú':'Peru','Panamá':'Panama','Haití':'Haiti',
    'Nueva Zelanda':'New Zealand','Uzbekistán':'Uzbekistan',
    'Kazajistán':'Kazakhstan','Tayikistán':'Tajikistan',
    'Kirguistán':'Kyrgyzstan','Azerbaiyán':'Azerbaijan',
    'Noruega':'Norway','Suecia':'Sweden','Dinamarca':'Denmark',
    'Suiza':'Switzerland','Croacia':'Croatia','Gales':'Wales',
    'Islandia':'Iceland','Finlandia':'Finland','Polonia':'Poland',
    'Hungría':'Hungary','República Checa':'Czech Republic',
    'Chequia':'Czech Republic','Eslovaquia':'Slovakia',
    'Eslovenia':'Slovenia','Rumanía':'Romania','Rumania':'Romania',
    'Grecia':'Greece','Ucrania':'Ukraine','Rusia':'Russia',
    'Moldavia':'Moldova','Bielorrusia':'Belarus',
    'Bosnia y Herzegovina':'Bosnia and Herzegovina',
    'Bosnia-Herzegovina':'Bosnia and Herzegovina',
    'Bosnia-Herzegobina':'Bosnia and Herzegovina',
    'Macedonia del Norte':'North Macedonia',
    'Surinam':'Suriname','Surinam':'Suriname',
    'Trinidad y Tobago':'Trinidad and Tobago',
    'Palestina':'Palestine','Siria':'Syria',
    'Irlanda del Norte':'Northern Ireland',
    'Irlanda':'Republic of Ireland',
    'Cabo Verde':'Cape Verde','Burkina Faso':'Burkina Faso',
    'Escocia':'Scotland','Portugal':'Portugal',
    'Inglaterra':'England','Argentina':'Argentina',
    'Colombia':'Colombia','Uruguay':'Uruguay',
    'Chile':'Chile','Ecuador':'Ecuador','Paraguay':'Paraguay',
    'Venezuela':'Venezuela','Bolivia':'Bolivia',
    'Costa Rica':'Costa Rica','Honduras':'Honduras',
    'El Salvador':'El Salvador','Guatemala':'Guatemala',
    'Nicaragua':'Nicaragua','Jamaica':'Jamaica',
    'Curazao':'Curacao','Curazao':'Curacao',
    'Luxemburgo':'Luxembourg','Albania':'Albania',
    'Kosovo':'Kosovo','Georgia':'Georgia','Armenia':'Armenia',
    'Montenegro':'Montenegro','Serbia':'Serbia',
    'Bermudas':'Bermuda','Bermuda':'Bermuda',
    'Nigeria':'Nigeria','Ghana':'Ghana','Senegal':'Senegal',
    'Kenia':'Kenya','Uganda':'Uganda','Tanzania':'Tanzania',
    'Zambia':'Zambia','Angola':'Angola','Mozambique':'Mozambique',
    'Zimbabue':'Zimbabwe','Zimbabwe':'Zimbabwe',
    'Namibia':'Namibia','Botsuana':'Botswana',
    'Gabón':'Gabon','Malí':'Mali','Mali':'Mali',
    'Benín':'Benin','Togo':'Togo','Guinea':'Guinea',
    'Sierra Leona':'Sierra Leone','Liberia':'Liberia',
    'Mauritania':'Mauritania','Somalia':'Somalia',
    'Ruanda':'Rwanda','Burundi':'Burundi',
    'República Centroafricana':'Central African Republic',
    'Congo':'Republic of Congo',
    'Libia':'Libya','Sudán':'Sudan','Sudán del Sur':'South Sudan',
    'Etiopía':'Ethiopia','Yibuti':'Djibouti',
    'Filipinas':'Philippines','Birmania':'Myanmar',
    'Tailandia':'Thailand','Vietnam':'Vietnam',
    'Camboya':'Cambodia','Laos':'Laos',
    'Singapur':'Singapore','Indonesia':'Indonesia',
    'Malaui':'Malawi','Eswatini':'Eswatini',
    'Lesoto':'Lesotho','Guinea Ecuatorial':'Equatorial Guinea',
    # Variantes inglés → estándar
    'Korea Republic':'South Korea','Republic of Korea':'South Korea',
    'USA':'United States','US':'United States',
    'Czechia':'Czech Republic','Bosnia & Herzegovina':'Bosnia and Herzegovina',
    'Cape Verde Islands':'Cape Verde','Cape Verde Isl.':'Cape Verde',
    'Ivory Coast':"Ivory Coast','Cote d'Ivoire":'Ivory Coast',
    'Trinidad & Tobago':'Trinidad and Tobago',
    'Curacao':'Curacao',
}

# ══════════════════════════════════════════════════════════════
# 2. ESTANDARIZACIÓN DE TORNEOS
# ══════════════════════════════════════════════════════════════
TORNEO_ESTANDAR = {
    'amistosos internacionales': 'Friendly',
    'amistoso internacional':    'Friendly',
    'amistoso':                  'Friendly',
    'international friendly':    'Friendly',
    'friendlies':                'Friendly',
    'copa mundial de la fifa':   'FIFA World Cup',
    'world cup':                 'FIFA World Cup',
    'clasificación para la copa mundial': 'FIFA World Cup qualification',
    'eliminatorias':             'FIFA World Cup qualification',
    'clasificatorias':           'FIFA World Cup qualification',
    'eurocopa':                  'UEFA Euro',
    'euro':                      'UEFA Euro',
    'copa america':              'Copa America',
    'copa americana':            'Copa America',
    'copa africana de naciones': 'African Cup of Nations',
    'afcon':                     'African Cup of Nations',
    'liga de naciones':          'UEFA Nations League',
    'nations league':            'UEFA Nations League',
}

def estandarizar_torneo(t):
    if pd.isna(t) or str(t).strip() == '':
        return 'Friendly'
    t_lower = str(t).lower().strip()
    for patron, estandar in TORNEO_ESTANDAR.items():
        if patron in t_lower:
            return estandar
    return str(t).strip()

# ══════════════════════════════════════════════════════════════
# PALABRAS PARA EXCLUIR NO-MAYORES MASCULINOS
# ══════════════════════════════════════════════════════════════
PALABRAS_EXCLUIR = [
    'U17','U20','U21','U23','U15','U16','U18','U19',
    'Sub-17','Sub-20','Sub-21','Sub-23',
    'Women','Femenino','Femenina','Female',
    'Olympic','Olympics',
    'Lecce','Udinese','Metalist','Urartu','Zanzíbar',
    'B team','B-team','Reserva',
]

def cargar_fuentes():
    fuentes = {}
    fuentes_config = [
        ('Base externa (limpia2)',             LIMPIA2_CSV),
        ('Kaggle (results.csv)',               RESULTS_CSV),
        ('Scraper (partidos_convertidos.csv)', PARTIDOS_CONV_CSV),
        ('Parche manual (results_2026_patch)', PATCH_2026_CSV),
    ]
    for nombre, ruta in fuentes_config:
        if os.path.exists(ruta):
            df = pd.read_csv(ruta, encoding='utf-8-sig', low_memory=False)
            fuentes[nombre] = df
            print(f"  ✓ {nombre:<42} {len(df):>7,} filas")
        else:
            print(f"  ⚠ No encontrado: {os.path.basename(ruta)}")
    return fuentes

def normalizar(df):
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    renames = {}
    for c in df.columns:
        if c == 'home_score': renames[c] = 'home_goals'
        if c == 'away_score': renames[c] = 'away_goals'
    df.rename(columns=renames, inplace=True)
    for col in ['home_goals','away_goals','tournament','neutral','city','country']:
        if col not in df.columns:
            df[col] = None
    for col in ['home_team','away_team']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df

def etl_completo(df):
    n0 = len(df)

    # PASO 1: Fechas
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    print(f"  [1] Fechas válidas:            {len(df):>7,}")

    # PASO 2: Filtrar no-mayores masculinos
    patron = '|'.join(PALABRAS_EXCLUIR)
    m1 = df['home_team'].str.contains(patron, case=False, na=False)
    m2 = df['away_team'].str.contains(patron, case=False, na=False)
    m3 = df['tournament'].astype(str).str.contains(patron, case=False, na=False)
    df = df[~(m1 | m2 | m3)]
    print(f"  [2] Sin sub-23/femenino/clubes:{len(df):>7,}")

    # PASO 3: Goles válidos → enteros
    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df = df.dropna(subset=['home_goals','away_goals'])
    df = df[(df['home_goals'] >= 0) & (df['away_goals'] >= 0)]
    df = df[(df['home_goals'] <= 30) & (df['away_goals'] <= 30)]
    df['home_goals'] = df['home_goals'].astype(int)
    df['away_goals'] = df['away_goals'].astype(int)
    print(f"  [3] Goles válidos (INT):       {len(df):>7,}")

    # PASO 4: Estandarizar nombres ANTES de deduplicar
    df['home_team'] = df['home_team'].map(
        lambda x: NOMBRES_ESTANDAR.get(str(x).strip(), str(x).strip()))
    df['away_team'] = df['away_team'].map(
        lambda x: NOMBRES_ESTANDAR.get(str(x).strip(), str(x).strip()))
    print(f"  [4] Nombres estandarizados:    {len(df):>7,}")

    # PASO 5: Estandarizar torneos
    df['tournament'] = df['tournament'].apply(estandarizar_torneo)
    print(f"  [5] Torneos estandarizados:    {len(df):>7,}")

    # PASO 6: Limpiar nulos en city/country/neutral
    df['city']    = df['city'].fillna('Unknown')
    df['country'] = df['country'].fillna('Unknown')
    df['neutral'] = df['neutral'].fillna(False)
    df['neutral'] = df['neutral'].astype(str).str.lower().isin(
        ['true','1','yes','true','verdadero'])
    print(f"  [6] Nulos limpiados (city/country/neutral): OK")

    # PASO 7: Deduplicar — con nombres ya estandarizados
    df = df.sort_values('date')
    df = df.drop_duplicates(subset=['date','home_team','away_team'], keep='last')
    df = df.reset_index(drop=True)
    print(f"  [7] Deduplicado final:         {len(df):>7,}")
    print(f"\n  Eliminados total: {n0 - len(df):,}")
    return df

def estadisticas(df):
    print(f"\n{'='*60}")
    print(f"  ESTADÍSTICAS DEL DATASET FINAL")
    print(f"{'='*60}")
    print(f"  Total partidos:     {len(df):,}")
    print(f"  Rango fechas:       {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"  Selecciones únicas: {pd.concat([df['home_team'],df['away_team']]).nunique()}")
    df['year'] = df['date'].dt.year
    print(f"\n  Por período:")
    for nombre, desde, hasta in [
        ('Antes 2010', 1872, 2009),
        ('2010-2018',  2010, 2018),
        ('2019-2022',  2019, 2022),
        ('2023-2024',  2023, 2024),
        ('2025-2026',  2025, 2026),
    ]:
        n = len(df[(df['year']>=desde) & (df['year']<=hasta)])
        print(f"    {nombre:<15} {n:>6,} partidos")
    print(f"\n  Top 8 torneos:")
    for t, c in df['tournament'].value_counts().head(8).items():
        print(f"    {str(t):<38} {c:>5,}")
    print(f"\n  Tipos de datos:")
    print(f"    home_goals: {df['home_goals'].dtype}")
    print(f"    away_goals: {df['away_goals'].dtype}")
    print(f"    neutral:    {df['neutral'].dtype}")
    print(f"    city nulos: {(df['city']=='Unknown').sum()}")

def main():
    print("=" * 65)
    print("  CONSTRUIR DATASET MAESTRO — ETL completo")
    print("  4 fuentes · estandarización · tipos · nulos · dedup")
    print("=" * 65)

    print(f"\n📂 Cargando fuentes (menor → mayor prioridad)...")
    fuentes = cargar_fuentes()
    if not fuentes:
        print("❌ Sin fuentes.")
        return

    print(f"\n🔧 Normalizando columnas...")
    dfs = [normalizar(df) for df in fuentes.values()]
    df_total = pd.concat(dfs, ignore_index=True)
    print(f"  Total antes de ETL: {len(df_total):,}")

    print(f"\n🧹 Aplicando ETL completo...")
    df_clean = etl_completo(df_total)

    estadisticas(df_clean)

    # Columnas finales
    cols_out = ['date','home_team','away_team','home_goals','away_goals',
                'tournament','neutral','city','country']
    df_out = df_clean[[c for c in cols_out if c in df_clean.columns]].copy()
    df_out['date'] = df_out['date'].dt.strftime('%Y-%m-%d')
    df_out.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

    print(f"\n{'='*65}")
    print(f"  ✅ Dataset maestro guardado:")
    print(f"     {OUTPUT_CSV}")
    print(f"     {len(df_out):,} partidos de calidad de producción")
    print(f"\n  Para usarlo en el modelo, en Config/config.py:")
    print(f"     RESULTS_CSV = os.path.join(INTL_DIR, 'base_datos_maestra.csv')")
    print(f"{'='*65}")

if __name__ == '__main__':
    main()
