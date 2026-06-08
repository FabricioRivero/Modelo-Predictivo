# diagnostico7.py
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

URL = "https://www.sportytrader.com/en/odds/ecuador-guatemala-8498031/"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(6000)  # esperar más tiempo
    
    # Tomar screenshot para ver qué hay visualmente
    page.screenshot(path="screenshot.png", full_page=True)
    print("Screenshot guardado: screenshot.png")
    
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    
    # Buscar cuotas típicas de fútbol (entre 1.01 y 20.00)
    print("\n=== NUMEROS TIPO CUOTA (1.01 - 20.00) ===")
    numeros = re.findall(r"\b(\d+\.\d{2})\b", html)
    cuotas = [n for n in numeros if 1.01 <= float(n) <= 20.0]
    print(cuotas[:30])
    
    # Buscar divs con data-attributes (Stimulus/Turbo)
    print("\n=== DATA ATTRIBUTES CON 'odds' ===")
    for tag in soup.find_all(True):
        attrs = str(tag.attrs)
        if "odds" in attrs.lower() or "quota" in attrs.lower() or "odd" in attrs.lower():
            print(tag.name, tag.attrs)
            if len([x for x in [] if x]) > 10:
                break
    
    # Buscar en scripts inline
    print("\n=== SCRIPTS CON NUMEROS TIPO CUOTA ===")
    for script in soup.find_all("script"):
        txt = script.get_text()
        if re.search(r"\b[12]\.\d{2}\b", txt) and len(txt) < 5000:
            print(txt[:1000])
            print("---")
    
    browser.close()