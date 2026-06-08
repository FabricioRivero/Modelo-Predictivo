# ranking_fifa.py
# Fuente: inside.fifa.com/es/fifa-world-ranking/men
# Output: D:\MODELO DE PREDICCION\Codigo\ranking_fifa.csv

import csv
import json
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_FILE = r"D:\MODELO DE PREDICCION\Codigo\ranking_fifa.csv"
URL         = "https://inside.fifa.com/es/fifa-world-ranking/men"
PROFILE_DIR = r"D:\MODELO DE PREDICCION\brave_profile_fifa"
BRAVE_PATH  = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

HEADERS = ["date", "semester", "rank", "prev_rank", "team", "acronym",
           "confederation", "total.points", "previous.points", "diff.points",
           "ranked_matches", "ranking_movement"]

def get_semester():
    return 1 if datetime.today().month <= 6 else 2

def parse_entries(entries):
    ranking = []
    today   = datetime.today()
    year    = today.year
    sem     = get_semester()

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        # TeamName es lista de {Locale, Description}
        team = ""
        team_list = entry.get("TeamName", [])
        if isinstance(team_list, list) and team_list:
            # Preferir español, si no el primero
            es = next((x for x in team_list if "es" in x.get("Locale", "").lower()), None)
            team = (es or team_list[0]).get("Description", "")
        elif isinstance(team_list, str):
            team = team_list

        total_pts = entry.get("TotalPoints", "")
        prev_pts  = entry.get("PrevPoints", "")

        diff_pts = ""
        try:
            if total_pts != "" and prev_pts != "":
                diff_pts = round(float(total_pts) - float(prev_pts), 4)
        except (ValueError, TypeError):
            pass

        ranking.append({
            "date":              year,
            "semester":          sem,
            "rank":              entry.get("Rank", ""),
            "prev_rank":         entry.get("PrevRank", ""),
            "team":              team,
            "acronym":           entry.get("IdCountry", ""),
            "confederation":     entry.get("ConfederationName", ""),
            "total.points":      round(float(total_pts), 6) if total_pts != "" else "",
            "previous.points":   round(float(prev_pts), 6)  if prev_pts  != "" else "",
            "diff.points":       diff_pts,
            "ranked_matches":    entry.get("RatedMatches", ""),
            "ranking_movement":  entry.get("RankingMovement", ""),
        })

    return ranking

def main():
    ranking  = []
    api_data = {}

    with sync_playwright() as pw:

        def on_response(response):
            if "fifarankings/rankings" in response.url and "rankingMatches" not in response.url:
                try:
                    body = response.json()
                    api_data["body"] = body
                    print(f"  [API] Capturada: {response.url}")
                except Exception as e:
                    print(f"  [API] Error: {e}")

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
            locale="es-ES",
        )

        page = context.new_page()
        page.on("response", on_response)

        print(f"  Abriendo {URL}...")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass

        print("  Esperando contenido...")
        try:
            page.wait_for_selector("table tbody tr", timeout=30000)
        except Exception:
            pass
        time.sleep(6)

        print("  Scroll para cargar todos los registros...")
        for _ in range(20):
            page.keyboard.press("End")
            time.sleep(0.5)
        time.sleep(3)

        if api_data.get("body"):
            body    = api_data["body"]
            entries = body.get("Results", []) if isinstance(body, dict) else body
            print(f"  {len(entries)} entradas en API")
            ranking = parse_entries(entries)

        context.close()

    if not ranking:
        print("\nNo se obtuvieron datos.")
        return

    ranking = ranking[:100]

    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for row in ranking:
            writer.writerow({k: row.get(k, "") for k in HEADERS})

    print(f"\nCSV guardado: {OUTPUT_FILE}")
    print(f"{len(ranking)} selecciones\n")
    print(f"{'RK':>4} {'PRV':>4} {'TEAM':<28} {'ACR':<5} {'CONF':<10} {'POINTS':>12} {'PREV':>12} {'DIFF':>9} {'MOV':>4}")
    print("-" * 100)
    for r in ranking[:20]:
        print(
            f"{str(r['rank']):>4} {str(r['prev_rank']):>4} "
            f"{str(r['team']):<28} {str(r['acronym']):<5} "
            f"{str(r['confederation']):<10} "
            f"{str(r['total.points']):>12} {str(r['previous.points']):>12} "
            f"{str(r['diff.points']):>9} {str(r['ranking_movement']):>4}"
        )
    if len(ranking) > 20:
        print(f"  ... y {len(ranking)-20} más")

if __name__ == "__main__":
    main()