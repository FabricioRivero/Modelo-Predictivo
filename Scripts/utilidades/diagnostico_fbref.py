# diagnostico_fbref.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
URL = "https://fbref.com/en/comps/1/2022/schedule/2022-FIFA-World-Cup-Scores-and-Fixtures"

options = Options()
options.binary_location = BRAVE_PATH
options.add_argument("--no-sandbox")
options.add_argument("--window-size=1440,900")
# SIN headless para ver qué pasa

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

driver.get(URL)
import time
time.sleep(8)

html = driver.page_source
print(f"Tamaño HTML: {len(html)//1024} KB")
print(f"Título: {driver.title}")
print(f"Tiene sched_all: {'sched_all' in html}")
print(f"Tiene Cloudflare: {'Just a moment' in html or 'cf-browser' in html}")
print(html[:2000])

driver.quit()