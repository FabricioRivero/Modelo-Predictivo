# Config/logger.py
# =============================================================================
# Sistema de Logging Estructurado — Modelo Predictivo de Futbol
# =============================================================================
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# ── Rutas ───────────────────────────────────────────────────────────────────
if os.path.exists(r"D:\MODELO DE PREDICCION"):
    BASE_DIR = Path(r"D:\MODELO DE PREDICCION")
elif os.path.exists("/content/Modelo-Predictivo"):
    BASE_DIR = Path("/content/Modelo-Predictivo")
else:
    BASE_DIR = Path(__file__).parent.parent

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Formato ─────────────────────────────────────────────────────────────────
CONSOLE_FORMAT = "%(levelname)-8s | %(name)-25s | %(message)s"
FILE_FORMAT    = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
DATE_FORMAT    = "%Y-%m-%d %H:%M:%S"

# ── Niveles de color (solo consola) ─────────────────────────────────────────
class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG:    "\033[36m",
        logging.INFO:     "\033[32m",
        logging.WARNING:  "\033[33m",
        logging.ERROR:    "\033[31m",
        logging.CRITICAL: "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)

# ── Configuracion global ────────────────────────────────────────────────────
def setup_logging(console_level=logging.INFO, file_level=logging.DEBUG, log_file=None):
    if log_file is None:
        log_file = f"modelo_{datetime.now().strftime('%Y-%m-%d')}.log"
    log_path = LOG_DIR / log_file

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.setLevel(logging.DEBUG)

    # Consola
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    console_fmt = ColoredFormatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT)
    console.setFormatter(console_fmt)
    root.addHandler(console)

    # Archivo
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_fmt = logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT)
    file_handler.setFormatter(file_fmt)
    root.addHandler(file_handler)

    root.info("=" * 70)
    root.info("Logging iniciado | Archivo: %s", log_path)
    root.info("=" * 70)
    return log_path

# ── Factory para loggers de modulos ─────────────────────────────────────────
def get_logger(name):
    short_name = name.replace("Scripts.principales.", "")
    short_name = short_name.replace("Scripts.scrapers.", "scraper:")
    short_name = short_name.replace("Scripts.utilidades.", "util:")
    short_name = short_name.replace("Config.", "cfg:")
    return logging.getLogger(short_name)

# ── Helpers especificos del dominio ─────────────────────────────────────────
def log_model_prediction(logger, home, away, prob_home, prob_draw, prob_away,
                         value_home, value_draw, value_away, recomendacion):
    logger.info(
        "PRED | %s vs %s | 1:%.1f%% X:%.1f%% 2:%.1f%% | "
        "VH:%+.1f%% VD:%+.1f%% VA:%+.1f%% | %s",
        home, away,
        prob_home*100, prob_draw*100, prob_away*100,
        value_home*100, value_draw*100, value_away*100,
        recomendacion
    )

def log_api_call(logger, api_name, endpoint, status, duration_ms, error=None):
    if error:
        logger.error("API | %s | %s | FAIL | %dms | %s", api_name, endpoint, duration_ms, error)
    else:
        logger.info("API | %s | %s | OK | %dms", api_name, endpoint, duration_ms)

def log_bet_decision(logger, match, market, selection, stake, odd, model_prob,
                     value_pct, confidence):
    if value_pct > 0:
        logger.info(
            "BET | %s | %s %s | Stake:%.2f%% | Odd:%.2f | "
            "Model:%.1f%% | Value:+%.1f%% | Conf:%.2f | OK",
            match, market, selection, stake*100, odd,
            model_prob*100, value_pct*100, confidence
        )
    else:
        logger.info(
            "BET | %s | %s %s | NO VALUE | Model:%.1f%% | Value:%+.1f%% | SKIP",
            match, market, selection, model_prob*100, value_pct*100
        )

def log_backtest_result(logger, module, n_matches, roi, accuracy, sharpe=None):
    logger.info(
        "BACKTEST | %s | N=%d | ROI=%+.2f%% | Acc=%.1f%% | Sharpe=%.2f",
        module, n_matches, roi*100, accuracy*100, sharpe if sharpe else 0
    )

# Auto-setup al importar
if not logging.getLogger().handlers:
    setup_logging()
