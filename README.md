# ⚽ Modelo Predictivo de Fútbol

Sistema completo de análisis estadístico de apuestas basado en **Dixon-Coles + Monte Carlo**.
Cubre **J-League** (ligas de clubes) y **Selecciones Nacionales** (incluyendo Mundial 2026).

---

## 📁 Estructura del Proyecto

```
Modelo-Predictivo/
│
├── 📊 Datos/
│   ├── jleague/              ← Datos J-League (football-data.co.uk)
│   │   ├── JPN.csv                     ⭐ Histórico 2012-2026 con cuotas Pinnacle
│   │   ├── J1_League_Player_Stats_2022_2025.csv
│   │   └── J1_League_Matches_2022_2025.csv
│   │
│   ├── internacional/        ← Datos selecciones nacionales
│   │   ├── results.csv                 ⭐ 49,411 partidos (Kaggle martj42, 1872-2026)
│   │   ├── former_names.csv            ← Nombres históricos de selecciones
│   │   ├── goalscorers.csv             ← Goleadores internacionales
│   │   ├── shootouts.csv               ← Tandas de penales
│   │   ├── results_2026_patch.csv      ← Parche manual resultados 2026
│   │   ├── partidos_internacionales.csv ← Scraper Soccerway (jun 2025-hoy)
│   │   └── ranking_fifa.csv            ← Ranking FIFA 2026 semestre 1 (local)
│   │
│   ├── rankings/             ← Ranking FIFA histórico (Kaggle cashncarry)
│   │   ├── fifa_mens_rank.csv
│   │   ├── fifa_ranking-2024-06-20.csv
│   │   ├── fifa_ranking-2024-04-04.csv
│   │   └── fifa_ranking-2023-07-20.csv
│   │
│   └── england/              ← EPL datos auxiliares
│       └── E0.csv, E0 (1-3).csv
│
├── 🤖 Scripts/
│   ├── principales/          ← Scripts que se ejecutan a diario
│   │   ├── jleague_analyzer.py         ⭐ Análisis J-League (valor bets + HTML)
│   │   ├── backtest_pinnacle.py        ← Backtest J-League vs Pinnacle
│   │   ├── international_analyzer.py   ⭐ Análisis selecciones/Mundial
│   │   └── backtest_internacional.py   ← Backtest walk-forward selecciones
│   │
│   ├── scrapers/             ← Obtención automática de datos
│   │   ├── scraper_cuotas.py           ← Cuotas sportytrader.com (Playwright)
│   │   └── scraper_109_selecciones.py  ← Resultados soccerway.com (Selenium)
│   │
│   └── utilidades/           ← Scripts auxiliares
│       ├── convertir_partidos.py       ← Conversor español→inglés del scraper
│       └── check_ligas.py              ← Diagnóstico de ligas disponibles
│
├── 📈 Reportes/              ← Generados automáticamente (.gitignore)
│   ├── jleague_report.html             ← Reporte diario J-League
│   ├── backtest_report.html            ← Backtest J-League
│   ├── international_report.html       ← Reporte diario selecciones
│   └── backtest_intl_report.html       ← Backtest internacional
│
├── ⚙️ Config/
│   └── config.py                       ← ⭐ Rutas, API keys y parámetros centralizados
│
├── .gitignore
└── README.md
```

---

## 🚀 Uso Diario

### Activar entorno (siempre primero)
```powershell
# Windows — desde D:\MODELO DE PREDICCION\
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".venv\Scripts\Activate.ps1"
```

### J-League (temporada enero-diciembre)
```powershell
python Scripts\principales\jleague_analyzer.py
# Abre Reportes\jleague_report.html
```

### Mundial / Selecciones Nacionales
```powershell
# 1. Actualizar cuotas (corre el scraper)
python Scripts\scrapers\scraper_cuotas.py

# 2. Analizar y detectar value bets
python Scripts\principales\international_analyzer.py
# Abre Reportes\international_report.html
```

### Backtest (hacer 1 vez al cambiar parámetros)
```powershell
python Scripts\principales\backtest_pinnacle.py        # J-League
python Scripts\principales\backtest_internacional.py   # Selecciones
```

### Actualizar datos scrapeados
```powershell
python Scripts\scrapers\scraper_109_selecciones.py   # Descarga resultados
python Scripts\utilidades\convertir_partidos.py      # Convierte español→inglés
```

---

## ⚙️ Configuración

Todo está centralizado en **`Config/config.py`** — rutas, API keys y parámetros:

```python
from config import *   # importa todo
```

Para cambiar parámetros del modelo, API keys o rutas: **edita solo `Config/config.py`**.

---

## 📊 APIs

| API | Clave | Uso |
|---|---|---|
| [The Odds API](https://the-odds-api.com) | `07fed81a...` | Cuotas Pinnacle en tiempo real |
| [API-Football](https://api-football.com) | `f7de0f5b...` | Convocados, lesionados, H2H |

---

## 📈 Resultados del Backtest

### J-League (backtest 2023-2025 vs Pinnacle)
| Mercado | ROI | Apuestas |
|---|---|---|
| **Visitante (2)** | **+11.2%** ✅ | 156 |
| Local (1) | -9.2% ❌ | — desactivado |
| Empate (X) | — | ⛔ desactivado |

### Selecciones (backtest 2022-2026)
| Mercado | ROI | Apuestas |
|---|---|---|
| **Local (1)** | **+5.4%** ✅ | 732 |
| Visitante (2) | -12.3% ❌ | — desactivado |
| Empate (X) | — | ⛔ desactivado |

---

## 🔄 Sincronización GitHub ↔ PC

```powershell
# Subir cambios al repo
git add Scripts/principales/jleague_analyzer.py
git commit -m "feat: descripción del cambio"
git push origin main

# Bajar cambios de GitHub
git pull origin main --rebase

# Actualizar datos (CSV) — commit separado
git add Datos/jleague/JPN.csv
git commit -m "data: actualizar JPN.csv temporada 2026"
git push origin main
```

**Regla de oro:** commits separados para **código**, **datos** y **config**.

---

## 📥 Fuentes de Datos

| Dataset | Fuente | Frecuencia actualización |
|---|---|---|
| JPN.csv (J-League) | [football-data.co.uk](https://football-data.co.uk/japanm.php) | Cada jornada |
| results.csv (Internacional) | [Kaggle martj42](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017) | Anual |
| Ranking FIFA | [Kaggle cashncarry](https://www.kaggle.com/datasets/cashncarry/fifaworldranking) | Semestral |
| Cuotas | sportytrader.com via scraper | Diario |
| Convocados/Lesionados | API-Football | Diario |

---

## ⚠️ Aviso Legal

Sistema estadístico basado en datos históricos.
**No garantiza resultados. Apuesta solo lo que puedas permitirte perder.**
