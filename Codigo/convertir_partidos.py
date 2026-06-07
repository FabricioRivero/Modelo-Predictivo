"""
convertir_partidos.py — Convierte partidos_internacionales.csv (español)
al formato estándar results.csv (inglés) para usar en el modelo Dixon-Coles.

Uso:
    python convertir_partidos.py

Input:  partidos_internacionales.csv  (Fecha DD/MM/YYYY, nombres en español)
Output: partidos_convertidos.csv      (date YYYY-MM-DD, nombres en inglés)
"""

import pandas as pd
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════
# DICCIONARIO COMPLETO: Español → Inglés (nombres en results.csv)
# ══════════════════════════════════════════════════════════════
NOMBRES = {
    # Europa
    "Albania":               "Albania",
    "Alemania":              "Germany",
    "Andorra":               "Andorra",
    "Austria":               "Austria",
    "Bélgica":               "Belgium",
    "Belgica":               "Belgium",
    "Bielorusia":            "Belarus",
    "Bielorrusia":           "Belarus",
    "Bosnia":                "Bosnia and Herzegovina",
    "Bosnia-Herzegovina":    "Bosnia and Herzegovina",
    "Bulgaria":              "Bulgaria",
    "Croacia":               "Croatia",
    "Dinamarca":             "Denmark",
    "Escocia":               "Scotland",
    "Eslovaquia":            "Slovakia",
    "Eslovenia":             "Slovenia",
    "España":                "Spain",
    "Espana":                "Spain",
    "Finlandia":             "Finland",
    "Francia":               "France",
    "Gales":                 "Wales",
    "Georgia":               "Georgia",
    "Grecia":                "Greece",
    "Hungría":               "Hungary",
    "Hungria":               "Hungary",
    "Irlanda del Norte":     "Northern Ireland",
    "Irlanda":               "Republic of Ireland",
    "Islandia":              "Iceland",
    "Israel":                "Israel",
    "Italia":                "Italy",
    "Kosovo":                "Kosovo",
    "Luxemburgo":            "Luxembourg",
    "Macedonia del Norte":   "North Macedonia",
    "Moldavia":              "Moldova",
    "Moldova":               "Moldova",
    "Montenegro":            "Montenegro",
    "Noruega":               "Norway",
    "Países Bajos":          "Netherlands",
    "Paises Bajos":          "Netherlands",
    "Polonia":               "Poland",
    "Portugal":              "Portugal",
    "República Checa":       "Czech Republic",
    "Republica Checa":       "Czech Republic",
    "Chequia":               "Czech Republic",
    "Rumanía":               "Romania",
    "Rumania":               "Romania",
    "Rusia":                 "Russia",
    "Serbia":                "Serbia",
    "Suecia":                "Sweden",
    "Suiza":                 "Switzerland",
    "Turquía":               "Turkey",
    "Turquia":               "Turkey",
    "Ucrania":               "Ukraine",
    "Inglaterra":            "England",
    # América del Sur
    "Argentina":             "Argentina",
    "Bolivia":               "Bolivia",
    "Brasil":                "Brazil",
    "Chile":                 "Chile",
    "Colombia":              "Colombia",
    "Ecuador":               "Ecuador",
    "Paraguay":              "Paraguay",
    "Perú":                  "Peru",
    "Peru":                  "Peru",
    "Uruguay":               "Uruguay",
    "Venezuela":             "Venezuela",
    # América Central y Norte
    "Canadá":                "Canada",
    "Canada":                "Canada",
    "Costa Rica":            "Costa Rica",
    "Cuba":                  "Cuba",
    "Curazao":               "Curacao",
    "EE. UU.":               "United States",
    "EE.UU.":                "United States",
    "EE. UU":                "United States",
    "Estados Unidos":        "United States",
    "El Salvador":           "El Salvador",
    "Guatemala":             "Guatemala",
    "Haití":                 "Haiti",
    "Haiti":                 "Haiti",
    "Honduras":              "Honduras",
    "Jamaica":               "Jamaica",
    "México":                "Mexico",
    "Mexico":                "Mexico",
    "Nicaragua":             "Nicaragua",
    "Panamá":                "Panama",
    "Panama":                "Panama",
    "Puerto Rico":           "Puerto Rico",
    "Trinidad y Tobago":     "Trinidad and Tobago",
    "Trinidad":              "Trinidad and Tobago",
    "Bermudas":              "Bermuda",
    "Aruba":                 "Aruba",
    # África
    "Argelia":               "Algeria",
    "Angola":                "Angola",
    "Benín":                 "Benin",
    "Benin":                 "Benin",
    "Burkina Faso":          "Burkina Faso",
    "Camerún":               "Cameroon",
    "Camerun":               "Cameroon",
    "Cabo Verde":            "Cape Verde",
    "Comoras":               "Comoros",
    "Congo DR":              "DR Congo",
    "RD del Congo":          "DR Congo",
    "RD Congo":              "DR Congo",
    "Costa de Marfil":       "Ivory Coast",
    "Egipto":                "Egypt",
    "Gabón":                 "Gabon",
    "Gabon":                 "Gabon",
    "Ghana":                 "Ghana",
    "Guinea":                "Guinea",
    "Guinea Ecuatorial":     "Equatorial Guinea",
    "Kenia":                 "Kenya",
    "Mali":                  "Mali",
    "Malí":                  "Mali",
    "Marruecos":             "Morocco",
    "Mauritania":            "Mauritania",
    "Níger":                 "Niger",
    "Niger":                 "Niger",
    "Nigeria":               "Nigeria",
    "Ruanda":                "Rwanda",
    "Senegal":               "Senegal",
    "Sudáfrica":             "South Africa",
    "Sudafrica":             "South Africa",
    "Tanzania":              "Tanzania",
    "Togo":                  "Togo",
    "Túnez":                 "Tunisia",
    "Tunez":                 "Tunisia",
    "Uganda":                "Uganda",
    "Zambia":                "Zambia",
    # Asia / Oceanía
    "Arabia Saudí":          "Saudi Arabia",
    "Arabia Saudi":          "Saudi Arabia",
    "Australia":             "Australia",
    "Baréin":                "Bahrain",
    "Barein":                "Bahrain",
    "Bahréin":               "Bahrain",
    "China":                 "China PR",
    "Corea del Sur":         "South Korea",
    "República de Corea":    "South Korea",
    "Emiratos Árabes":       "United Arab Emirates",
    "Emiratos Árabes Unidos":"United Arab Emirates",
    "EAU":                   "United Arab Emirates",
    "Filipinas":             "Philippines",
    "India":                 "India",
    "Indonesia":             "Indonesia",
    "Irak":                  "Iraq",
    "Irán":                  "Iran",
    "Iran":                  "Iran",
    "RI de Irán":            "Iran",
    "Japón":                 "Japan",
    "Japon":                 "Japan",
    "Jordania":              "Jordan",
    "Kirguistán":            "Kyrgyzstan",
    "Kirguistan":            "Kyrgyzstan",
    "Kuwait":                "Kuwait",
    "Nueva Zelanda":         "New Zealand",
    "Omán":                  "Oman",
    "Oman":                  "Oman",
    "Palestina":             "Palestine",
    "Qatar":                 "Qatar",
    "Catar":                 "Qatar",
    "Arabia Saudita":        "Saudi Arabia",
    "Singapur":              "Singapore",
    "Siria":                 "Syria",
    "Tayikistán":            "Tajikistan",
    "Tayikistan":            "Tajikistan",
    "Tailandia":             "Thailand",
    "Uzbekistán":            "Uzbekistan",
    "Uzbekistan":            "Uzbekistan",
    "Vietnam":               "Vietnam",
    "Islandia":              "Iceland",
}

# Torneos → peso en el modelo
TORNEO_MAP = {
    "eliminatorias":         "FIFA World Cup qualification",
    "clasificacion":         "FIFA World Cup qualification",
    "clasificatoria":        "FIFA World Cup qualification",
    "copa del mundo":        "FIFA World Cup",
    "eurocopa":              "UEFA Euro",
    "copa america":          "Copa America",
    "copa áfrica":           "Africa Cup of Nations",
    "nations league uefa":   "UEFA Nations League",
    "nations league":        "UEFA Nations League",
    "conmebol":              "FIFA World Cup qualification",
    "amistoso":              "Friendly",
    "amistosos":             "Friendly",
}

def normalizar_torneo(torneo_raw):
    t = torneo_raw.lower().strip()
    for key, val in TORNEO_MAP.items():
        if key in t:
            return val
    return "Friendly"

def convertir(input_path, output_path):
    df = pd.read_csv(input_path, encoding='utf-8-sig')

    # Normalizar columnas
    df.columns = [c.strip() for c in df.columns]
    # Renombrar a estándar
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if 'fecha' in cl:           col_map[c] = 'fecha_raw'
        elif 'local' in cl:         col_map[c] = 'home_raw'
        elif 'visitante' in cl:     col_map[c] = 'away_raw'
        elif 'goles l' in cl or cl == 'goles l': col_map[c] = 'home_goals'
        elif 'goles v' in cl or cl == 'goles v': col_map[c] = 'away_goals'
        elif 'torneo' in cl or 'competencia' in cl: col_map[c] = 'tournament_raw'
    df.rename(columns=col_map, inplace=True)

    # Parsear fecha DD/MM/YYYY → YYYY-MM-DD
    df['date'] = pd.to_datetime(df['fecha_raw'], format='%d/%m/%Y', errors='coerce')
    df.dropna(subset=['date'], inplace=True)

    # Convertir nombres
    not_found_home = set()
    not_found_away = set()

    def traduce(name, side):
        n = str(name).strip()
        if n in NOMBRES:
            return NOMBRES[n]
        # Intento fuzzy: buscar si alguna clave está contenida
        for k, v in NOMBRES.items():
            if k.lower() == n.lower():
                return v
        if side == 'home':
            not_found_home.add(n)
        else:
            not_found_away.add(n)
        return n  # devolver tal cual si no se encuentra

    df['home_team'] = df['home_raw'].apply(lambda x: traduce(x, 'home'))
    df['away_team'] = df['away_raw'].apply(lambda x: traduce(x, 'away'))

    # Torneo
    if 'tournament_raw' in df.columns:
        df['tournament'] = df['tournament_raw'].apply(normalizar_torneo)
    else:
        df['tournament'] = 'Friendly'

    # Goles
    df['home_score'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_score'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df.dropna(subset=['home_score', 'away_score'], inplace=True)
    df['home_score'] = df['home_score'].astype(int)
    df['away_score'] = df['away_score'].astype(int)

    # Neutral: amistosos en USA antes del Mundial son neutrales
    df['neutral'] = df['tournament'].str.lower().str.contains('friendly').astype(str).str.upper()

    # Formato final igual a results.csv
    out = df[['date','home_team','away_team','home_score','away_score','tournament','neutral']].copy()
    out['date'] = out['date'].dt.strftime('%Y-%m-%d')
    out.columns = ['date','home_team','away_team','home_score','away_score','tournament','neutral']
    out = out.sort_values('date').reset_index(drop=True)
    out.to_csv(output_path, index=False, encoding='utf-8-sig')

    print(f"✅ Convertidos: {len(out)} partidos")
    print(f"   Rango fechas: {out['date'].min()} → {out['date'].max()}")
    print(f"   Selecciones únicas: {pd.concat([out['home_team'],out['away_team']]).nunique()}")
    if not_found_home | not_found_away:
        print(f"\n⚠️  Nombres NO encontrados en diccionario:")
        all_nf = (not_found_home | not_found_away) - {''}
        for n in sorted(all_nf):
            print(f"   '{n}'")
        print("   → Agrégalos al diccionario NOMBRES si son importantes")
    return out

if __name__ == '__main__':
    inp = os.path.join(BASE, 'partidos_internacionales.csv')
    out = os.path.join(BASE, 'partidos_convertidos.csv')
    if not os.path.exists(inp):
        print(f"❌ No encontrado: {inp}")
    else:
        convertir(inp, out)
        print(f"\n📂 Guardado en: {out}")
