# PROMPT PARA PEDIR DATOS A UNA IA

## Cómo usar este prompt

Copia el texto del bloque de abajo y pégalo en ChatGPT, Claude, Gemini, o
cualquier IA. Te devolverá un CSV limpio que puedes guardar directamente como
`results_2026_patch.csv` o agregar a `base_maestra.csv`.

---

## PROMPT (copiar desde aquí)

```
Necesito que me generes un CSV con TODOS los resultados de partidos de
selecciones nacionales masculinas absolutas que se hayan jugado entre
[FECHA_INICIO] y [FECHA_FIN].

FORMATO EXACTO del CSV (respeta el orden de columnas):

date,home_team,away_team,home_score,away_score,tournament,city,country,neutral

REGLAS OBLIGATORIAS:

1. IDIOMA: Todo en INGLÉS. Nombres de equipos en inglés estándar FIFA:
   - Germany (no Alemania)
   - Spain (no España)
   - France (no Francia)
   - Netherlands (no Países Bajos, no Holland)
   - South Korea (no Korea Republic, no República de Corea)
   - United States (no USA, no EEUU, no Estados Unidos)
   - Ivory Coast (no Côte d'Ivoire)
   - Czech Republic (no Czechia)
   - DR Congo (no Congo DR, no RD Congo)
   - Iran (no IR Iran)
   - Turkey (no Türkiye)
   - Bosnia and Herzegovina (no Bosnia-Herzegovina)
   - North Macedonia (no Macedonia del Norte)
   - Northern Ireland (no Irlanda del Norte)
   - Cape Verde (no Cabo Verde)

2. FORMATO FECHA: YYYY-MM-DD (ejemplo: 2026-06-15)

3. GOLES: Números enteros. Solo partidos YA JUGADOS con resultado final.
   - Si fue a penales, usar el resultado en tiempo reglamentario/extra
   - NO incluir partidos futuros sin resultado
   - NO incluir partidos suspendidos/cancelados

4. TORNEOS: Usar estos nombres exactos:
   - "Friendly" (para amistosos)
   - "FIFA World Cup" (fase final del mundial)
   - "FIFA World Cup qualification" (eliminatorias/clasificatorias)
   - "UEFA Euro" (fase final Eurocopa)
   - "UEFA Euro qualification"
   - "UEFA Nations League"
   - "Copa America"
   - "Africa Cup of Nations"
   - "Africa Cup of Nations qualification"
   - "AFC Asian Cup"
   - "AFC Asian Cup qualification"
   - "CONCACAF Gold Cup"
   - "CONCACAF Nations League"

5. NEUTRAL: TRUE si el partido se jugó en sede neutral (ejemplo: Mundial en
   USA para Argentina vs Francia). FALSE si se jugó en casa de alguno de los
   dos equipos.

6. FILTROS — NO INCLUIR:
   - Sub-17, Sub-20, Sub-21, Sub-23 (juveniles)
   - Selecciones femeninas
   - Torneos olímpicos
   - Equipos no reconocidos por FIFA (Cataluña, País Vasco, etc.)
   - Partidos de clubes

7. SIN DUPLICADOS: Cada partido aparece UNA sola vez.

8. CITY/COUNTRY: Ciudad y país donde se jugó el partido. Si no estás seguro,
   pon "Unknown".

EJEMPLO de cómo debe verse cada fila:
2026-06-15,Argentina,Chile,2,0,FIFA World Cup,Miami Gardens,United States,TRUE
2026-06-11,Germany,Scotland,3,1,FIFA World Cup,Houston,United States,TRUE
2025-10-10,Spain,Serbia,1,0,UEFA Nations League,Seville,Spain,FALSE

Dame TODOS los partidos que encuentres en ese rango de fechas. No omitas
ninguno. Prefiero que sean muchos y completos a que falten partidos.

Si un partido tiene resultado confirmado, inclúyelo. Si hay duda sobre el
resultado, NO lo incluyas.

Genera el CSV completo sin explicaciones adicionales, solo el CSV puro para
poder pegarlo directamente en un archivo.
```

---

## VARIANTE: Pedir solo partidos de un torneo específico

```
Necesito todos los resultados del [TORNEO] [AÑO] en formato CSV.
Usa exactamente este formato de columnas:

date,home_team,away_team,home_score,away_score,tournament,city,country,neutral

[Mismas reglas que arriba...]

Solo incluye partidos de: [TORNEO ESPECÍFICO]
```

---

## VARIANTE: Validar datos existentes

```
Tengo este CSV con resultados de partidos internacionales. Necesito que lo
VALIDES y CORRIJAS:

1. Verifica que los resultados sean correctos
2. Corrige nombres de equipos que no estén en inglés estándar
3. Marca con "ERROR:" al inicio de la línea si detectas un resultado incorrecto
4. Agrega partidos que FALTEN en el rango de fechas del CSV

CSV actual:
[PEGAR AQUÍ TU CSV]

Devuelve el CSV corregido completo + una lista de cambios realizados.
```

---

## VARIANTE: Actualizar con resultados más recientes

```
Mi base de datos de partidos internacionales tiene datos hasta [ULTIMA_FECHA].
Necesito todos los resultados de selecciones nacionales masculinas desde
[ULTIMA_FECHA] hasta hoy.

Formato:
date,home_team,away_team,home_score,away_score,tournament,city,country,neutral

[Mismas reglas de siempre: inglés, YYYY-MM-DD, sin duplicados, sin juveniles,
solo partidos jugados con resultado]

Incluye TODOS los partidos de:
- Eliminatorias mundialistas (todas las confederaciones)
- Amistosos FIFA
- Nations League (UEFA, CONCACAF)
- Copa América
- Copa África
- Copa Asia
- Cualquier otro torneo oficial de selecciones mayores

NO incluir: juveniles, femenino, olímpico, equipos no-FIFA.
```

---

## DESPUÉS DE RECIBIR LOS DATOS

1. Guarda el CSV como: `Datos/internacional/results_2026_patch.csv`
2. Ejecuta: `python Scripts/utilidades/consolidar_base_maestra.py`
3. El script automáticamente:
   - Traduce lo que falte a inglés
   - Elimina duplicados (el patch tiene prioridad)
   - Valida goles y fechas
   - Genera `base_maestra.csv` actualizada

---

## RANGOS SUGERIDOS PARA PEDIR

| Período | Qué pedir |
|---------|-----------|
| Pre-Mundial | Junio 2025 → Junio 2026 (amistosos + eliminatorias) |
| Mundial J1 | Primeros partidos del grupo |
| Mundial J2 | Segundos partidos del grupo |
| Post-Mundial | Octavos → Final |
