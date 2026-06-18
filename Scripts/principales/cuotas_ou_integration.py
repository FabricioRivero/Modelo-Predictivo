#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cuotas_ou_integration.py — Integración de O/U 2.5 y BTTS en international_analyzer.py
===================================================================================
Este módulo se importa en international_analyzer.py y permite:
  - Cargar cuotas extendidas (1X2 + O/U 2.5 + BTTS) desde cuotas_hoy_ou.csv
  - Calcular value bets para mercados O/U 2.5 y BTTS
  - Integrar con el tracker de apuestas para todos los mercados

Uso en international_analyzer.py:
    from cuotas_ou_integration import load_cuotas_ou, calc_value_ou_btts

    # Reemplazar carga de cuotas:
    # cuotas_dict = load_cuotas_from_csv(cuotas_csv)  # ← viejo
    cuotas_dict = load_cuotas_ou(cuotas_csv)  # ← nuevo (carga 1X2 + O/U + BTTS)

    # En el loop de análisis, calcular value para O/U y BTTS:
    value_ou_btts = calc_value_ou_btts(pred, cuota)
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta, timezone

# ── Importar config ───────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'Config'))
from config import CUOTAS_HOY_CSV


def load_cuotas_ou(cuotas_csv=None):
    """
    Carga cuotas extendidas (1X2 + O/U 2.5 + BTTS) desde CSV.

    Busca primero cuotas_hoy_ou.csv (con O/U y BTTS), si no existe,
    fallback a cuotas_hoy.csv (solo 1X2).

    Args:
        cuotas_csv: path al CSV. Si None, usa CUOTAS_HOY_CSV

    Returns:
        dict: {(home_lower, away_lower): {
            'home': float, 'draw': float, 'away': float,
            'over25': float, 'under25': float,
            'btts_yes': float, 'btts_no': float,
            'source': str, 'date': datetime
        }}
    """
    if cuotas_csv is None:
        cuotas_csv = CUOTAS_HOY_CSV

    # Buscar versión extendida primero
    ou_csv = cuotas_csv.replace('.csv', '_ou.csv')

    if os.path.exists(ou_csv):
        print(f"  ✓ Cargando cuotas extendidas (1X2 + O/U + BTTS): {ou_csv}")
        df = pd.read_csv(ou_csv, encoding='utf-8')
        has_ou = True
    elif os.path.exists(cuotas_csv):
        print(f"  ⚠ CSV extendido no encontrado. Usando 1X2 solo: {cuotas_csv}")
        print(f"    Ejecuta: python scraper_cuotas_ou.py")
        df = pd.read_csv(cuotas_csv, encoding='utf-8')
        has_ou = False
    else:
        print(f"  ❌ No se encontró archivo de cuotas: {cuotas_csv}")
        return {}

    cuotas_dict = {}

    for _, row in df.iterrows():
        home = str(row.get('home_team', '')).strip()
        away = str(row.get('away_team', '')).strip()

        if not home or not away:
            continue

        # Parsear fecha
        date_str = str(row.get('date', ''))
        try:
            if pd.notna(row.get('date')):
                if isinstance(row['date'], pd.Timestamp):
                    match_date = row['date'].to_pydatetime()
                else:
                    match_date = pd.to_datetime(row['date'])
            else:
                match_date = datetime.now()
        except:
            match_date = datetime.now()

        # Asegurar timezone
        if hasattr(match_date, 'tzinfo') and match_date.tzinfo is None:
            match_date = match_date.replace(tzinfo=timezone.utc)

        # Cuotas 1X2
        o1 = float(row['odds_home']) if pd.notna(row.get('odds_home')) else None
        ox = float(row['odds_draw']) if pd.notna(row.get('odds_draw')) else None
        o2 = float(row['odds_away']) if pd.notna(row.get('odds_away')) else None

        # Cuotas O/U 2.5 (solo si existen en CSV extendido)
        over25 = float(row['odds_over25']) if has_ou and pd.notna(row.get('odds_over25')) else None
        under25 = float(row['odds_under25']) if has_ou and pd.notna(row.get('odds_under25')) else None

        # Cuotas BTTS (solo si existen en CSV extendido)
        btts_yes = float(row['odds_btts_yes']) if has_ou and pd.notna(row.get('odds_btts_yes')) else None
        btts_no = float(row['odds_btts_no']) if has_ou and pd.notna(row.get('odds_btts_no')) else None

        source = str(row.get('source', 'scraper')).split('|')[0] if pd.notna(row.get('source')) else 'scraper'

        cuotas_dict[(home.lower(), away.lower())] = {
            'home': o1, 'draw': ox, 'away': o2,
            'over25': over25, 'under25': under25,
            'btts_yes': btts_yes, 'btts_no': btts_no,
            'source': source,
            'date': match_date,
        }

    ou_count = sum(1 for v in cuotas_dict.values() if v['over25'] is not None)
    btts_count = sum(1 for v in cuotas_dict.values() if v['btts_yes'] is not None)

    print(f"  ✓ {len(cuotas_dict)} partidos con cuotas cargadas")
    if has_ou:
        print(f"  ✓ {ou_count} con O/U 2.5 | {btts_count} con BTTS")

    return cuotas_dict


def calc_value_ou_btts(pred, cuota):
    """
    Calcula value bets para mercados O/U 2.5 y BTTS.

    Args:
        pred: dict de predicción del modelo (con p_over25, p_under25, p_btts_yes, p_btts_no)
        cuota: dict con cuotas {'over25': float, 'under25': float, 'btts_yes': float, 'btts_no': float}

    Returns:
        dict: {
            'over25': {'value': float, 'has_value': bool, 'strong_value': bool},
            'under25': {'value': float, 'has_value': bool, 'strong_value': bool},
            'btts_yes': {'value': float, 'has_value': bool, 'strong_value': bool},
            'btts_no': {'value': float, 'has_value': bool, 'strong_value': bool},
        }
    """
    results = {}

    # Umbral para value bet (calibrado con backtest)
    VALUE_THRESH = 0.04  # 4% de ventaja mínima
    EDGE_REL_THRESH = 0.09  # 9% edge relativo para value sólido

    # ── Over/Under 2.5 ──
    for market, prob_key, odd_key in [
        ('over25', 'p_over25', 'over25'),
        ('under25', 'p_under25', 'under25'),
    ]:
        odd = cuota.get(odd_key)
        prob = pred.get(prob_key, 0)

        if not odd or odd <= 1.0 or prob is None:
            results[market] = {
                'prob_model': prob,
                'prob_implied': None,
                'odd': odd,
                'value': 0,
                'edge_rel': 0,
                'has_value': False,
                'strong_value': False,
            }
            continue

        implied = 1.0 / odd
        value = prob - implied
        edge_rel = value / implied if implied > 0 else 0

        has_value = value > VALUE_THRESH
        strong_value = has_value and edge_rel > EDGE_REL_THRESH

        results[market] = {
            'prob_model': prob,
            'prob_implied': implied,
            'odd': odd,
            'value': value,
            'edge_rel': edge_rel,
            'has_value': has_value,
            'strong_value': strong_value,
        }

    # ── BTTS ──
    for market, prob_key, odd_key in [
        ('btts_yes', 'p_btts_yes', 'btts_yes'),
        ('btts_no', 'p_btts_no', 'btts_no'),
    ]:
        odd = cuota.get(odd_key)
        prob = pred.get(prob_key, 0)

        if not odd or odd <= 1.0 or prob is None:
            results[market] = {
                'prob_model': prob,
                'prob_implied': None,
                'odd': odd,
                'value': 0,
                'edge_rel': 0,
                'has_value': False,
                'strong_value': False,
            }
            continue

        implied = 1.0 / odd
        value = prob - implied
        edge_rel = value / implied if implied > 0 else 0

        has_value = value > VALUE_THRESH
        strong_value = has_value and edge_rel > EDGE_REL_THRESH

        results[market] = {
            'prob_model': prob,
            'prob_implied': implied,
            'odd': odd,
            'value': value,
            'edge_rel': edge_rel,
            'has_value': has_value,
            'strong_value': strong_value,
        }

    return results


def format_ou_btts_value(value_dict):
    """
    Formatea value bets O/U y BTTS para mostrar en consola/HTML.

    Args:
        value_dict: dict retornado por calc_value_ou_btts()

    Returns:
        str: texto formateado
    """
    lines = []

    # O/U 2.5
    ou = value_dict.get('over25', {})
    uu = value_dict.get('under25', {})
    if ou.get('odd') or uu.get('odd'):
        ou_str = f"O2.5:{ou['odd']:.2f}(+{ou['value']*100:.1f}%)" if ou.get('has_value') else f"O2.5:{ou['odd']:.2f}"
        uu_str = f"U2.5:{uu['odd']:.2f}(+{uu['value']*100:.1f}%)" if uu.get('has_value') else f"U2.5:{uu['odd']:.2f}"
        lines.append(f"    O/U 2.5 → {ou_str} | {uu_str}")

    # BTTS
    by = value_dict.get('btts_yes', {})
    bn = value_dict.get('btts_no', {})
    if by.get('odd') or bn.get('odd'):
        by_str = f"YES:{by['odd']:.2f}(+{by['value']*100:.1f}%)" if by.get('has_value') else f"YES:{by['odd']:.2f}"
        bn_str = f"NO:{bn['odd']:.2f}(+{bn['value']*100:.1f}%)" if bn.get('has_value') else f"NO:{bn['odd']:.2f}"
        lines.append(f"    BTTS    → {by_str} | {bn_str}")

    return "\n".join(lines) if lines else "    O/U y BTTS: No disponibles"


# ═══════════════════════════════════════════════════════════════════════════════
# Funciones para modificar international_analyzer.py
# ═══════════════════════════════════════════════════════════════════════════════

def patch_analyzer_for_ou():
    """
    Retorna instrucciones de cómo modificar international_analyzer.py
    para usar cuotas O/U 2.5 y BTTS.
    """
    instructions = """
    ═══════════════════════════════════════════════════════════════════════════
    MODIFICACIONES PARA international_analyzer.py
    ═══════════════════════════════════════════════════════════════════════════

    1. IMPORTAR (al inicio del archivo, después de los imports existentes):

        from cuotas_ou_integration import load_cuotas_ou, calc_value_ou_btts, format_ou_btts_value

    2. REEMPLAZAR CARGA DE CUOTAS (buscar la sección donde carga cuotas_hoy.csv):

        # ANTES (línea ~1560):
        cuotas_dict = {}
        if os.path.exists(cuotas_csv):
            try:
                cdf = pd.read_csv(cuotas_csv, encoding='utf-8')
                ...

        # DESPUÉS:
        cuotas_dict = load_cuotas_ou(cuotas_csv)

    3. AGREGAR CÁLCULO DE VALUE O/U Y BTTS (en el loop de análisis, después de calc_value()):

        # Calcular value para O/U 2.5 y BTTS si hay cuotas disponibles
        cuota_ou = cuotas_dict.get((h_name.lower(), a_name.lower()))
        if cuota_ou and (cuota_ou.get('over25') or cuota_ou.get('btts_yes')):
            value_ou_btts = calc_value_ou_btts(pred, cuota_ou)

            # Agregar al análisis
            analysis_data['value_ou_btts'] = value_ou_btts

            # Mostrar en consola
            print(format_ou_btts_value(value_ou_btts))

    4. AGREGAR AL HTML (en generate_html, después de mostrar 1X2):

        # Mostrar O/U y BTTS si hay value
        if 'value_ou_btts' in a:
            vou = a['value_ou_btts']
            # Agregar badges para O/U y BTTS
            ...

    5. AGREGAR AL TRACKER (en tracker_auto.py, detectar mercados O/U y BTTS):

        # En auto_register_bet(), buscar también value_ou_btts
        for market_key in ['over25', 'under25', 'btts_yes', 'btts_no']:
            v = value_ou_btts.get(market_key, {})
            if v.get('has_value') or v.get('strong_value'):
                # Registrar apuesta O/U o BTTS
                ...
    """
    print(instructions)
    return instructions


if __name__ == '__main__':
    # Test
    print("=== Test de integración O/U + BTTS ===")

    # Test 1: Cargar cuotas
    cuotas = load_cuotas_ou()

    # Test 2: Calcular value
    pred_test = {
        'p_over25': 0.65,
        'p_under25': 0.35,
        'p_btts_yes': 0.55,
        'p_btts_no': 0.45,
    }
    cuota_test = {
        'over25': 1.80,
        'under25': 2.10,
        'btts_yes': 1.90,
        'btts_no': 1.95,
    }

    value = calc_value_ou_btts(pred_test, cuota_test)
    print("\nValue calculado:")
    print(format_ou_btts_value(value))
