# ⚽ Modelo Predictivo de Fútbol — Dixon-Coles

Sistema completo de análisis estadístico de apuestas para **selecciones nacionales** y **ligas de clubes** (J-League).

---

## 📁 Estructura del proyecto

```
Modelo-Predictivo/
├── Codigo/
│   ├── 📊 DATOS
│   │   ├── results.csv                    ← 49,411 partidos internacionales (Kaggle 1872-2026)
│   │   ├── partidos_internacionales.csv   ← 875 partidos scrapeados jun 2025 - actualidad
│   │   ├── partidos_convertidos.csv       ← partidos_internacionales convertido a inglés
│   │   ├── results_2026_patch.csv         ← parche manual con resultados 2026
│   │   ├── JPN.csv                        ← Histórico J-League 2012-2025 (Pinnacle)
│   │   ├── former_names.csv               ← Nombres históricos selecciones
│   │   ├── goalscorers.csv                ← Goleadores internacionales
│   │   ├── shootouts.csv                  ← Penales internacionales
│   │   ├── fifa_mens_rank.csv             ← Ranking FIFA histórico
│   │   ├── fifa_ranking-2023-07-20.csv    ← Ranking FIFA julio 2023
│   │   ├── fifa_ranking-2024-04-04.csv    ← Ranking FIFA abril 2024
│   │   └── fifa_ranking-2024-06-20.csv    ← Ranking FIFA junio 2024
│   │
│   ├── 🤖 SCRIPTS PRINCIPALES
│   │   ├── international_analyzer.py      ← ⭐ SISTEMA PRINCIPAL — selecciones/Mundial
│   │   ├── jleague_analyzer.py            ← Sistema J-League (usar cuando vuelva la liga)
│   │   ├── backtest_pinnacle.py           ← Validación histórica del modelo J-League
│   │   └── convertir_partidos.py          ← Conversor español→inglés para el scraper
│   │
│   └── 🔧 SCRIPTS AUXILIARES
│       └── scraper_109_selecciones.py     ← Scraper Soccerway para actualizar datos
│
└── README.md
```

---

## 🚀 Uso diario

### Activar entorno (hacer siempre primero)
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& "d:\MODELO DE PREDICCION\Codigo\.venv\Scripts\Activate.ps1"
cd "D:\MODELO DE PREDICCION\Codigo"
```

### Mundial 2026 / Amistosos internacionales
```powershell
python international_analyzer.py
```
Abre `international_report.html` en el navegador.

### J-League (cuando vuelva en enero)
```powershell
python jleague_analyzer.py
```

### Actualizar datos con partidos recientes
```powershell
# 1. Ejecutar scraper (necesita Chrome instalado)
python scraper_109_selecciones.py

# 2. Convertir nombres español → inglés
python convertir_partidos.py

# 3. El analyzer carga automáticamente partidos_convertidos.csv
python international_analyzer.py
```

---

## 📊 Flujo de datos

```
results.csv (Kaggle 1872-2026)
         +
partidos_internacionales.csv (scraper Soccerway jun 2025-hoy)
         ↓
convertir_partidos.py → partidos_convertidos.csv
         +
results_2026_patch.csv (parche manual)
         ↓
international_analyzer.py
  → Dixon-Coles + Monte Carlo 100k
  → The Odds API (cuotas Pinnacle)
  → API-Football (convocados, lesionados, H2H)
         ↓
international_report.html
```

---

## 🔧 APIs configuradas

| API | Clave | Uso |
|---|---|---|
| The Odds API | `07fed81a...` | Cuotas Pinnacle en tiempo real |
| API-Football | `f7de0f5b...` | Convocados, lesionados, H2H |

---

## 📈 Resultados del backtest (J-League)

| Métrica | Valor |
|---|---|
| ROI total value bets | **+3.2%** |
| ROI visitante | **+11.2%** (156 apuestas) |
| Temporadas 2023-2024 | +6.0% / +6.2% |

---

## ⚠️ Aviso

Sistema estadístico basado en datos históricos. No garantiza resultados futuros.
**Apuesta solo lo que puedas permitirte perder.**
