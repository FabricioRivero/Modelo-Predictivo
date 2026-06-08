# resolver_captcha.py
import subprocess
import time

print("Abriendo Brave para resolver Cloudflare...")
print("1. Resuelve el captcha en el navegador")
print("2. Navega un poco por sportytrader")  
print("3. Cierra el navegador cuando hayas terminado")
print()

subprocess.Popen([
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "--user-data-dir=D:\\MODELO DE PREDICCION\\brave_profile",
    "https://www.sportytrader.com/en/odds/football/"
])

input("Presiona ENTER aquí cuando hayas resuelto el captcha y navegado la página...")
print("Listo. Ahora corre scraper_cuotas.py")
