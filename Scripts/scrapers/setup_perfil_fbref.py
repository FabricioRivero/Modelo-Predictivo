# setup_perfil_fbref.py
# Paso 1: Abre Brave con el perfil fbref y resuelve Cloudflare manualmente
# Paso 2: Luego corre scraper_xg.py

import subprocess
from pathlib import Path

PROFILE_DIR = r"D:\MODELO DE PREDICCION\brave_profile_fbref"
BRAVE_PATH  = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("  SETUP PERFIL FBREF")
print("=" * 60)
print()
print("  Se abrirá Brave con el perfil dedicado a fbref.")
print()
print("  QUÉ TIENES QUE HACER:")
print("  1. Espera que cargue fbref.com")
print("  2. Si aparece 'Verifying you are human' — espera unos")
print("     segundos, suele resolverse solo.")
print("  3. Si NO se resuelve, recarga la página (F5) 1 o 2 veces.")
print("  4. Navega 2-3 páginas dentro de fbref (cualquier liga,")
print("     cualquier equipo) para que Cloudflare te reconozca.")
print("  5. Cierra el navegador cuando veas páginas normales.")
print()
print("  Abriendo Brave...")
print()

proc = subprocess.Popen([
    BRAVE_PATH,
    f"--user-data-dir={PROFILE_DIR}",
    "--no-first-run",
    "--no-default-browser-check",
    "https://fbref.com/en/comps/685/2024/schedule/2024-Copa-America-Scores-and-Fixtures",
])
proc.wait()

print()
print("  Navegador cerrado.")
print("  Ahora corre: python scraper_xg.py")