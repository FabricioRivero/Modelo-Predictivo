#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tracker_auto.py — Integracion automatica del tracker con international_analyzer.py
================================================================================
Se importa desde international_analyzer.py y ofrece:
  - auto_register_bet(): detecta value bets y pregunta si registrar
  - batch_register(): registra multiples apuestas al final del analisis
  - silent_mode: modo silencioso para automatizacion (no pregunta, solo registra)

Uso en international_analyzer.py:
    from tracker_auto import auto_register_bet, batch_register, integrate_into_analyzer

    # Al final del loop de analisis, para cada partido con value:
    auto_register_bet(analysis, interactive=True)

    # O al finalizar todo, registrar todas las value bets encontradas:
    integrate_into_analyzer(analyses, mode='interactive')

Modos:
    'interactive' — pregunta cada apuesta (default)
    'auto'        — registra todas automaticamente
    'silent'      — registra sin output (para cron jobs)
    'off'         — desactivado
"""

import sys
import os
from datetime import datetime, date

# ── Importar tracker ──────────────────────────────────────────
UTILIDADES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'utilidades')
sys.path.insert(0, UTILIDADES_DIR)
from tracker_apuestas import registrar_apuesta, ver_historial

# ── Importar config para rutas ─────────────────────────────────
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'Config')
sys.path.insert(0, CONFIG_DIR)
from config import REPO_ROOT, DATOS_DIR

# ── Configuracion ─────────────────────────────────────────────
DEFAULT_STAKE_PCT = 1.5  # % del bankroll por defecto si no se especifica
MAX_STAKE_PCT = 5.0      # maximo stake permitido
MIN_VALUE_PCT = 2.0      # minimo value para considerar registro automatico


def _parse_partido(partido_str):
    """Parsea 'Equipo A vs Equipo B' -> (home, away)."""
    if ' vs ' in partido_str:
        parts = partido_str.split(' vs ', 1)
        return parts[0].strip(), parts[1].strip()
    elif ' - ' in partido_str:
        parts = partido_str.split(' - ', 1)
        return parts[0].strip(), parts[1].strip()
    return partido_str, ""


def _ask_yes_no(prompt, default='n'):
    """Pregunta si/no en consola."""
    suffix = " [s/N]" if default.lower() == 'n' else " [S/n]"
    resp = input(f"{prompt}{suffix}: ").strip().lower()
    if not resp:
        return default.lower() == 's'
    return resp in ['s', 'si', 'yes', 'y']


def _ask_float(prompt, default=None, min_val=0, max_val=100):
    """Pregunta un numero float."""
    while True:
        suffix = f" [{default}]" if default is not None else ""
        resp = input(f"{prompt}{suffix}: ").strip()
        if not resp and default is not None:
            return float(default)
        try:
            val = float(resp)
            if min_val <= val <= max_val:
                return val
            print(f"   ⚠ Debe estar entre {min_val} y {max_val}")
        except ValueError:
            print(f"   ⚠ Ingresa un numero valido")


def auto_register_bet(analysis, interactive=True, silent=False, 
                       default_stake=DEFAULT_STAKE_PCT, 
                       min_value=MIN_VALUE_PCT):
    """
    Detecta si un analisis tiene value bet y pregunta/registra automaticamente.

    Args:
        analysis: dict con 'fixture', 'pred', 'value', 'form_home', 'form_away'
        interactive: Si True, pregunta al usuario. Si False, registra silenciosamente.
        silent: Si True, no imprime nada (para batch processing).
        default_stake: Stake por defecto en %.
        min_value: Value minimo para considerar registro.

    Returns:
        dict con la apuesta registrada, o None si no se registro.
    """
    fix = analysis['fixture']
    val = analysis['value']
    pred = analysis['pred']

    # Buscar el mejor value bet
    best_value = None
    best_outcome = None
    best_odd = None

    for outcome, v in val.items():
        if v.get('has_value') or v.get('strong_value'):
            if best_value is None or v['value'] > best_value:
                best_value = v['value']
                best_outcome = outcome
                best_odd = v['odd']

    if best_value is None:
        return None  # No hay value bet

    # Mapear outcome a mercado y seleccion
    outcome_map = {
        'home': ('1', 'H'),
        'draw': ('X', 'D'),
        'away': ('2', 'A'),
    }
    mercado, seleccion = outcome_map.get(best_outcome, (best_outcome.upper()[:3], best_outcome.upper()))

    # Verificar minimo value
    value_pct = best_value * 100
    if value_pct < min_value:
        if not silent:
            print(f"   ℹ Value {value_pct:.1f}% < {min_value}% — no registrado")
        return None

    partido = f"{fix['home_api']} vs {fix['away_api']}"
    fecha_partido = fix['commence'].astimezone().strftime('%Y-%m-%d') if hasattr(fix['commence'], 'astimezone') else str(date.today())
    cuota = best_odd
    prob_modelo = pred.get(f'p_{best_outcome}', 0) * 100

    # Modo silencioso o no interactivo
    if not interactive:
        stake = default_stake
        try:
            apuesta = registrar_apuesta(
                fecha_partido=fecha_partido,
                partido=partido,
                mercado=mercado,
                seleccion=seleccion,
                cuota=cuota,
                stake_pct=stake,
                value_modelo_pct=value_pct,
                prob_modelo_pct=prob_modelo,
                notas=f"Auto-registrada | Edge: {best_value*100:.1f}%"
            )
            if not silent:
                print(f"   ✅ Auto-registrada: {partido} {mercado} @ {cuota} (stake {stake}%)")
            return apuesta
        except Exception as e:
            if not silent:
                print(f"   ❌ Error auto-registrando: {e}")
            return None

    # Modo interactivo — preguntar al usuario
    print(f"\n   💡 VALUE BET DETECTADO: {partido}")
    print(f"      Mercado: {mercado} {seleccion} | Cuota: {cuota} | Value: +{value_pct:.1f}%")
    print(f"      Prob modelo: {prob_modelo:.1f}% | Prob implicita: {100/cuota:.1f}%")

    if not _ask_yes_no("   ¿Registrar esta apuesta en el tracker?", default='n'):
        print(f"   ℹ Apuesta omitida.")
        return None

    # Preguntar stake
    stake = _ask_float(f"   Stake (% del bankroll)", default=default_stake, 
                        min_val=0.1, max_val=MAX_STAKE_PCT)

    # Notas opcionales
    notas = input(f"   Notas (opcional): ").strip()
    notas = notas if notas else f"Edge: {value_pct:.1f}% | Auto-detectado"

    try:
        apuesta = registrar_apuesta(
            fecha_partido=fecha_partido,
            partido=partido,
            mercado=mercado,
            seleccion=seleccion,
            cuota=cuota,
            stake_pct=stake,
            value_modelo_pct=value_pct,
            prob_modelo_pct=prob_modelo,
            notas=notas
        )
        print(f"   ✅ Apuesta #{apuesta['id']} registrada exitosamente.")
        return apuesta
    except Exception as e:
        print(f"   ❌ Error registrando: {e}")
        return None


def batch_register(analyses, interactive=True, silent=False,
                    default_stake=DEFAULT_STAKE_PCT,
                    min_value=MIN_VALUE_PCT,
                    auto_all=False):
    """
    Registra todas las value bets de un batch de analisis.

    Args:
        analyses: lista de dicts de analisis
        interactive: Si True, pregunta cada una. Si False, registra todas.
        silent: Si True, no imprime nada.
        default_stake: Stake por defecto.
        min_value: Value minimo para registrar.
        auto_all: Si True, registra TODAS sin preguntar (modo automatizado).

    Returns:
        lista de apuestas registradas
    """
    registradas = []

    for analysis in analyses:
        apuesta = auto_register_bet(
            analysis,
            interactive=interactive and not auto_all,
            silent=silent,
            default_stake=default_stake,
            min_value=min_value
        )
        if apuesta:
            registradas.append(apuesta)

    if not silent and registradas:
        print(f"\n📊 BATCH COMPLETADO: {len(registradas)} apuestas registradas")
        print(f"   Usa: python tracker_apuestas.py summary")

    return registradas


def integrate_into_analyzer(analyses, mode='interactive'):
    """
    Funcion principal de integracion. Se llama al final de international_analyzer.py

    Args:
        analyses: lista de analisis del modelo
        mode: 'interactive' (pregunta cada una), 'auto' (registra todas), 
              'silent' (registra sin output), 'off' (no hace nada)

    Returns:
        lista de apuestas registradas
    """
    if mode == 'off':
        return []

    interactive = (mode == 'interactive')
    silent = (mode == 'silent')
    auto_all = (mode == 'auto')

    # Contar value bets disponibles
    value_count = sum(
        1 for a in analyses 
        for v in a['value'].values() 
        if v.get('has_value') or v.get('strong_value')
    )

    if value_count == 0:
        if not silent:
            print("\n📭 No hay value bets para registrar.")
        return []

    if not silent:
        print(f"\n{'='*60}")
        print(f"💰 TRACKER DE APUESTAS — {value_count} value bets detectadas")
        print(f"{'='*60}")
        if interactive:
            print("   Modo interactivo: se preguntara por cada apuesta.")
            print("   Presiona Enter para omitir, 's' para registrar.\n")

    return batch_register(
        analyses,
        interactive=interactive,
        silent=silent,
        auto_all=auto_all
    )
