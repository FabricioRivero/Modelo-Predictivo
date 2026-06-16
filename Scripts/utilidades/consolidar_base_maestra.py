"""
consolidar_base_maestra.py — UNA SOLA BASE DE DATOS LIMPIA
============================================================
Toma TODAS las fuentes y genera UN SOLO archivo:

    Datos/internacional/base_maestra.csv

Formato de salida:
    date,home_team,away_team,home_goals,away_goals,tournament,city,country,neutral

Reglas:
  - Todo en INGLES
  - Fecha formato YYYY-MM-DD
  - Sin duplicados (prioridad: patch > scraper > kaggle)
  - Sin partidos futuros (NA en goles)
  - Sin sub-categorias (U17, U20, femenino, olimpico)
  - Solo selecciones mayores masculinas
  - neutral = TRUE/FALSE
  - Goles como enteros

Fuentes (de menor a mayor prioridad):
  1. results.csv           (Kaggle — base historica)
  2. partidos_internacionales.csv (Scraper — español, 2025)
  3. results_2026_patch.csv       (Parche manual — maxima prioridad)

Uso:
    python Scripts/utilidades/consolidar_base_maestra.py
"""
import os, sys
import csv
from datetime import datetime
from collections import OrderedDict

# Config
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', '..', 'Config'))
from config import RESULTS_CSV, PATCH_2026_CSV, INTL_DIR

PARTIDOS_INTL = os.path.join(INTL_DIR, 'partidos_internacionales.csv')
OUTPUT_CSV = os.path.join(INTL_DIR, 'base_maestra.csv')


# ══════════════════════════════════════════════════════════════
# DICCIONARIO COMPLETO: ESPAÑOL/VARIANTES → INGLES ESTANDAR
# ══════════════════════════════════════════════════════════════
TEAM_NAME_MAP = {
    # === ESPAÑOL → INGLES ===
    'Afganistán':'Afghanistan','Albania':'Albania','Alemania':'Germany',
    'Andorra':'Andorra','Angola':'Angola','Anguila':'Anguilla',
    'Antigua & Barbuda':'Antigua and Barbuda',
    'Arabia Saudí':'Saudi Arabia','Arabia Saudita':'Saudi Arabia',
    'Argelia':'Algeria','Argelia B':'Algeria',
    'Argentina':'Argentina','Armenia':'Armenia','Aruba':'Aruba',
    'Australia':'Australia','Austria':'Austria','Azerbaiyán':'Azerbaijan',
    'Bahamas':'Bahamas','Bahréin':'Bahrain','Baréin':'Bahrain',
    'Bangladés':'Bangladesh','Barbados':'Barbados',
    'Bélgica':'Belgium','Belice':'Belize','Benín':'Benin',
    'Bermudas':'Bermuda','Bielorrusia':'Belarus',
    'Birmania':'Myanmar','Bolivia':'Bolivia',
    'Bosnia-Herzegovina':'Bosnia and Herzegovina',
    'Bosnia y Herzegovina':'Bosnia and Herzegovina',
    'Botsuana':'Botswana','Brasil':'Brazil','Brunéi':'Brunei',
    'Bulgaria':'Bulgaria','Burkina Faso':'Burkina Faso',
    'Burundi':'Burundi','Bután':'Bhutan',
    'Cabo Verde':'Cape Verde','Camboya':'Cambodia',
    'Camerún':'Cameroon','Canadá':'Canada','Catar':'Qatar',
    'Chad':'Chad','Chile':'Chile','China':'China',
    'Chipre':'Cyprus','Colombia':'Colombia',
    'Comoras':'Comoros','Congo':'Republic of Congo',
    'Corea del Norte':'North Korea','Corea del Sur':'South Korea',
    'Costa de Marfil':'Ivory Coast','Costa Rica':'Costa Rica',
    'Croacia':'Croatia','Cuba':'Cuba','Curazao':'Curacao',
    'Dinamarca':'Denmark','Dominica':'Dominica',
    'Ecuador':'Ecuador','Egipto':'Egypt',
    'El Salvador':'El Salvador','Emiratos Árabes Unidos':'United Arab Emirates',
    'Emiratos Árabes':'United Arab Emirates',
    'Eritrea':'Eritrea','Escocia':'Scotland',
    'Eslovaquia':'Slovakia','Eslovenia':'Slovenia',
    'España':'Spain','Estados Unidos':'United States',
    'EEUU':'United States','EE.UU.':'United States',
    'Estonia':'Estonia','Esuatini':'Eswatini','Eswatini':'Eswatini',
    'Etiopía':'Ethiopia',

    'Filipinas':'Philippines','Finlandia':'Finland',
    'Francia':'France','Gabón':'Gabon','Gambia':'Gambia',
    'Georgia':'Georgia','Ghana':'Ghana','Granada':'Grenada',
    'Grecia':'Greece','Guatemala':'Guatemala','Guinea':'Guinea',
    'Guinea Ecuatorial':'Equatorial Guinea',
    'Guinea-Bisáu':'Guinea-Bissau','Guyana':'Guyana',
    'Haití':'Haiti','Honduras':'Honduras','Hungría':'Hungary',
    'India':'India','Indonesia':'Indonesia',
    'Inglaterra':'England','Irak':'Iraq','Irán':'Iran',
    'Irlanda':'Republic of Ireland','Irlanda del Norte':'Northern Ireland',
    'Islandia':'Iceland','Islas Caimán':'Cayman Islands',
    'Islas Cook':'Cook Islands','Islas Feroe':'Faroe Islands',
    'Islas Salomón':'Solomon Islands',
    'Islas Turcas y Caicos':'Turks and Caicos Islands',
    'Islas Vírgenes':'US Virgin Islands',
    'Israel':'Israel','Italia':'Italy','Jamaica':'Jamaica',
    'Japón':'Japan','Jordania':'Jordan',
    'Kazajistán':'Kazakhstan','Kenia':'Kenya',
    'Kirguistán':'Kyrgyzstan','Kosovo':'Kosovo',
    'Kuwait':'Kuwait','Laos':'Laos','Lesoto':'Lesotho',
    'Letonia':'Latvia','Líbano':'Lebanon','Liberia':'Liberia',
    'Libia':'Libya','Liechtenstein':'Liechtenstein',
    'Lituania':'Lithuania','Luxemburgo':'Luxembourg',
    'Macedonia del Norte':'North Macedonia',
    'Madagascar':'Madagascar','Malasia':'Malaysia',
    'Malaui':'Malawi','Maldivas':'Maldives','Malí':'Mali',
    'Malta':'Malta','Marruecos':'Morocco',
    'Mauricio':'Mauritius','Mauritania':'Mauritania',
    'México':'Mexico','Moldavia':'Moldova',
    'Mongolia':'Mongolia','Montenegro':'Montenegro',
    'Mozambique':'Mozambique','Myanmar':'Myanmar',
    'Namibia':'Namibia','Nepal':'Nepal',
    'Nicaragua':'Nicaragua','Níger':'Niger','Nigeria':'Nigeria',
    'Noruega':'Norway','Nueva Zelanda':'New Zealand',
    'Omán':'Oman',

    'Países Bajos':'Netherlands','Pakistán':'Pakistan',
    'Palestina':'Palestine','Panamá':'Panama',
    'Papua Nueva Guinea':'Papua New Guinea',
    'Paraguay':'Paraguay','Perú':'Peru','Polonia':'Poland',
    'Portugal':'Portugal','Puerto Rico':'Puerto Rico',
    'RD del Congo':'DR Congo','RD Congo':'DR Congo',
    'Congo RD':'DR Congo',
    'Reino Unido':'England',
    'República Centroafricana':'Central African Republic',
    'República Checa':'Czech Republic',
    'República de Corea':'South Korea',
    'República Dominicana':'Dominican Republic',
    'Ruanda':'Rwanda','Rumanía':'Romania','Rumania':'Romania',
    'Rusia':'Russia',
    'Samoa':'Samoa','San Marino':'San Marino',
    'San Cristóbal y Nieves':'Saint Kitts and Nevis',
    'Santo Tomé y Príncipe':'São Tomé and Príncipe',
    'Senegal':'Senegal','Serbia':'Serbia',
    'Sierra Leona':'Sierra Leone','Singapur':'Singapore',
    'Siria':'Syria','Somalia':'Somalia',
    'Sri Lanka':'Sri Lanka','Sudáfrica':'South Africa',
    'Sudán':'Sudan','Sudán del Sur':'South Sudan',
    'Suecia':'Sweden','Suiza':'Switzerland',
    'Surinam':'Suriname','Tailandia':'Thailand',
    'Taiwán':'Chinese Taipei','Tanzania':'Tanzania',
    'Tayikistán':'Tajikistan','Togo':'Togo',
    'Trinidad y Tobago':'Trinidad and Tobago',
    'Túnez':'Tunisia','Turkmenistán':'Turkmenistan',
    'Turquía':'Turkey','Ucrania':'Ukraine','Uganda':'Uganda',
    'Uruguay':'Uruguay','Uzbekistán':'Uzbekistan',
    'Venezuela':'Venezuela','Vietnam':'Vietnam',
    'Yemen':'Yemen','Zambia':'Zambia',
    'Zimbabue':'Zimbabwe','Zimbabwe':'Zimbabwe',

    # === Nombres residuales ===
    'Gales':'Wales','EE. UU.':'United States',
    'Santa Lucía':'Saint Lucia','Zanzíbar':'Zanzibar',
    'Islas Vírgenes Estadounidenses':'US Virgin Islands',
    # === VARIANTES INGLES / FIFA / UNICODE → ESTANDAR ===
    'IR Iran':'Iran','RI de Irán':'Iran',
    'Türkiye':'Turkey','Turkiye':'Turkey',
    'Korea Republic':'South Korea','Republic of Korea':'South Korea',
    'Korea DPR':'North Korea',
    'USA':'United States','US':'United States',
    'United States of America':'United States',
    "Côte d'Ivoire":'Ivory Coast',"Cote d'Ivoire":'Ivory Coast',
    'Congo DR':'DR Congo','Democratic Republic of Congo':'DR Congo',
    'Czechia':'Czech Republic','Czech Rep.':'Czech Republic',
    'China PR':'China','RP China':'China',
    'Bosnia & Herzegovina':'Bosnia and Herzegovina',
    'Cape Verde Islands':'Cape Verde','Cape Verde Isl.':'Cape Verde',
    'Trinidad & Tobago':'Trinidad and Tobago',
    'Trinidad And Tobago':'Trinidad and Tobago',
    'Curaçao':'Curacao',
    'Korea Rep.':'South Korea',
    'Bermuda':'Bermuda',
}


# ══════════════════════════════════════════════════════════════
# TORNEOS: ESPAÑOL/VARIANTES → INGLES ESTANDAR
# ══════════════════════════════════════════════════════════════
TOURNAMENT_MAP = {
    'amistosos internacionales': 'Friendly',
    'amistoso internacional': 'Friendly',
    'amistoso': 'Friendly',
    'international friendly': 'Friendly',
    'friendlies': 'Friendly',
    'friendly': 'Friendly',
    'fifa series': 'Friendly',
    'campeonato del mundo': 'FIFA World Cup qualification',
    'copa mundial': 'FIFA World Cup',
    'fifa world cup': 'FIFA World Cup',
    'fifa world cup qualification': 'FIFA World Cup qualification',
    'world cup': 'FIFA World Cup',
    'world cup qualification': 'FIFA World Cup qualification',
    'eurocopa': 'UEFA Euro',
    'uefa euro': 'UEFA Euro',
    'uefa euro qualification': 'UEFA Euro qualification',
    'uefa nations league': 'UEFA Nations League',
    'liga de naciones': 'UEFA Nations League',
    'nations league': 'UEFA Nations League',
    'copa america': 'Copa America',
    'copa américa': 'Copa America',
    'copa de africa de naciones': 'Africa Cup of Nations',
    'copa de áfrica de naciones': 'Africa Cup of Nations',
    'copa africana de naciones': 'Africa Cup of Nations',
    'africa cup of nations': 'Africa Cup of Nations',
    'africa cup of nations qualification': 'Africa Cup of Nations qualification',
    'campeonato africano de naciones': 'CHAN',
    'afc asian cup': 'AFC Asian Cup',
    'copa asiática': 'AFC Asian Cup',
    'afc asian cup qualification': 'AFC Asian Cup qualification',
    'gold cup': 'CONCACAF Gold Cup',
    'copa oro': 'CONCACAF Gold Cup',
    'concacaf gold cup': 'CONCACAF Gold Cup',
    'concacaf nations league': 'CONCACAF Nations League',
    'concacaf series': 'CONCACAF Nations League',
    'conmebol world cup qualification': 'FIFA World Cup qualification',
    'cosafa cup': 'COSAFA Cup',
    'cafa nations cup': 'CAFA Nations Cup',
    'eaff e-1 football championship': 'EAFF Championship',
    'kings cup - tailandia': 'Kings Cup',
    'fifa arab cup': 'Arab Cup',
}

def normalize_tournament(t):
    """Normaliza nombre de torneo a ingles estandar."""
    if not t or str(t).strip() == '':
        return 'Friendly'
    t_lower = str(t).lower().strip()
    # Busqueda exacta
    if t_lower in TOURNAMENT_MAP:
        return TOURNAMENT_MAP[t_lower]
    # Busqueda parcial
    for key, val in TOURNAMENT_MAP.items():
        if key in t_lower:
            return val
    # Patrones genericos
    if 'qualif' in t_lower or 'clasificat' in t_lower:
        return 'FIFA World Cup qualification'
    if 'friendly' in t_lower or 'amist' in t_lower:
        return 'Friendly'
    # Devolver original en Title Case
    return str(t).strip().title()


# ══════════════════════════════════════════════════════════════
# FUNCIONES DE CARGA POR FUENTE
# ══════════════════════════════════════════════════════════════

def normalize_team(name):
    """Normaliza nombre de equipo a ingles estandar."""
    if not name:
        return ''
    name = str(name).strip()
    # Quitar codigos de pais tipo "Argentina ar", "Ecuador ec"
    parts = name.rsplit(' ', 1)
    if len(parts) == 2 and len(parts[1]) <= 3 and parts[1].islower():
        name = parts[0]
    return TEAM_NAME_MAP.get(name, name)


def is_valid_match(home, away, tournament):
    """Filtra partidos no validos (sub-categorias, femenino, etc)."""
    exclude_words = [
        'U17','U20','U21','U23','U15','U16','U18','U19',
        'Sub-17','Sub-20','Sub-21','Sub-23','Sub 17','Sub 20',
        'Women','Femenino','Femenina','Female','Olympic',
        'B team','B-team','Reserva',' B',
    ]
    text = f"{home} {away} {tournament}"
    for w in exclude_words:
        if w.lower() in text.lower():
            return False
    return True


def load_kaggle_results():
    """Carga results.csv de Kaggle (base principal)."""
    if not os.path.exists(RESULTS_CSV):
        print(f"  ! No encontrado: {RESULTS_CSV}")
        return []
    
    rows = []
    with open(RESULTS_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Saltar partidos futuros (sin resultado)
            hs = r.get('home_score', '').strip()
            aws = r.get('away_score', '').strip()
            if not hs or not aws or hs == 'NA' or aws == 'NA':
                continue
            try:
                hg = int(float(hs))
                ag = int(float(aws))
            except (ValueError, TypeError):
                continue
            if hg < 0 or ag < 0 or hg > 30 or ag > 30:
                continue
            
            home = normalize_team(r.get('home_team', ''))
            away = normalize_team(r.get('away_team', ''))
            tourn = normalize_tournament(r.get('tournament', ''))
            
            if not home or not away:
                continue
            if not is_valid_match(home, away, tourn):
                continue
            
            neutral = r.get('neutral', 'FALSE').strip().upper()
            neutral = 'TRUE' if neutral in ('TRUE','1','YES') else 'FALSE'
            
            rows.append({
                'date': r.get('date', '').strip(),
                'home_team': home,
                'away_team': away,
                'home_goals': hg,
                'away_goals': ag,
                'tournament': tourn,
                'city': r.get('city', 'Unknown').strip() or 'Unknown',
                'country': r.get('country', 'Unknown').strip() or 'Unknown',
                'neutral': neutral,
                'source': 'kaggle',
            })
    print(f"  [1] Kaggle results.csv: {len(rows):,} partidos validos")
    return rows


def load_partidos_internacionales():
    """Carga partidos_internacionales.csv (español, DD/MM/YYYY)."""
    if not os.path.exists(PARTIDOS_INTL):
        print(f"  [2] partidos_internacionales.csv: NO ENCONTRADO")
        return []
    
    rows = []
    with open(PARTIDOS_INTL, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Fecha DD/MM/YYYY → YYYY-MM-DD
            fecha = r.get('Fecha', '').strip()
            if not fecha:
                continue
            try:
                dt = datetime.strptime(fecha, '%d/%m/%Y')
                date_str = dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
            
            # Goles
            try:
                hg = int(float(r.get('Goles L', '0').strip()))
                ag = int(float(r.get('Goles V', '0').strip()))
            except (ValueError, TypeError):
                continue
            if hg < 0 or ag < 0 or hg > 30 or ag > 30:
                continue
            
            home = normalize_team(r.get('Local', ''))
            away = normalize_team(r.get('Visitante', ''))
            tourn = normalize_tournament(r.get('Torneo', ''))
            
            if not home or not away:
                continue
            if not is_valid_match(home, away, tourn):
                continue
            
            rows.append({
                'date': date_str,
                'home_team': home,
                'away_team': away,
                'home_goals': hg,
                'away_goals': ag,
                'tournament': tourn,
                'city': 'Unknown',
                'country': 'Unknown',
                'neutral': 'FALSE',
                'source': 'scraper_intl',
            })
    print(f"  [2] partidos_internacionales.csv: {len(rows):,} partidos")
    return rows


def load_patch_2026():
    """Carga results_2026_patch.csv (maxima prioridad)."""
    if not os.path.exists(PATCH_2026_CSV):
        print(f"  [3] results_2026_patch.csv: NO ENCONTRADO")
        return []
    
    rows = []
    with open(PATCH_2026_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            hs = r.get('home_score', '').strip()
            aws = r.get('away_score', '').strip()
            if not hs or not aws or hs == 'NA' or aws == 'NA':
                continue
            try:
                hg = int(float(hs))
                ag = int(float(aws))
            except (ValueError, TypeError):
                continue
            
            home = normalize_team(r.get('home_team', ''))
            away = normalize_team(r.get('away_team', ''))
            tourn = normalize_tournament(r.get('tournament', ''))
            
            if not home or not away:
                continue
            
            neutral = r.get('neutral', 'FALSE').strip().upper()
            neutral = 'TRUE' if neutral in ('TRUE','1','YES') else 'FALSE'
            
            rows.append({
                'date': r.get('date', '').strip(),
                'home_team': home,
                'away_team': away,
                'home_goals': hg,
                'away_goals': ag,
                'tournament': tourn,
                'city': r.get('city', 'Unknown').strip() or 'Unknown',
                'country': r.get('country', 'Unknown').strip() or 'Unknown',
                'neutral': neutral,
                'source': 'patch_2026',
            })
    print(f"  [3] results_2026_patch.csv: {len(rows):,} partidos")
    return rows


# ══════════════════════════════════════════════════════════════
# CONSOLIDACION Y DEDUPLICACION
# ══════════════════════════════════════════════════════════════

# Prioridad: patch > scraper > kaggle
SOURCE_PRIORITY = {'patch_2026': 3, 'scraper_intl': 2, 'kaggle': 1}

def consolidate(all_rows):
    """
    Deduplica por (date, home_team, away_team).
    Si hay duplicado, gana la fuente con mayor prioridad.
    """
    # Ordenar por prioridad (menor primero, se sobreescribe con mayor)
    all_rows.sort(key=lambda r: SOURCE_PRIORITY.get(r['source'], 0))
    
    seen = {}  # key → row
    for row in all_rows:
        key = (row['date'], row['home_team'], row['away_team'])
        seen[key] = row  # el ultimo (mayor prioridad) gana
    
    # Ordenar resultado por fecha
    result = sorted(seen.values(), key=lambda r: r['date'])
    return result


def validate_output(rows):
    """Validaciones finales de calidad."""
    errors = []
    
    for i, r in enumerate(rows):
        # Fecha valida
        try:
            dt = datetime.strptime(r['date'], '%Y-%m-%d')
            if dt.year < 1870 or dt.year > 2030:
                errors.append(f"Fila {i}: fecha fuera de rango ({r['date']})")
        except ValueError:
            errors.append(f"Fila {i}: fecha invalida ({r['date']})")
        
        # Equipos no vacios
        if not r['home_team'] or not r['away_team']:
            errors.append(f"Fila {i}: equipo vacio")
        
        # Equipo no juega contra si mismo
        if r['home_team'] == r['away_team']:
            errors.append(f"Fila {i}: {r['home_team']} vs si mismo")
        
        # Goles razonables
        if r['home_goals'] > 20 or r['away_goals'] > 20:
            errors.append(f"Fila {i}: goles excesivos "
                         f"({r['home_goals']}-{r['away_goals']})")
    
    return errors


def write_output(rows, path):
    """Escribe el CSV final."""
    cols = ['date','home_team','away_team','home_goals','away_goals',
            'tournament','city','country','neutral']
    
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def print_stats(rows):
    """Imprime estadisticas del dataset final."""
    dates = [r['date'] for r in rows]
    teams = set()
    for r in rows:
        teams.add(r['home_team'])
        teams.add(r['away_team'])
    tournaments = {}
    for r in rows:
        t = r['tournament']
        tournaments[t] = tournaments.get(t, 0) + 1
    
    # Por decada
    by_decade = {}
    for r in rows:
        decade = r['date'][:3] + '0s'
        by_decade[decade] = by_decade.get(decade, 0) + 1
    
    print(f"\n{'='*60}")
    print(f"  DATASET FINAL: base_maestra.csv")
    print(f"{'='*60}")
    print(f"  Total partidos:     {len(rows):,}")
    print(f"  Rango:              {min(dates)} a {max(dates)}")
    print(f"  Selecciones unicas: {len(teams)}")
    print(f"  Torneos unicos:     {len(tournaments)}")
    print(f"\n  Top 10 torneos:")
    for t, c in sorted(tournaments.items(), key=lambda x: -x[1])[:10]:
        print(f"    {t:<42} {c:>5,}")
    print(f"\n  Partidos recientes (2020+):")
    recent = [r for r in rows if r['date'] >= '2020']
    print(f"    Total 2020-2026: {len(recent):,}")
    r2025 = [r for r in rows if r['date'] >= '2025']
    print(f"    Total 2025-2026: {len(r2025):,}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  CONSOLIDAR BASE MAESTRA — Una sola fuente de verdad")
    print("=" * 60)
    
    # 1. Cargar todas las fuentes
    print("\n[1/4] Cargando fuentes...")
    kaggle_rows = load_kaggle_results()
    intl_rows = load_partidos_internacionales()
    patch_rows = load_patch_2026()
    
    all_rows = kaggle_rows + intl_rows + patch_rows
    print(f"\n  Total bruto (todas las fuentes): {len(all_rows):,}")
    
    # 2. Consolidar y deduplicar
    print("\n[2/4] Deduplicando (prioridad: patch > scraper > kaggle)...")
    final = consolidate(all_rows)
    n_removed = len(all_rows) - len(final)
    print(f"  Duplicados eliminados: {n_removed:,}")
    print(f"  Partidos unicos:       {len(final):,}")
    
    # 3. Validar
    print("\n[3/4] Validando calidad...")
    errors = validate_output(final)
    if errors:
        print(f"  ! {len(errors)} errores encontrados:")
        for e in errors[:10]:
            print(f"    {e}")
        # Eliminar filas con error
        valid_final = []
        for i, r in enumerate(final):
            try:
                datetime.strptime(r['date'], '%Y-%m-%d')
                if r['home_team'] and r['away_team']:
                    if r['home_team'] != r['away_team']:
                        valid_final.append(r)
            except ValueError:
                pass
        final = valid_final
        print(f"  Despues de limpiar errores: {len(final):,}")
    else:
        print(f"  OK — 0 errores")
    
    # 4. Escribir
    print(f"\n[4/4] Escribiendo {OUTPUT_CSV}...")
    write_output(final, OUTPUT_CSV)
    
    # Stats
    print_stats(final)
    
    print(f"\n{'='*60}")
    print(f"  LISTO: {OUTPUT_CSV}")
    print(f"  {len(final):,} partidos limpios, en ingles, sin duplicados")
    print(f"\n  Para usar en el modelo, cambia en Config/config.py:")
    print(f"    RESULTS_CSV = os.path.join(INTL_DIR, 'base_maestra.csv')")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
