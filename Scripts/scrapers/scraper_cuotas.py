# scraper_cuotas.py
# Fuente: sportytrader.com — extracción desde lista principal
# Output: D:\MODELO DE PREDICCION\Codigo\cuotas_hoy.csv

import csv
import re
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

OUTPUT_FILE = r"D:\MODELO DE PREDICCION\Codigo\cuotas_hoy.csv"
DAYS_AHEAD  = 7
LIST_URL    = "https://www.sportytrader.com/en/odds/football/"
PROFILE_DIR = r"D:\MODELO DE PREDICCION\brave_profile_st"
BRAVE_PATH  = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

HEADERS = ["home_team", "away_team", "date", "odds_home", "odds_draw", "odds_away", "source"]

MONTHS_EN = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
    "sep":9,"oct":10,"nov":11,"dec":12,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_cloudflare(title: str) -> bool:
    t = title.lower()
    return any(x in t for x in ["moment", "momento", "human", "checking", "verify", "verificar"])

def is_valid_date(date_str: str) -> bool:
    try:
        dt  = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.today()
        return now.date() <= dt.date() <= (now + timedelta(days=DAYS_AHEAD)).date()
    except Exception:
        return False

def to_float(s):
    if not s:
        return None
    s = str(s).strip().replace(",", ".")
    if s in ("-", "N/A", "", "?", "—"):
        return None
    try:
        v = float(s)
        return v if 1.01 <= v <= 100 else None
    except ValueError:
        return None

def new_stealth_page(context):
    page = context.new_page()
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    """)
    return page

# ── Esperar página lista ──────────────────────────────────────────────────────

def wait_page_ready(page, max_wait=300) -> bool:
    deadline = time.time() + max_wait
    primer_aviso = True
    while time.time() < deadline:
        try:
            title = page.title()
        except Exception:
            return False
        if not is_cloudflare(title) and title.strip():
            return True
        if primer_aviso:
            print("    [CF] Cloudflare activo — haz clic en el checkbox del navegador...")
            primer_aviso = False
        time.sleep(2)
    return False

# ── Extraer con JavaScript ────────────────────────────────────────────────────

def extract_with_js(page) -> list:
    print("  Extrayendo datos con JavaScript...")
    data = page.evaluate("""
        () => {
            const results = [];
            const blocks = document.querySelectorAll('div[data-navigation-url-value*="/en/odds/"]');
            
            blocks.forEach(block => {
                const url = block.getAttribute('data-navigation-url-value');
                if (!url || !/\\/en\\/odds\\/[a-z0-9][a-z0-9-]+-\\d{5,}\\/?$/.test(url)) return;

                // Equipos
                const matchLink = block.querySelector('a[href*="/en/odds/"]');
                const matchText = matchLink ? matchLink.innerText.trim() : '';

                // Fecha
                const spans = block.querySelectorAll('span');
                let dateRaw = '';
                spans.forEach(s => {
                    if (/\\d{2} [A-Za-z]{3} - \\d{2}:\\d{2}/.test(s.innerText) || 
                        /\\d{2} [A-Za-z]+ \\d{4}/.test(s.innerText) ||
                        /\\d{2} [A-Za-z]{3,}/.test(s.innerText)) {
                        dateRaw = s.innerText.trim();
                    }
                });

                // Cuotas — buscar divs con bg-primary-yellow (valor) y bg-gray-50 (tipo 1/X/2)
                const oddsLinks = block.querySelectorAll('a[href*="/en/book/"]');
                const odds = {};
                const sources = {};
                oddsLinks.forEach(link => {
                    const typeDiv = link.querySelector('div.bg-gray-50');
                    const valDiv  = link.querySelector('div.bg-primary-yellow');
                    if (!typeDiv || !valDiv) return;
                    const tipo = typeDiv.innerText.trim();  // "1", "X", "2"
                    const val  = parseFloat(valDiv.innerText.trim().replace(',', '.'));
                    const bm   = link.getAttribute('href').match(/\\/en\\/book\\/([^\\/]+)\\//);
                    if (!isNaN(val) && val >= 1.01 && val <= 100) {
                        odds[tipo] = val;
                        if (bm) sources[tipo] = bm[1];
                    }
                });

                results.push({
                    url:     url,
                    match:   matchText,
                    dateRaw: dateRaw,
                    o1:      odds['1'] || null,
                    ox:      odds['X'] || null,
                    o2:      odds['2'] || null,
                    src1:    sources['1'] || '',
                    srcX:    sources['X'] || '',
                    src2:    sources['2'] || '',
                });
            });
            return results;
        }
    """)
    return data

# ── Parsear datos crudos ──────────────────────────────────────────────────────

def parse_js_data(js_data: list) -> list:
    rows = []
    seen = set()

    for item in js_data:
        url = item.get("url", "")
        if url in seen:
            continue
        seen.add(url)

        # Equipos desde el texto del partido (más fiable que el slug)
        match_text = item.get("match", "")
        if " - " in match_text:
            parts = match_text.split(" - ", 1)
            home = parts[0].strip()
            away = parts[1].strip()
        else:
            # Fallback al slug
            m = re.search(r"/en/odds/([a-z0-9][a-z0-9-]+)-(\d{5,})/?$", url)
            if not m:
                continue
            slug  = m.group(1)
            parts = slug.split("-")
            mid   = len(parts) // 2
            home  = " ".join(parts[:mid]).title()
            away  = " ".join(parts[mid:]).title()

        # Fecha — formato "07 Jun - 19:00" o similar
        date_str = ""
        date_raw = item.get("dateRaw", "")
        # Intentar "07 Jun - 19:00"
        dm = re.search(r"(\d{1,2})\s+([A-Za-z]{3,})", date_raw)
        if dm:
            day   = int(dm.group(1))
            month = MONTHS_EN.get(dm.group(2).lower())
            year  = datetime.today().year
            if month:
                # Si el mes es anterior al actual, es el año siguiente
                if month < datetime.today().month:
                    year += 1
                try:
                    date_str = datetime(year, month, day).strftime("%Y-%m-%d")
                except ValueError:
                    pass

        o1 = item.get("o1")
        ox = item.get("ox")
        o2 = item.get("o2")

        rows.append({
            "home_team": home,
            "away_team": away,
            "date":      date_str,
            "odds_home": o1,
            "odds_draw": ox,
            "odds_away": o2,
            "source":    f"{item.get('src1','')}|{item.get('srcX','')}|{item.get('src2','')}",
        })

    return rows

# ── CSV ───────────────────────────────────────────────────────────────────────

def save_csv(rows: list):
    if not rows:
        print("\nNo se obtuvieron cuotas válidas. CSV no generado.")
        return

    seen, unique = set(), []
    for r in rows:
        key = (r["home_team"].lower(), r["away_team"].lower(), r.get("date", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    unique.sort(key=lambda x: x.get("date", ""))

    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for row in unique:
            writer.writerow({k: row.get(k, "") for k in HEADERS})

    print(f"\nCSV guardado: {OUTPUT_FILE}")
    print(f"{len(unique)} partidos\n")
    print(f"{'HOME':<25} {'AWAY':<25} {'DATE':<12} {'1':>6} {'X':>6} {'2':>6}")
    print("-" * 85)
    for r in unique:
        print(
            f"{r['home_team']:<25} {r['away_team']:<25} {r.get('date',''):<12} "
            f"{str(r.get('odds_home','') or ''):>6} "
            f"{str(r.get('odds_draw','') or ''):>6} "
            f"{str(r.get('odds_away','') or ''):>6}"
        )

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.now()
    print("=" * 60)
    print("  SCRAPER CUOTAS - FUTBOL INTERNACIONAL")
    print(f"  Ejecutado: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Próximos {DAYS_AHEAD} días")
    print("=" * 60)

    Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            executable_path=BRAVE_PATH,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )

        page = new_stealth_page(context)

        print("\n  Abriendo sportytrader...")
        print("  Si aparece Cloudflare, haz clic en el checkbox del navegador.")
        print("  El script espera hasta 5 minutos.\n")

        try:
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass

        ok = wait_page_ready(page, max_wait=300)
        if not ok:
            print("No se pudo pasar Cloudflare. Abortando.")
            context.close()
            return

        print(f"  Título: '{page.title()}'")

        # Esperar contenido dinámico
        print("  Esperando contenido dinámico...")
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        time.sleep(5)

        # Scroll para activar lazy loading
        print("  Cargando partidos con scroll...")
        for _ in range(15):
            page.keyboard.press("End")
            time.sleep(0.8)
        page.keyboard.press("Home")
        time.sleep(3)

        print(f"  Título final: '{page.title()}'")

        # Extraer datos
        js_data = extract_with_js(page)
        print(f"  {len(js_data)} bloques encontrados")
        # Guardar HTML para inspeccionar
        with open(r"D:\MODELO DE PREDICCION\Codigo\debug.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("  HTML guardado en debug.html")

        # Muestra debug de primeros 3
        if js_data:
            print("\n  -- MUESTRA (primeros 3) --")
            for item in js_data[:3]:
                print(f"  url   : {item['url']}")
                print(f"  match : {item['match']}")
                print(f"  date  : {item['dateRaw']}")
                print(f"  1/X/2 : {item['o1']} / {item['ox']} / {item['o2']}")
                print(f"  src   : {item['src1']} | {item['srcX']} | {item['src2']}")
                print()

        context.close()

    # Parsear y guardar
    rows = parse_js_data(js_data)
    print(f"  {len(rows)} partidos parseados")
    save_csv(rows)

if __name__ == "__main__":
    main()