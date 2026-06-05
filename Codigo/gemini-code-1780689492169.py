import pandas as pd
import io
import os

# Le indicamos a Python exactamente dónde están tus archivos
ruta_descargas = r"C:\Users\Usuario\Downloads"

# --- PARTE 1: PARTIDOS (FIXTURES) ---
fixtures_files = {
    '2022': os.path.join(ruta_descargas, '2022 J1 League - Hoja 1.csv'),
    '2023': os.path.join(ruta_descargas, '2023 J1 League - Hoja 1.csv'),
    '2024': os.path.join(ruta_descargas, '2024 J1 League - Hoja 1.csv'),
    '2025': os.path.join(ruta_descargas, '2025 J1 League - Hoja 1.csv')
}

dfs_matches = []
for year, file in fixtures_files.items():
    try:
        with open(file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        header_idx = -1
        for i, line in enumerate(lines):
            if 'Wk,Day,Date' in line:
                header_idx = i
                break
                
        if header_idx != -1:
            csv_data = "".join(lines[header_idx:])
            df = pd.read_csv(io.StringIO(csv_data))
            df = df.dropna(subset=['Wk', 'Date'], how='all')
            df['Season'] = year
            dfs_matches.append(df)
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo: {file}")

if dfs_matches:
    df_all_matches = pd.concat(dfs_matches, ignore_index=True)
    df_all_matches = df_all_matches.dropna(axis=1, how='all')
    df_all_matches = df_all_matches[df_all_matches['Date'].astype(str).str.contains('-', na=False)]
    
    # Esto guardará el resultado en la carpeta donde estás trabajando (D:\MODELO DE PREDICCION)
    df_all_matches.to_csv('J1_League_Matches_2022_2025.csv', index=False)
    print("✅ Archivo de partidos guardado exitosamente: J1_League_Matches_2022_2025.csv")


# --- PARTE 2: ESTADÍSTICAS DE JUGADORES ---
stats_files = {
    '2022': os.path.join(ruta_descargas, '2022 J1 League.csv'),
    '2023': os.path.join(ruta_descargas, '2023 J1 League.csv'),
    '2024': os.path.join(ruta_descargas, '2024 J1 League.csv'),
    '2025': os.path.join(ruta_descargas, '2025 J1 League.csv')
}

dfs_players = []
for year, file in stats_files.items():
    try:
        with open(file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        header_idx = -1
        for i, line in enumerate(lines):
            if line.startswith('Rk,Player,Nation,Pos'):
                header_idx = i
                break
                
        if header_idx != -1:
            csv_data = "".join(lines[header_idx:])
            df = pd.read_csv(io.StringIO(csv_data))
            df = df.dropna(subset=['Player']) 
            df = df[df['Player'] != 'Player'] 
            df['Season'] = year
            dfs_players.append(df)
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo: {file}")

if dfs_players:
    df_all_players = pd.concat(dfs_players, ignore_index=True)
    df_all_players = df_all_players.dropna(axis=1, how='all')
    
    # Esto guardará el resultado en la carpeta donde estás trabajando (D:\MODELO DE PREDICCION)
    df_all_players.to_csv('J1_League_Player_Stats_2022_2025.csv', index=False)
    print("✅ Archivo de jugadores guardado exitosamente: J1_League_Player_Stats_2022_2025.csv")