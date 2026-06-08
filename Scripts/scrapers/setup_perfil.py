# setup_perfil.py
import subprocess

print("Abriendo Brave con perfil NUEVO para sportytrader...")
print("→ Resuelve el captcha de Cloudflare")
print("→ Navega un par de páginas del sitio")
print("→ Cierra el navegador cuando termines")
print()

proc = subprocess.Popen([
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"--user-data-dir=D:\MODELO DE PREDICCION\brave_profile_st",
    "https://www.sportytrader.com/en/odds/football/"
])
proc.wait()
print("\nNavegador cerrado. Ahora corre scraper_cuotas.py")