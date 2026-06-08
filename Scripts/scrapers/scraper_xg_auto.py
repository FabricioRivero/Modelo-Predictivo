# scraper_xg_auto.py
# Fuente: fbref.com — descarga a través de Playwright con perfil de Brave
# Output: D:\MODELO DE PREDICCION\Codigo\xg_partidos.csv

import csv
import re
import time
import random
import logging
import pandas as pd
from io import StringIO
from pathlib import Path
from datetime import datetime

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PWTimeout,
    Error as PWError,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            r"D:\MODELO DE PREDICCION\Codigo\scraper_xg.log",
            encoding="utf-8",
            mode="w",
        ),
    ],
)
log = logging.getLogger(__name__)

# ── Rutas y constantes ────────────────────────────────────────────────────────
OUTPUT_FILE = r"D:\MODELO DE PREDICCION\Codigo\xg_partidos.csv"
CACHE_DIR   = Path(r"D:\MODELO DE PREDICCION\Codigo\fbref_cache")
BRAVE_PATH  = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
PROFILE_DIR = r"D:\MODELO DE PREDICCION\brave_profile_st"

MAX_BROWSER_RETRIES = 3
BROWSER_RETRY_DELAY = 8
CF_WAIT_SECONDS     = 180

HEADERS = [
    "Tournament", "Confederation", "Season", "Round",
    "Date", "Venue",
    "Team", "Goals_For", "xG_For",
    "Opponent", "Goals_Against", "xG_Against",
    "xG_disponible",
]

TOURNAMENTS = [
    ("wc_2022",            "Copa Mundial Qatar 2022",              "FIFA",     "2022",
     "https://fbref.com/en/comps/1/2022/schedule/2022-FIFA-World-Cup-Scores-and-Fixtures",           True),
    ("wcq_conmebol",       "Eliminatorias CONMEBOL 2026",          "CONMEBOL", "2026",
     "https://fbref.com/en/comps/4/schedule/WCQ-CONMEBOL-Scores-and-Fixtures",                       True),
    ("copa_america_2024",  "Copa América 2024",                    "CONMEBOL", "2024",
     "https://fbref.com/en/comps/685/2024/schedule/2024-Copa-America-Scores-and-Fixtures",           True),
    ("nations_lg_2223",    "UEFA Nations League 2022-2023",        "UEFA",     "2022-2023",
     "https://fbref.com/en/comps/677/2022-2023/schedule/2022-2023-UEFA-Nations-League-Scores-and-Fixtures", True),
    ("euro_qual_2024",     "Clasificación Eurocopa 2024",          "UEFA",     "2022-2023",
     "https://fbref.com/en/comps/678/2022-2023/schedule/2022-2023-UEFA-Euro-Qualifying-Scores-and-Fixtures", True),
    ("euro_2024",          "Eurocopa Alemania 2024",               "UEFA",     "2024",
     "https://fbref.com/en/comps/676/2024/schedule/2024-UEFA-Euro-Scores-and-Fixtures",              True),
    ("nations_lg_2425",    "UEFA Nations League 2024-2025",        "UEFA",     "2024-2025",
     "https://fbref.com/en/comps/690/2024-2025/schedule/2024-2025-UEFA-Nations-League-Scores-and-Fixtures", True),
    ("wcq_uefa",           "Eliminatorias UEFA 2026",              "UEFA",     "2024-2025",
     "https://fbref.com/en/comps/6/2024-2025/schedule/2024-2025-WCQ-UEFA-Scores-and-Fixtures",      True),
    ("concacaf_nl_2223",   "CONCACAF Nations League 2022-2023",    "CONCACAF", "2022-2023",
     "https://fbref.com/en/comps/680/2022-2023/schedule/2022-2023-CONCACAF-Nations-League-Scores-and-Fixtures", False),
    ("gold_cup_2023",      "Copa Oro CONCACAF 2023",               "CONCACAF", "2023",
     "https://fbref.com/en/comps/681/2023/schedule/2023-Gold-Cup-Scores-and-Fixtures",               True),
    ("concacaf_nl_2324",   "CONCACAF Nations League 2023-2024",    "CONCACAF", "2023-2024",
     "https://fbref.com/en/comps/680/2023-2024/schedule/2023-2024-CONCACAF-Nations-League-Scores-and-Fixtures", False),
    ("concacaf_nl_2425",   "CONCACAF Nations League 2024-2025",    "CONCACAF", "2024-2025",
     "https://fbref.com/en/comps/680/2024-2025/schedule/2024-2025-CONCACAF-Nations-League-Scores-and-Fixtures", False),
    ("gold_cup_2025",      "Copa Oro CONCACAF 2025",               "CONCACAF", "2025",
     "https://fbref.com/en/comps/681/2025/schedule/2025-Gold-Cup-Scores-and-Fixtures",               True),
    ("wcq_concacaf",       "Eliminatorias CONCACAF 2026",          "CONCACAF", "2026",
     "https://fbref.com/en/comps/3/schedule/WCQ-CONCACAF-Scores-and-Fixtures",                       False),
    ("afcon_qual_2023",    "Clasificación AFCON 2023",             "CAF",      "2022-2023",
     "https://fbref.com/en/comps/660/2022-2023/schedule/2022-2023-Africa-Cup-of-Nations-Qualifying-Scores-and-Fixtures", False),
    ("afcon_2023",         "Copa Africana de Naciones 2023",       "CAF",      "2023",
     "https://fbref.com/en/comps/656/2023/schedule/2023-Africa-Cup-of-Nations-Scores-and-Fixtures",  True),
    ("afcon_qual_2025",    "Clasificación AFCON 2025",             "CAF",      "2023-2024",
     "https://fbref.com/en/comps/657/2023-2024/schedule/2023-2024-Africa-Cup-of-Nations-Qualifying-Scores-and-Fixtures", False),
    ("afcon_2025",         "Copa Africana de Naciones 2025",       "CAF",      "2025",
     "https://fbref.com/en/comps/656/2025/schedule/2025-Africa-Cup-of-Nations-Scores-and-Fixtures",  True),
    ("wcq_caf",            "Eliminatorias CAF 2026",               "CAF",      "2025",
     "https://fbref.com/en/comps/2/schedule/WCQ-CAF-Scores-and-Fixtures",                            False),
    ("asian_cup_qual_2023","Clasificación Copa Asiática 2023",     "AFC",      "2022-2023",
     "https://fbref.com/en/comps/665/2022-2023/schedule/2022-2023-AFC-Asian-Cup-Qualifying-Scores-and-Fixtures", False),
    ("asian_cup_2023",     "Copa Asiática AFC 2023",               "AFC",      "2023",
     "https://fbref.com/en/comps/664/2023/schedule/2023-AFC-Asian-Cup-Scores-and-Fixtures",          True),
    ("wcq_afc",            "Eliminatorias AFC 2026",               "AFC",      "2026",
     "https://fbref.com/en/comps/7/schedule/WCQ-AFC-Scores-and-Fixtures",                            True),
    ("ofc_nations_2024",   "Copa de Naciones OFC 2024",            "OFC",      "2024",
     "https://fbref.com/en/comps/257/2024/schedule/2024-OFC-Nations-Cup-Scores-and-Fixtures",        False),
    ("wcq_ofc",            "Eliminatorias OFC 2026",               "OFC",      "2026",
     "https://fbref.com/en/comps/5/schedule/WCQ-OFC-Scores-and-Fixtures",                            False),
]

# ── Variables globales de Playwright ─────────────────────────────────────────
_pw_playwright = None
_pw_context    = None
_pw_page       = None

# ── Gestión del navegador ─────────────────────────────────────────────────────

def _apply_stealth_scripts(page) -> None:
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'platform',  {get: () => 'Win32'});
        window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (params) =>
            params.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(params);
    """)

def _safe_close_browser() -> None:
    global _pw_playwright, _pw_context, _pw_page
    _pw_page = None
    if _pw_context is not None:
        try:
            _pw_context.close()
            log.debug("Contexto cerrado.")
        except Exception as exc:
            log.debug("Error cerrando contexto: %s", exc)
        _pw_context = None
    if _pw_playwright is not None:
        try:
            _pw_playwright.stop()
            log.debug("Playwright detenido.")
        except Exception as exc:
            log.debug("Error deteniendo Playwright: %s", exc)
        _pw_playwright = None

def init_browser() -> None:
    global _pw_playwright, _pw_context, _pw_page
    _safe_close_browser()
    log.info("Iniciando Playwright y navegador Brave...")
    try:
        _pw_playwright = sync_playwright().start()
        _pw_context = _pw_playwright.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            executable_path=BRAVE_PATH,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        pages = _pw_context.pages
        _pw_page = pages[0] if pages else _pw_context.new_page()
        _apply_stealth_scripts(_pw_page)
        log.info("Navegador listo. URL inicial: %s", _pw_page.url)
    except Exception as exc:
        log.critical("No se pudo iniciar el navegador: %s", exc, exc_info=True)
        raise

def close_browser() -> None:
    log.info("Cerrando navegador...")
    _safe_close_browser()

def reinit_browser(attempt: int = 1) -> bool:
    log.warning("Reiniciando navegador (intento %d/%d)...", attempt, MAX_BROWSER_RETRIES)
    time.sleep(BROWSER_RETRY_DELAY * attempt)
    try:
        init_browser()
        log.info("Navegador reiniciado exitosamente.")
        return True
    except Exception as exc:
        log.error("Fallo al reiniciar: %s", exc)
        return False

def _recover_page() -> bool:
    """Recuperación ligera: abre un tab nuevo si el contexto sigue vivo."""
    global _pw_page, _pw_context
    if _pw_context is None:
        return False
    try:
        log.info("Recuperación ligera: abriendo nuevo tab...")
        _pw_page = _pw_context.new_page()
        _apply_stealth_scripts(_pw_page)
        _pw_page.goto("about:blank", timeout=5_000)
        log.info("Recuperación ligera exitosa.")
        return True
    except Exception as exc:
        log.warning("Recuperación ligera fallida: %s", exc)
        _pw_page = None
        return False

# ── Salud del navegador ───────────────────────────────────────────────────────

def is_browser_alive() -> bool:
    if _pw_context is None or _pw_page is None:
        log.debug("is_browser_alive → False (objetos None)")
        return False
    try:
        _ = _pw_page.url
        _pw_page.evaluate("1 + 1")
        return True
    except PWError as exc:
        log.warning("is_browser_alive → False: %s", exc)
        return False
    except Exception as exc:
        log.warning("is_browser_alive → False (inesperado): %s", exc)
        return False

def _is_cloudflare_challenge(page) -> bool:
    CF_TITLE_KEYWORDS = [
        "moment", "momento", "verify", "checking", "just a moment",
        "attention required", "cloudflare", "challenge", "blocked",
    ]
    CF_URL_PATTERNS = [
        "/cdn-cgi/challenge-platform",
        "challenges.cloudflare.com",
        "__cf_chl",
    ]
    try:
        title = page.title().lower()
        url   = page.url.lower()
    except Exception:
        return False
    return (
        any(kw in title for kw in CF_TITLE_KEYWORDS) or
        any(pat in url  for pat in CF_URL_PATTERNS)
    )

def _ensure_live_page() -> bool:
    """
    Garantiza que hay una página utilizable antes de navegar.
    Nivel 1: nuevo tab (rápido, si el contexto vive).
    Nivel 2: reinicio completo del navegador.
    """
    if is_browser_alive():
        return True
    log.warning("Página muerta. Intentando recuperación ligera...")
    if _recover_page() and is_browser_alive():
        return True
    log.warning("Recuperación ligera insuficiente. Reiniciando navegador completo...")
    for attempt in range(1, MAX_BROWSER_RETRIES + 1):
        if reinit_browser(attempt) and is_browser_alive():
            return True
        log.error("Reintento %d/%d fallido.", attempt, MAX_BROWSER_RETRIES)
    log.error("No se pudo recuperar el navegador.")
    return False

# ── Helpers de datos ──────────────────────────────────────────────────────────

def clean(v) -> str:
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "—", "-", "") else s

def parse_score(score_str: str):
    s = re.sub(r'\(.*?\)', '', str(score_str)).strip()
    m = re.search(r'(\d+)\s*[–\-:]\s*(\d+)', s)
    return (m.group(1), m.group(2)) if m else ("", "")

def find_col(df, *candidates):
    for c in candidates:
        if c in df.columns:
            return c
    for c in candidates:
        hits = [col for col in df.columns if c in str(col).lower()]
        if hits:
            return hits[0]
    return None

# ── Descarga con caché y Playwright ───────────────────────────────────────────

def get_html(url: str, slug: str) -> str | None:
    """
    Descarga el HTML de *url* usando caché local cuando sea válido.
    NUNCA llama a reinit_browser() — solo retorna None si algo falla.
    La recuperación del navegador es responsabilidad exclusiva de main().
    """
    global _pw_page
    cache_file = CACHE_DIR / f"{slug}.html"

    # Etapa 1: caché
    if cache_file.exists():
        content = cache_file.read_text(encoding="utf-8", errors="ignore")
        if "sched_all" in content or len(content) > 100_000:
            log.info("[caché] %s.html (%d KB)", slug, len(content) // 1024)
            return content
        else:
            log.warning("[caché inválido] %s (%d bytes) — eliminando.", slug, len(content))
            cache_file.unlink()

    # Etapa 2: health check (solo reportar)
    if not is_browser_alive():
        log.error("Navegador muerto en get_html() para %s.", slug)
        return None

    # Etapa 3: navegar
    log.info("Navegando → %s", url)
    try:
        _pw_page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        log.debug("goto() OK. URL: %s", _pw_page.url)
    except PWTimeout:
        log.warning("Timeout en goto() para %s. Continuando...", slug)
    except PWError as exc:
        log.error("PWError en goto() [%s]: %s", slug, exc)
        return None
    except Exception as exc:
        log.error("Error en goto() [%s]: %s", slug, exc)
        return None

    # Etapa 4: bucle de espera Cloudflare (máx CF_WAIT_SECONDS)
    deadline    = time.time() + CF_WAIT_SECONDS
    cf_reported = False
    cf_active   = False

    while time.time() < deadline:
        # CF puede cerrar el tab activamente — detectarlo aquí
        if not is_browser_alive():
            log.error("Tab cerrado por CF para %s. Retornando None.", slug)
            return None

        cf_active = _is_cloudflare_challenge(_pw_page)

        if not cf_active:
            try:
                title = _pw_page.title().strip()
            except Exception:
                log.error("No se pudo leer título para %s.", slug)
                return None
            if title:
                log.debug("CF superado. Título: '%s'", title)
                break
        else:
            if not cf_reported:
                log.warning(
                    "[CF] ⚠️  Resuelve el challenge en el navegador para '%s'. "
                    "Esperando hasta %d segundos...", slug, CF_WAIT_SECONDS,
                )
                cf_reported = True
        time.sleep(2)
    else:
        if cf_active:
            log.error("CF no resuelto en %ds para %s. Saltando.", CF_WAIT_SECONDS, slug)
            return None
        log.warning("Tiempo CF agotado para %s pero sin CF activo. Continuando...", slug)

    # Etapa 5: esperar tabla
    table_found = False
    try:
        _pw_page.wait_for_selector("table#sched_all", timeout=15_000)
        table_found = True
        log.debug("Tabla #sched_all encontrada.")
    except PWTimeout:
        log.warning("Tabla no apareció en 15s para %s.", slug)
    except PWError as exc:
        log.error("PWError esperando tabla [%s]: %s", slug, exc)
        return None

    if not table_found and _is_cloudflare_challenge(_pw_page):
        log.error("Bloqueado por CF (tabla no cargó) para %s.", slug)
        return None

    # Etapa 6: obtener y validar HTML
    time.sleep(random.uniform(2, 4))
    try:
        html = _pw_page.content()
    except PWError as exc:
        log.error("Error obteniendo content() para %s: %s", slug, exc)
        return None

    size_kb = len(html) // 1024
    if len(html) < 50_000:
        log.warning("HTML muy pequeño (%d KB) para %s — descartando.", size_kb, slug)
        return None

    if "sched_all" not in html:
        log.warning("HTML %d KB para %s sin 'sched_all' — no se cachea.", size_kb, slug)
    else:
        cache_file.write_text(html, encoding="utf-8")
        log.info("✓ %d KB guardados en caché para %s", size_kb, slug)

    time.sleep(random.uniform(3, 6))
    return html

# ── Parser ────────────────────────────────────────────────────────────────────

def parse_schedule(html, comp_name, confederation, season, tiene_xg) -> list:
    df = None
    try:
        tables = pd.read_html(StringIO(html), attrs={"id": "sched_all"})
        if tables:
            df = tables[0]
    except Exception:
        pass

    if df is None:
        try:
            for t in sorted(pd.read_html(StringIO(html)), key=len, reverse=True):
                cols = " ".join(str(c).lower() for c in t.columns)
                if ("home" in cols or "local" in cols) and ("away" in cols or "visit" in cols):
                    df = t
                    break
        except Exception:
            pass

    if df is None:
        log.warning("✗ No se encontró tabla para %s", comp_name)
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join(str(c) for c in col if "Unnamed" not in str(c)).strip("_")
            for col in df.columns
        ]

    df.columns = [
        str(c).strip().lower()
          .replace(" ", "_").replace("(", "").replace(")", "")
          .replace("/", "_").replace("%", "pct")
        for c in df.columns
    ]

    col_date  = find_col(df, "date", "fecha")
    col_round = find_col(df, "round", "wk", "matchweek", "stage", "ronda")
    col_home  = find_col(df, "home", "local", "home_team")
    col_away  = find_col(df, "away", "visitor", "visitante", "away_team")
    col_score = find_col(df, "score", "result", "resultado", "ftr", "marcador")
    col_venue = find_col(df, "venue", "estadio", "ground")

    xg_cols     = [c for c in df.columns if re.fullmatch(r"xg\.?\d*", c)]
    col_xg_home = xg_cols[0] if len(xg_cols) >= 1 else None
    col_xg_away = xg_cols[1] if len(xg_cols) >= 2 else None

    if not all([col_home, col_away, col_score]):
        log.warning("✗ Columnas faltantes para %s: home=%s away=%s score=%s",
                    comp_name, col_home, col_away, col_score)
        log.debug("Columnas disponibles: %s", list(df.columns))
        return []

    xg_tag = "Si" if tiene_xg else "No"
    rows   = []

    for _, row in df.iterrows():
        home  = clean(row.get(col_home, ""))
        away  = clean(row.get(col_away, ""))
        score = clean(row.get(col_score, ""))
        if not home or not away:
            continue
        if home.lower() in ("home", "local", "squad"):
            continue
        if not score or score in ("vs.", "v", "–", "-"):
            continue
        gf, ga = parse_score(score)
        if not gf and not ga:
            continue

        date  = clean(row[col_date])  if col_date  else ""
        rnd   = clean(row[col_round]) if col_round else ""
        venue = clean(row[col_venue]) if col_venue else ""
        xgf   = clean(row[col_xg_home]) if col_xg_home else ""
        xga   = clean(row[col_xg_away]) if col_xg_away else ""

        base = dict(Tournament=comp_name, Confederation=confederation,
                    Season=season, Round=rnd, Date=date, Venue=venue,
                    xG_disponible=xg_tag)
        rows.append({**base, "Team": home, "Goals_For": gf, "xG_For": xgf,
                               "Opponent": away, "Goals_Against": ga, "xG_Against": xga})
        rows.append({**base, "Team": away, "Goals_For": ga, "xG_For": xga,
                               "Opponent": home, "Goals_Against": gf, "xG_Against": xgf})
    return rows

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    start_time = datetime.now()
    log.info("=" * 70)
    log.info("  SCRAPER xG — SELECCIONES NACIONALES")
    log.info("  Inicio: %s", start_time.strftime("%Y-%m-%d %H:%M"))
    log.info("=" * 70)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Si aparece Cloudflare, resuélvelo manualmente en el navegador.")
    log.info("Los torneos siguientes usarán las cookies del perfil guardado.")

    init_browser()

    all_rows           = []
    failed_tournaments = []

    try:
        total = len(TOURNAMENTS)
        for idx, (slug, comp_name, confederation, season, url, tiene_xg) in enumerate(TOURNAMENTS, 1):
            tag = "✓ xG" if tiene_xg else "~ sin xG"
            log.info("  [%d/%d | %s] %s (%s)", idx, total, tag, comp_name, season)

            # Asegurar página viva ANTES de cada torneo
            if not _ensure_live_page():
                reason = "navegador irrecuperable"
                log.error("  ✗ '%s': %s", comp_name, reason)
                failed_tournaments.append((comp_name, reason))
                log.info("")
                continue

            # Descarga con reintentos
            html = None
            for attempt in range(1, MAX_BROWSER_RETRIES + 1):
                try:
                    html = get_html(url, slug)
                    if html is not None:
                        break
                    # None devuelto: tab posiblemente cerrado por CF
                    if attempt < MAX_BROWSER_RETRIES:
                        log.warning("  Intento %d/%d fallido para '%s'. Recuperando...",
                                    attempt, MAX_BROWSER_RETRIES, comp_name)
                        time.sleep(3 * attempt)
                        if not _ensure_live_page():
                            log.error("  Irrecuperable para '%s'.", comp_name)
                            break
                    else:
                        log.error("  Todos los intentos agotados para '%s'.", comp_name)

                except (PWError, PWTimeout) as exc:
                    log.error("  PWError en '%s' (intento %d): %s", comp_name, attempt, exc)
                    if attempt < MAX_BROWSER_RETRIES:
                        if not _ensure_live_page():
                            break
                except Exception as exc:
                    log.exception("  Error inesperado para '%s': %s", comp_name, exc)
                    break

            if html is None:
                failed_tournaments.append((comp_name, "descarga fallida"))
                log.warning("  ✗ Sin HTML para '%s'.", comp_name)
                log.info("")
                continue

            rows    = parse_schedule(html, comp_name, confederation, season, tiene_xg)
            matches = len(rows) // 2
            con_xg  = sum(1 for r in rows if r.get("xG_For")) // 2

            if not rows:
                failed_tournaments.append((comp_name, "parse fallido"))
                log.warning("  ✗ Sin datos para '%s'.", comp_name)
                log.info("")
                continue

            log.info("  → %d partidos | %d con xG", matches, con_xg)
            all_rows.extend(rows)
            log.info("")

    finally:
        close_browser()

    if not all_rows:
        log.error("Sin datos para guardar.")
        return

    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in HEADERS})

    elapsed       = (datetime.now() - start_time).seconds
    total_matches = len(all_rows) // 2
    con_xg_total  = sum(1 for r in all_rows if r.get("xG_For")) // 2

    log.info("=" * 70)
    log.info("  CSV: %s", OUTPUT_FILE)
    log.info("  Total: %d partidos | Con xG: %d | Tiempo: %dm %ds",
             total_matches, con_xg_total, elapsed // 60, elapsed % 60)
    if failed_tournaments:
        log.warning("  Torneos con error (%d):", len(failed_tournaments))
        for name, reason in failed_tournaments:
            log.warning("    • %s → %s", name, reason)
    else:
        log.info("  Todos los torneos completados sin errores.")
    log.info("=" * 70)

if __name__ == "__main__":
    main()
