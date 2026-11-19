"""Aplicación Web Flask para la demo interactiva independiente de Almacén de Barrio.

Desplegable como Web Service en Render con Gunicorn.
"""

from __future__ import annotations

import os
from flask import Flask, jsonify, render_template, request

from demo_logic import (
    abrir_caja,
    ajustar_stock,
    anular_venta,
    cerrar_caja,
    init_db,
    listar_clientes,
    listar_productos,
    listar_ventas,
    obtener_caja_info,
    obtener_cliente_detalle,
    obtener_estado_general,
    obtener_reportes,
    obtener_venta_detalle,
    registrar_cobro_cliente,
    registrar_movimiento_caja,
    registrar_venta,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "almacen-de-barrio-demo-key-2026")

# Inicializar base de datos SQLite si no existe al arrancar
with app.app_context():
    init_db(forzar_reinicio=False)


# --------------------------------------------------------------------------- #
# Vistas HTML
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    """Sirve la interfaz POS interactiva completa."""
    return render_template("almacen_demo.html")


# --------------------------------------------------------------------------- #
# API REST: Estado y Reinicio
# --------------------------------------------------------------------------- #
@app.route("/api/estado", methods=["GET"])
def api_estado():
    """Devuelve el estado de la caja y contadores rápidos."""
    try:
        data = obtener_estado_general()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/demo/reset", methods=["POST"])
def api_demo_reset():
    """Reinicia la base de datos de demostración a su estado inicial limpio."""
    try:
        init_db(forzar_reinicio=True)
        return jsonify({"mensaje": "La base de datos de demostración ha sido reiniciada con éxito."})
    except Exception as e:
        return jsonify({"error": f"Error al reiniciar demo: {str(e)}"}), 500


# --------------------------------------------------------------------------- #
# API REST: Catálogo y Stock
# --------------------------------------------------------------------------- #
@app.route("/api/productos", methods=["GET"])
def api_productos():
    """Lista productos con filtros opcionales de búsqueda y categoría."""
    try:
        categoria_id = request.args.get("cat", type=int)
        busqueda = request.args.get("q", type=str)
        solo_stock_bajo = request.args.get("stock_bajo", type=str) in ("1", "true")
        prods = listar_productos(categoria_id=categoria_id, busqueda=busqueda, solo_stock_bajo=solo_stock_bajo)
        return jsonify(prods)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/productos/<int:prod_id>/stock", methods=["POST"])
def api_ajustar_stock(prod_id: int):
    """Simula un ingreso de mercadería o ajuste de inventario."""
    try:
        data = request.get_json(force=True) or {}
        delta = int(data.get("delta", 0))
        tipo = data.get("tipo", "AJUSTE")
        motivo = data.get("motivo", "Ajuste manual de demostración")
        if delta == 0:
            return jsonify({"error": "La cantidad no puede ser cero"}), 400

        res = ajustar_stock(prod_id, delta, tipo, motivo)
        return jsonify(res)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------------------------- #
# API REST: Clientes y Fiados
# --------------------------------------------------------------------------- #
@app.route("/api/clientes", methods=["GET"])
def api_clientes():
    """Lista todos los clientes con saldo y crédito disponible."""
    try:
        return jsonify(listar_clientes())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clientes/<int:cliente_id>", methods=["GET"])
def api_cliente_detalle(cliente_id: int):
    """Devuelve la ficha del cliente y su historial de cuenta corriente."""
    try:
        cliente = obtener_cliente_detalle(cliente_id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404
        return jsonify(cliente)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clientes/<int:cliente_id>/cobrar", methods=["POST"])
def api_cobrar_cliente(cliente_id: int):
    """Registra el cobro de la deuda de un cliente."""
    try:
        data = request.get_json(force=True) or {}
        monto_centavos = int(data.get("monto_centavos", 0))
        medio = data.get("medio", "EFECTIVO")
        res = registrar_cobro_cliente(cliente_id, monto_centavos, medio)
        return jsonify(res)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------------------------- #
# API REST: Ventas y Cobros
# --------------------------------------------------------------------------- #
@app.route("/api/ventas", methods=["GET"])
def api_ventas_list():
    """Lista el historial de ventas recientes."""
    try:
        limite = request.args.get("limite", default=50, type=int)
        return jsonify(listar_ventas(limite))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ventas", methods=["POST"])
def api_registrar_venta():
    """Registra una venta en el mostrador."""
    try:
        data = request.get_json(force=True) or {}
        items = data.get("items", [])
        pagos = data.get("pagos", [])
        cliente_id = int(data.get("cliente_id", 1))
        descuento_general = int(data.get("descuento_centavos", 0))

        res = registrar_venta(items, pagos, cliente_id, descuento_general)
        return jsonify(res), 201
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Error al procesar la venta: {str(e)}"}), 500


@app.route("/api/ventas/<int:venta_id>", methods=["GET"])
def api_venta_detalle(venta_id: int):
    """Obtiene el detalle completo de ítems y medios de pago de una venta."""
    try:
        venta = obtener_venta_detalle(venta_id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404
        return jsonify(venta)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ventas/<int:venta_id>/anular", methods=["POST"])
def api_anular_venta(venta_id: int):
    """Anula una venta y revierte el stock, caja y saldo fiado."""
    try:
        data = request.get_json(force=True) or {}
        motivo = data.get("motivo", "")
        res = anular_venta(venta_id, motivo)
        return jsonify(res)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------------------------- #
# API REST: Caja Diaria y Arqueo
# --------------------------------------------------------------------------- #
@app.route("/api/caja", methods=["GET"])
def api_caja():
    """Devuelve la información de la caja diaria y sus movimientos."""
    try:
        return jsonify(obtener_caja_info())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/caja/abrir", methods=["POST"])
def api_abrir_caja():
    """Abre la jornada de caja."""
    try:
        data = request.get_json(force=True) or {}
        monto_centavos = int(data.get("monto_inicial_centavos", 0))
        res = abrir_caja(monto_centavos)
        return jsonify(res)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/caja/movimiento", methods=["POST"])
def api_movimiento_caja():
    """Registra un movimiento manual (ingreso, retiro, gasto)."""
    try:
        data = request.get_json(force=True) or {}
        tipo = data.get("tipo", "INGRESO")
        monto_centavos = int(data.get("monto_centavos", 0))
        motivo = data.get("motivo", "")
        medio = data.get("medio", "EFECTIVO")
        res = registrar_movimiento_caja(tipo, monto_centavos, motivo, medio)
        return jsonify(res)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/caja/cerrar", methods=["POST"])
def api_cerrar_caja():
    """Cierra la caja diaria y asienta el arqueo."""
    try:
        data = request.get_json(force=True) or {}
        contado = int(data.get("contado_efectivo_centavos", 0))
        observaciones = data.get("observaciones", "")
        res = cerrar_caja(contado, observaciones)
        return jsonify(res)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------------------------- #
# API REST: Reportes y Métricas
# --------------------------------------------------------------------------- #
@app.route("/api/reportes", methods=["GET"])
def api_reportes():
    """Retorna las métricas y rankings según el período."""
    try:
        periodo = request.args.get("periodo", default="hoy", type=str)
        if periodo not in ("hoy", "semana", "mes", "anio", "todo"):
            periodo = "hoy"
        return jsonify(obtener_reportes(periodo))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------------------------- #
# Ejecución Local
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=puerto, debug=False)
