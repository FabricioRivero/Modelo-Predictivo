#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tracker_apuestas.py — Registro y seguimiento de apuestas deportivas
====================================================================
Registra cada apuesta recomendada por el modelo, sus resultados y calcula
ROI real vs teorico. Compatible con el sistema Modelo Predictivo de Futbol.

Uso desde terminal:
    python tracker_apuestas.py add --partido "Mexico vs South Africa" --mercado 1 --cuota 1.41 --stake 2 --value 3.5
    python tracker_apuestas.py result --partido "Mexico vs South Africa" --resultado H
    python tracker_apuestas.py summary
    python tracker_apuestas.py history
    python tracker_apuestas.py export --format excel

Estructura CSV:
    fecha, partido, mercado, seleccion, cuota, stake, value_modelo, 
    resultado, pnl, roi_apuesta, bankroll_post, notas
"""

import sys
import os
import csv
import argparse
from datetime import datetime, date
from pathlib import Path

# ── Cargar configuracion central ──────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'Config'))
from config import REPO_ROOT, DATOS_DIR, INTL_DIR

# ── Rutas ─────────────────────────────────────────────────────
APUESTAS_DIR = os.path.join(DATOS_DIR, "apuestas")
os.makedirs(APUESTAS_DIR, exist_ok=True)

CSV_PATH = os.path.join(APUESTAS_DIR, "registro_apuestas.csv")

# ── Columnas del CSV ──────────────────────────────────────────
COLUMNAS = [
    'id', 'fecha_registro', 'fecha_partido', 'partido', 'mercado',
    'seleccion', 'cuota', 'stake_pct', 'stake_unidades', 'bankroll_pre',
    'value_modelo_pct', 'prob_modelo_pct', 'odd_implied_pct',
    'resultado_real', 'goles_home', 'goles_away', 'pnl_unidades',
    'roi_apuesta_pct', 'bankroll_post', 'estado', 'notas'
]

# ── Bankroll por defecto (se lee/escribe de archivo) ──────────
BANKROLL_FILE = os.path.join(APUESTAS_DIR, "bankroll.txt")
BANKROLL_INICIAL = 100.0  # unidades


def _get_bankroll():
    """Lee el bankroll actual desde archivo. Si no existe, inicializa."""
    if os.path.exists(BANKROLL_FILE):
        try:
            with open(BANKROLL_FILE, 'r') as f:
                return float(f.read().strip())
        except:
            pass
    return BANKROLL_INICIAL


def _set_bankroll(valor):
    """Guarda el bankroll actual en archivo."""
    with open(BANKROLL_FILE, 'w') as f:
        f.write(str(round(valor, 4)))


def _get_next_id():
    """Obtiene el siguiente ID autoincremental."""
    if not os.path.exists(CSV_PATH):
        return 1
    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            ids = [int(row['id']) for row in reader if row.get('id')]
            return max(ids) + 1 if ids else 1
    except:
        return 1


def _init_csv():
    """Inicializa el archivo CSV con headers si no existe."""
    if not os.path.exists(CSV_PATH):
        os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
        with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNAS)
            writer.writeheader()
        print(f"✅ CSV creado: {CSV_PATH}")
        _set_bankroll(BANKROLL_INICIAL)
        print(f"💰 Bankroll inicial: {BANKROLL_INICIAL} unidades")


def registrar_apuesta(fecha_partido, partido, mercado, seleccion, cuota, stake_pct,
                       value_modelo_pct, prob_modelo_pct=None, notas=""):
    """
    Registra una nueva apuesta en el CSV.

    Args:
        fecha_partido:  Fecha del partido (YYYY-MM-DD)
        partido:        Nombre del partido (ej: "Mexico vs South Africa")
        mercado:        1, X, 2, O2.5, U2.5, BTTS_Y, BTTS_N
        seleccion:      H (home), D (draw), A (away), Over, Under, Yes, No
        cuota:          Cuota decimal (ej: 1.41)
        stake_pct:      % del bankroll apostado (ej: 2.0 para 2%)
        value_modelo_pct: Value detectado por el modelo (ej: 3.5 para +3.5%)
        prob_modelo_pct: Probabilidad del modelo (opcional, ej: 70.9)
        notas:          Notas adicionales (opcional)

    Returns:
        dict con los datos registrados
    """
    _init_csv()

    # Validaciones
    if cuota <= 1.0:
        raise ValueError(f"Cuota debe ser > 1.0, recibido: {cuota}")
    if stake_pct <= 0 or stake_pct > 100:
        raise ValueError(f"Stake debe ser entre 0 y 100, recibido: {stake_pct}")

    bankroll = _get_bankroll()
    stake_unidades = round(bankroll * (stake_pct / 100), 4)
    odd_implied = round((1.0 / cuota) * 100, 2)

    apuesta = {
        'id': _get_next_id(),
        'fecha_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'fecha_partido': fecha_partido,
        'partido': partido,
        'mercado': mercado,
        'seleccion': seleccion,
        'cuota': round(cuota, 3),
        'stake_pct': round(stake_pct, 2),
        'stake_unidades': stake_unidades,
        'bankroll_pre': round(bankroll, 4),
        'value_modelo_pct': round(value_modelo_pct, 2),
        'prob_modelo_pct': round(prob_modelo_pct, 2) if prob_modelo_pct else '',
        'odd_implied_pct': odd_implied,
        'resultado_real': '',
        'goles_home': '',
        'goles_away': '',
        'pnl_unidades': '',
        'roi_apuesta_pct': '',
        'bankroll_post': '',
        'estado': 'PENDIENTE',
        'notas': notas,
    }

    with open(CSV_PATH, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS)
        writer.writerow(apuesta)

    print(f"\n✅ APUESTA REGISTRADA #{apuesta['id']}")
    print(f"   📅 {fecha_partido} | {partido}")
    print(f"   🎯 {mercado} {seleccion} @ {cuota} | Stake: {stake_pct}% ({stake_unidades:.2f}u)")
    print(f"   📊 Value modelo: +{value_modelo_pct}% | Prob implicita: {odd_implied}%")
    print(f"   💰 Bankroll actual: {bankroll:.2f}u")

    return apuesta


def registrar_resultado(partido, resultado_real, goles_home=None, goles_away=None, notas=""):
    """
    Actualiza el resultado de una apuesta existente.

    Args:
        partido:        Nombre exacto del partido como fue registrado
        resultado_real: H (gano local), D (empate), A (gano visitante),
                        Over, Under, Yes, No
        goles_home:     Goles del local (opcional)
        goles_away:     Goles del visitante (opcional)
        notas:          Notas adicionales (opcional)

    Returns:
        dict con el resultado actualizado, o None si no se encontro
    """
    if not os.path.exists(CSV_PATH):
        print(f"❌ No existe el archivo de apuestas: {CSV_PATH}")
        return None

    rows = []
    updated = None

    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['partido'] == partido and row['estado'] == 'PENDIENTE':
                # Calcular PnL
                cuota = float(row['cuota'])
                stake_unidades = float(row['stake_unidades'])
                seleccion = row['seleccion']

                # Determinar si gano
                ganado = False
                if resultado_real.upper() in ['H', 'HOME', '1'] and seleccion.upper() in ['H', 'HOME', '1']:
                    ganado = True
                elif resultado_real.upper() in ['D', 'DRAW', 'X'] and seleccion.upper() in ['D', 'DRAW', 'X']:
                    ganado = True
                elif resultado_real.upper() in ['A', 'AWAY', '2'] and seleccion.upper() in ['A', 'AWAY', '2']:
                    ganado = True
                elif resultado_real.upper() == seleccion.upper():
                    ganado = True

                if ganado:
                    pnl = round(stake_unidades * (cuota - 1), 4)
                    roi = round((cuota - 1) * 100, 2)
                    estado = 'GANADA'
                else:
                    pnl = round(-stake_unidades, 4)
                    roi = -100.0
                    estado = 'PERDIDA'

                bankroll_pre = float(row['bankroll_pre'])
                bankroll_post = round(bankroll_pre + pnl, 4)

                row['resultado_real'] = resultado_real.upper()
                row['goles_home'] = goles_home if goles_home is not None else ''
                row['goles_away'] = goles_away if goles_away is not None else ''
                row['pnl_unidades'] = pnl
                row['roi_apuesta_pct'] = roi
                row['bankroll_post'] = bankroll_post
                row['estado'] = estado
                row['notas'] = (row['notas'] + " | " + notas).strip(" |") if notas else row['notas']

                updated = row
                _set_bankroll(bankroll_post)
            rows.append(row)

    if not updated:
        print(f"❌ No se encontro apuesta pendiente para: '{partido}'")
        print(f"   Use 'history' para ver los partidos registrados.")
        return None

    # Reescribir CSV
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS)
        writer.writeheader()
        writer.writerows(rows)

    emoji = "🎉" if updated['estado'] == 'GANADA' else "😞"
    print(f"\n{emoji} RESULTADO REGISTRADO")
    print(f"   📅 {updated['fecha_partido']} | {partido}")
    print(f"   🎯 {updated['mercado']} {updated['seleccion']} @ {updated['cuota']}")
    print(f"   📊 Resultado: {resultado_real.upper()} | Estado: {updated['estado']}")
    print(f"   💰 PnL: {updated['pnl_unidades']:+.2f}u | ROI: {updated['roi_apuesta_pct']:.1f}%")
    print(f"   💼 Bankroll nuevo: {updated['bankroll_post']:.2f}u")

    return updated


def ver_resumen():
    """
    Muestra resumen estadistico de todas las apuestas.
    """
    if not os.path.exists(CSV_PATH):
        print(f"❌ No existe el archivo de apuestas: {CSV_PATH}")
        print(f"   Registra tu primera apuesta con: add")
        return

    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("📭 No hay apuestas registradas.")
        return

    total = len(rows)
    pendientes = sum(1 for r in rows if r['estado'] == 'PENDIENTE')
    ganadas = sum(1 for r in rows if r['estado'] == 'GANADA')
    perdidas = sum(1 for r in rows if r['estado'] == 'PERDIDA')

    # Calcular metricas
    pnl_total = sum(float(r['pnl_unidades']) for r in rows if r['pnl_unidades'])
    stake_total = sum(float(r['stake_unidades']) for r in rows if r['stake_unidades'])
    roi_total = round((pnl_total / stake_total) * 100, 2) if stake_total > 0 else 0

    win_pct = round((ganadas / (ganadas + perdidas)) * 100, 1) if (ganadas + perdidas) > 0 else 0

    bankroll_actual = _get_bankroll()
    bankroll_inicial = BANKROLL_INICIAL
    retorno_total = round(((bankroll_actual - bankroll_inicial) / bankroll_inicial) * 100, 2)

    # Promedio value modelo de apuestas ganadas vs perdidas
    value_ganadas = [float(r['value_modelo_pct']) for r in rows if r['estado'] == 'GANADA' and r['value_modelo_pct']]
    value_perdidas = [float(r['value_modelo_pct']) for r in rows if r['estado'] == 'PERDIDA' and r['value_modelo_pct']]
    avg_value_ganadas = round(sum(value_ganadas) / len(value_ganadas), 2) if value_ganadas else 0
    avg_value_perdidas = round(sum(value_perdidas) / len(value_perdidas), 2) if value_perdidas else 0

    # Mejor y peor apuesta
    apuestas_con_pnl = [(r['partido'], float(r['pnl_unidades'])) for r in rows if r['pnl_unidades']]
    if apuestas_con_pnl:
        mejor = max(apuestas_con_pnl, key=lambda x: x[1])
        peor = min(apuestas_con_pnl, key=lambda x: x[1])

    print(f"\n{'='*60}")
    print(f"📊 RESUMEN DE APUESTAS")
    print(f"{'='*60}")
    print(f"\n📈 Metricas Generales")
    print(f"   Total apuestas:     {total}")
    print(f"   ✅ Ganadas:         {ganadas}")
    print(f"   ❌ Perdidas:        {perdidas}")
    print(f"   ⏳ Pendientes:      {pendientes}")
    print(f"   Win %:              {win_pct}%")
    print(f"\n💰 Financiero")
    print(f"   Bankroll inicial:   {bankroll_inicial:.2f}u")
    print(f"   Bankroll actual:    {bankroll_actual:.2f}u")
    print(f"   Retorno total:      {retorno_total:+.2f}%")
    print(f"   Stake total:        {stake_total:.2f}u")
    print(f"   PnL total:          {pnl_total:+.2f}u")
    print(f"   ROI total:          {roi_total:+.2f}%")
    print(f"\n📊 Value Modelo (promedio)")
    print(f"   Apuestas ganadas:   +{avg_value_ganadas}%")
    print(f"   Apuestas perdidas:  +{avg_value_perdidas}%")
    if apuestas_con_pnl:
        print(f"\n🏆 Mejor apuesta:     {mejor[0]} ({mejor[1]:+.2f}u)")
        print(f"   😞 Peor apuesta:     {peor[0]} ({peor[1]:+.2f}u)")
    print(f"{'='*60}")


def ver_historial(limite=50, mercado=None, estado=None):
    """
    Muestra historial de apuestas en formato tabla.

    Args:
        limite: Numero maximo de apuestas a mostrar
        mercado: Filtrar por mercado (1, X, 2, O2.5, etc.)
        estado: Filtrar por estado (PENDIENTE, GANADA, PERDIDA)
    """
    if not os.path.exists(CSV_PATH):
        print(f"❌ No existe el archivo de apuestas: {CSV_PATH}")
        return

    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Filtros
            if mercado and row['mercado'] != mercado:
                continue
            if estado and row['estado'] != estado:
                continue
            rows.append(row)

    if not rows:
        print("📭 No hay apuestas que coincidan con los filtros.")
        return

    # Ordenar por fecha descendente
    rows.sort(key=lambda x: x['fecha_registro'], reverse=True)
    rows = rows[:limite]

    print(f"\n{'='*100}")
    print(f"📋 HISTORIAL DE APUESTAS (ultimas {len(rows)})")
    print(f"{'='*100}")
    print(f"{'ID':<4} {'Fecha':<12} {'Partido':<30} {'Merc':<6} {'Sel':<4} {'Cuota':<6} {'Stake%':<7} {'Value%':<7} {'Estado':<10} {'PnL':<10} {'Bankroll':<10}")
    print(f"{'-'*100}")

    for r in rows:
        id_ = r['id']
        fecha = r['fecha_partido']
        partido = r['partido'][:28]
        merc = r['mercado']
        sel = r['seleccion']
        cuota = r['cuota']
        stake = r['stake_pct']
        value = r['value_modelo_pct']
        estado = r['estado']

        if estado == 'PENDIENTE':
            pnl = "—"
            bank = r['bankroll_pre']
            estado_icon = "⏳"
        else:
            pnl = f"{float(r['pnl_unidades']):+.2f}"
            bank = r['bankroll_post']
            estado_icon = "✅" if estado == 'GANADA' else "❌"

        print(f"{id_:<4} {fecha:<12} {partido:<30} {merc:<6} {sel:<4} {cuota:<6} {stake:<7} {value:<7} {estado_icon} {estado:<8} {pnl:<10} {bank:<10}")

    print(f"{'='*100}")
    print(f"💡 Tip: Usa --mercado o --estado para filtrar")


def exportar(formato='csv'):
    """
    Exporta las apuestas a otro formato.

    Args:
        formato: 'csv', 'excel', 'json'
    """
    if not os.path.exists(CSV_PATH):
        print(f"❌ No existe el archivo de apuestas: {CSV_PATH}")
        return

    if formato == 'csv':
        print(f"✅ CSV ya disponible en: {CSV_PATH}")
        return

    if formato == 'excel':
        try:
            import pandas as pd
            df = pd.read_csv(CSV_PATH)
            excel_path = CSV_PATH.replace('.csv', '.xlsx')
            df.to_excel(excel_path, index=False, engine='openpyxl')
            print(f"✅ Excel exportado: {excel_path}")
        except ImportError:
            print("❌ Instala pandas y openpyxl: pip install pandas openpyxl")
        except Exception as e:
            print(f"❌ Error exportando: {e}")

    elif formato == 'json':
        try:
            import pandas as pd
            df = pd.read_csv(CSV_PATH)
            json_path = CSV_PATH.replace('.csv', '.json')
            df.to_json(json_path, orient='records', indent=2, force_ascii=False)
            print(f"✅ JSON exportado: {json_path}")
        except ImportError:
            print("❌ Instala pandas: pip install pandas")
        except Exception as e:
            print(f"❌ Error exportando: {e}")
    else:
        print(f"❌ Formato no soportado: {formato}. Use: csv, excel, json")


def borrar_apuesta(partido=None, id_=None, confirmar=False):
    """
    Borra una apuesta por partido o ID. Requiere confirmacion.

    Args:
        partido: Nombre del partido a borrar
        id_: ID de la apuesta a borrar
        confirmar: Si True, no pide confirmacion
    """
    if not os.path.exists(CSV_PATH):
        print("❌ No hay apuestas registradas.")
        return

    rows = []
    target = None
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (partido and row['partido'] == partido) or (id_ and row['id'] == str(id_)):
                target = row
                continue
            rows.append(row)

    if not target:
        print(f"❌ No se encontro apuesta para: {partido or id_}")
        return

    if not confirmar:
        resp = input(f"⚠ ¿Borrar apuesta #{target['id']} {target['partido']}? (s/n): ")
        if resp.lower() != 's':
            print("❌ Cancelado.")
            return

    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Apuesta #{target['id']} borrada.")


# ══════════════════════════════════════════════════════════════
# CLI — Interfaz de linea de comandos
# ══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description='Tracker de apuestas deportivas — Modelo Predictivo de Futbol',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Ejemplos:
  python tracker_apuestas.py add --partido "Mexico vs South Africa" --mercado 1 --cuota 1.41 --stake 2 --value 3.5
  python tracker_apuestas.py add --partido "Spain vs Brazil" --fecha 2026-06-20 --mercado 1 --cuota 2.15 --stake 1.5 --value 5.2 --prob 46.5
  python tracker_apuestas.py result --partido "Mexico vs South Africa" --resultado H --goles-home 2 --goles-away 0
  python tracker_apuestas.py result --partido "Spain vs Brazil" --resultado D --goles-home 1 --goles-away 1
  python tracker_apuestas.py summary
  python tracker_apuestas.py history --limite 20
  python tracker_apuestas.py history --mercado 1 --estado GANADA
  python tracker_apuestas.py export --format excel
        '''
    )

    subparsers = parser.add_subparsers(dest='comando', help='Comando a ejecutar')

    # ── add ─────────────────────────────────────────────────────
    add_parser = subparsers.add_parser('add', help='Registrar nueva apuesta')
    add_parser.add_argument('--partido', required=True, help='Nombre del partido')
    add_parser.add_argument('--fecha', default=date.today().strftime('%Y-%m-%d'), help='Fecha del partido (YYYY-MM-DD)')
    add_parser.add_argument('--mercado', required=True, choices=['1', 'X', '2', 'O2.5', 'U2.5', 'BTTS_Y', 'BTTS_N'], help='Mercado')
    add_parser.add_argument('--seleccion', default=None, help='Seleccion (H, D, A, Over, Under, Yes, No)')
    add_parser.add_argument('--cuota', required=True, type=float, help='Cuota decimal')
    add_parser.add_argument('--stake', required=True, type=float, help='Stake en % del bankroll')
    add_parser.add_argument('--value', required=True, type=float, help='Value del modelo en %')
    add_parser.add_argument('--prob', type=float, help='Probabilidad del modelo en % (opcional)')
    add_parser.add_argument('--notas', default='', help='Notas adicionales')

    # ── result ──────────────────────────────────────────────────
    result_parser = subparsers.add_parser('result', help='Registrar resultado de una apuesta')
    result_parser.add_argument('--partido', required=True, help='Nombre exacto del partido')
    result_parser.add_argument('--resultado', required=True, help='Resultado: H, D, A, Over, Under, Yes, No')
    result_parser.add_argument('--goles-home', type=int, help='Goles del local')
    result_parser.add_argument('--goles-away', type=int, help='Goles del visitante')
    result_parser.add_argument('--notas', default='', help='Notas adicionales')

    # ── summary ─────────────────────────────────────────────────
    summary_parser = subparsers.add_parser('summary', help='Ver resumen estadistico')

    # ── history ───────────────────────────────────────────────
    history_parser = subparsers.add_parser('history', help='Ver historial de apuestas')
    history_parser.add_argument('--limite', type=int, default=50, help='Numero maximo de apuestas')
    history_parser.add_argument('--mercado', choices=['1', 'X', '2', 'O2.5', 'U2.5', 'BTTS_Y', 'BTTS_N'], help='Filtrar por mercado')
    history_parser.add_argument('--estado', choices=['PENDIENTE', 'GANADA', 'PERDIDA'], help='Filtrar por estado')

    # ── export ──────────────────────────────────────────────────
    export_parser = subparsers.add_parser('export', help='Exportar apuestas')
    export_parser.add_argument('--format', choices=['csv', 'excel', 'json'], default='csv', help='Formato de exportacion')

    # ── delete ──────────────────────────────────────────────────
    delete_parser = subparsers.add_parser('delete', help='Borrar una apuesta')
    delete_parser.add_argument('--partido', help='Nombre del partido')
    delete_parser.add_argument('--id', type=int, help='ID de la apuesta')
    delete_parser.add_argument('--yes', action='store_true', help='No pedir confirmacion')

    args = parser.parse_args()

    if not args.comando:
        parser.print_help()
        return

    if args.comando == 'add':
        # Inferir seleccion del mercado si no se especifica
        seleccion = args.seleccion
        if not seleccion:
            map_mercado = {'1': 'H', 'X': 'D', '2': 'A', 'O2.5': 'Over', 'U2.5': 'Under', 'BTTS_Y': 'Yes', 'BTTS_N': 'No'}
            seleccion = map_mercado.get(args.mercado, args.mercado)

        registrar_apuesta(
            fecha_partido=args.fecha,
            partido=args.partido,
            mercado=args.mercado,
            seleccion=seleccion,
            cuota=args.cuota,
            stake_pct=args.stake,
            value_modelo_pct=args.value,
            prob_modelo_pct=args.prob,
            notas=args.notas
        )

    elif args.comando == 'result':
        registrar_resultado(
            partido=args.partido,
            resultado_real=args.resultado,
            goles_home=args.goles_home,
            goles_away=args.goles_away,
            notas=args.notas
        )

    elif args.comando == 'summary':
        ver_resumen()

    elif args.comando == 'history':
        ver_historial(
            limite=args.limite,
            mercado=args.mercado,
            estado=args.estado
        )

    elif args.comando == 'export':
        exportar(formato=args.format)

    elif args.comando == 'delete':
        if not args.partido and not args.id:
            print("❌ Especifique --partido o --id")
            return
        borrar_apuesta(
            partido=args.partido,
            id_=args.id,
            confirmar=args.yes
        )


if __name__ == '__main__':
    main()
