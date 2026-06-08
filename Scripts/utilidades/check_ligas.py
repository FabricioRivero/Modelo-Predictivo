"""
Paso 1: Verificar qué partidos hay HOY/MAÑANA con cuotas.
Ejecutar: .\.venv\Scripts\python.exe check_ligas.py
"""

import urllib.request
import json
from datetime import datetime, timezone, timedelta

API_KEY = "07fed81a038a0eb0b8c6c4abedcdcd35"

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

# ── 1. Ligas de fútbol activas ──────────────────────────
print("🔍 Consultando ligas activas...\n")
sports = get(f"https://api.the-odds-api.com/v4/sports/?apiKey={API_KEY}")
soccer = [s for s in sports if s.get('group') == 'Soccer' and s.get('active')]

print(f"⚽ Ligas de fútbol con cuotas ahora: {len(soccer)}\n")
for s in soccer:
    print(f"  {s['key']:<50} {s['title']}")

# ── 2. Buscar partidos en las próximas 48 horas ─────────
print("\n\n📅 Partidos en las próximas 48 horas:\n")

ahora      = datetime.now(timezone.utc)
limite     = ahora + timedelta(hours=48)
encontrados = []

for s in soccer:
    try:
        url = (f"https://api.the-odds-api.com/v4/sports/{s['key']}/odds/"
               f"?apiKey={API_KEY}&regions=eu&markets=h2h&oddsFormat=decimal")
        events = get(url)
        for ev in events:
            ct = datetime.fromisoformat(ev['commence_time'].replace('Z', '+00:00'))
            if ahora <= ct <= limite:
                # Extraer cuotas promedio
                cuotas = {'home': None, 'draw': None, 'away': None}
                for bk in ev.get('bookmakers', [])[:3]:
                    for mkt in bk.get('markets', []):
                        if mkt['key'] == 'h2h':
                            for oc in mkt['outcomes']:
                                if oc['name'] == ev['home_team']:
                                    cuotas['home'] = oc['price']
                                elif oc['name'] == ev['away_team']:
                                    cuotas['away'] = oc['price']
                                else:
                                    cuotas['draw'] = oc['price']
                            break
                    break

                encontrados.append({
                    'liga':     s['title'],
                    'key':      s['key'],
                    'home':     ev['home_team'],
                    'away':     ev['away_team'],
                    'hora_utc': ct.strftime('%Y-%m-%d %H:%M UTC'),
                    'cuota_h':  cuotas['home'],
                    'cuota_d':  cuotas['draw'],
                    'cuota_a':  cuotas['away'],
                })
    except Exception:
        pass

if not encontrados:
    print("  No hay partidos con cuotas en las próximas 48 horas.")
else:
    print(f"  {'Liga':<30} {'Partido':<45} {'Hora':<20} {'1':>5} {'X':>5} {'2':>5}")
    print("  " + "-" * 115)
    for p in sorted(encontrados, key=lambda x: x['hora_utc']):
        partido = f"{p['home']} vs {p['away']}"
        h = f"{p['cuota_h']:.2f}" if p['cuota_h'] else "  -"
        d = f"{p['cuota_d']:.2f}" if p['cuota_d'] else "  -"
        a = f"{p['cuota_a']:.2f}" if p['cuota_a'] else "  -"
        print(f"  {p['liga']:<30} {partido:<45} {p['hora_utc']:<20} {h:>5} {d:>5} {a:>5}")

    print(f"\n  Total: {len(encontrados)} partidos encontrados")
    print("\n✅ Copia el 'key' de la liga que quieras analizar")
    print("   y el nombre EXACTO de los equipos para el modelo.")
