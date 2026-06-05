# ⚽ Modelo Predictivo J-League — Dixon-Coles v2

Sistema completo de análisis estadístico de apuestas para la J1 League japonesa.  
Usa el modelo **Dixon-Coles** con **Monte Carlo 100k simulaciones** para detectar value bets.

---

## 📁 Archivos del proyecto

| Archivo | Descripción |
|---|---|
| `jleague_analyzer.py` | **Script principal** — genera el reporte de hoy/mañana |
| `backtest_pinnacle.py` | **Backtest** — valida el edge del modelo vs Pinnacle |
| `JPN.csv` | Histórico J-League 2012–2025 con cuotas Pinnacle (football-data.co.uk) |
| `J1_League_Matches_2022_2025.csv` | Partidos con asistencia y estadio (FBref) |
| `J1_League_Player_Stats_2022_2025.csv` | Stats de jugadores por equipo (FBref) |
| `jleague_report.html` | Reporte visual generado (abrir en navegador) |
| `backtest_report.html` | Reporte de backtest generado |

---

## 🚀 Uso rápido

### Paso 1 — Activar entorno y entrar a la carpeta
```powershell
# En PowerShell, desde D:\MODELO DE PREDICCION
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& "d:\MODELO DE PREDICCION\Codigo\.venv\Scripts\Activate.ps1"
cd Codigo
```

### Paso 2 — Generar reporte de partidos de hoy/mañana
```powershell
python jleague_analyzer.py
```
Abre `jleague_report.html` en el navegador → verás los partidos con value bets.

### Paso 3 — Validar el edge del modelo (hacer 1 vez)
```powershell
python backtest_pinnacle.py
```
Abre `backtest_report.html` → verás el ROI histórico y Brier Score vs Pinnacle.

---

## 🔧 Configuración

En `jleague_analyzer.py`, bloque de configuración al inicio:

```python
BASE        = r"D:\MODELO DE PREDICCION\Codigo"   # ← tu ruta
API_KEY     = "tu_api_key_aqui"                    # ← The Odds API key
CSV_FILE    = "JPN.csv"                            # ← nombre del CSV
FORM_MATCHES = 6     # partidos recientes con peso extra
FORM_BOOST   = 2.5   # multiplicador de peso para forma reciente
VALUE_THRESH = 0.03  # umbral value bet (3%)
N_SIM        = 100_000  # simulaciones Monte Carlo
```

---

## 📊 Cómo leer el reporte

### Indicadores de value bet

| Icono | Significado |
|---|---|
| 🔥 **Value sólido** | >3% ventaja vs cuota **Y** >8% edge relativo — apuesta con más confianza |
| 🟢 **Value detectado** | >3% de ventaja vs la probabilidad implícita de la cuota |
| 🔴 **Sin value** | La casa tiene ventaja en este resultado |

### Métricas del modelo

- **λ local / λ visitante** — goles esperados según el modelo (Poisson)
- **Confianza** — qué tan seguro está el modelo del resultado más probable
- **Forma reciente** — últimos 6 partidos: W=victoria, D=empate, L=derrota
- **Top marcadores** — los 5 marcadores más probables con % de ocurrencia
- **Heatmap** — probabilidad de cada marcador exacto (0-5 goles)

### Fuente de cuotas (badge de colores)

| Color | Fuente | Fiabilidad |
|---|---|---|
| 🟢 Verde | Pinnacle | Máxima — referencia global |
| 🔵 Azul | Betfair Exchange | Muy alta — mercado real |
| 🟡 Amarillo | Bet365 / otras | Media — más margen |

---

## 📈 Cómo interpretar el backtest

El backtest (`backtest_pinnacle.py`) entrena con datos 2012–2022 y testea en 2023–2025 partido a partido.

| Métrica | Qué significa | Objetivo |
|---|---|---|
| **ROI total** | Retorno sobre inversión apostando 1u en cada value bet | >0% = modelo rentable |
| **Brier Score modelo** | Calibración de probabilidades (menor = mejor) | <0.65 |
| **Brier Score Pinnacle** | Benchmark — el mejor modelo del mercado | Referencia |
| **Diferencia Brier** | Si el modelo es mejor o peor que Pinnacle | >0 = modelo mejor |

**Interpretación del ROI:**
- `ROI > +3%` → Edge sólido, puedes apostar con confianza
- `ROI 0% a +3%` → Edge marginal, apuesta con staking bajo (1-2% bankroll)
- `ROI < 0%` → Sin edge, revisa los parámetros antes de apostar

---

## 🛠️ Metodología técnica

### Dixon-Coles
Modelo de regresión de Poisson bivariada con corrección de dependencia para marcadores 0-0, 1-0, 0-1 y 1-1. Estándar de la industria para predicción de fútbol.

### Time Decay + Forma reciente
```
peso(partido) = exp(-ξ × días_desde_partido)  × boost_forma
```
- `ξ = 0.00325` (los últimos 6 meses tienen >50% del peso)
- Los últimos 6 partidos de cada equipo reciben **2.5× más peso** para capturar forma actual

### Ajuste por stats de jugadores
El índice ofensivo de cada equipo (goles/90 agregados por plantilla, última temporada) ajusta el parámetro de ataque en ±0.15 como prior suave.

### Monte Carlo 100k
100,000 simulaciones de goles con corrección Dixon-Coles aplicada en tiempo real para calcular probabilidades 1X2, marcadores exactos y heatmap.

### Value bet
```
value = P_modelo - P_implícita_cuota
P_implícita = 1 / cuota_decimal
```
Se reporta `has_value` (>3%) y `strong_value` (>3% Y edge relativo >8%).

---

## 📥 Actualizar datos

### CSV de partidos (cada mes/temporada)
1. Ve a [football-data.co.uk/japan.php](https://football-data.co.uk/japan.php)
2. Descarga `JPN.csv` (J1 League)
3. Reemplaza el archivo en la carpeta `Codigo`

### Stats de jugadores (cada temporada)
1. Ve a [fbref.com/en/comps/25/J1-League-Stats](https://fbref.com/en/comps/25/J1-League-Stats)
2. Exporta la tabla de "Standard Stats" como CSV
3. Reemplaza `J1_League_Player_Stats_2022_2025.csv`

---

## ⚠️ Aviso legal

Este sistema es una herramienta estadística de análisis. No garantiza resultados.  
**Apuesta solo lo que puedas permitirte perder. Juega con responsabilidad.**

---

## 🔗 Dependencias

```
pip install numpy pandas scipy
```
Python 3.10+ requerido.
