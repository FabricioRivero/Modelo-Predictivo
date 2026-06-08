"""
config.py — Configuración central del proyecto Modelo Predictivo
================================================================
Todas las rutas, API keys y parámetros del modelo en un solo lugar.
Importa este módulo en cualquier script con:

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Config'))
    from config import *
"""

import os

# ══════════════════════════════════════════════════════════════
# RAÍZ DEL PROYECTO
# ══════════════════════════════════════════════════════════════
# Detecta automáticamente si estás en Windows (D:\MODELO DE PREDICCION)
# o en Google Colab (/content/Modelo-Predictivo)
_THIS_FILE   = os.path.abspath(__file__)           # .../Config/config.py
REPO_ROOT    = os.path.dirname(os.path.dirname(_THIS_FILE))   # raíz del repo

# ══════════════════════════════════════════════════════════════
# CARPETAS PRINCIPALES
# ══════════════════════════════════════════════════════════════
DATOS_DIR    = os.path.join(REPO_ROOT, "Datos")
SCRIPTS_DIR  = os.path.join(REPO_ROOT, "Scripts")
REPORTES_DIR = os.path.join(REPO_ROOT, "Reportes")
CONFIG_DIR   = os.path.join(REPO_ROOT, "Config")

# ── Sub-carpetas de Datos ─────────────────────────────────────
JLEAGUE_DIR      = os.path.join(DATOS_DIR, "jleague")
INTL_DIR         = os.path.join(DATOS_DIR, "internacional")
RANKINGS_DIR     = os.path.join(DATOS_DIR, "rankings")
ENGLAND_DIR      = os.path.join(DATOS_DIR, "england")

# ── Sub-carpetas de Scripts ───────────────────────────────────
PRINCIPALES_DIR  = os.path.join(SCRIPTS_DIR, "principales")
SCRAPERS_DIR     = os.path.join(SCRIPTS_DIR, "scrapers")
UTILIDADES_DIR   = os.path.join(SCRIPTS_DIR, "utilidades")

# ══════════════════════════════════════════════════════════════
# ARCHIVOS DE DATOS — J-LEAGUE
# ══════════════════════════════════════════════════════════════
JPN_CSV          = os.path.join(JLEAGUE_DIR, "JPN.csv")
J1_STATS_CSV     = os.path.join(JLEAGUE_DIR, "J1_League_Player_Stats_2022_2025.csv")
J1_MATCHES_CSV   = os.path.join(JLEAGUE_DIR, "J1_League_Matches_2022_2025.csv")

# ══════════════════════════════════════════════════════════════
# ARCHIVOS DE DATOS — INTERNACIONAL
# ══════════════════════════════════════════════════════════════
RESULTS_CSV          = os.path.join(INTL_DIR, "results.csv")
FORMER_NAMES_CSV     = os.path.join(INTL_DIR, "former_names.csv")
GOALSCORERS_CSV      = os.path.join(INTL_DIR, "goalscorers.csv")
SHOOTOUTS_CSV        = os.path.join(INTL_DIR, "shootouts.csv")
PATCH_2026_CSV       = os.path.join(INTL_DIR, "results_2026_patch.csv")
PARTIDOS_INTL_CSV    = os.path.join(INTL_DIR, "partidos_internacionales.csv")
PARTIDOS_CONV_CSV    = os.path.join(INTL_DIR, "partidos_convertidos.csv")
CUOTAS_HOY_CSV       = os.path.join(INTL_DIR, "cuotas_hoy.csv")  # generado por scraper

# ══════════════════════════════════════════════════════════════
# ARCHIVOS DE DATOS — RANKINGS FIFA
# ══════════════════════════════════════════════════════════════
# El script carga el primero que encuentre (en orden de prioridad)
FIFA_RANKING_CANDIDATES = [
    os.path.join(INTL_DIR,    "ranking_fifa.csv"),       # 2026 — más reciente
    os.path.join(RANKINGS_DIR, "fifa_mens_rank.csv"),
    os.path.join(RANKINGS_DIR, "fifa_ranking-2024-06-20.csv"),
    os.path.join(RANKINGS_DIR, "fifa_ranking-2024-04-04.csv"),
    os.path.join(RANKINGS_DIR, "fifa_ranking-2023-07-20.csv"),
]

# ══════════════════════════════════════════════════════════════
# REPORTES (generados automáticamente, en .gitignore)
# ══════════════════════════════════════════════════════════════
JLEAGUE_REPORT_HTML     = os.path.join(REPORTES_DIR, "jleague_report.html")
BACKTEST_REPORT_HTML    = os.path.join(REPORTES_DIR, "backtest_report.html")
BACKTEST_CSV            = os.path.join(REPORTES_DIR, "backtest_results.csv")
INTL_REPORT_HTML        = os.path.join(REPORTES_DIR, "international_report.html")
INTL_BACKTEST_HTML      = os.path.join(REPORTES_DIR, "backtest_intl_report.html")
INTL_BACKTEST_CSV       = os.path.join(REPORTES_DIR, "backtest_intl_results.csv")

# ══════════════════════════════════════════════════════════════
# API KEYS
# ══════════════════════════════════════════════════════════════
API_KEY_ODDS     = "07fed81a038a0eb0b8c6c4abedcdcd35"   # The Odds API → cuotas Pinnacle
API_KEY_FOOTBALL = "f7de0f5bd4e48491c6e02aefa322d67a"   # API-Football  → convocados/lesionados

# ══════════════════════════════════════════════════════════════
# PARÁMETROS DEL MODELO — J-LEAGUE
# ══════════════════════════════════════════════════════════════
XI_JLEAGUE           = 0.00325   # time decay J-League
N_SIM_JLEAGUE        = 100_000   # simulaciones Monte Carlo
FORM_MATCHES_JLEAGUE = 6         # partidos recientes con peso extra
FORM_BOOST_JLEAGUE   = 2.5       # multiplicador peso forma reciente

# Umbrales value bet J-League (calibrados con backtest: visitante +11.2%, local -9.2%)
VT_HOME_JLEAGUE = 0.08   # local: umbral alto (ROI negativo histórico)
VT_AWAY_JLEAGUE = 0.04   # visitante: umbral estándar
FORM_MIN_HOME_JLEAGUE = 1.5
FORM_MIN_AWAY_JLEAGUE = 1.2
DRAW_ENABLED_JLEAGUE  = False   # empates desactivados (ROI -46%)

# ══════════════════════════════════════════════════════════════
# PARÁMETROS DEL MODELO — INTERNACIONAL
# ══════════════════════════════════════════════════════════════
XI_INTL           = 0.00180   # time decay más suave (selecciones juegan menos)
N_SIM_INTL        = 100_000
FORM_MATCHES_INTL = 8         # últimos 8 partidos
TRAIN_FROM_INTL   = 2010      # datos desde 2010

# Umbrales value bet Internacional (calibrados con backtest: local +5.4%, visitante -12.3%)
VT_HOME_INTL = 0.05   # local: umbral (ROI positivo histórico)
VT_AWAY_INTL = 0.99   # visitante: DESACTIVADO (ROI -12.3%)
FORM_MIN_HOME_INTL = 1.3
FORM_MIN_AWAY_INTL = 1.0
DRAW_ENABLED_INTL  = False

# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════
def ensure_dirs():
    """Crea las carpetas de output si no existen."""
    os.makedirs(REPORTES_DIR, exist_ok=True)
    os.makedirs(INTL_DIR, exist_ok=True)

if __name__ == "__main__":
    print("=== Configuración del Proyecto ===")
    print(f"REPO_ROOT:    {REPO_ROOT}")
    print(f"JPN_CSV:      {JPN_CSV}  — existe: {os.path.exists(JPN_CSV)}")
    print(f"RESULTS_CSV:  {RESULTS_CSV}  — existe: {os.path.exists(RESULTS_CSV)}")
    for p in FIFA_RANKING_CANDIDATES:
        if os.path.exists(p):
            print(f"RANKING FIFA: {p}  ✓")
            break
    print(f"REPORTES_DIR: {REPORTES_DIR}")
