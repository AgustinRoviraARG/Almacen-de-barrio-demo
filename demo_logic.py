"""Lógica de negocio y persistencia para la demo web independiente de Almacén de Barrio.

Reglas fundamentales respetadas:
    - Dinero: SIEMPRE en enteros de centavos (int), sin errores de redondeo float.
    - Stock: Columna única en unidad base (unidades enteras o gramos).
    - Pesables: precio por kg, cálculo: (precio_kg * gramos) // 1000.
    - Cajas: apertura, arqueo, cierre, movimientos manuales.
    - Fiados: cuenta corriente con validación de límite de crédito.
    - Pagos mixtos: la suma de pagos debe igualar el total de la venta.
    - Bajas lógicas y anulación con reversión de stock, caja y fiado.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

# Ruta de la base de datos de la demo
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ALMACEN_DEMO_DB", BASE_DIR / "almacen_demo.db"))

# Constantes de dominio
TIPO_UNIDAD = "UNIDAD"
TIPO_PESO = "PESO"

MEDIO_EFECTIVO = "EFECTIVO"
MEDIO_DEBITO = "DEBITO"
MEDIO_TRANSFERENCIA = "TRANSFERENCIA"
MEDIO_MERCADO_PAGO = "MERCADO_PAGO"
MEDIO_FIADO = "FIADO"

MEDIOS_PAGO = (
    MEDIO_EFECTIVO,
    MEDIO_DEBITO,
    MEDIO_TRANSFERENCIA,
    MEDIO_MERCADO_PAGO,
    MEDIO_FIADO,
)

MEDIOS_ETIQUETAS = {
    MEDIO_EFECTIVO: "Efectivo",
    MEDIO_DEBITO: "Débito",
    MEDIO_TRANSFERENCIA: "Transferencia",
    MEDIO_MERCADO_PAGO: "Mercado Pago / QR",
    MEDIO_FIADO: "Fiado (Cta. Cte.)",
}

VENTA_CONFIRMADA = "CONFIRMADA"
VENTA_ANULADA = "ANULADA"

CAJA_ABIERTA = "ABIERTA"
CAJA_CERRADA = "CERRADA"

CAJA_MOV_APERTURA = "APERTURA"
CAJA_MOV_VENTA = "VENTA"
CAJA_MOV_INGRESO = "INGRESO"
CAJA_MOV_RETIRO = "RETIRO"
CAJA_MOV_GASTO = "GASTO"
CAJA_MOV_ANULACION = "ANULACION"

MOV_VENTA = "VENTA"
MOV_ANULACION = "ANULACION"
MOV_AJUSTE = "AJUSTE"
MOV_INGRESO = "INGRESO"
MOV_INICIAL = "INICIAL"


# --------------------------------------------------------------------------- #
# Helpers de Dinero y Conversión
# --------------------------------------------------------------------------- #
def a_centavos(valor: Any) -> int:
    """Convierte pesos a centavos enteros (maneja formato argentino y números)."""
    if valor is None:
        return 0
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor * 100
    if isinstance(valor, Decimal):
        return int((valor * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    
    texto = str(valor).strip().replace("$", "").replace(" ", "").replace("\u00a0", "")
    if not texto:
        return 0
    
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    elif texto.count(".") > 1:
        texto = texto.replace(".", "")
    elif "." in texto:
        entero, _, dec = texto.partition(".")
        if len(dec) == 3 and entero.isdigit() and dec.isdigit():
            texto = entero + dec

    try:
        dec_val = Decimal(texto) * 100
        return int(dec_val.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def a_pesos(centavos: int) -> Decimal:
    """Devuelve el monto en pesos como Decimal."""
    return (Decimal(int(centavos)) / Decimal(100)).quantize(Decimal("0.01"))


def formatear_centavos(centavos: int) -> str:
    """Formatea centavos a estilo argentino: $ 1.250,50."""
    centavos = int(centavos or 0)
    signo = "-" if centavos < 0 else ""
    entero, resto = divmod(abs(centavos), 100)
    miles = f"{entero:,}".replace(",", ".")
    return f"{signo}$ {miles},{resto:02d}"


def a_gramos(valor: Any) -> int:
    """Convierte peso (en kg o gramos) a gramos enteros."""
    if valor is None:
        return 0
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower().replace("kg", "").replace("g", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(",", ".")
    try:
        kg = Decimal(texto)
        return int((kg * Decimal(1000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def formatear_cantidad(cantidad: int, tipo_venta: str) -> str:
    """Formatea la cantidad según sea unidad o gramos."""
    if tipo_venta == TIPO_PESO:
        if cantidad >= 1000:
            kg = cantidad / 1000.0
            return f"{kg:.3f} kg".replace(".", ",")
        return f"{cantidad} g"
    return f"{int(cantidad)} u"


def calcular_subtotal_linea(tipo_venta: str, cantidad: int, precio_unitario_centavos: int, descuento_centavos: int = 0) -> int:
    """Calcula el subtotal en centavos. Si es PESO, cantidad son gramos y precio es por kg."""
    if tipo_venta == TIPO_PESO:
        bruto = (int(precio_unitario_centavos) * int(cantidad)) // 1000
    else:
        bruto = int(precio_unitario_centavos) * int(cantidad)
    return max(0, bruto - int(descuento_centavos))


# --------------------------------------------------------------------------- #
# Base de datos y Conexión
# --------------------------------------------------------------------------- #
def get_db() -> sqlite3.Connection:
    """Obtiene una conexión con soporte para claves foráneas y acceso por nombre."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(forzar_reinicio: bool = False) -> None:
    """Inicializa la base de datos SQLite y carga los datos de demostración."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if forzar_reinicio and DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except Exception:
            pass

    conn = get_db()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            categoria_id INTEGER NOT NULL REFERENCES categorias(id),
            codigo_barras TEXT UNIQUE,
            tipo_venta TEXT NOT NULL DEFAULT 'UNIDAD',
            precio_costo_centavos INTEGER NOT NULL DEFAULT 0,
            precio_venta_centavos INTEGER NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            stock_minimo INTEGER NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            limite_fiado_centavos INTEGER NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS cajas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            estado TEXT NOT NULL DEFAULT 'ABIERTA',
            abierta_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            cerrada_en TEXT,
            monto_inicial_centavos INTEGER NOT NULL DEFAULT 0,
            contado_efectivo_centavos INTEGER,
            diferencia_centavos INTEGER,
            total_efectivo_centavos INTEGER NOT NULL DEFAULT 0,
            total_debito_centavos INTEGER NOT NULL DEFAULT 0,
            total_transferencia_centavos INTEGER NOT NULL DEFAULT 0,
            total_mercado_pago_centavos INTEGER NOT NULL DEFAULT 0,
            total_fiado_centavos INTEGER NOT NULL DEFAULT 0,
            observaciones TEXT
        );

        CREATE TABLE IF NOT EXISTS movimientos_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caja_id INTEGER NOT NULL REFERENCES cajas(id),
            tipo TEXT NOT NULL,
            medio TEXT,
            monto_centavos INTEGER NOT NULL,
            motivo TEXT,
            venta_id INTEGER,
            creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            cliente_id INTEGER REFERENCES clientes(id),
            caja_id INTEGER REFERENCES cajas(id),
            subtotal_centavos INTEGER NOT NULL DEFAULT 0,
            descuento_centavos INTEGER NOT NULL DEFAULT 0,
            total_centavos INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'CONFIRMADA',
            anulada_en TEXT,
            motivo_anulacion TEXT
        );

        CREATE TABLE IF NOT EXISTS items_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            descripcion TEXT NOT NULL,
            tipo_venta TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            precio_unitario_centavos INTEGER NOT NULL,
            descuento_centavos INTEGER NOT NULL DEFAULT 0,
            subtotal_centavos INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pagos_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
            medio TEXT NOT NULL,
            monto_centavos INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS movimientos_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            tipo TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            stock_resultante INTEGER NOT NULL,
            motivo TEXT,
            venta_id INTEGER REFERENCES ventas(id),
            creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS movimientos_cuenta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL REFERENCES clientes(id),
            tipo TEXT NOT NULL,
            monto_centavos INTEGER NOT NULL,
            saldo_resultante_centavos INTEGER NOT NULL,
            descripcion TEXT,
            venta_id INTEGER REFERENCES ventas(id),
            creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        """)

    # Verificar si precisa seed de demostración
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM productos")
        if cursor.fetchone()[0] == 0:
            sembrar_datos_demo(conn)
            conn.commit()
    conn.close()


def sembrar_datos_demo(conn: sqlite3.Connection) -> None:
    """Carga 32 productos típicos de almacén argentino, categorías, clientes y ventas."""
    categorias = [
        "Bebidas",
        "Almacén y Secos",
        "Fiambrería y Lácteos",
        "Panadería",
        "Frutas y Verduras",
        "Golosinas y Kiosco",
        "Limpieza",
        "Perfumería e Higiene",
    ]
    for cat in categorias:
        conn.execute("INSERT INTO categorias (nombre) VALUES (?)", (cat,))

    # Mapeo de categorías
    cats: dict[str, int] = {}
    for row in conn.execute("SELECT id, nombre FROM categorias"):
        cats[row["nombre"]] = row["id"]

    # 32 productos argentinos curados
    productos = [
        # Bebidas
        ("Coca-Cola 2.25L", cats["Bebidas"], "7790895000430", TIPO_UNIDAD, 280000, 380000, 48, 10),
        ("Coca-Cola 1.5L", cats["Bebidas"], "7790895000423", TIPO_UNIDAD, 200000, 270000, 36, 8),
        ("Agua Mineral 2L", cats["Bebidas"], "7790314058226", TIPO_UNIDAD, 90000, 140000, 30, 6),
        ("Cerveza Quilmes 1L", cats["Bebidas"], "7792798000018", TIPO_UNIDAD, 210000, 290000, 24, 6),
        ("Cerveza Lata 473ml", cats["Bebidas"], "7792798000025", TIPO_UNIDAD, 120000, 180000, 40, 12),
        ("Vino Malbec 750ml", cats["Bebidas"], "7790123004561", TIPO_UNIDAD, 280000, 420000, 18, 4),
        # Almacén
        ("Yerba Mate Playadito 1kg", cats["Almacén y Secos"], "7791234567890", TIPO_UNIDAD, 320000, 460000, 25, 5),
        ("Azúcar Ledesma 1kg", cats["Almacén y Secos"], "7790080012345", TIPO_UNIDAD, 85000, 125000, 50, 10),
        ("Arroz Lucchetti 1kg", cats["Almacén y Secos"], "7790070023456", TIPO_UNIDAD, 130000, 195000, 35, 8),
        ("Fideos Matarazzo 500g", cats["Almacén y Secos"], "7790070034567", TIPO_UNIDAD, 95000, 145000, 40, 10),
        ("Aceite de Girasol 900ml", cats["Almacén y Secos"], "7790040045678", TIPO_UNIDAD, 170000, 240000, 22, 6),
        ("Puré de Tomate 520g", cats["Almacén y Secos"], "7790060056789", TIPO_UNIDAD, 60000, 95000, 45, 10),
        ("Atún al Natural 170g", cats["Almacén y Secos"], "7790050067890", TIPO_UNIDAD, 180000, 260000, 15, 5),
        # Fiambrería y Lácteos (Pesables y unidades)
        ("Queso Cremoso La Serenísima", cats["Fiambrería y Lácteos"], "2000001000000", TIPO_PESO, 620000, 890000, 15000, 3000), # 15 kg
        ("Jamón Cocido Paladini", cats["Fiambrería y Lácteos"], "2000002000000", TIPO_PESO, 890000, 1280000, 8000, 2000),   # 8 kg
        ("Salame Milán Feteado", cats["Fiambrería y Lácteos"], "2000003000000", TIPO_PESO, 1100000, 1550000, 4000, 1500), # 4 kg
        ("Queso Tybo en Barra", cats["Fiambrería y Lácteos"], "2000004000000", TIPO_PESO, 750000, 1050000, 12000, 3000),  # 12 kg
        ("Leche La Serenísima 1L", cats["Fiambrería y Lácteos"], "7790030078901", TIPO_UNIDAD, 105000, 145000, 30, 8),
        ("Manteca 200g", cats["Fiambrería y Lácteos"], "7790030089012", TIPO_UNIDAD, 160000, 230000, 18, 5),
        ("Yogur Bebible 1L", cats["Fiambrería y Lácteos"], "7790030090123", TIPO_UNIDAD, 140000, 210000, 14, 4),
        # Panadería
        ("Pan Lactal Blanco", cats["Panadería"], "7790020011223", TIPO_UNIDAD, 190000, 270000, 16, 5),
        ("Pan Francés", cats["Panadería"], "2000005000000", TIPO_PESO, 150000, 230000, 25000, 5000), # 25 kg
        # Frutas y Verduras (Pesables)
        ("Papas Negras Selección", cats["Frutas y Verduras"], "2000006000000", TIPO_PESO, 70000, 110000, 60000, 10000), # 60 kg
        ("Cebolla Comercial", cats["Frutas y Verduras"], "2000007000000", TIPO_PESO, 65000, 99000, 35000, 8000),      # 35 kg
        ("Tomate Redondo", cats["Frutas y Verduras"], "2000008000000", TIPO_PESO, 180000, 260000, 20000, 5000),        # 20 kg
        ("Banana Ecuador", cats["Frutas y Verduras"], "2000009000000", TIPO_PESO, 160000, 230000, 18000, 4000),        # 18 kg
        # Golosinas y Kiosco
        ("Alfajor Triple Havanna", cats["Golosinas y Kiosco"], "7790010022334", TIPO_UNIDAD, 120000, 175000, 24, 6),
        ("Alfajor Guaymallén Simple", cats["Golosinas y Kiosco"], "7790010033445", TIPO_UNIDAD, 30000, 50000, 80, 15),
        ("Chocolate con Maní 100g", cats["Golosinas y Kiosco"], "7790010044556", TIPO_UNIDAD, 150000, 220000, 20, 5),
        # Limpieza e Higiene
        ("Detergente Magistral 500ml", cats["Limpieza"], "7790090055667", TIPO_UNIDAD, 180000, 260000, 20, 5),
        ("Lavandina Ayudín 1L", cats["Limpieza"], "7790090066778", TIPO_UNIDAD, 85000, 130000, 30, 8),
        ("Papel Higiénico Higienol 4u", cats["Perfumería e Higiene"], "7790088077889", TIPO_UNIDAD, 170000, 250000, 28, 6),
    ]

    for p in productos:
        conn.execute(
            """INSERT INTO productos
               (nombre, categoria_id, codigo_barras, tipo_venta, precio_costo_centavos, precio_venta_centavos, stock, stock_minimo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            p,
        )

    # 10 clientes con límites y deudas realistas
    clientes = [
        ("Consumidor Final", None, 0),
        ("Juan Pérez", "11-4567-8901", 5000000),       # Límite: $50.000
        ("María González", "11-3456-7890", 6000000),   # Límite: $60.000
        ("Carlos Rodríguez", "11-2345-6789", 4000000), # Límite: $40.000
        ("Laura Fernández", "11-5678-9012", 7000000),  # Límite: $70.000
        ("Pedro Martínez", "11-6789-0123", 3000000),   # Límite: $30.000
        ("Sofía Romero", "11-7890-1234", 4500000),     # Límite: $45.000
        ("Martín Benítez", "11-8901-2345", 3500000),   # Límite: $35.000
        ("Elena Acosta", "11-9012-3456", 5500000),     # Límite: $55.000
        ("Diego López", "11-1234-5678", 4000000),      # Límite: $40.000
    ]
    for c in clientes:
        conn.execute(
            "INSERT INTO clientes (nombre, telefono, limite_fiado_centavos) VALUES (?, ?, ?)",
            c,
        )

    # Apertura de caja de hoy
    fondo_inicial = 5000000  # $ 50.000
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO cajas (estado, monto_inicial_centavos, abierta_en)
           VALUES ('ABIERTA', ?, datetime('now', 'localtime'))""",
        (fondo_inicial,),
    )
    caja_id = cur.lastrowid
    conn.execute(
        """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo)
           VALUES (?, 'APERTURA', 'EFECTIVO', ?, 'Apertura de jornada')""",
        (caja_id, fondo_inicial),
    )

    # Ventas sintéticas de muestra para que la demo arranque viva
    # Venta 1: En efectivo (Coca + Pan)
    _sembrar_venta(
        conn,
        caja_id=caja_id,
        cliente_id=1,  # Consumidor final
        items=[(1, 1, 380000), (21, 1, 270000)], # Coca 2.25L ($3.800) + Pan Lactal ($2.700)
        pagos=[(MEDIO_EFECTIVO, 650000)],
    )

    # Venta 2: Pago Mixto (Yerba + Azucar + Fideos)
    _sembrar_venta(
        conn,
        caja_id=caja_id,
        cliente_id=1,
        items=[(7, 1, 460000), (8, 2, 250000), (10, 2, 290000)],
        pagos=[(MEDIO_EFECTIVO, 500000), (MEDIO_MERCADO_PAGO, 500000)],
    )

    # Venta 3: Fiado a Juan Pérez (Queso Cremoso 500g + Pan Francés 1kg)
    # Queso 500g a $8.900/kg = $4.450. Pan 1000g a $2.300/kg = $2.300. Total = $6.750
    _sembrar_venta(
        conn,
        caja_id=caja_id,
        cliente_id=2,  # Juan Pérez
        items=[(14, 500, 445000), (22, 1000, 230000)],
        pagos=[(MEDIO_FIADO, 675000)],
    )

    # Venta 4: Débito (Artículos de limpieza)
    _sembrar_venta(
        conn,
        caja_id=caja_id,
        cliente_id=1,
        items=[(30, 2, 520000), (31, 1, 130000), (32, 2, 500000)],
        pagos=[(MEDIO_DEBITO, 1150000)],
    )

    # Deuda histórica previa de clientes para que se puedan probar cobros inmediatamente
    deudas_iniciales = [
        (2, 1250000, "Saldo pendiente compras de la semana"), # Juan Pérez ($ 12.500)
        (4, 1850000, "Venta fiada anterior"),                # Carlos Rodríguez ($ 18.500)
        (5, 3400000, "Saldo mercadería"),                    # Laura Fernández ($ 34.000)
        (7, 850000, "Fiado almacén"),                        # Sofía Romero ($ 8.500)
        (10, 3150000, "Compras mes corriente"),              # Diego López ($ 31.500)
    ]
    for cid, monto, desc in deudas_iniciales:
        conn.execute(
            """INSERT INTO movimientos_cuenta (cliente_id, tipo, monto_centavos, saldo_resultante_centavos, descripcion)
               VALUES (?, 'FIADO', ?, ?, ?)""",
            (cid, monto, monto, desc),
        )

    # Movimientos manuales de caja de ejemplo (ingreso cambio y gasto menor)
    conn.execute(
        """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo)
           VALUES (?, 'INGRESO', 'EFECTIVO', 1000000, 'Ingreso cambio chico (monedas y billetes)')""",
        (caja_id,),
    )
    conn.execute(
        """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo)
           VALUES (?, 'GASTO', 'EFECTIVO', -350000, 'Compra de bolsas camiseta para despacho')""",
        (caja_id,),
    )


def _sembrar_venta(
    conn: sqlite3.Connection,
    caja_id: int,
    cliente_id: int,
    items: list[tuple[int, int, int]], # (producto_id, cantidad_o_gramos, subtotal_centavos)
    pagos: list[tuple[str, int]],      # (medio, monto_centavos)
) -> int:
    """Helper para sembrar una venta consistente en la base de datos."""
    subtotal = sum(i[2] for i in items)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO ventas (caja_id, cliente_id, subtotal_centavos, total_centavos, estado)
           VALUES (?, ?, ?, ?, 'CONFIRMADA')""",
        (caja_id, cliente_id, subtotal, subtotal),
    )
    venta_id = cur.lastrowid

    for prod_id, cant, sub in items:
        prod = conn.execute("SELECT nombre, tipo_venta, precio_venta_centavos, stock FROM productos WHERE id = ?", (prod_id,)).fetchone()
        conn.execute(
            """INSERT INTO items_venta (venta_id, producto_id, descripcion, tipo_venta, cantidad, precio_unitario_centavos, subtotal_centavos)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (venta_id, prod_id, prod["nombre"], prod["tipo_venta"], cant, prod["precio_venta_centavos"], sub),
        )
        # Descontar stock
        nuevo_stock = max(0, prod["stock"] - cant)
        conn.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo_stock, prod_id))
        conn.execute(
            """INSERT INTO movimientos_stock (producto_id, tipo, cantidad, stock_resultante, venta_id, motivo)
               VALUES (?, 'VENTA', ?, ?, ?, 'Venta mostrador')""",
            (prod_id, -cant, nuevo_stock, venta_id),
        )

    for medio, monto in pagos:
        conn.execute(
            "INSERT INTO pagos_venta (venta_id, medio, monto_centavos) VALUES (?, ?, ?)",
            (venta_id, medio, monto),
        )
        # Impacto en caja si corresponde
        conn.execute(
            """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo, venta_id)
               VALUES (?, 'VENTA', ?, ?, 'Venta #' || ?, ?)""",
            (caja_id, medio, monto, venta_id, venta_id),
        )
        # Impacto en fiado
        if medio == MEDIO_FIADO and cliente_id > 1:
            # Obtener saldo actual
            saldo_row = conn.execute(
                "SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_cuenta WHERE cliente_id = ?",
                (cliente_id,),
            ).fetchone()
            saldo_act = saldo_row[0] if saldo_row else 0
            conn.execute(
                """INSERT INTO movimientos_cuenta (cliente_id, tipo, monto_centavos, saldo_resultante_centavos, descripcion, venta_id)
                   VALUES (?, 'FIADO', ?, ?, 'Venta a fiado #' || ?, ?)""",
                (cliente_id, monto, saldo_act + monto, venta_id, venta_id),
            )
    return venta_id


# --------------------------------------------------------------------------- #
# Lógica de Dominio: Consultas y Servicios
# --------------------------------------------------------------------------- #
def obtener_estado_general() -> dict[str, Any]:
    """Retorna el estado de la caja abierta, totales y datos rápidos del sistema."""
    conn = get_db()
    caja = conn.execute("SELECT * FROM cajas WHERE estado = 'ABIERTA' ORDER BY id DESC LIMIT 1").fetchone()
    if not caja:
        conn.close()
        return {
            "caja_abierta": False,
            "caja_id": None,
            "monto_inicial": 0,
            "efectivo_esperado": 0,
            "efectivo_esperado_formateado": "$ 0,00",
        }

    # Sumar todos los movimientos de efectivo de esta caja
    row = conn.execute(
        """SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_caja
           WHERE caja_id = ? AND medio = 'EFECTIVO'""",
        (caja["id"],),
    ).fetchone()
    efectivo_esperado = row[0]

    # Conteo de productos con stock bajo
    bajo_stock_count = conn.execute(
        "SELECT COUNT(*) FROM productos WHERE activo = 1 AND stock <= stock_minimo"
    ).fetchone()[0]

    conn.close()
    return {
        "caja_abierta": True,
        "caja_id": caja["id"],
        "abierta_en": caja["abierta_en"],
        "monto_inicial": caja["monto_inicial_centavos"],
        "efectivo_esperado": efectivo_esperado,
        "efectivo_esperado_formateado": formatear_centavos(efectivo_esperado),
        "productos_stock_bajo": bajo_stock_count,
    }


def listar_productos(categoria_id: int | None = None, busqueda: str | None = None, solo_stock_bajo: bool = False) -> list[dict[str, Any]]:
    """Devuelve el catálogo de productos con formateo de precios y flags."""
    conn = get_db()
    query = """
        SELECT p.*, c.nombre as categoria_nombre
        FROM productos p
        JOIN categorias c ON p.categoria_id = c.id
        WHERE p.activo = 1
    """
    params: list[Any] = []
    if categoria_id:
        query += " AND p.categoria_id = ?"
        params.append(categoria_id)
    if busqueda:
        query += " AND (p.nombre LIKE ? OR p.codigo_barras LIKE ?)"
        term = f"%{busqueda.strip()}%"
        params.extend([term, term])
    if solo_stock_bajo:
        query += " AND p.stock <= p.stock_minimo"

    query += " ORDER BY p.nombre ASC"
    rows = conn.execute(query, params).fetchall()
    resultado = []
    for r in rows:
        resultado.append({
            "id": r["id"],
            "nombre": r["nombre"],
            "categoria_id": r["categoria_id"],
            "categoria": r["categoria_nombre"],
            "codigo_barras": r["codigo_barras"] or "",
            "tipo_venta": r["tipo_venta"],
            "precio_venta_centavos": r["precio_venta_centavos"],
            "precio_venta_formateado": formatear_centavos(r["precio_venta_centavos"]),
            "precio_costo_centavos": r["precio_costo_centavos"],
            "precio_costo_formateado": formatear_centavos(r["precio_costo_centavos"]),
            "stock": r["stock"],
            "stock_minimo": r["stock_minimo"],
            "stock_formateado": formatear_cantidad(r["stock"], r["tipo_venta"]),
            "stock_minimo_formateado": formatear_cantidad(r["stock_minimo"], r["tipo_venta"]),
            "stock_bajo": r["stock"] <= r["stock_minimo"],
            "activo": bool(r["activo"]),
        })
    conn.close()
    return resultado


def obtener_producto(producto_id: int) -> dict[str, Any] | None:
    conn = get_db()
    r = conn.execute(
        """SELECT p.*, c.nombre as categoria_nombre
           FROM productos p
           JOIN categorias c ON p.categoria_id = c.id
           WHERE p.id = ?""",
        (producto_id,),
    ).fetchone()
    conn.close()
    if not r:
        return None
    return {
        "id": r["id"],
        "nombre": r["nombre"],
        "categoria": r["categoria_nombre"],
        "tipo_venta": r["tipo_venta"],
        "precio_venta_centavos": r["precio_venta_centavos"],
        "precio_venta_formateado": formatear_centavos(r["precio_venta_centavos"]),
        "stock": r["stock"],
        "stock_minimo": r["stock_minimo"],
        "stock_bajo": r["stock"] <= r["stock_minimo"],
    }


def ajustar_stock(producto_id: int, delta: int, tipo: str, motivo: str) -> dict[str, Any]:
    """Ajusta el stock de un producto y audita el movimiento."""
    conn = get_db()
    with conn:
        prod = conn.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
        if not prod:
            raise ValueError(f"No existe el producto con ID {producto_id}")
        nuevo_stock = prod["stock"] + delta
        if nuevo_stock < 0:
            raise ValueError(f"El ajuste dejaría el stock en negativo ({nuevo_stock})")
        conn.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo_stock, producto_id))
        conn.execute(
            """INSERT INTO movimientos_stock (producto_id, tipo, cantidad, stock_resultante, motivo)
               VALUES (?, ?, ?, ?, ?)""",
            (producto_id, tipo, delta, nuevo_stock, motivo),
        )
    conn.close()
    return {"nuevo_stock": nuevo_stock, "nuevo_stock_formateado": formatear_cantidad(nuevo_stock, prod["tipo_venta"])}


def listar_clientes() -> list[dict[str, Any]]:
    """Lista todos los clientes con su saldo deudor actual y crédito disponible."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY id ASC").fetchall()
    resultado = []
    for r in rows:
        # Calcular saldo actual deudor
        saldo_row = conn.execute(
            "SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_cuenta WHERE cliente_id = ?",
            (r["id"],),
        ).fetchone()
        saldo_centavos = saldo_row[0] if saldo_row else 0
        limite = r["limite_fiado_centavos"]
        disponible = max(0, limite - saldo_centavos) if limite > 0 else 0

        resultado.append({
            "id": r["id"],
            "nombre": r["nombre"],
            "telefono": r["telefono"] or "-",
            "limite_fiado_centavos": limite,
            "limite_formateado": formatear_centavos(limite),
            "saldo_centavos": saldo_centavos,
            "saldo_formateado": formatear_centavos(saldo_centavos),
            "credito_disponible_centavos": disponible,
            "credito_disponible_formateado": formatear_centavos(disponible),
            "tiene_fiado": limite > 0,
        })
    conn.close()
    return resultado


def obtener_cliente_detalle(cliente_id: int) -> dict[str, Any] | None:
    conn = get_db()
    c = conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
    if not c:
        conn.close()
        return None

    saldo = conn.execute(
        "SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_cuenta WHERE cliente_id = ?",
        (cliente_id,),
    ).fetchone()[0]
    limite = c["limite_fiado_centavos"]
    disponible = max(0, limite - saldo) if limite > 0 else 0

    movs_rows = conn.execute(
        """SELECT * FROM movimientos_cuenta WHERE cliente_id = ?
           ORDER BY id DESC LIMIT 50""",
        (cliente_id,),
    ).fetchall()

    movimientos = []
    for m in movs_rows:
        movimientos.append({
            "id": m["id"],
            "tipo": m["tipo"],
            "monto_centavos": m["monto_centavos"],
            "monto_formateado": formatear_centavos(abs(m["monto_centavos"])),
            "saldo_resultante_centavos": m["saldo_resultante_centavos"],
            "saldo_resultante_formateado": formatear_centavos(m["saldo_resultante_centavos"]),
            "descripcion": m["descripcion"] or "",
            "venta_id": m["venta_id"],
            "fecha": m["creado_en"],
        })

    conn.close()
    return {
        "id": c["id"],
        "nombre": c["nombre"],
        "telefono": c["telefono"] or "-",
        "limite_fiado_centavos": limite,
        "limite_formateado": formatear_centavos(limite),
        "saldo_centavos": saldo,
        "saldo_formateado": formatear_centavos(saldo),
        "credito_disponible_centavos": disponible,
        "credito_disponible_formateado": formatear_centavos(disponible),
        "tiene_fiado": limite > 0,
        "movimientos": movimientos,
    }


def registrar_cobro_cliente(cliente_id: int, monto_centavos: int, medio: str) -> dict[str, Any]:
    """Registra el pago de una deuda de cliente, reduciendo su saldo e ingresando a caja."""
    if monto_centavos <= 0:
        raise ValueError("El monto de cobro debe ser mayor a cero")

    conn = get_db()
    with conn:
        cliente = conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
        if not cliente:
            raise ValueError(f"Cliente {cliente_id} no encontrado")

        saldo_actual = conn.execute(
            "SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_cuenta WHERE cliente_id = ?",
            (cliente_id,),
        ).fetchone()[0]

        if saldo_actual <= 0:
            raise ValueError("El cliente no tiene deuda pendiente")
        if monto_centavos > saldo_actual:
            raise ValueError(f"No se puede cobrar más que la deuda actual ({formatear_centavos(saldo_actual)})")

        nuevo_saldo = saldo_actual - monto_centavos
        conn.execute(
            """INSERT INTO movimientos_cuenta (cliente_id, tipo, monto_centavos, saldo_resultante_centavos, descripcion)
               VALUES (?, 'PAGO', ?, ?, 'Cobro cuenta corriente - ' || ?)""",
            (cliente_id, -monto_centavos, nuevo_saldo, MEDIOS_ETIQUETAS.get(medio, medio)),
        )

        # Si hay caja abierta, registrar ingreso del dinero cobrado
        caja = conn.execute("SELECT id FROM cajas WHERE estado = 'ABIERTA' ORDER BY id DESC LIMIT 1").fetchone()
        if caja:
            conn.execute(
                """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo)
                   VALUES (?, 'INGRESO', ?, ?, 'Cobro fiado ' || ?)""",
                (caja["id"], medio, monto_centavos, cliente["nombre"]),
            )

    conn.close()
    return {
        "nuevo_saldo_centavos": nuevo_saldo,
        "nuevo_saldo_formateado": formatear_centavos(nuevo_saldo),
        "monto_cobrado_formateado": formatear_centavos(monto_centavos),
    }


# --------------------------------------------------------------------------- #
# Lógica de Venta Completa
# --------------------------------------------------------------------------- #
def registrar_venta(
    items: list[dict[str, Any]],
    pagos: list[dict[str, Any]],
    cliente_id: int = 1,
    descuento_general_centavos: int = 0,
) -> dict[str, Any]:
    """Registra una venta atómica con validación de stock, snapshot de precios,

    pagos mixtos, cuenta corriente e impacto en caja.
    """
    if not items:
        raise ValueError("El carrito no tiene productos")
    if not pagos:
        raise ValueError("Debe ingresar al menos un medio de pago")

    conn = get_db()
    with conn:
        # 1. Obtener caja abierta
        caja = conn.execute("SELECT id FROM cajas WHERE estado = 'ABIERTA' ORDER BY id DESC LIMIT 1").fetchone()
        if not caja:
            raise ValueError("No se puede vender: la caja está cerrada. Abra la caja primero.")
        caja_id = caja["id"]

        # 2. Validar y procesar líneas del carrito
        lineas_procesadas = []
        subtotal_total = 0
        for idx, it in enumerate(items, start=1):
            prod_id = int(it.get("producto_id", 0))
            cant = int(it.get("cantidad", 0))
            if cant <= 0:
                raise ValueError(f"Línea {idx}: La cantidad o peso debe ser mayor a 0")

            prod = conn.execute("SELECT * FROM productos WHERE id = ?", (prod_id,)).fetchone()
            if not prod:
                raise ValueError(f"Producto con ID {prod_id} no existe")
            if not prod["activo"]:
                raise ValueError(f"El producto '{prod['nombre']}' se encuentra inactivo")

            # Control estricto de existencias
            if prod["stock"] < cant:
                disponible = formatear_cantidad(prod["stock"], prod["tipo_venta"])
                solicitado = formatear_cantidad(cant, prod["tipo_venta"])
                raise ValueError(f"Stock insuficiente para '{prod['nombre']}': hay {disponible} y se solicitan {solicitado}")

            desc_linea = int(it.get("descuento_centavos", 0))
            sub_linea = calcular_subtotal_linea(prod["tipo_venta"], cant, prod["precio_venta_centavos"], desc_linea)
            subtotal_total += sub_linea

            lineas_procesadas.append({
                "producto": prod,
                "cantidad": cant,
                "precio_unitario": prod["precio_venta_centavos"],
                "descuento": desc_linea,
                "subtotal": sub_linea,
            })

        total_venta = max(0, subtotal_total - int(descuento_general_centavos))

        # 3. Validar pagos mixtos
        suma_pagos = sum(int(p.get("monto_centavos", 0)) for p in pagos)
        if suma_pagos != total_venta:
            diferencia = formatear_centavos(abs(suma_pagos - total_venta))
            raise ValueError(f"El total de los pagos ({formatear_centavos(suma_pagos)}) no coincide con el total de la venta ({formatear_centavos(total_venta)}). Diferencia: {diferencia}")

        # 4. Validar Fiado si corresponde
        pago_fiado = next((p for p in pagos if p.get("medio") == MEDIO_FIADO), None)
        if pago_fiado:
            monto_fiado = int(pago_fiado["monto_centavos"])
            if cliente_id <= 1:
                raise ValueError("Para vender a fiado debe seleccionar un cliente registrado (no Consumidor Final)")
            cliente = conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
            if not cliente:
                raise ValueError("Cliente seleccionado no existe")
            if cliente["limite_fiado_centavos"] <= 0:
                raise ValueError(f"El cliente {cliente['nombre']} no tiene crédito de fiado habilitado")

            saldo_act = conn.execute(
                "SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_cuenta WHERE cliente_id = ?",
                (cliente_id,),
            ).fetchone()[0]

            if saldo_act + monto_fiado > cliente["limite_fiado_centavos"]:
                disponible = max(0, cliente["limite_fiado_centavos"] - saldo_act)
                raise ValueError(f"El cliente no tiene crédito disponible suficiente. Disponible: {formatear_centavos(disponible)} | Solicitado a fiar: {formatear_centavos(monto_fiado)}")

        # 5. Insertar encabezado de Venta
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO ventas (cliente_id, caja_id, subtotal_centavos, descuento_centavos, total_centavos, estado)
               VALUES (?, ?, ?, ?, ?, 'CONFIRMADA')""",
            (cliente_id if cliente_id > 1 else None, caja_id, subtotal_total, descuento_general_centavos, total_venta),
        )
        venta_id = cur.lastrowid

        # 6. Insertar items y descontar stock auditado
        for lp in lineas_procesadas:
            prod = lp["producto"]
            cant = lp["cantidad"]
            conn.execute(
                """INSERT INTO items_venta (venta_id, producto_id, descripcion, tipo_venta, cantidad, precio_unitario_centavos, descuento_centavos, subtotal_centavos)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (venta_id, prod["id"], prod["nombre"], prod["tipo_venta"], cant, lp["precio_unitario"], lp["descuento"], lp["subtotal"]),
            )
            nuevo_stock = prod["stock"] - cant
            conn.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo_stock, prod["id"]))
            conn.execute(
                """INSERT INTO movimientos_stock (producto_id, tipo, cantidad, stock_resultante, motivo, venta_id)
                   VALUES (?, 'VENTA', ?, ?, 'Venta #' || ?, ?)""",
                (prod["id"], -cant, nuevo_stock, venta_id, venta_id),
            )

        # 7. Insertar pagos y asentar en caja / cuenta corriente
        for p in pagos:
            medio = p["medio"]
            monto_p = int(p["monto_centavos"])
            conn.execute(
                "INSERT INTO pagos_venta (venta_id, medio, monto_centavos) VALUES (?, ?, ?)",
                (venta_id, medio, monto_p),
            )
            # En la caja se asienta el movimiento
            conn.execute(
                """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo, venta_id)
                   VALUES (?, 'VENTA', ?, ?, 'Venta #' || ?, ?)""",
                (caja_id, medio, monto_p, venta_id, venta_id),
            )
            # Si fue fiado, impactar cuenta corriente
            if medio == MEDIO_FIADO and cliente_id > 1:
                saldo_previo = conn.execute(
                    "SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_cuenta WHERE cliente_id = ?",
                    (cliente_id,),
                ).fetchone()[0]
                conn.execute(
                    """INSERT INTO movimientos_cuenta (cliente_id, tipo, monto_centavos, saldo_resultante_centavos, descripcion, venta_id)
                       VALUES (?, 'FIADO', ?, ?, 'Venta fiada #' || ?, ?)""",
                    (cliente_id, monto_p, saldo_previo + monto_p, venta_id, venta_id),
                )

    conn.close()
    return {
        "venta_id": venta_id,
        "venta_numero": f"{venta_id:06d}",
        "total_centavos": total_venta,
        "total_formateado": formatear_centavos(total_venta),
        "items_count": len(lineas_procesadas),
    }


def anular_venta(venta_id: int, motivo: str) -> dict[str, Any]:
    """Anula una venta lógicamente: devuelve el stock, contrarresta caja y revierte fiados."""
    if not motivo or not motivo.strip():
        raise ValueError("Debe ingresar un motivo obligatorio para la anulación")

    conn = get_db()
    with conn:
        venta = conn.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
        if not venta:
            raise ValueError(f"No existe la venta #{venta_id}")
        if venta["estado"] == VENTA_ANULADA:
            raise ValueError(f"La venta #{venta_id} ya se encuentra ANULADA")

        # 1. Revertir stock de cada item
        items = conn.execute("SELECT * FROM items_venta WHERE venta_id = ?", (venta_id,)).fetchall()
        for it in items:
            prod = conn.execute("SELECT * FROM productos WHERE id = ?", (it["producto_id"],)).fetchone()
            if prod:
                nuevo_stock = prod["stock"] + it["cantidad"]
                conn.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo_stock, prod["id"]))
                conn.execute(
                    """INSERT INTO movimientos_stock (producto_id, tipo, cantidad, stock_resultante, motivo, venta_id)
                       VALUES (?, 'ANULACION', ?, ?, 'Anulación venta #' || ?, ?)""",
                    (prod["id"], it["cantidad"], nuevo_stock, venta_id, venta_id),
                )

        # 2. Revertir impacto en caja
        pagos = conn.execute("SELECT * FROM pagos_venta WHERE venta_id = ?", (venta_id,)).fetchall()
        caja_activa = conn.execute("SELECT id FROM cajas WHERE estado = 'ABIERTA' ORDER BY id DESC LIMIT 1").fetchone()
        caja_destino_id = caja_activa["id"] if caja_activa else venta["caja_id"]
        for p in pagos:
            if caja_destino_id:
                conn.execute(
                    """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo, venta_id)
                       VALUES (?, 'ANULACION', ?, ?, 'Anulación Venta #' || ?, ?)""",
                    (caja_destino_id, p["medio"], -p["monto_centavos"], venta_id, venta_id),
                )
            # 3. Si hubo pago a Fiado, compensar la deuda en cuenta corriente
            if p["medio"] == MEDIO_FIADO and venta["cliente_id"]:
                saldo_prev = conn.execute(
                    "SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_cuenta WHERE cliente_id = ?",
                    (venta["cliente_id"],),
                ).fetchone()[0]
                conn.execute(
                    """INSERT INTO movimientos_cuenta (cliente_id, tipo, monto_centavos, saldo_resultante_centavos, descripcion, venta_id)
                       VALUES (?, 'PAGO', ?, ?, 'Anulación venta #' || ?, ?)""",
                    (venta["cliente_id"], -p["monto_centavos"], saldo_prev - p["monto_centavos"], venta_id, venta_id),
                )

        # 4. Marcar venta como ANULADA
        conn.execute(
            """UPDATE ventas
               SET estado = 'ANULADA', anulada_en = datetime('now', 'localtime'), motivo_anulacion = ?
               WHERE id = ?""",
            (motivo.strip(), venta_id),
        )

    conn.close()
    return {"venta_id": venta_id, "estado": "ANULADA"}


def listar_ventas(limite: int = 50) -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        """SELECT v.*, c.nombre as cliente_nombre
           FROM ventas v
           LEFT JOIN clientes c ON v.cliente_id = c.id
           ORDER BY v.id DESC LIMIT ?""",
        (limite,),
    ).fetchall()

    ventas = []
    for r in rows:
        # Obtener medios de pago de esta venta
        pagos = conn.execute("SELECT medio, monto_centavos FROM pagos_venta WHERE venta_id = ?", (r["id"],)).fetchall()
        medios_txt = ", ".join(f"{MEDIOS_ETIQUETAS.get(p['medio'], p['medio'])} ({formatear_centavos(p['monto_centavos'])})" for p in pagos)

        ventas.append({
            "id": r["id"],
            "numero": f"{r['id']:06d}",
            "fecha": r["fecha"],
            "cliente": r["cliente_nombre"] or "Consumidor final",
            "total_centavos": r["total_centavos"],
            "total_formateado": formatear_centavos(r["total_centavos"]),
            "estado": r["estado"],
            "es_anulada": r["estado"] == VENTA_ANULADA,
            "motivo_anulacion": r["motivo_anulacion"] or "",
            "medios_pago": medios_txt,
        })
    conn.close()
    return ventas


def obtener_venta_detalle(venta_id: int) -> dict[str, Any] | None:
    conn = get_db()
    v = conn.execute(
        """SELECT v.*, c.nombre as cliente_nombre
           FROM ventas v
           LEFT JOIN clientes c ON v.cliente_id = c.id
           WHERE v.id = ?""",
        (venta_id,),
    ).fetchone()
    if not v:
        conn.close()
        return None

    items = conn.execute("SELECT * FROM items_venta WHERE venta_id = ?", (venta_id,)).fetchall()
    pagos = conn.execute("SELECT * FROM pagos_venta WHERE venta_id = ?", (venta_id,)).fetchall()
    conn.close()

    return {
        "id": v["id"],
        "numero": f"{v['id']:06d}",
        "fecha": v["fecha"],
        "cliente": v["cliente_nombre"] or "Consumidor final",
        "subtotal_formateado": formatear_centavos(v["subtotal_centavos"]),
        "descuento_formateado": formatear_centavos(v["descuento_centavos"]),
        "total_centavos": v["total_centavos"],
        "total_formateado": formatear_centavos(v["total_centavos"]),
        "estado": v["estado"],
        "motivo_anulacion": v["motivo_anulacion"] or "",
        "items": [
            {
                "descripcion": it["descripcion"],
                "tipo_venta": it["tipo_venta"],
                "cantidad": it["cantidad"],
                "cantidad_formateada": formatear_cantidad(it["cantidad"], it["tipo_venta"]),
                "precio_unitario_formateado": formatear_centavos(it["precio_unitario_centavos"]),
                "subtotal_formateado": formatear_centavos(it["subtotal_centavos"]),
            }
            for it in items
        ],
        "pagos": [
            {
                "medio": p["medio"],
                "medio_etiqueta": MEDIOS_ETIQUETAS.get(p["medio"], p["medio"]),
                "monto_formateado": formatear_centavos(p["monto_centavos"]),
            }
            for p in pagos
        ],
    }


# --------------------------------------------------------------------------- #
# Lógica de Caja
# --------------------------------------------------------------------------- #
def obtener_caja_info() -> dict[str, Any]:
    """Información completa de la caja abierta actual y sus movimientos."""
    conn = get_db()
    caja = conn.execute("SELECT * FROM cajas WHERE estado = 'ABIERTA' ORDER BY id DESC LIMIT 1").fetchone()
    if not caja:
        conn.close()
        return {"abierta": False}

    caja_id = caja["id"]
    movs = conn.execute(
        """SELECT * FROM movimientos_caja WHERE caja_id = ?
           ORDER BY id DESC LIMIT 100""",
        (caja_id,),
    ).fetchall()

    # Totales de ventas por medio en esta caja
    totales_medios: dict[str, int] = {m: 0 for m in MEDIOS_PAGO}
    totales_filas = conn.execute(
        """SELECT medio, COALESCE(SUM(monto_centavos), 0) as total
           FROM movimientos_caja
           WHERE caja_id = ? AND tipo = 'VENTA'
           GROUP BY medio""",
        (caja_id,),
    ).fetchall()
    for row in totales_filas:
        if row["medio"] in totales_medios:
            totales_medios[row["medio"]] = row["total"]

    # Suma por tipo de movimiento
    suma_ingresos = conn.execute("SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_caja WHERE caja_id = ? AND tipo = 'INGRESO'", (caja_id,)).fetchone()[0]
    suma_gastos = conn.execute("SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_caja WHERE caja_id = ? AND tipo = 'GASTO'", (caja_id,)).fetchone()[0]
    suma_retiros = conn.execute("SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_caja WHERE caja_id = ? AND tipo = 'RETIRO'", (caja_id,)).fetchone()[0]
    total_efectivo = conn.execute("SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_caja WHERE caja_id = ? AND medio = 'EFECTIVO'", (caja_id,)).fetchone()[0]

    conn.close()

    movimientos_formateados = []
    for m in movs:
        movimientos_formateados.append({
            "id": m["id"],
            "tipo": m["tipo"],
            "medio": m["medio"],
            "medio_etiqueta": MEDIOS_ETIQUETAS.get(m["medio"], m["medio"] or "-"),
            "monto_centavos": m["monto_centavos"],
            "monto_formateado": formatear_centavos(m["monto_centavos"]),
            "motivo": m["motivo"] or "",
            "fecha": m["creado_en"],
        })

    return {
        "abierta": True,
        "id": caja_id,
        "abierta_en": caja["abierta_en"],
        "monto_inicial_centavos": caja["monto_inicial_centavos"],
        "monto_inicial_formateado": formatear_centavos(caja["monto_inicial_centavos"]),
        "total_ventas_efectivo": formatear_centavos(totales_medios[MEDIO_EFECTIVO]),
        "total_ventas_debito": formatear_centavos(totales_medios[MEDIO_DEBITO]),
        "total_ventas_transferencia": formatear_centavos(totales_medios[MEDIO_TRANSFERENCIA]),
        "total_ventas_mp": formatear_centavos(totales_medios[MEDIO_MERCADO_PAGO]),
        "total_ventas_fiado": formatear_centavos(totales_medios[MEDIO_FIADO]),
        "total_ventas_todas": formatear_centavos(sum(totales_medios.values())),
        "ingresos_manuales": formatear_centavos(suma_ingresos),
        "gastos_manuales": formatear_centavos(abs(suma_gastos)),
        "retiros_manuales": formatear_centavos(abs(suma_retiros)),
        "efectivo_esperado_centavos": total_efectivo,
        "efectivo_esperado_formateado": formatear_centavos(total_efectivo),
        "movimientos": movimientos_formateados,
    }


def registrar_movimiento_caja(tipo: str, monto_centavos: int, motivo: str, medio: str = MEDIO_EFECTIVO) -> dict[str, Any]:
    """Registra un movimiento manual (INGRESO, RETIRO, GASTO)."""
    if monto_centavos <= 0:
        raise ValueError("El monto debe ser mayor a cero")
    if not motivo or not motivo.strip():
        raise ValueError("Debe ingresar el motivo del movimiento")

    conn = get_db()
    with conn:
        caja = conn.execute("SELECT id FROM cajas WHERE estado = 'ABIERTA' ORDER BY id DESC LIMIT 1").fetchone()
        if not caja:
            raise ValueError("No hay ninguna caja abierta actualmente")

        monto_firmado = monto_centavos if tipo == CAJA_MOV_INGRESO else -monto_centavos
        conn.execute(
            """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo)
               VALUES (?, ?, ?, ?, ?)""",
            (caja["id"], tipo, medio, monto_firmado, motivo.strip()),
        )
    conn.close()
    return {"tipo": tipo, "monto_formateado": formatear_centavos(monto_centavos)}


def abrir_caja(monto_inicial_centavos: int) -> dict[str, Any]:
    conn = get_db()
    with conn:
        caja_activa = conn.execute("SELECT id FROM cajas WHERE estado = 'ABIERTA'").fetchone()
        if caja_activa:
            raise ValueError("Ya existe una caja abierta en el sistema")

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cajas (estado, monto_inicial_centavos) VALUES ('ABIERTA', ?)",
            (monto_inicial_centavos,),
        )
        caja_id = cur.lastrowid
        conn.execute(
            """INSERT INTO movimientos_caja (caja_id, tipo, medio, monto_centavos, motivo)
               VALUES (?, 'APERTURA', 'EFECTIVO', ?, 'Fondo inicial')""",
            (caja_id, monto_inicial_centavos),
        )
    conn.close()
    return {"caja_id": caja_id, "monto_inicial_formateado": formatear_centavos(monto_inicial_centavos)}


def cerrar_caja(contado_efectivo_centavos: int, observaciones: str = "") -> dict[str, Any]:
    conn = get_db()
    with conn:
        caja = conn.execute("SELECT * FROM cajas WHERE estado = 'ABIERTA' ORDER BY id DESC LIMIT 1").fetchone()
        if not caja:
            raise ValueError("No hay ninguna caja abierta para cerrar")

        caja_id = caja["id"]
        # Calcular efectivo esperado
        total_efectivo = conn.execute(
            "SELECT COALESCE(SUM(monto_centavos), 0) FROM movimientos_caja WHERE caja_id = ? AND medio = 'EFECTIVO'",
            (caja_id,),
        ).fetchone()[0]

        diferencia = contado_efectivo_centavos - total_efectivo
        conn.execute(
            """UPDATE cajas
               SET estado = 'CERRADA', cerrada_en = datetime('now', 'localtime'),
                   contado_efectivo_centavos = ?, diferencia_centavos = ?, observaciones = ?
               WHERE id = ?""",
            (contado_efectivo_centavos, diferencia, observaciones.strip(), caja_id),
        )

    conn.close()
    return {
        "caja_id": caja_id,
        "efectivo_esperado_formateado": formatear_centavos(total_efectivo),
        "contado_efectivo_formateado": formatear_centavos(contado_efectivo_centavos),
        "diferencia_centavos": diferencia,
        "diferencia_formateada": formatear_centavos(diferencia),
        "estado": "CERRADA",
    }


# --------------------------------------------------------------------------- #
# Lógica de Reportes y Estadísticas
# --------------------------------------------------------------------------- #
def obtener_reportes(periodo: str = "hoy") -> dict[str, Any]:
    """Genera las métricas principales según el período de tiempo solicitado."""
    conn = get_db()
    filtro_fecha = ""
    if periodo == "hoy":
        filtro_fecha = "date(v.fecha) = date('now', 'localtime')"
    elif periodo == "semana":
        filtro_fecha = "date(v.fecha) >= date('now', '-6 days', 'localtime')"
    elif periodo == "mes":
        filtro_fecha = "strftime('%Y-%m', v.fecha) = strftime('%Y-%m', 'now', 'localtime')"
    elif periodo == "anio":
        filtro_fecha = "strftime('%Y', v.fecha) = strftime('%Y', 'now', 'localtime')"
    else:
        filtro_fecha = "1=1"

    # 1. KPIs Generales de Ventas Confirmadas
    kpis = conn.execute(
        f"""SELECT
                COUNT(v.id) as cantidad_ventas,
                COALESCE(SUM(v.total_centavos), 0) as total_ventas,
                COALESCE(AVG(v.total_centavos), 0) as ticket_promedio
            FROM ventas v
            WHERE v.estado = 'CONFIRMADA' AND {filtro_fecha}"""
    ).fetchone()

    total_centavos = kpis["total_ventas"]
    cant_ventas = kpis["cantidad_ventas"]
    ticket_prom = int(kpis["ticket_promedio"])

    # 2. Total unidades/peso despachado
    despacho_row = conn.execute(
        f"""SELECT COALESCE(SUM(iv.cantidad), 0)
            FROM items_venta iv
            JOIN ventas v ON iv.venta_id = v.id
            WHERE v.estado = 'CONFIRMADA' AND {filtro_fecha}"""
    ).fetchone()
    total_despachado = despacho_row[0] if despacho_row else 0

    # 3. Ventas por Medio de Pago
    medios_rows = conn.execute(
        f"""SELECT pv.medio, COALESCE(SUM(pv.monto_centavos), 0) as total, COUNT(pv.id) as transacciones
            FROM pagos_venta pv
            JOIN ventas v ON pv.venta_id = v.id
            WHERE v.estado = 'CONFIRMADA' AND {filtro_fecha}
            GROUP BY pv.medio
            ORDER BY total DESC"""
    ).fetchall()

    ventas_por_medio = []
    for r in medios_rows:
        porcentaje = (r["total"] / total_centavos * 100) if total_centavos > 0 else 0
        ventas_por_medio.append({
            "medio": r["medio"],
            "medio_etiqueta": MEDIOS_ETIQUETAS.get(r["medio"], r["medio"]),
            "total_centavos": r["total"],
            "total_formateado": formatear_centavos(r["total"]),
            "porcentaje": round(porcentaje, 1),
            "transacciones": r["transacciones"],
        })

    # 4. Top 5 Productos más Vendidos
    top_rows = conn.execute(
        f"""SELECT iv.producto_id, iv.descripcion, iv.tipo_venta,
                   SUM(iv.cantidad) as total_cantidad,
                   SUM(iv.subtotal_centavos) as total_recaudado
            FROM items_venta iv
            JOIN ventas v ON iv.venta_id = v.id
            WHERE v.estado = 'CONFIRMADA' AND {filtro_fecha}
            GROUP BY iv.producto_id, iv.descripcion, iv.tipo_venta
            ORDER BY total_recaudado DESC
            LIMIT 5"""
    ).fetchall()

    top_productos = []
    for tp in top_rows:
        top_productos.append({
            "descripcion": tp["descripcion"],
            "tipo_venta": tp["tipo_venta"],
            "cantidad_formateada": formatear_cantidad(tp["total_cantidad"], tp["tipo_venta"]),
            "total_formateado": formatear_centavos(tp["total_recaudado"]),
        })

    # 5. Productos con Stock Bajo (alerta reposición)
    bajos_rows = conn.execute(
        """SELECT p.nombre, p.tipo_venta, p.stock, p.stock_minimo, c.nombre as categoria
           FROM productos p
           JOIN categorias c ON p.categoria_id = c.id
           WHERE p.activo = 1 AND p.stock <= p.stock_minimo
           ORDER BY p.stock ASC LIMIT 10"""
    ).fetchall()

    stock_alertas = []
    for b in bajos_rows:
        stock_alertas.append({
            "nombre": b["nombre"],
            "categoria": b["categoria"],
            "stock_formateado": formatear_cantidad(b["stock"], b["tipo_venta"]),
            "stock_minimo_formateado": formatear_cantidad(b["stock_minimo"], b["tipo_venta"]),
        })

    conn.close()
    return {
        "periodo": periodo,
        "cantidad_ventas": cant_ventas,
        "total_ventas_centavos": total_centavos,
        "total_ventas_formateado": formatear_centavos(total_centavos),
        "ticket_promedio_formateado": formatear_centavos(ticket_prom),
        "total_despachado": total_despachado,
        "ventas_por_medio": ventas_por_medio,
        "top_productos": top_productos,
        "stock_alertas": stock_alertas,
    }
