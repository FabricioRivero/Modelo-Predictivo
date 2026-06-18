# ⚽ Modelo Predictivo de Fútbol — Dixon-Coles + Monte Carlo

Sistema completo de análisis estadístico de apuestas deportivas basado en el modelo **Dixon-Coles** con simulación **Monte Carlo (100,000 iteraciones)**.

Cubre dos módulos independientes:
- 🇯🇵 **J-League** — liga japonesa de clubes
- 🌍 **Selecciones Nacionales** — Mundial 2026 + amistosos internacionales

---

## 📊 Rendimiento Validado (Backtest Walk-Forward)

| Módulo | ROI | Apuestas | Período test | Estrategia activa |
|---|---|---|---|---|
| **J-League (visitante)** | **+11.2%** ✅ | 156 | 2023-2025 | Solo visitante >4% + forma ≥1.2 |
| **J-League (total)** | **+3.2%** | 341 | 2023-2025 | Con filtros combinados |
| **Selecciones (local)** | **+5.4%** ✅ | 732 | 2022-2026 | Solo local >5% + forma ≥1.3 |

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
│   │   ├── base_datos_maestra.csv      ⭐ Dataset maestro ETL (~47k partidos limpios)
│   │   ├── results.csv                 ← Kaggle martj42 (49,411 partidos 1872-2026)
│   │   ├── ranking_fifa.csv            ← Ranking FIFA 2026 semestre 1
│   │   ├── results_2026_patch.csv      ← Parche manual resultados recientes
│   │   ├── partidos_internacionales.csv ← Scraper Soccerway (jun 2025-hoy)
│   │   ├── former_names.csv            ← Nombres históricos de selecciones
│   │   ├── goalscorers.csv             ← Goleadores internacionales
│   │   └── shootouts.csv              ← Tandas de penales
│   │
│   ├── rankings/             ← Ranking FIFA histórico (Kaggle cashncarry)
│   │   ├── fifa_ranking-2024-06-20.csv
│   │   ├── fifa_ranking-2024-04-04.csv
│   │   └── fifa_ranking-2023-07-20.csv
│   │
│   └── england/              ← EPL datos auxiliares (futuro)
│       └── E0.csv, E0 (1-3).csv
│
├── 🤖 Scripts/
│   ├── principales/          ← Scripts que se ejecutan a diario
│   │   ├── international_analyzer.py   ⭐ Análisis selecciones/Mundial 2026
│   │   ├── jleague_analyzer.py         ⭐ Análisis J-League (value bets + HTML)
│   │   ├── backtest_internacional.py   ← Backtest walk-forward selecciones
│   │   └── backtest_pinnacle.py        ← Backtest J-League vs Pinnacle
│   │
│   ├── scrapers/             ← Obtención automática de datos
│   │   ├── scraper_cuotas.py           ← Cuotas sportytrader.com (Playwright)
│   │   ├── scraper_xg_auto.py         ← xG automático
│   │   ├── setup_perfil.py            ← Configuración perfil navegador
│   │   └── setup_perfil_fbref.py      ← Perfil FBref
│   │
│   └── utilidades/           ← Scripts auxiliares y diagnóstico
│       ├── construir_dataset.py        ← ETL: 4 fuentes → dataset maestro limpio
│       ├── verificar_datos.py          ← Verificar últimos 10 partidos por equipo
│       ├── check_ligas.py             ← Partidos 2018-2026 por año por selección
│       ├── estadisticas_dataset.py    ← Stats de cobertura por equipo
│       ├── convertir_partidos.py      ← Conversor español→inglés del scraper
│       ├── diagnostico.py             ← Diagnóstico general
│       ├── diagnostico_fbref.py       ← Diagnóstico FBref
│       └── ranking_fifa.py            ← Utilidad ranking
│
├── 📈 Reportes/              ← Generados automáticamente (.gitignore)
│   ├── international_report.html       ← Reporte diario selecciones
│   ├── jleague_report.html            ← Reporte diario J-League
│   ├── backtest_intl_report.html      ← Backtest internacional
│   └── backtest_report.html           ← Backtest J-League
│
├── ⚙️ Config/
│   └── config.py                       ← ⭐ Rutas, API keys y parámetros centralizados
│
├── .gitignore
└── README.md
```

---

## 🚀 Instalación y Configuración

### Requisitos
- **Python** 3.10+ (probado con 3.13 y 3.14)
- **Librerías:** numpy, pandas, scipy, playwright, beautifulsoup4, selenium, webdriver-manager
- **Navegador:** Brave o Chrome (para scrapers)

### Instalación rápida
```bash
# Clonar repositorio
git clone https://github.com/FabricioRivero/Modelo-Predictivo.git
cd Modelo-Predictivo

# Crear entorno virtual
python -m venv .venv

# Activar (Windows PowerShell)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1

# Instalar dependencias
pip install numpy pandas scipy playwright beautifulsoup4 selenium webdriver-manager
playwright install chromium
```

### Google Colab (alternativa sin instalación local)
```python
!pip install numpy pandas scipy -q
!git clone https://github.com/FabricioRivero/Modelo-Predictivo.git
import os
os.chdir('/content/Modelo-Predictivo')
!python Scripts/principales/international_analyzer.py
```

---

## 🏆 Uso Diario — Mundial 2026

```powershell
# Activar entorno
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".venv\Scripts\Activate.ps1"

# 1. Actualizar cuotas (scraper automático)
python Scripts\scrapers\scraper_cuotas.py

# 2. Analizar partidos y detectar value bets
python Scripts\principales\international_analyzer.py

# 3. Abrir reporte visual
# → Reportes\international_report.html
```

### J-League (cuando vuelva la temporada)
```powershell
python Scripts\principales\jleague_analyzer.py
```

### Backtest (validar edge después de cambiar parámetros)
```powershell
python Scripts\principales\backtest_internacional.py   # Selecciones
python Scripts\principales\backtest_pinnacle.py        # J-League
```

### Actualizar dataset maestro
```powershell
python Scripts\scrapers\scraper_109_selecciones.py     # Descargar resultados
python Scripts\utilidades\convertir_partidos.py        # Español → inglés
python Scripts\utilidades\construir_dataset.py         # Regenerar base_datos_maestra.csv
```

### Verificar datos de las 48 selecciones del Mundial
```powershell
python Scripts\utilidades\check_ligas.py               # Partidos por año
python Scripts\utilidades\verificar_datos.py           # Últimos 10 partidos
```

---

## ⚙️ Arquitectura del Modelo

```
Datos históricos (47k+ partidos limpios)
    ↓
Pesos por torneo: Mundial=1.0 | Clasif=0.85 | Amistoso=0.40
    ↓
Time decay: xi=0.00180 (selecciones) | xi=0.00325 (J-League)
    ↓
Dixon-Coles MLE (SLSQP) → λ_ataque, λ_defensa, ρ, γ
    ↓
Sede neutral: γ=0 cuando neutral=TRUE (Mundial)
    ↓
Monte Carlo 100,000 simulaciones por partido
    ↓
Probabilidades 1X2 + Over/Under + BTTS
    ↓
Ranking FIFA 2026 como prior para equipos con poco historial
    ↓
Comparar vs cuotas Pinnacle → detectar value bets (>5% umbral)
    ↓
Filtro forma reciente (≥1.3 pts/j últimos 8 partidos)
    ↓
Reporte HTML visual con heatmaps, forma, H2H, convocados
```

---

## 📊 APIs Integradas

| API | Clave | Uso | Límite |
|---|---|---|---|
| [The Odds API](https://the-odds-api.com) | `07fed81a...` | Cuotas Pinnacle en tiempo real | 500 req/mes gratis |
| [API-Football](https://api-football.com) | `f7de0f5b...` | Convocados, lesionados, H2H | 100 req/día gratis |

---

## 📥 Fuentes de Datos

| Dataset | Fuente | Frecuencia | Partidos |
|---|---|---|---|
| results.csv | [Kaggle martj42](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017) | Anual | 49,411 |
| base_datos_maestra.csv | ETL propio (4 fuentes combinadas) | Bajo demanda | ~47,000 |
| JPN.csv | [football-data.co.uk](https://football-data.co.uk/japanm.php) | Cada jornada | 4,523 |
| Ranking FIFA | [Kaggle cashncarry](https://www.kaggle.com/datasets/cashncarry/fifaworldranking) | Semestral | 100 selecciones |
| Cuotas en vivo | sportytrader.com via scraper | Diario | 97/ejecución |
| Convocados | API-Football | Diario | Por partido |

---

## 🎯 Reglas de Apuesta (calibradas con backtest)

### Selecciones Nacionales / Mundial 2026
```
✅ APOSTAR:  Local con value >5% + forma ≥1.3 pts/j
⛔ NO APOSTAR: Visitante (ROI histórico -12.3%)
⛔ NO APOSTAR: Empates
⛔ NUNCA:     Múltiples/combinadas
💰 STAKE:    1-2% del bankroll por apuesta
```

### J-League
```
✅ APOSTAR:  Visitante con value >4% + forma ≥1.2 pts/j
⛔ NO APOSTAR: Local (ROI histórico -9.2%)
⛔ NO APOSTAR: Empates (ROI -46%)
```

---

## 🔧 Configuración Centralizada

Todo en **`Config/config.py`**:
- Rutas auto-detectadas (Windows/Colab/Linux)
- API keys
- Parámetros del modelo (xi, N_SIM, umbrales)
- Lista de archivos candidatos para ranking FIFA

```python
# Ejemplo de uso en cualquier script:
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'Config'))
from config import *
```

---

## 📋 Problemas Conocidos

| Problema | Estado | Impacto |
|---|---|---|
| Dataset africano con CHAN/Arab Cup mezclado | 🟡 Parcialmente resuelto | Medio — afecta forma de equipos africanos |
| Scraper mezcla selección A y B | 🟡 Filtros aplicados | Medio — requiere limpieza manual |
| API keys en código (no en .env) | 🔴 Pendiente | Seguridad — mover a variables de entorno |
| Sin requirements.txt | 🔴 Pendiente | Onboarding — colaboradores no saben qué instalar |
| Sin tests unitarios | 🟡 Futuro | Mantenibilidad |

---

## 🔄 Sincronización GitHub ↔ PC

```powershell
# Subir cambios
git add Scripts/principales/international_analyzer.py
git commit -m "feat: descripción del cambio"
git push origin main

# Bajar cambios
git pull origin main

# Actualizar datos (commit separado)
git add Datos/internacional/results_2026_patch.csv
git commit -m "data: agregar resultados jornada 1 Mundial"
git push origin main
```

**Regla de oro:** commits separados para **código**, **datos** y **config**.

---

## 👥 Contribución

1. Fork del repositorio
2. Crear rama: `git checkout -b feature/nueva-mejora`
3. Hacer cambios y tests
4. Pull request a `main` con descripción clara

### Áreas que necesitan contribución:
- Limpieza dataset africano (CHAN/Copa Árabe)
- Tests unitarios con pytest
- Scraper de cuotas Over/Under
- CI/CD con GitHub Actions
- Tracker de apuestas reales (SQLite/CSV)

---

## ⚠️ Aviso Legal

Sistema estadístico basado en datos históricos y modelos probabilísticos.
**No garantiza resultados futuros. Apuesta solo lo que puedas permitirte perder.**
El edge estadístico se manifiesta a largo plazo (100+ apuestas), no en partidos individuales.

---

## 📈 Historial de Desarrollo

| Fecha | Hito |
|---|---|
| Jun 2026 | Sistema en producción para Mundial 2026 |
| Jun 2026 | ETL completo con 4 fuentes + estandarización |
| Jun 2026 | Backtest internacional validado (+5.4% local) |
| Jun 2026 | Over/Under + BTTS integrados |
| Jun 2026 | Ranking FIFA 2026 real integrado |
| Jun 2026 | Reorganización completa del repositorio |
| Jun 2026 | Backtest J-League validado (+11.2% visitante) |
| Jun 2026 | Sistema J-League operativo con Pinnacle |
