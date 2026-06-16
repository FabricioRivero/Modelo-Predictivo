"""
international_analyzer_v2.py — Sistema Predictivo MEJORADO para Mundial 2026
=============================================================================
MEJORAS sobre v1:
  1. NECESIDAD DE GANAR: Indice de importancia del partido (jornada, puntos, grupo)
  2. FORMA CONTEXTUAL: Pondera calidad del rival enfrentado + competencia
  3. xG INTEGRATION: Usa expected goals cuando disponible
  4. IMPACTO DE BAJAS: Cuantifica el efecto real en lambda (no solo visual)
  5. FORTALEZAS/DEBILIDADES: Métricas ofensivas/defensivas específicas
  6. FATIGA: Días de descanso entre partidos
  7. MOMENTUM JORNADA 1: Ajuste post-resultado primera jornada

Basado en Dixon-Coles + Monte Carlo 100k + todos los factores anteriores.
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
import json, os, sys, warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings('ignore')

# ── Cargar configuracion central ──────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', '..', 'Config'))
from config import (
    RESULTS_CSV, PATCH_2026_CSV, PARTIDOS_CONV_CSV, CUOTAS_HOY_CSV,
    INTL_REPORT_HTML, INTL_DIR,
    FIFA_RANKING_CANDIDATES,
    API_KEY_ODDS, API_KEY_FOOTBALL,
    XI_INTL, N_SIM_INTL, FORM_MATCHES_INTL, TRAIN_FROM_INTL,
    VT_HOME_INTL, VT_AWAY_INTL,
    FORM_MIN_HOME_INTL, FORM_MIN_AWAY_INTL,
    DRAW_ENABLED_INTL,
    ensure_dirs,
)
ensure_dirs()


# ══════════════════════════════════════════════════════════════
# CONFIGURACION GENERAL
# ══════════════════════════════════════════════════════════════
BASE         = INTL_DIR
RESULTS_CSV_PATH = RESULTS_CSV
OUTPUT_HTML  = INTL_REPORT_HTML.replace('.html', '_v2.html')

XI              = XI_INTL
TRAIN_FROM_YEAR = TRAIN_FROM_INTL
MIN_MATCHES     = 10
N_SIM           = N_SIM_INTL
FORM_MATCHES    = FORM_MATCHES_INTL

# Umbrales value bet MEJORADOS para Mundial Jornada 2
# Reactivamos visitante con umbral alto (en mundiales hay value en underdogs)
VALUE_THRESH_HOME = 0.04    # local: umbral ligeramente mas bajo para Mundial
VALUE_THRESH_AWAY = 0.07    # visitante: REACTIVADO para Mundial (umbral alto)
VALUE_THRESH_DRAW = 0.06    # empate: activado para Mundial (empates frecuentes J2)
DRAW_ENABLED      = True    # empates ACTIVADOS para Jornada 2 Mundial
FORM_MIN_PTS_HOME = 1.2     # forma minima local
FORM_MIN_PTS_AWAY = 1.0     # forma minima visitante


# Whitelist de selecciones
TEAM_WHITELIST = {
    'Albania','Germany','Andorra','Austria','Belarus','Belgium',
    'Bosnia and Herzegovina','Bulgaria','Croatia','Czech Republic',
    'Czechia','Denmark','England','Scotland','Northern Ireland',
    'Finland','France','Georgia','Greece','Hungary','Iceland',
    'Israel','Italy','Kosovo','Luxembourg','Moldova','Montenegro',
    'Netherlands','North Macedonia','Norway','Poland','Portugal',
    'Romania','Russia','Serbia','Slovakia','Slovenia','Spain',
    'Sweden','Switzerland','Turkey','Ukraine','Wales',
    'Argentina','Bolivia','Brazil','Canada','Chile','Colombia',
    'Costa Rica','Cuba','Curacao','Ecuador','El Salvador','Guatemala',
    'Haiti','Honduras','Jamaica','Mexico','Nicaragua','Panama',
    'Paraguay','Peru','Puerto Rico','United States','Uruguay',
    'Venezuela','Bermuda','Aruba',
    'Algeria','Angola','Benin','Burkina Faso','Cameroon',
    'Cape Verde','Congo DR','DR Congo','Ivory Coast',"Cote d'Ivoire",
    "Cote d'Ivoire",'Egypt','Gabon','Ghana','Guinea','Mali',
    'Mauritania','Morocco','Niger','Nigeria','Senegal','South Africa',
    'Tunisia','Uganda','Zambia',
    'Australia','Bahrain','China','China PR','Indonesia','Iran',
    'Iraq','Japan','Jordan','Kuwait','Kyrgyzstan','New Zealand',
    'Oman','Palestine','Qatar','Saudi Arabia','Singapore','South Korea',
    'Korea Republic','Syria','Tajikistan','Thailand','UAE',
    'United Arab Emirates','Uzbekistan','Vietnam',
}


# Pesos por tipo de torneo
TOURNAMENT_WEIGHTS = {
    'fifa world cup':                   1.00,
    'uefa euro':                        1.00,
    'copa america':                     1.00,
    'africa cup of nations':            1.00,
    'afc asian cup':                    1.00,
    'gold cup':                         0.95,
    'fifa world cup qualification':     0.85,
    'uefa euro qualification':          0.85,
    'conmebol world cup qualification': 0.85,
    'caf world cup qualification':      0.85,
    'afc world cup qualification':      0.85,
    'concacaf world cup qualification': 0.85,
    'uefa nations league':              0.80,
    'conmebol-uefa finalissima':        0.90,
    'concacaf nations league':          0.75,
    'aff championship':                 0.70,
    'friendly':                         0.40,
}

def get_tournament_weight(tournament_name):
    t = str(tournament_name).lower().strip()
    for key, w in TOURNAMENT_WEIGHTS.items():
        if key in t:
            return w
    if 'qualif' in t or 'qualifier' in t: return 0.82
    if 'friendly' in t or 'amistoso' in t: return 0.40
    if 'nations' in t: return 0.78
    return 0.60



# ══════════════════════════════════════════════════════════════
# MODULO 1: NECESIDAD DE GANAR (Match Importance Index)
# ══════════════════════════════════════════════════════════════
"""
Calcula un indice de 0.0 a 1.0 representando cuanto NECESITA ganar un equipo.
Factores:
  - Fase del torneo (grupo J2 = alta importancia)
  - Puntos actuales en el grupo
  - Resultado Jornada 1 (si perdio, necesidad maxima)
  - Diferencia de goles
  - Historial de clasificacion del equipo
"""

def calc_match_importance(team, matchday=2, points=None, gd=None,
                          j1_result=None, group_position=None,
                          is_world_cup=True):
    """
    Calcula el indice de necesidad de ganar (0.0 - 1.0).
    
    Args:
        team: nombre del equipo
        matchday: jornada actual (1, 2, 3)
        points: puntos actuales en el grupo
        gd: diferencia de goles actual
        j1_result: resultado jornada 1 ('W', 'D', 'L', None)
        group_position: posicion actual (1-4)
        is_world_cup: si es Mundial (maxima importancia base)
    
    Returns:
        float entre 0.0 y 1.0 (1.0 = necesidad maxima)
    """
    importance = 0.5  # base neutra
    
    # Factor 1: Fase del torneo
    if is_world_cup:
        importance += 0.15  # Mundial siempre alta importancia
    
    # Factor 2: Jornada
    matchday_boost = {1: 0.0, 2: 0.10, 3: 0.20}
    importance += matchday_boost.get(matchday, 0.10)
    
    # Factor 3: Resultado Jornada 1 (el mas critico para J2)
    if j1_result == 'L':
        importance += 0.25  # Perdio J1 → NECESITA ganar J2
    elif j1_result == 'D':
        importance += 0.10  # Empato → necesita sumar
    elif j1_result == 'W':
        importance -= 0.05  # Gano → algo mas relajado pero sigue necesitando
    
    # Factor 4: Puntos actuales
    if points is not None:
        if points == 0:
            importance += 0.15  # Sin puntos, urgencia maxima
        elif points == 1:
            importance += 0.05
        elif points >= 3:
            importance -= 0.05  # Ya tiene 3 pts, menos presion
    
    # Factor 5: Posicion en grupo
    if group_position is not None:
        if group_position >= 3:
            importance += 0.10  # Ultimo o penultimo
        elif group_position == 1:
            importance -= 0.05  # Lider
    
    # Factor 6: Diferencia de goles
    if gd is not None:
        if gd <= -2:
            importance += 0.05  # Goleada en contra, necesita golear
        elif gd >= 2:
            importance -= 0.03
    
    return float(np.clip(importance, 0.0, 1.0))


def importance_to_lambda_adj(importance_home, importance_away):
    """
    Convierte la necesidad de ganar en un ajuste multiplicativo para lambda.
    
    Un equipo que NECESITA ganar tiende a:
    - Atacar mas (lambda ofensivo sube)
    - Pero tambien exponerse mas (lambda defensivo sube para rival)
    
    Returns:
        (adj_home_attack, adj_away_attack): multiplicadores para lambda
    """
    # Escala: importancia 0.5 = neutro, 0.8+ = ataque agresivo
    adj_home = 1.0 + (importance_home - 0.5) * 0.15  # max +7.5%
    adj_away = 1.0 + (importance_away - 0.5) * 0.15
    
    return float(np.clip(adj_home, 0.92, 1.10)), \
           float(np.clip(adj_away, 0.92, 1.10))



# ══════════════════════════════════════════════════════════════
# MODULO 2: FORMA CONTEXTUAL (Quality-Weighted Recent Form)
# ══════════════════════════════════════════════════════════════
"""
Mejora sobre forma plana: pondera cada resultado por:
  - Ranking FIFA del rival enfrentado
  - Peso del torneo donde se jugo
  - Recencia (mas reciente = mas peso)
"""

def get_contextual_form(df, team, fifa_ranking, n=FORM_MATCHES):
    """
    Calcula forma reciente ponderada por calidad del rival.
    
    Returns:
        dict con:
        - weighted_pts_pg: puntos por juego ponderados
        - attack_form: rendimiento ofensivo contextual
        - defense_form: rendimiento defensivo contextual
        - momentum: tendencia (mejorando/empeorando)
        - form_sequence: secuencia W/D/L
    """
    mask = (df['home_team'] == team) | (df['away_team'] == team)
    recent = df[mask].tail(n).copy()
    
    if len(recent) == 0:
        return {
            'weighted_pts_pg': None, 'attack_form': 0.5,
            'defense_form': 0.5, 'momentum': 0.0,
            'form_sequence': [], 'avg_gf': 0, 'avg_ga': 0,
            'quality_faced': 0.5,
        }
    
    results = []
    for idx, (_, row) in enumerate(recent.iterrows()):
        is_home = row['home_team'] == team
        gf = row['home_goals'] if is_home else row['away_goals']
        ga = row['away_goals'] if is_home else row['home_goals']
        rival = row['away_team'] if is_home else row['home_team']
        
        # Peso por calidad del rival (mejor ranking = mas dificil)
        rival_rank = fifa_ranking.get(rival, 60)
        # Top 10 → quality=1.0, rank 80+ → quality=0.3
        rival_quality = max(0.3, 1.0 - (rival_rank - 1) * 0.7 / 79)
        
        # Peso por torneo
        tourn_w = get_tournament_weight(row.get('tournament', 'Friendly'))
        
        # Peso por recencia (mas reciente = mas peso)
        recency_w = 0.5 + 0.5 * (idx / max(len(recent) - 1, 1))
        
        # Peso combinado
        combined_w = rival_quality * tourn_w * recency_w
        
        # Puntos
        if gf > ga:
            pts = 3
            result = 'W'
        elif gf == ga:
            pts = 1
            result = 'D'
        else:
            pts = 0
            result = 'L'
        
        results.append({
            'pts': pts, 'gf': gf, 'ga': ga, 'result': result,
            'weight': combined_w, 'rival_quality': rival_quality,
            'rival': rival, 'tournament': row.get('tournament', ''),
        })
    
    # Calculo ponderado
    total_w = sum(r['weight'] for r in results)
    if total_w == 0:
        total_w = 1.0
    
    weighted_pts = sum(r['pts'] * r['weight'] for r in results) / total_w
    weighted_gf = sum(r['gf'] * r['weight'] for r in results) / total_w
    weighted_ga = sum(r['ga'] * r['weight'] for r in results) / total_w
    avg_quality = sum(r['rival_quality'] for r in results) / len(results)
    
    # Momentum: comparar primera mitad vs segunda mitad
    mid = len(results) // 2
    if mid > 0:
        first_half_pts = sum(r['pts'] for r in results[:mid]) / mid
        second_half_pts = sum(r['pts'] for r in results[mid:]) / max(len(results) - mid, 1)
        momentum = (second_half_pts - first_half_pts) / 3.0  # normalizado -1 a +1
    else:
        momentum = 0.0
    
    # Forma ofensiva/defensiva (normalizada 0-1)
    attack_form = min(1.0, weighted_gf / 2.0)  # 2+ goles/partido = excelente
    defense_form = max(0.0, 1.0 - weighted_ga / 2.0)  # 0 goles = excelente
    
    return {
        'weighted_pts_pg': round(weighted_pts / 3.0 * 3, 2),  # escala 0-3
        'attack_form': round(attack_form, 3),
        'defense_form': round(defense_form, 3),
        'momentum': round(momentum, 3),
        'form_sequence': [r['result'] for r in results][::-1],
        'avg_gf': round(np.mean([r['gf'] for r in results]), 2),
        'avg_ga': round(np.mean([r['ga'] for r in results]), 2),
        'quality_faced': round(avg_quality, 3),
    }



# ══════════════════════════════════════════════════════════════
# MODULO 3: IMPACTO DE BAJAS (Quantified Injury Impact)
# ══════════════════════════════════════════════════════════════
"""
Convierte las bajas de jugadores en un ajuste numerico real.
Pondera por:
  - Posicion del jugador (delantero clave vs suplente)
  - Rol en el equipo (capitan, goleador, creador)
  - Disponibilidad de reemplazo de calidad
"""

# Impacto por posicion (cuanto afecta al lambda ofensivo/defensivo)
POSITION_IMPACT = {
    'Goalkeeper':  {'attack': 0.00, 'defense': 0.08},
    'Defender':    {'attack': 0.01, 'defense': 0.05},
    'Midfielder':  {'attack': 0.04, 'defense': 0.03},
    'Attacker':    {'attack': 0.07, 'defense': 0.01},
}

def calc_injury_impact(injuries, squad=None):
    """
    Calcula el impacto total de las bajas en las capacidades del equipo.
    
    Args:
        injuries: lista de dicts [{name, reason, status, position?}]
        squad: lista de jugadores del equipo (para contextualizar)
    
    Returns:
        dict con:
        - attack_penalty: reduccion porcentual del lambda ofensivo (0.0-0.25)
        - defense_penalty: reduccion porcentual del lambda defensivo (0.0-0.20)
        - n_starters_out: estimacion de titulares ausentes
        - severity: 'low', 'medium', 'high', 'critical'
    """
    if not injuries:
        return {
            'attack_penalty': 0.0, 'defense_penalty': 0.0,
            'n_starters_out': 0, 'severity': 'low',
            'key_players_out': [],
        }
    
    attack_pen = 0.0
    defense_pen = 0.0
    key_players = []
    
    for inj in injuries:
        pos = inj.get('position', 'Midfielder')  # default midfielder
        # Intentar detectar posicion del nombre si API no la da
        name = inj.get('name', '')
        
        impact = POSITION_IMPACT.get(pos, POSITION_IMPACT['Midfielder'])
        
        # Multiplicador por severidad de la baja
        reason = str(inj.get('reason', '')).lower()
        if 'suspension' in reason or 'red card' in reason:
            severity_mult = 1.2  # suspension = confirmado que no juega
        elif 'acl' in reason or 'surgery' in reason:
            severity_mult = 1.0  # baja larga confirmada
        elif 'muscle' in reason or 'hamstring' in reason:
            severity_mult = 0.9
        elif 'doubt' in reason or 'duda' in reason:
            severity_mult = 0.5  # podria jugar
        else:
            severity_mult = 0.8
        
        attack_pen += impact['attack'] * severity_mult
        defense_pen += impact['defense'] * severity_mult
        
        if impact['attack'] >= 0.05 or impact['defense'] >= 0.05:
            key_players.append(name)
    
    # Limitar el impacto maximo (no puede desmantelar completamente)
    attack_pen = min(attack_pen, 0.25)
    defense_pen = min(defense_pen, 0.20)
    
    # Estimar titulares ausentes
    n_starters = min(len(injuries), 5)  # maximo razonable
    
    # Severidad general
    total_impact = attack_pen + defense_pen
    if total_impact >= 0.25:
        severity = 'critical'
    elif total_impact >= 0.15:
        severity = 'high'
    elif total_impact >= 0.08:
        severity = 'medium'
    else:
        severity = 'low'
    
    return {
        'attack_penalty': round(attack_pen, 4),
        'defense_penalty': round(defense_pen, 4),
        'n_starters_out': n_starters,
        'severity': severity,
        'key_players_out': key_players[:5],
    }



# ══════════════════════════════════════════════════════════════
# MODULO 4: FORTALEZAS Y DEBILIDADES (Team Profile)
# ══════════════════════════════════════════════════════════════
"""
Genera un perfil de fortalezas/debilidades por equipo basado en:
  - Rendimiento ofensivo (goles/xG por partido)
  - Solidez defensiva (goles en contra)
  - Rendimiento en primeros tiempos vs segundos tiempos
  - Eficiencia en partidos cerrados (1 gol diferencia)
  - Rendimiento bajo presion (partidos eliminatorios)
"""

def build_team_profile(df, team, fifa_ranking, n_matches=15):
    """
    Construye perfil de fortalezas y debilidades.
    
    Returns:
        dict con metricas de fortaleza/debilidad
    """
    mask = (df['home_team'] == team) | (df['away_team'] == team)
    recent = df[mask].tail(n_matches).copy()
    
    if len(recent) < 3:
        return {
            'attack_rating': 0.5, 'defense_rating': 0.5,
            'clean_sheet_pct': 0.0, 'scoring_consistency': 0.5,
            'close_game_record': 0.5, 'big_game_performance': 0.5,
            'goals_per_game': 1.0, 'conceded_per_game': 1.0,
            'strengths': [], 'weaknesses': [],
        }
    
    gf_list, ga_list, results_list = [], [], []
    official_results = []
    
    for _, row in recent.iterrows():
        is_home = row['home_team'] == team
        gf = row['home_goals'] if is_home else row['away_goals']
        ga = row['away_goals'] if is_home else row['home_goals']
        gf_list.append(gf)
        ga_list.append(ga)
        
        if gf > ga: r = 'W'
        elif gf < ga: r = 'L'
        else: r = 'D'
        results_list.append(r)
        
        # Partidos oficiales (peso > 0.6)
        tw = get_tournament_weight(row.get('tournament', 'Friendly'))
        if tw >= 0.7:
            official_results.append({'gf': gf, 'ga': ga, 'result': r})
    
    avg_gf = np.mean(gf_list)
    avg_ga = np.mean(ga_list)
    clean_sheets = sum(1 for ga in ga_list if ga == 0) / len(ga_list)
    scoring_games = sum(1 for gf in gf_list if gf >= 1) / len(gf_list)
    
    # Partidos cerrados (1 gol de diferencia)
    close_games = [(gf, ga) for gf, ga in zip(gf_list, ga_list) 
                   if abs(gf - ga) <= 1]
    if close_games:
        close_wins = sum(1 for gf, ga in close_games if gf > ga)
        close_game_record = close_wins / len(close_games)
    else:
        close_game_record = 0.5
    
    # Rendimiento en partidos oficiales grandes
    if official_results:
        big_game_wins = sum(1 for r in official_results if r['result'] == 'W')
        big_game_perf = big_game_wins / len(official_results)
    else:
        big_game_perf = 0.5
    
    # Consistencia goleadora (desviacion estandar baja = consistente)
    scoring_consistency = 1.0 - min(1.0, np.std(gf_list) / 2.0)
    
    # Ratings normalizados (0-1)
    attack_rating = min(1.0, avg_gf / 2.5)
    defense_rating = max(0.0, 1.0 - avg_ga / 2.0)
    
    # Identificar fortalezas y debilidades
    strengths, weaknesses = [], []
    
    if attack_rating >= 0.7:
        strengths.append(f"Ataque potente ({avg_gf:.1f} goles/partido)")
    if defense_rating >= 0.7:
        strengths.append(f"Defensa solida ({avg_ga:.1f} goles recibidos/partido)")
    if clean_sheets >= 0.4:
        strengths.append(f"Porteria a cero frecuente ({clean_sheets*100:.0f}%)")
    if close_game_record >= 0.6:
        strengths.append("Efectivo en partidos cerrados")
    if big_game_perf >= 0.6:
        strengths.append("Buen rendimiento en partidos grandes")
    if scoring_games >= 0.85:
        strengths.append("Raramente se queda sin marcar")
    
    if attack_rating < 0.4:
        weaknesses.append(f"Ataque limitado ({avg_gf:.1f} goles/partido)")
    if defense_rating < 0.4:
        weaknesses.append(f"Defensa vulnerable ({avg_ga:.1f} goles recibidos)")
    if clean_sheets < 0.15:
        weaknesses.append("Dificultad para mantener porteria a cero")
    if close_game_record < 0.35:
        weaknesses.append("Debil en partidos cerrados")
    if scoring_consistency < 0.4:
        weaknesses.append("Ataque inconsistente (depende del dia)")
    if scoring_games < 0.6:
        weaknesses.append("Se queda sin marcar con frecuencia")
    
    return {
        'attack_rating': round(attack_rating, 3),
        'defense_rating': round(defense_rating, 3),
        'clean_sheet_pct': round(clean_sheets, 3),
        'scoring_consistency': round(scoring_consistency, 3),
        'close_game_record': round(close_game_record, 3),
        'big_game_performance': round(big_game_perf, 3),
        'goals_per_game': round(avg_gf, 2),
        'conceded_per_game': round(avg_ga, 2),
        'strengths': strengths,
        'weaknesses': weaknesses,
    }



# ══════════════════════════════════════════════════════════════
# MODULO 5: FATIGA Y DESCANSO
# ══════════════════════════════════════════════════════════════

def calc_fatigue_factor(df, team, match_date):
    """
    Calcula factor de fatiga basado en dias de descanso.
    En Mundial: J1 y J2 separadas por 3-5 dias tipicamente.
    
    Returns:
        float: multiplicador (0.95-1.02)
        - < 3 dias: penalizacion fuerte
        - 3-4 dias: penalizacion leve
        - 5+ dias: neutro o leve beneficio
    """
    mask = (df['home_team'] == team) | (df['away_team'] == team)
    team_matches = df[mask].copy()
    team_matches = team_matches[team_matches['match_date'] < match_date]
    
    if len(team_matches) == 0:
        return 1.0  # sin datos, neutro
    
    last_match = team_matches['match_date'].max()
    days_rest = (match_date - last_match).days
    
    if days_rest <= 2:
        return 0.95  # fatiga alta (raro en mundiales)
    elif days_rest == 3:
        return 0.97  # fatiga moderada
    elif days_rest == 4:
        return 0.99  # fatiga leve
    elif days_rest <= 6:
        return 1.00  # optimo
    elif days_rest <= 10:
        return 1.01  # bien descansado
    else:
        return 1.00  # demasiado sin jugar, neutro


# ══════════════════════════════════════════════════════════════
# MODULO 6: MATCHUP ANALYSIS (Fortaleza vs Debilidad)
# ══════════════════════════════════════════════════════════════

def calc_matchup_adjustment(profile_home, profile_away):
    """
    Analiza como las fortalezas de un equipo explotan las debilidades del otro.
    
    Ejemplo: Equipo con ataque potente vs equipo con defensa debil
             → ajuste positivo al lambda ofensivo del atacante
    
    Returns:
        (home_attack_adj, away_attack_adj): ajustes multiplicativos
    """
    # Ataque de home vs defensa de away
    home_exploit = profile_home['attack_rating'] * (1 - profile_away['defense_rating'])
    # Ataque de away vs defensa de home  
    away_exploit = profile_away['attack_rating'] * (1 - profile_home['defense_rating'])
    
    # Convertir a ajuste (0.0 exploit = no cambio, 0.5+ = boost)
    home_adj = 1.0 + (home_exploit - 0.25) * 0.12  # -3% a +3%
    away_adj = 1.0 + (away_exploit - 0.25) * 0.12
    
    # Ajuste por consistencia (equipo consistente explota mejor)
    home_adj *= (0.95 + profile_home['scoring_consistency'] * 0.10)
    away_adj *= (0.95 + profile_away['scoring_consistency'] * 0.10)
    
    return (float(np.clip(home_adj, 0.93, 1.08)),
            float(np.clip(away_adj, 0.93, 1.08)))



# ══════════════════════════════════════════════════════════════
# BLOQUE DATA: CARGA Y PREPARACION DE DATOS
# ══════════════════════════════════════════════════════════════

def load_results(base_path=None):
    """Carga datos identico a v1 (funcionalidad probada)."""
    if base_path is None:
        base_path = INTL_DIR
    path = RESULTS_CSV_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"No encontrado: {path}")

    df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    rename = {}
    for c in df.columns:
        if 'home_score' in c: rename[c] = 'home_goals'
        if 'away_score' in c: rename[c] = 'away_goals'
    df.rename(columns=rename, inplace=True)

    col_map = {}
    for c in df.columns:
        if 'home_team' in c:    col_map[c] = 'home_team'
        elif 'away_team' in c:  col_map[c] = 'away_team'
        elif 'home_goal' in c:  col_map[c] = 'home_goals'
        elif 'away_goal' in c:  col_map[c] = 'away_goals'
        elif c == 'date':       col_map[c] = 'date'
        elif 'tournament' in c: col_map[c] = 'tournament'
        elif 'neutral' in c:    col_map[c] = 'neutral'
    df.rename(columns=col_map, inplace=True)

    required = ['date', 'home_team', 'away_team', 'home_goals', 'away_goals']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}")

    df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce')
    df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce')
    df.dropna(subset=['home_goals', 'away_goals'], inplace=True)
    df['home_goals'] = df['home_goals'].astype(int)
    df['away_goals'] = df['away_goals'].astype(int)
    df['match_date'] = pd.to_datetime(df['date'], errors='coerce')
    df.dropna(subset=['match_date'], inplace=True)
    df['year'] = df['match_date'].dt.year

    if 'neutral' not in df.columns:
        df['neutral'] = False
    df['neutral'] = df['neutral'].astype(str).str.lower().isin(['true', '1', 'yes'])
    if 'tournament' not in df.columns:
        df['tournament'] = 'Friendly'

    df = df[df['year'] >= TRAIN_FROM_YEAR].copy()

    # Parches adicionales
    patch_sources = [
        (PARTIDOS_CONV_CSV, 'Scraper 2025-2026'),
        (PATCH_2026_CSV, 'Parche manual 2026'),
    ]
    for patch_file, label in patch_sources:
        if not os.path.exists(patch_file):
            continue
        try:
            patch = pd.read_csv(patch_file, encoding='utf-8-sig', low_memory=False)
            patch.columns = [c.strip().lower().replace(' ','_') for c in patch.columns]
            for old, new in [('home_score','home_goals'),('away_score','away_goals')]:
                if old in patch.columns:
                    patch.rename(columns={old: new}, inplace=True)
            if 'date' not in patch.columns and 'fecha' in patch.columns:
                patch['date'] = patch['fecha']
            patch['match_date'] = pd.to_datetime(patch['date'], errors='coerce')
            patch['year'] = patch['match_date'].dt.year
            if 'neutral' in patch.columns:
                patch['neutral'] = patch['neutral'].astype(str).str.lower().isin(
                    ['true','1','yes','TRUE'])
            else:
                patch['neutral'] = True
            if 'tournament' not in patch.columns:
                patch['tournament'] = 'Friendly'
            patch['home_goals'] = pd.to_numeric(patch.get('home_goals', 0), errors='coerce')
            patch['away_goals'] = pd.to_numeric(patch.get('away_goals', 0), errors='coerce')
            patch = patch.dropna(subset=['home_goals','away_goals','match_date',
                                         'home_team','away_team'])
            patch['home_goals'] = patch['home_goals'].astype(int)
            patch['away_goals'] = patch['away_goals'].astype(int)
            df_keys = set(zip(df['match_date'].dt.date, df['home_team'], df['away_team']))
            patch_new = patch[~patch.apply(
                lambda r: (r['match_date'].date(), r['home_team'], r['away_team']) in df_keys,
                axis=1)]
            if len(patch_new) > 0:
                df = pd.concat([df, patch_new], ignore_index=True)
                print(f"  + {label}: +{len(patch_new)} partidos")
        except Exception as e:
            print(f"  ! Error {patch_file}: {e}")

    # Filtrar whitelist
    df = df[df['home_team'].isin(TEAM_WHITELIST) &
            df['away_team'].isin(TEAM_WHITELIST)].copy()
    df = df.sort_values('match_date').reset_index(drop=True)

    # Pesos
    ref = df['match_date'].max()
    df['time_diff_days'] = (ref - df['match_date']).dt.days
    df['t_weight'] = df['tournament'].apply(get_tournament_weight)
    df['td_weight'] = np.exp(-XI * df['time_diff_days'].values)
    df['weight'] = df['t_weight'] * df['td_weight']

    print(f"  [v2] {len(df):,} partidos ({df['year'].min()}-{df['year'].max()})")
    return df



# ══════════════════════════════════════════════════════════════
# RANKING FIFA
# ══════════════════════════════════════════════════════════════
FIFA_NAME_MAP = {
    'IR Iran':'Iran','Turkiye':'Turkey','Korea Republic':'South Korea',
    'USA':'United States',"Cote d'Ivoire":'Ivory Coast',
    'Congo DR':'DR Congo','Czechia':'Czech Republic','China PR':'China',
    'Bosnia & Herzegovina':'Bosnia and Herzegovina',
    'Espana':'Spain','Francia':'France','Inglaterra':'England',
    'Brasil':'Brazil','Marruecos':'Morocco','Paises Bajos':'Netherlands',
    'Belgica':'Belgium','Alemania':'Germany','Croacia':'Croatia',
    'Italia':'Italy','Mexico':'Mexico','EEUU':'United States',
    'Japon':'Japan','Suiza':'Switzerland','Dinamarca':'Denmark',
    'RI de Iran':'Iran','Turquia':'Turkey',
    'Republica de Corea':'South Korea','Argelia':'Algeria',
    'Egipto':'Egypt','Canada':'Canada','Noruega':'Norway',
    'Ucrania':'Ukraine','Costa de Marfil':'Ivory Coast',
    'Panama':'Panama','Rusia':'Russia','Polonia':'Poland',
    'Gales':'Wales','Suecia':'Sweden','Republica Checa':'Czech Republic',
    'Hungria':'Hungary','Escocia':'Scotland','Camerun':'Cameroon',
    'RD del Congo':'DR Congo','Tunez':'Tunisia','Eslovaquia':'Slovakia',
    'Grecia':'Greece','Uzbekistan':'Uzbekistan','Peru':'Peru',
    'Rumania':'Romania','Chile':'Chile','Irak':'Iraq',
    'Eslovenia':'Slovenia','Sudafrica':'South Africa',
    'Arabia Saudi':'Saudi Arabia','Jordania':'Jordan',
    'Bosnia y Herzegovina':'Bosnia and Herzegovina',
    'Albania':'Albania','Cabo Verde':'Cape Verde',
    'Macedonia del Norte':'North Macedonia',
    'Irlanda del Norte':'Northern Ireland','Georgia':'Georgia',
    'Islandia':'Iceland','Bolivia':'Bolivia','Kosovo':'Kosovo',
    'Oman':'Oman','Montenegro':'Montenegro','Curazao':'Curacao',
    'Haiti':'Haiti','Siria':'Syria','Nueva Zelanda':'New Zealand',
    'RP China':'China','Barein':'Bahrain','Tailandia':'Thailand',
    'Palestina':'Palestine','Bielorrusia':'Belarus',
    'Tayikistan':'Tajikistan',
}

FIFA_RANKING = {}

def load_fifa_ranking(base_path=None):
    """Carga ranking FIFA desde CSV."""
    candidates = list(FIFA_RANKING_CANDIDATES)
    if base_path:
        local = [os.path.join(base_path, f) for f in
                 ['ranking_fifa.csv','fifa_mens_rank.csv',
                  'fifa_ranking-2024-06-20.csv']]
        candidates = local + candidates
    
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            rdf = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
            rdf.columns = [c.strip().lower().replace('.','_').replace(' ','_')
                           for c in rdf.columns]
            if 'team' in rdf.columns and 'semester' in rdf.columns:
                latest = rdf[rdf['date'] == rdf['date'].max()]
                latest = latest[latest['semester'] == latest['semester'].max()]
                ranking = {}
                for _, row in latest.iterrows():
                    name = FIFA_NAME_MAP.get(str(row['team']).strip(),
                                             str(row['team']).strip())
                    ranking[name] = int(row['rank'])
                print(f"  [v2] Ranking FIFA: {len(ranking)} selecciones")
                return ranking
            if 'country_full' in rdf.columns:
                latest = rdf[rdf['rank_date'] == rdf['rank_date'].max()]
                ranking = {}
                for _, row in latest.iterrows():
                    name = FIFA_NAME_MAP.get(str(row['country_full']).strip(),
                                             str(row['country_full']).strip())
                    ranking[name] = int(row['rank'])
                print(f"  [v2] Ranking FIFA: {len(ranking)} selecciones")
                return ranking
        except Exception as e:
            print(f"  ! Error ranking: {e}")
    
    # Fallback
    print("  ! Usando ranking FIFA hardcodeado (fallback)")
    return {
        'Argentina':1,'France':2,'Spain':3,'England':4,'Brazil':5,
        'Portugal':6,'Netherlands':7,'Belgium':8,'Italy':9,'Germany':10,
        'Uruguay':11,'Colombia':12,'Croatia':13,'Morocco':14,'Japan':15,
        'United States':16,'Senegal':17,'Iran':18,'Mexico':19,
        'Switzerland':20,'Denmark':21,'Austria':22,'South Korea':23,
        'Ecuador':24,'Ukraine':25,'Australia':26,'Sweden':27,
        'Turkey':28,'Wales':29,'Hungary':30,'Poland':31,'Serbia':32,
    }

def get_fifa_prior(team, n_teams=100):
    rank = FIFA_RANKING.get(team, 80)
    prior = 0.20 - (rank - 1) * (0.40 / 79)
    return float(np.clip(prior, -0.25, 0.25))



# ══════════════════════════════════════════════════════════════
# DIXON-COLES MODEL
# ══════════════════════════════════════════════════════════════

def rho_correction(hg, ag, lam, mu, rho):
    if   hg == 0 and ag == 0: return max(1e-10, 1 - lam * mu * rho)
    elif hg == 0 and ag == 1: return max(1e-10, 1 + lam * rho)
    elif hg == 1 and ag == 0: return max(1e-10, 1 + mu * rho)
    elif hg == 1 and ag == 1: return max(1e-10, 1 - rho)
    return 1.0

def dc_log_likelihood(params, df, teams, neutral_idx):
    n = len(teams)
    atk = params[:n]
    dfc = params[n:2*n]
    rho = params[2*n]
    gam = params[2*n + 1]

    hidx = np.array([teams.index(t) for t in df['home_team']])
    aidx = np.array([teams.index(t) for t in df['away_team']])
    home_adv = np.where(neutral_idx, 0.0, gam)

    lam = np.exp(atk[hidx] + dfc[aidx] + home_adv)
    mu  = np.exp(atk[aidx] + dfc[hidx])

    hg = df['home_goals'].values
    ag = df['away_goals'].values
    w  = df['weight'].values

    rc = np.array([rho_correction(h, a, l, m, rho)
                   for h, a, l, m in zip(hg, ag, lam, mu)])
    ll = w * (poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu) + np.log(rc))
    return -np.sum(ll)

def fit_model(df, verbose=True):
    df_fit = df.copy()
    teams = sorted(set(df_fit['home_team']) | set(df_fit['away_team']))
    n = len(teams)

    x0 = np.zeros(2 * n + 2)
    for i, team in enumerate(teams):
        x0[i] = get_fifa_prior(team, n)
        x0[n + i] = -get_fifa_prior(team, n) * 0.5
    x0[2*n + 1] = 0.25

    bounds = ([(-2.5, 2.5)] * n + [(-2.5, 2.5)] * n +
              [(-0.99, 0.99)] + [(0, 1.5)])
    neutral_idx = df_fit['neutral'].values.astype(float)

    res = minimize(dc_log_likelihood, x0,
                   args=(df_fit, teams, neutral_idx),
                   method='SLSQP', bounds=bounds,
                   options={'maxiter': 1000, 'ftol': 1e-8})

    if verbose:
        print(f"  [v2] Convergencia: {res.success} | Equipos: {len(teams)}")
        print(f"  rho={res.x[2*n]:.4f}  gamma={res.x[2*n+1]:.4f}")

    return {
        'attack':  dict(zip(teams, res.x[:n])),
        'defence': dict(zip(teams, res.x[n:2*n])),
        'rho':     res.x[2*n],
        'gamma':   res.x[2*n + 1],
        'success': res.success,
        'teams':   teams,
    }



# ══════════════════════════════════════════════════════════════
# PREDICCION MONTE CARLO MEJORADA (v2)
# ══════════════════════════════════════════════════════════════
"""
DIFERENCIA CLAVE vs v1:
  En v1, predict_match solo usa los parametros base de Dixon-Coles.
  En v2, predict_match_v2 INTEGRA todos los ajustes:
    - Necesidad de ganar → ajuste lambda
    - Forma contextual → ajuste lambda
    - Bajas → penalizacion lambda
    - Matchup → ajuste lambda
    - Fatiga → multiplicador lambda
"""

def predict_match_v2(home, away, params, neutral=False, n_sim=N_SIM,
                     importance_home=0.5, importance_away=0.5,
                     form_home=None, form_away=None,
                     injuries_home=None, injuries_away=None,
                     profile_home=None, profile_away=None,
                     fatigue_home=1.0, fatigue_away=1.0):
    """
    Prediccion mejorada con todos los factores integrados.
    
    Args:
        params: parametros Dixon-Coles del modelo base
        importance_*: indice de necesidad de ganar (0-1)
        form_*: dict de forma contextual
        injuries_*: dict de impacto de bajas
        profile_*: dict de perfil de equipo
        fatigue_*: factor de fatiga (0.95-1.02)
    """
    atk = params['attack']
    dfc = params['defence']
    rho = params['rho']
    gamma = params['gamma'] if not neutral else 0.0

    # Lambda base (Dixon-Coles)
    atk_h = atk.get(home, get_fifa_prior(home))
    dfc_a = dfc.get(away, -get_fifa_prior(away) * 0.5)
    atk_a = atk.get(away, get_fifa_prior(away))
    dfc_h = dfc.get(home, -get_fifa_prior(home) * 0.5)

    lam_h = np.exp(atk_h + dfc_a + gamma)
    lam_a = np.exp(atk_a + dfc_h)

    # ── AJUSTE 1: Necesidad de ganar ──
    imp_adj_h, imp_adj_a = importance_to_lambda_adj(importance_home,
                                                     importance_away)
    lam_h *= imp_adj_h
    lam_a *= imp_adj_a

    # ── AJUSTE 2: Forma contextual ──
    if form_home and form_home.get('weighted_pts_pg') is not None:
        # Momentum positivo → boost ofensivo
        momentum_h = form_home.get('momentum', 0)
        form_attack_h = form_home.get('attack_form', 0.5)
        # Ajuste suave basado en forma ofensiva vs promedio (0.5)
        form_adj_h = 1.0 + (form_attack_h - 0.5) * 0.08 + momentum_h * 0.04
        lam_h *= np.clip(form_adj_h, 0.94, 1.06)
    
    if form_away and form_away.get('weighted_pts_pg') is not None:
        momentum_a = form_away.get('momentum', 0)
        form_attack_a = form_away.get('attack_form', 0.5)
        form_adj_a = 1.0 + (form_attack_a - 0.5) * 0.08 + momentum_a * 0.04
        lam_a *= np.clip(form_adj_a, 0.94, 1.06)

    # ── AJUSTE 3: Impacto de bajas ──
    if injuries_home:
        lam_h *= (1.0 - injuries_home.get('attack_penalty', 0))
        # Bajas defensivas del HOME benefician al AWAY
        lam_a *= (1.0 + injuries_home.get('defense_penalty', 0) * 0.5)
    
    if injuries_away:
        lam_a *= (1.0 - injuries_away.get('attack_penalty', 0))
        lam_h *= (1.0 + injuries_away.get('defense_penalty', 0) * 0.5)

    # ── AJUSTE 4: Matchup (fortalezas vs debilidades) ──
    if profile_home and profile_away:
        mu_adj_h, mu_adj_a = calc_matchup_adjustment(profile_home, profile_away)
        lam_h *= mu_adj_h
        lam_a *= mu_adj_a

    # ── AJUSTE 5: Fatiga ──
    lam_h *= fatigue_home
    lam_a *= fatigue_away

    # Asegurar lambdas razonables
    lam_h = float(np.clip(lam_h, 0.3, 4.0))
    lam_a = float(np.clip(lam_a, 0.2, 3.5))

    # ── Monte Carlo ──
    hg = np.random.poisson(lam_h, n_sim)
    ag = np.random.poisson(lam_a, n_sim)

    # Correccion rho (Dixon-Coles para scores bajos)
    r = np.random.random(n_sim)
    ok = np.ones(n_sim, dtype=bool)
    for mask, thresh in [
        ((hg==0)&(ag==0), max(0, 1 - lam_h*lam_a*rho)),
        ((hg==1)&(ag==0), max(0, 1 + lam_a*rho)),
        ((hg==0)&(ag==1), max(0, 1 + lam_h*rho)),
        ((hg==1)&(ag==1), max(0, 1 - rho)),
    ]:
        ok[mask] &= r[mask] < thresh

    hg, ag = hg[ok], ag[ok]
    nv = max(len(hg), 1)

    # Marcadores mas probables
    scores = {}
    for h, a in zip(hg, ag):
        k = (int(h), int(a))
        scores[k] = scores.get(k, 0) + 1
    top5 = sorted(scores.items(), key=lambda x: -x[1])[:5]
    top5 = [(h, a, cnt/nv) for (h, a), cnt in top5]

    # Matriz de marcadores
    matrix = np.zeros((6, 6))
    for (h, a), cnt in scores.items():
        if h <= 5 and a <= 5:
            matrix[h, a] = cnt / nv

    total = hg + ag

    return {
        'home': home, 'away': away,
        'lambda_home': lam_h, 'lambda_away': lam_a,
        'p_home': np.sum(hg > ag) / nv,
        'p_draw': np.sum(hg == ag) / nv,
        'p_away': np.sum(ag > hg) / nv,
        'top_scores': top5,
        'score_matrix': matrix.tolist(),
        'neutral': neutral,
        'known_home': home in params['teams'],
        'known_away': away in params['teams'],
        # Over/Under
        'p_over05':   np.sum(total >= 1) / nv,
        'p_over15':   np.sum(total >= 2) / nv,
        'p_over25':   np.sum(total >= 3) / nv,
        'p_over35':   np.sum(total >= 4) / nv,
        'p_over45':   np.sum(total >= 5) / nv,
        'p_under25':  np.sum(total <= 2) / nv,
        'p_under35':  np.sum(total <= 3) / nv,
        # BTTS
        'p_btts_yes': np.sum((hg >= 1) & (ag >= 1)) / nv,
        'p_btts_no':  np.sum((hg == 0) | (ag == 0)) / nv,
        # Goles esperados
        'exp_goals_home': round(lam_h, 3),
        'exp_goals_away': round(lam_a, 3),
        'exp_goals_total': round(lam_h + lam_a, 3),
        # Ajustes aplicados (para debugging/reporte)
        'adjustments': {
            'importance': (imp_adj_h, imp_adj_a),
            'fatigue': (fatigue_home, fatigue_away),
        },
    }



# ══════════════════════════════════════════════════════════════
# VALUE BET CALCULATION (Mejorado para Mundial J2)
# ══════════════════════════════════════════════════════════════

def calc_value_v2(pred, odds, form_home=None, form_away=None,
                  importance_home=0.5, importance_away=0.5):
    """
    Calculo de value bet mejorado para Mundial.
    Diferencias vs v1:
      - Empates activados (frecuentes en J2)
      - Visitante reactivado con umbral alto
      - Bonus por necesidad de ganar alta (equipo presionado puede fallar)
    """
    res = {}
    for outcome, prob_key, odd in [
        ('home', 'p_home', odds.get('home')),
        ('draw', 'p_draw', odds.get('draw')),
        ('away', 'p_away', odds.get('away')),
    ]:
        if not (odd and odd > 1.0):
            continue

        implied = 1.0 / odd
        model_p = pred[prob_key]
        value = model_p - implied
        edge_rel = value / implied if implied > 0 else 0

        # Umbrales diferenciados
        if outcome == 'home':
            thresh = VALUE_THRESH_HOME
            form_min = FORM_MIN_PTS_HOME
            form_pts = form_home
        elif outcome == 'away':
            thresh = VALUE_THRESH_AWAY
            form_min = FORM_MIN_PTS_AWAY
            form_pts = form_away
        else:  # draw
            if not DRAW_ENABLED:
                res[outcome] = {
                    'prob_model': model_p, 'prob_implied': implied,
                    'odd': odd, 'value': value, 'edge_rel': edge_rel,
                    'has_value': False, 'strong_value': False,
                    'blocked_reason': 'Empates desactivados',
                }
                continue
            thresh = VALUE_THRESH_DRAW
            form_min = 0.0
            form_pts = None

        # Filtro de forma
        form_ok = True
        form_warn = None
        if value > thresh and form_pts is not None:
            if form_pts < form_min:
                form_ok = False
                form_warn = f'Forma baja: {form_pts} pts/j (min {form_min})'

        has_value = value > thresh and form_ok
        strong_value = has_value and edge_rel > 0.08

        # BONUS Mundial J2: si equipo rival tiene presion extrema,
        # el empate tiene mas value (equipo presionado puede bloquearse)
        if outcome == 'draw' and has_value:
            max_imp = max(importance_home, importance_away)
            if max_imp >= 0.8:
                strong_value = strong_value or (edge_rel > 0.05)

        res[outcome] = {
            'prob_model': model_p,
            'prob_implied': implied,
            'odd': odd,
            'value': value,
            'edge_rel': edge_rel,
            'has_value': has_value,
            'strong_value': strong_value,
            'blocked_reason': form_warn,
        }
    return res



# ══════════════════════════════════════════════════════════════
# API-FOOTBALL INTEGRATION (reutilizada de v1)
# ══════════════════════════════════════════════════════════════
AF_BASE = "https://v3.football.api-sports.io"

def _af_get(endpoint, params_dict, api_key):
    import time
    try:
        import urllib.request, urllib.parse
        qs = urllib.parse.urlencode(params_dict)
        url = f"{AF_BASE}/{endpoint}?{qs}"
        req = urllib.request.Request(url, headers={"x-apisports-key": api_key})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        time.sleep(0.5)
        return data.get("response", [])
    except Exception as e:
        print(f"  ! API-Football [{endpoint}]: {e}")
        return []

def get_team_id(team_name, api_key):
    res = _af_get("teams", {"name": team_name, "type": "National"}, api_key)
    if not res:
        res = _af_get("teams", {"search": team_name[:6]}, api_key)
    if res:
        return res[0]["team"]["id"], res[0]["team"]["name"]
    return None, None

def get_injuries(team_id, api_key):
    res = _af_get("injuries", {"team": team_id, "league": 1}, api_key)
    players = []
    for p in res:
        players.append({
            "name": p["player"]["name"],
            "reason": p["player"].get("reason", "Lesion"),
            "status": p["player"].get("type", "?"),
            "position": p.get("player", {}).get("position", "Midfielder"),
        })
    return players

def get_squad(team_id, api_key):
    res = _af_get("players/squads", {"team": team_id}, api_key)
    if not res:
        return []
    players = []
    for p in res[0].get("players", []):
        players.append({
            "name": p["name"],
            "position": p["position"],
            "age": p.get("age", "?"),
            "number": p.get("number", "?"),
        })
    return players

def get_head_to_head(team_id_home, team_id_away, api_key, last=5):
    res = _af_get("fixtures/headtohead",
                  {"h2h": f"{team_id_home}-{team_id_away}", "last": last},
                  api_key)
    matches = []
    for m in res:
        fix = m.get("fixture", {})
        tms = m.get("teams", {})
        goal = m.get("goals", {})
        matches.append({
            "date": fix.get("date", "")[:10],
            "home": tms.get("home", {}).get("name", "?"),
            "away": tms.get("away", {}).get("name", "?"),
            "home_goals": goal.get("home"),
            "away_goals": goal.get("away"),
        })
    return matches

def fetch_pre_match_info(home_name, away_name, api_key):
    """Recopila info pre-partido de API-Football con datos de bajas."""
    print(f"  [API] {home_name} vs {away_name}...")
    home_id, home_official = get_team_id(home_name, api_key)
    away_id, away_official = get_team_id(away_name, api_key)
    if not home_id or not away_id:
        return None
    
    h2h = get_head_to_head(home_id, away_id, api_key, last=5)
    home_injuries = get_injuries(home_id, api_key)
    away_injuries = get_injuries(away_id, api_key)
    home_squad = get_squad(home_id, api_key)
    away_squad = get_squad(away_id, api_key)
    
    return {
        "home_id": home_id, "away_id": away_id,
        "home_official": home_official, "away_official": away_official,
        "h2h": h2h,
        "home_injuries": home_injuries, "away_injuries": away_injuries,
        "home_squad": home_squad, "away_squad": away_squad,
    }



# ══════════════════════════════════════════════════════════════
# THE ODDS API (selecciones)
# ══════════════════════════════════════════════════════════════
INTL_SPORT_KEYS = [
    'soccer_fifa_world_cup',
    'soccer_fifa_world_cup_winner',
    'soccer_international_friendlies',
    'soccer_conmebol_copa_america',
    'soccer_uefa_european_championship',
    'soccer_uefa_nations_league',
]

def fetch_international_fixtures(api_key, hours_ahead=240):
    """Consulta The Odds API para partidos internacionales."""
    try:
        import urllib.request
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)
        all_fixtures = []

        # Descubrir sports activos
        try:
            url = f"https://api.the-odds-api.com/v4/sports/?apiKey={api_key}"
            with urllib.request.urlopen(url, timeout=10) as r:
                all_sports = json.loads(r.read())
            active_keys = [s['key'] for s in all_sports
                          if s.get('active') and any(
                              x in s['key'] for x in
                              ['world_cup','international','copa_america',
                               'european_championship','nations_league'])]
        except Exception:
            active_keys = INTL_SPORT_KEYS

        if not active_keys:
            active_keys = INTL_SPORT_KEYS

        for sport_key in active_keys:
            url = (f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
                   f"?apiKey={api_key}&regions=eu&markets=h2h"
                   f"&oddsFormat=decimal"
                   f"&bookmakers=pinnacle,bet365,unibet")
            try:
                with urllib.request.urlopen(url, timeout=8) as resp:
                    data = json.loads(resp.read())
            except Exception:
                continue

            for g in data:
                t = datetime.fromisoformat(
                    g['commence_time'].replace('Z', '+00:00'))
                if t > cutoff:
                    continue

                home_api = g['home_team']
                away_api = g['away_team']

                odds_by_book = {}
                for book in g.get('bookmakers', []):
                    for mkt in book.get('markets', []):
                        if mkt['key'] == 'h2h':
                            o = {'home': None, 'draw': None, 'away': None}
                            for outcome in mkt['outcomes']:
                                nm = outcome['name']
                                if nm == home_api:   o['home'] = outcome['price']
                                elif nm == 'Draw':   o['draw'] = outcome['price']
                                elif nm == away_api: o['away'] = outcome['price']
                            if o['home']:
                                odds_by_book[book['key']] = o
                            break

                odds, source = None, 'N/A'
                for pref in ['pinnacle', 'bet365', 'unibet']:
                    if pref in odds_by_book:
                        odds = odds_by_book[pref]
                        source = pref
                        break
                if odds is None and odds_by_book:
                    source, odds = next(iter(odds_by_book.items()))
                if odds is None:
                    odds = {'home': None, 'draw': None, 'away': None}

                neutral_detected = sport_key in [
                    'soccer_fifa_world_cup',
                    'soccer_conmebol_copa_america',
                    'soccer_uefa_european_championship',
                ]

                all_fixtures.append({
                    'commence': t,
                    'home_api': home_api, 'away_api': away_api,
                    'home_csv': home_api, 'away_csv': away_api,
                    'odds': odds, 'odds_source': source,
                    'sport_key': sport_key,
                    'neutral': neutral_detected,
                    'tournament': sport_key.replace('soccer_','').replace('_',' ').title(),
                })

        # Deduplicar
        seen = set()
        unique = []
        for fx in all_fixtures:
            key = (fx['home_api'], fx['away_api'], fx['commence'].date())
            if key not in seen:
                seen.add(key)
                unique.append(fx)

        return sorted(unique, key=lambda x: x['commence'])[:30]
    except Exception as e:
        print(f"  ! Error Odds API: {e}")
        return []



# ══════════════════════════════════════════════════════════════
# REPORTE HTML v2 (con todos los factores nuevos)
# ══════════════════════════════════════════════════════════════

def generate_html_v2(analyses, output_path):
    """Genera reporte HTML mejorado mostrando todos los factores."""
    
    def form_dots(seq):
        if not seq:
            return '<span style="color:#4a5568">Sin datos</span>'
        dots = ""
        for r in seq:
            c = {'W':'#48bb78','D':'#f6e05e','L':'#fc8181'}[r]
            dots += (f'<span style="display:inline-block;width:18px;height:18px;'
                     f'border-radius:50%;background:{c};font-size:.6rem;'
                     f'line-height:18px;text-align:center;color:#000;'
                     f'font-weight:700;margin-right:2px">{r}</span>')
        return dots
    
    def importance_badge(imp):
        if imp >= 0.8:
            return (f'<span style="background:rgba(252,129,129,.15);border:1px solid #fc8181;'
                    f'color:#fc8181;padding:.2rem .5rem;border-radius:8px;font-size:.7rem">'
                    f'NECESITA GANAR ({imp*100:.0f}%)</span>')
        elif imp >= 0.6:
            return (f'<span style="background:rgba(246,224,94,.1);border:1px solid #f6e05e;'
                    f'color:#f6e05e;padding:.2rem .5rem;border-radius:8px;font-size:.7rem">'
                    f'Presion alta ({imp*100:.0f}%)</span>')
        else:
            return (f'<span style="background:rgba(72,187,120,.08);border:1px solid #48bb78;'
                    f'color:#48bb78;padding:.2rem .5rem;border-radius:8px;font-size:.7rem">'
                    f'Normal ({imp*100:.0f}%)</span>')
    
    def injury_badge(inj_impact):
        if not inj_impact or inj_impact['severity'] == 'low':
            return '<span style="color:#48bb78;font-size:.72rem">Sin bajas significativas</span>'
        col = {'medium':'#f6e05e','high':'#fc8181','critical':'#e53e3e'}
        c = col.get(inj_impact['severity'], '#f6e05e')
        pen = inj_impact['attack_penalty'] + inj_impact['defense_penalty']
        txt = f"Impacto: -{pen*100:.1f}% capacidad"
        if inj_impact['key_players_out']:
            txt += f" ({', '.join(inj_impact['key_players_out'][:3])})"
        return (f'<span style="color:{c};font-size:.72rem">'
                f'{inj_impact["severity"].upper()}: {txt}</span>')
    
    def profile_html(profile):
        if not profile:
            return ''
        s_html = ""
        for s in profile.get('strengths', [])[:3]:
            s_html += f'<div style="color:#48bb78;font-size:.7rem">+ {s}</div>'
        for w in profile.get('weaknesses', [])[:3]:
            s_html += f'<div style="color:#fc8181;font-size:.7rem">- {w}</div>'
        return s_html

    def badge(outcome, label, val_dict):
        v = val_dict.get(outcome)
        if not v:
            return f'<span class="badge no-data">{label} --</span>'
        pct = f"{v['prob_model']*100:.1f}%"
        odd = f"{v['odd']:.2f}"
        tip = f"+{v['value']*100:.1f}%" if v['value'] > 0 else f"{v['value']*100:.1f}%"
        if v.get('blocked_reason') and not v['has_value']:
            return (f'<span class="badge badge-blocked">'
                    f'! {label}: {pct} @ {odd} ({tip})</span>')
        if v['strong_value']:
            cls, icon = 'value-strong', 'FIRE'
        elif v['has_value']:
            cls, icon = 'value-yes', 'GO'
        else:
            cls, icon = 'value-no', 'NO'
        return (f'<span class="badge {cls}">'
                f'[{icon}] {label}: {pct} @ {odd} ({tip})</span>')

    cards = ""
    for a in analyses:
        pred = a['pred']
        val = a['value']
        fix = a['fixture']
        ctx_home = a.get('ctx_form_home', {})
        ctx_away = a.get('ctx_form_away', {})
        imp_h = a.get('importance_home', 0.5)
        imp_a = a.get('importance_away', 0.5)
        inj_h = a.get('injury_impact_home')
        inj_a = a.get('injury_impact_away')
        prof_h = a.get('profile_home')
        prof_a = a.get('profile_away')

        hora = fix['commence'].astimezone().strftime('%H:%M')
        fecha = fix['commence'].astimezone().strftime('%d/%m/%Y')
        rank_h = FIFA_RANKING.get(fix['home_csv'], '?')
        rank_a = FIFA_RANKING.get(fix['away_csv'], '?')

        # Top marcadores
        top_html = ""
        for h, ag_s, p in pred['top_scores']:
            w = min(int(p * 500), 260)
            top_html += (f'<div class="score-row">'
                         f'<span class="slabel">{h}-{ag_s}</span>'
                         f'<div class="bwrap"><div class="bbar" style="width:{w}px"></div></div>'
                         f'<span class="spct">{p*100:.1f}%</span></div>')

        cards += f"""
        <div class="card">
          <div class="mh">
            <div class="teams">{fix['home_api']} <span class="vs">vs</span> {fix['away_api']}</div>
            <div class="mtime">{fecha} {hora}</div>
          </div>
          <div style="font-size:.72rem;color:#4a5568;margin-bottom:.5rem">
            FIFA: #{rank_h} vs #{rank_a} | {fix.get('tournament','')}
            {'| SEDE NEUTRAL' if fix.get('neutral') else ''}
          </div>
          
          <div class="section-title">NECESIDAD DE GANAR</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin-bottom:.8rem">
            <div>{importance_badge(imp_h)} <span style="font-size:.68rem;color:#4a5568">{fix['home_api']}</span></div>
            <div>{importance_badge(imp_a)} <span style="font-size:.68rem;color:#4a5568">{fix['away_api']}</span></div>
          </div>

          <div class="section-title">FORMA CONTEXTUAL (ult. {FORM_MATCHES})</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin-bottom:.8rem">
            <div>
              <div style="font-size:.72rem;color:#63b3ed;margin-bottom:.3rem">{fix['home_api']}</div>
              {form_dots(ctx_home.get('form_sequence', []))}
              <div style="font-size:.68rem;color:#4a5568;margin-top:.3rem">
                Pts pond: {ctx_home.get('weighted_pts_pg','?')} |
                Atq: {ctx_home.get('attack_form','?')} |
                Def: {ctx_home.get('defense_form','?')} |
                Mom: {ctx_home.get('momentum','?')}
              </div>
            </div>
            <div>
              <div style="font-size:.72rem;color:#b794f4;margin-bottom:.3rem">{fix['away_api']}</div>
              {form_dots(ctx_away.get('form_sequence', []))}
              <div style="font-size:.68rem;color:#4a5568;margin-top:.3rem">
                Pts pond: {ctx_away.get('weighted_pts_pg','?')} |
                Atq: {ctx_away.get('attack_form','?')} |
                Def: {ctx_away.get('defense_form','?')} |
                Mom: {ctx_away.get('momentum','?')}
              </div>
            </div>
          </div>

          <div class="section-title">BAJAS E IMPACTO</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin-bottom:.8rem">
            <div>{injury_badge(inj_h)}</div>
            <div>{injury_badge(inj_a)}</div>
          </div>

          <div class="section-title">FORTALEZAS Y DEBILIDADES</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin-bottom:.8rem">
            <div>{profile_html(prof_h)}</div>
            <div>{profile_html(prof_a)}</div>
          </div>

          <div class="section-title">PREDICCION v2</div>
          <div class="lam">
            Lambda local <strong>{pred['lambda_home']:.2f}</strong> |
            Lambda visitante <strong>{pred['lambda_away']:.2f}</strong> |
            Goles esp: <strong>{pred['exp_goals_total']:.2f}</strong>
          </div>
          <div class="badges">
            {badge('home','1',val)}
            {badge('draw','X',val)}
            {badge('away','2',val)}
          </div>

          <div class="section-title">MERCADOS ADICIONALES</div>
          <div style="font-size:.78rem;display:grid;grid-template-columns:1fr 1fr;gap:.5rem;margin-bottom:.8rem">
            <div>+1.5: {pred.get('p_over15',0)*100:.1f}% | +2.5: {pred.get('p_over25',0)*100:.1f}% | +3.5: {pred.get('p_over35',0)*100:.1f}%</div>
            <div>BTTS Si: {pred.get('p_btts_yes',0)*100:.1f}% | BTTS No: {pred.get('p_btts_no',0)*100:.1f}%</div>
          </div>

          <div class="section-title">TOP MARCADORES</div>
          <div class="scores">{top_html}</div>
        </div>"""

    n_value = sum(1 for a in analyses for v in a['value'].values()
                  if v.get('has_value'))
    n_strong = sum(1 for a in analyses for v in a['value'].values()
                   if v.get('strong_value'))
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>International Analyzer v2 - Mundial 2026</title>
<style>
:root{{--bg:#080d18;--card:#0f1623;--bord:#1a2235;--acc:#63b3ed;--grn:#48bb78;--red:#fc8181;--ylw:#f6e05e;--txt:#dde3ee;--mut:#4a5568;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--txt);font-family:'Inter',system-ui,sans-serif;font-size:14px;}}
header{{background:linear-gradient(135deg,#050a14,#0d2240,#14082a);border-bottom:1px solid var(--bord);padding:2.5rem 1rem;text-align:center;}}
header h1{{font-size:1.8rem;color:var(--acc);letter-spacing:3px;font-family:monospace;}}
header p{{color:var(--mut);margin-top:.5rem;font-size:.8rem;}}
.grid{{max-width:1000px;margin:0 auto;padding:2rem 1rem;display:grid;gap:1.5rem;}}
.statsbar{{display:flex;flex-wrap:wrap;gap:2rem;background:var(--card);border:1px solid var(--bord);border-radius:12px;padding:1.2rem;}}
.stat .sl{{font-size:.65rem;text-transform:uppercase;color:var(--mut);}}
.stat .sv{{font-family:monospace;font-size:1.2rem;color:var(--acc);margin-top:.2rem;}}
.card{{background:var(--card);border:1px solid var(--bord);border-radius:14px;padding:1.5rem;}}
.mh{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.6rem;}}
.teams{{font-family:monospace;font-size:1.1rem;color:#fff;}}
.vs{{color:var(--mut);font-size:.8rem;margin:0 .4rem;}}
.mtime{{font-size:.82rem;color:var(--acc);}}
.section-title{{font-size:.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--mut);margin:1rem 0 .4rem;border-bottom:1px solid var(--bord);padding-bottom:.3rem;}}
.lam{{font-size:.8rem;color:var(--mut);margin-bottom:.6rem;}}
.lam strong{{color:var(--txt);}}
.badges{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.8rem;}}
.badge{{padding:.35rem .75rem;border-radius:20px;font-family:monospace;font-size:.72rem;}}
.value-strong{{background:rgba(246,224,94,.12);border:1px solid var(--ylw);color:var(--ylw);}}
.value-yes{{background:rgba(72,187,120,.12);border:1px solid var(--grn);color:var(--grn);}}
.value-no{{background:rgba(252,129,129,.08);border:1px solid var(--red);color:var(--red);}}
.no-data{{background:rgba(74,85,104,.15);border:1px solid var(--mut);color:var(--mut);}}
.badge-blocked{{background:rgba(74,85,104,.12);border:1px solid #2d3748;color:#718096;}}
.scores{{display:flex;flex-direction:column;gap:.3rem;}}
.score-row{{display:flex;align-items:center;gap:.7rem;}}
.slabel{{font-family:monospace;font-size:.82rem;color:var(--acc);width:2.5rem;}}
.bwrap{{flex:1;max-width:260px;background:rgba(255,255,255,.05);border-radius:3px;height:5px;}}
.bbar{{height:100%;background:linear-gradient(90deg,var(--acc),#b794f4);border-radius:3px;}}
.spct{{font-size:.75rem;color:var(--mut);width:3rem;text-align:right;}}
footer{{text-align:center;padding:2rem;color:var(--mut);font-size:.72rem;border-top:1px solid var(--bord);margin-top:2rem;}}
</style>
</head>
<body>
<header>
  <h1>INTERNATIONAL ANALYZER v2</h1>
  <p>Dixon-Coles + Necesidad de Ganar + Forma Contextual + Bajas + Matchup | {now_str}</p>
</header>
<div class="grid">
  <div class="statsbar">
    <div class="stat"><div class="sl">Partidos</div><div class="sv">{len(analyses)}</div></div>
    <div class="stat"><div class="sl">Value bets</div><div class="sv">{n_value}</div></div>
    <div class="stat"><div class="sl">Value solido</div><div class="sv" style="color:var(--ylw)">{n_strong}</div></div>
    <div class="stat"><div class="sl">Modelo</div><div class="sv">v2.0</div></div>
  </div>
  {cards if analyses else '<div style="text-align:center;padding:3rem;color:var(--mut)">Sin partidos disponibles</div>'}
</div>
<footer>
  Modelo v2 - Dixon-Coles + Factores Contextuales. No garantiza resultados. Apuesta con responsabilidad.
</footer>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n  [v2] Reporte HTML: {output_path}")



# ══════════════════════════════════════════════════════════════
# MAIN — EJECUCION COMPLETA v2
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 65)
    print("  INTERNATIONAL ANALYZER v2 — Mundial 2026 Jornada 2")
    print("  Mejoras: Necesidad+Forma+Bajas+Matchup+Fatiga")
    print("=" * 65)

    # 0. Ranking FIFA
    print(f"\n[1/6] Cargando ranking FIFA...")
    FIFA_RANKING.update(load_fifa_ranking())

    # 1. Cargar datos
    print(f"\n[2/6] Cargando datos historicos...")
    df = load_results()

    # 2. Entrenar modelo Dixon-Coles
    print(f"\n[3/6] Entrenando Dixon-Coles...")
    params = fit_model(df, verbose=True)

    # Top equipos
    print(f"\n  Top 10 ataques:")
    for team, v in sorted(params['attack'].items(), key=lambda x: -x[1])[:10]:
        rank = FIFA_RANKING.get(team, '?')
        print(f"    #{str(rank):<3} {team:<22} {v:+.3f}")

    # 3. Obtener partidos
    print(f"\n[4/6] Buscando partidos proximos...")
    fixtures = fetch_international_fixtures(API_KEY_ODDS)

    if not fixtures:
        print("  Sin partidos con cuotas. Usando demo Mundial J2...")
        demo_matches = [
            ('Argentina', 'Chile', True),
            ('France', 'Denmark', True),
            ('Spain', 'Japan', True),
            ('Germany', 'Scotland', True),
            ('Brazil', 'Switzerland', True),
            ('England', 'Iran', True),
            ('Netherlands', 'Ecuador', True),
            ('Portugal', 'South Korea', True),
        ]
        now = datetime.now(timezone.utc)
        fixtures = []
        for i, (h, a, neutral) in enumerate(demo_matches):
            fixtures.append({
                'commence': now + timedelta(hours=i*3),
                'home_api': h, 'away_api': a,
                'home_csv': h, 'away_csv': a,
                'odds': {'home': None, 'draw': None, 'away': None},
                'odds_source': 'demo',
                'sport_key': 'soccer_fifa_world_cup',
                'neutral': neutral,
                'tournament': 'FIFA World Cup 2026 - Matchday 2',
            })
    
    print(f"  {len(fixtures)} partidos encontrados")

    # 4. Configuracion de Jornada 2 (EDITAR AQUI para cada partido)
    # DATOS REALES JORNADA 1 — Mundial 2026 (actualizado 16/06/2026)
    MATCHDAY_2_INFO = {
        # === GANARON J1 (3 pts) ===
        'Australia':             {'j1_result': 'W', 'points': 3, 'gd': +2, 'group_position': 1},
        'France':                {'j1_result': 'W', 'points': 3, 'gd': +2, 'group_position': 1},
        'Germany':               {'j1_result': 'W', 'points': 3, 'gd': +6, 'group_position': 1},
        'Ivory Coast':           {'j1_result': 'W', 'points': 3, 'gd': +1, 'group_position': 1},
        'Mexico':                {'j1_result': 'W', 'points': 3, 'gd': +2, 'group_position': 1},
        'Scotland':              {'j1_result': 'W', 'points': 3, 'gd': +1, 'group_position': 1},
        'South Korea':           {'j1_result': 'W', 'points': 3, 'gd': +1, 'group_position': 1},
        'Sweden':                {'j1_result': 'W', 'points': 3, 'gd': +4, 'group_position': 1},
        'United States':         {'j1_result': 'W', 'points': 3, 'gd': +3, 'group_position': 1},
        # === EMPATARON J1 (1 pt) ===
        'Belgium':               {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Bosnia and Herzegovina':{'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Brazil':                {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Canada':                {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Cape Verde':            {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Egypt':                 {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Iran':                  {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Japan':                 {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Morocco':               {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Netherlands':           {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'New Zealand':           {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Qatar':                 {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Saudi Arabia':          {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Spain':                 {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Switzerland':           {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        'Uruguay':               {'j1_result': 'D', 'points': 1, 'gd': 0, 'group_position': 2},
        # === PERDIERON J1 (0 pts) — NECESITAN GANAR ===
        'Curacao':               {'j1_result': 'L', 'points': 0, 'gd': -6, 'group_position': 4},
        'Czech Republic':        {'j1_result': 'L', 'points': 0, 'gd': -1, 'group_position': 4},
        'Ecuador':               {'j1_result': 'L', 'points': 0, 'gd': -1, 'group_position': 4},
        'Haiti':                 {'j1_result': 'L', 'points': 0, 'gd': -1, 'group_position': 4},
        'Paraguay':              {'j1_result': 'L', 'points': 0, 'gd': -3, 'group_position': 4},
        'Senegal':               {'j1_result': 'L', 'points': 0, 'gd': -2, 'group_position': 4},
        'South Africa':          {'j1_result': 'L', 'points': 0, 'gd': -2, 'group_position': 4},
        'Tunisia':               {'j1_result': 'L', 'points': 0, 'gd': -4, 'group_position': 4},
        'Turkey':                {'j1_result': 'L', 'points': 0, 'gd': -2, 'group_position': 4},
    }

    # 5. Analizar cada partido con TODOS los factores
    print(f"\n[5/6] Analizando partidos con modelo v2...")
    analyses = []

    for fix in fixtures:
        home = fix['home_csv']
        away = fix['away_csv']
        
        # ── Necesidad de ganar ──
        h_info = MATCHDAY_2_INFO.get(home, {})
        a_info = MATCHDAY_2_INFO.get(away, {})
        
        imp_home = calc_match_importance(
            home, matchday=2,
            points=h_info.get('points'),
            gd=h_info.get('gd'),
            j1_result=h_info.get('j1_result'),
            group_position=h_info.get('group_position'),
            is_world_cup=True
        )
        imp_away = calc_match_importance(
            away, matchday=2,
            points=a_info.get('points'),
            gd=a_info.get('gd'),
            j1_result=a_info.get('j1_result'),
            group_position=a_info.get('group_position'),
            is_world_cup=True
        )
        
        # ── Forma contextual ──
        ctx_home = get_contextual_form(df, home, FIFA_RANKING, FORM_MATCHES)
        ctx_away = get_contextual_form(df, away, FIFA_RANKING, FORM_MATCHES)
        
        # ── Perfil de equipo ──
        prof_home = build_team_profile(df, home, FIFA_RANKING)
        prof_away = build_team_profile(df, away, FIFA_RANKING)
        
        # ── Fatiga ──
        match_date = fix['commence']
        if hasattr(match_date, 'replace'):
            if match_date.tzinfo:
                match_date_naive = match_date.replace(tzinfo=None)
            else:
                match_date_naive = match_date
        else:
            match_date_naive = match_date
        
        # Convertir a pandas Timestamp para comparacion
        match_ts = pd.Timestamp(match_date_naive)
        fatigue_h = calc_fatigue_factor(df, home, match_ts)
        fatigue_a = calc_fatigue_factor(df, away, match_ts)
        
        # ── Bajas (de API-Football si disponible) ──
        inj_impact_h = {'attack_penalty': 0, 'defense_penalty': 0,
                        'severity': 'low', 'key_players_out': [],
                        'n_starters_out': 0}
        inj_impact_a = inj_impact_h.copy()
        
        pre_info = None
        if API_KEY_FOOTBALL and len(analyses) < 3:  # primeros 3 partidos
            pre_info = fetch_pre_match_info(home, away, API_KEY_FOOTBALL)
            if pre_info:
                inj_impact_h = calc_injury_impact(pre_info.get('home_injuries', []))
                inj_impact_a = calc_injury_impact(pre_info.get('away_injuries', []))
        
        # ── PREDICCION v2 (todo integrado) ──
        pred = predict_match_v2(
            home, away, params,
            neutral=fix.get('neutral', False),
            n_sim=N_SIM,
            importance_home=imp_home,
            importance_away=imp_away,
            form_home=ctx_home,
            form_away=ctx_away,
            injuries_home=inj_impact_h,
            injuries_away=inj_impact_a,
            profile_home=prof_home,
            profile_away=prof_away,
            fatigue_home=fatigue_h,
            fatigue_away=fatigue_a,
        )
        
        # ── Value bet ──
        value = calc_value_v2(
            pred, fix['odds'],
            form_home=ctx_home.get('weighted_pts_pg'),
            form_away=ctx_away.get('weighted_pts_pg'),
            importance_home=imp_home,
            importance_away=imp_away,
        )
        
        analyses.append({
            'fixture': fix, 'pred': pred, 'value': value,
            'ctx_form_home': ctx_home, 'ctx_form_away': ctx_away,
            'importance_home': imp_home, 'importance_away': imp_away,
            'injury_impact_home': inj_impact_h, 'injury_impact_away': inj_impact_a,
            'profile_home': prof_home, 'profile_away': prof_away,
            'pre_info': pre_info,
        })
        
        # Print resumen
        neu = " [NEUTRAL]" if fix.get('neutral') else ""
        print(f"\n  {home} vs {away}{neu}")
        print(f"    Necesidad: {home[:12]}={imp_home:.2f} | {away[:12]}={imp_away:.2f}")
        print(f"    Forma ctx: {home[:12]}={''.join(ctx_home.get('form_sequence',[]))} "
              f"({ctx_home.get('weighted_pts_pg','?')} pts) | "
              f"{away[:12]}={''.join(ctx_away.get('form_sequence',[]))} "
              f"({ctx_away.get('weighted_pts_pg','?')} pts)")
        print(f"    Bajas: {home[:12]}={inj_impact_h['severity']} | "
              f"{away[:12]}={inj_impact_a['severity']}")
        print(f"    Perfil: {home[:12]} atq={prof_home['attack_rating']:.2f} "
              f"def={prof_home['defense_rating']:.2f} | "
              f"{away[:12]} atq={prof_away['attack_rating']:.2f} "
              f"def={prof_away['defense_rating']:.2f}")
        print(f"    v2 Pred: 1:{pred['p_home']*100:.1f}% "
              f"X:{pred['p_draw']*100:.1f}% "
              f"2:{pred['p_away']*100:.1f}% "
              f"(lambda {pred['lambda_home']:.2f}/{pred['lambda_away']:.2f})")
        print(f"    Goles: +2.5={pred.get('p_over25',0)*100:.1f}% "
              f"BTTS={pred.get('p_btts_yes',0)*100:.1f}% "
              f"Total={pred['exp_goals_total']:.2f}")
        
        for out, v in value.items():
            if v.get('strong_value'):
                print(f"    >>> VALUE SOLIDO: {out.upper()} "
                      f"edge={v['value']*100:+.1f}% odd={v['odd']}")
            elif v.get('has_value'):
                print(f"    >> VALUE: {out.upper()} "
                      f"edge={v['value']*100:+.1f}% odd={v['odd']}")

    # 6. Generar HTML
    print(f"\n[6/6] Generando reporte HTML v2...")
    generate_html_v2(analyses, OUTPUT_HTML)
    
    print("\n" + "=" * 65)
    print("  MODELO v2 COMPLETO")
    print("  Factores integrados:")
    print("    1. Necesidad de ganar (resultado J1 + posicion grupo)")
    print("    2. Forma contextual (calidad rival + torneo + recencia)")
    print("    3. Impacto de bajas (cuantificado por posicion)")
    print("    4. Fortalezas/debilidades (matchup ofensivo/defensivo)")
    print("    5. Fatiga (dias de descanso)")
    print("    6. Empates reactivados para fase de grupos Mundial")
    print("=" * 65)
    print(f"\n  INSTRUCCIONES JORNADA 2:")
    print(f"  1. Edita MATCHDAY_2_INFO con resultados REALES de Jornada 1")
    print(f"  2. Ejecuta: python international_analyzer_v2.py")
    print(f"  3. Revisa el reporte HTML generado")
    print(f"  4. Las value bets se calculan automaticamente")
    print("=" * 65)
