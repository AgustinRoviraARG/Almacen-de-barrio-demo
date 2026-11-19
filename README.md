# Almacén de Barrio — Demo Web Interactiva POS

Demo web pública e interactiva del software de Punto de Venta (POS), control de existencias, cuentas corrientes ("fiados") y caja diaria para comercios minoristas de barrio.

Esta aplicación es un **proyecto independiente** diseñado para desplegarse como **Web Service autónomo en Render**, listo para enlazarse desde un portfolio mediante un botón externo:

```text
PORTFOLIO (Django)
    │
    │  [ Ver Demo ]  (enlace externo target="_blank")
    ▼
DEMO ALMACÉN DE BARRIO (Flask en Render)
https://almacen-de-barrio-demo.onrender.com
```

---

## 🚀 Tecnologías Utilizadas

* **Backend:** Python 3.13 + Flask 3.1+
* **Servidor de Producción:** Gunicorn
* **Base de Datos:** SQLite3 (autocontenida, inicializada automáticamente con datos argentinos realistas)
* **Frontend:** HTML5 semántico, CSS3 moderno (arquitectura POS empresarial) y JavaScript Vanilla puro (SPA ligera y reactiva, sin frameworks pesados)
* **Estilo de Moneda:** Centavos enteros (int), sin errores de coma flotante, respetando el formato regional argentino (`$ 1.250,50`).

---

## 🌟 Módulos y Funcionalidades Demostrables

### 1. 🛒 Mostrador de Ventas (POS)
* **Buscador ágil:** Búsqueda en tiempo real por nombre de producto o simulación de lector de código de barras (al presionar `Enter`).
* **Filtros por categoría:** Chips interactivos para filtrar entre Bebidas, Almacén, Lácteos/Fiambres, Panadería, Frutas/Verduras, Kiosco, Limpieza y Perfumería.
* **Venta por Unidad:** Incremento/decremento de unidades con verificación estricta de existencias máximas.
* **Venta por Peso (Pesables):** Modal para productos por peso (ej. *Queso Cremoso*, *Jamón Cocido*, *Pan Francés*, *Papas*). Permite ingresar gramos o kilos (ej. `250g`, `0.5kg`) y calcula el subtotal exacto con la fórmula de dominio:
  $$\text{subtotal} = \frac{\text{precio\_por\_kg} \times \text{gramos}}{1000}$$
* **Carrito Reactivo:** Modificación dinámica de cantidades, eliminación de líneas, vaciado rápido y descuento global.
* **Atajos de Teclado:**
  * `[F2]`: Enfoca inmediatamente el buscador de productos.
  * `[F4]`: Abre la pasarela de cobro si hay productos en el carrito.
  * `[ESC]`: Cierra cualquier ventana modal abierta.

### 2. 💳 Pasarela de Cobro y Pagos Mixtos
* **Efectivo y Vuelto:** Cálculo instantáneo del vuelto a entregar con validación en vivo si el dinero recibido es insuficiente.
* **Medios Digitales:** Selección directa de Débito, Transferencia Bancaria y Mercado Pago / QR.
* **Fiado (Cuenta Corriente):** Selección del cliente con visualización en tiempo real de su deuda actual, límite de crédito y margen disponible. Bloqueo automático si la compra supera el cupo.
* **Pagos Mixtos (Divididos):** Permite fraccionar una misma venta en múltiples medios (ej. `$ 4.000` en efectivo y `$ 3.500` con débito), validando que la suma de pagos sea idéntica al total facturado.
* **Ticket de Venta:** Modal con el resumen imprimible de la venta confirmada, número correlativo de ticket y desglose de medios de pago.

### 3. 📦 Catálogo y Control de Stock
* Tabla completa de inventario con identificación de existencias en unidades o gramos.
* Alerta visual de **`⚠ STOCK BAJO`** cuando el inventario cae por debajo del stock mínimo.
* Modales interactivos para simular **Ingreso de Mercadería** o **Ajuste por Rotura/Merma**, reflejando el cambio de inmediato.

### 4. 👥 Clientes y Cobro de Fiados
* Padrón de clientes de demostración con sus límites de crédito y saldos deudores.
* Ficha de cliente con historial completo de movimientos de cuenta corriente (cargos de fiado y pagos).
* Modal de **Cobranza de Deuda**: permite ingresar pagos parciales o totales (en efectivo, débito, transferencia o MP), reduciendo la deuda e ingresando el dinero a la caja diaria.

### 5. 💰 Caja Diaria y Arqueo
* Panel de control de caja con fondo inicial, ventas acumuladas por medio de pago, ingresos extraordinarios, retiros del titular y gastos de mostrador.
* Indicador del **Efectivo Esperado en Cajón**.
* Botones para registrar movimientos manuales (`+ Ingreso`, `- Retiro`, `- Gasto`).
* **Arqueo y Cierre de Jornada:** El operador declara el efectivo contado físicamente y el sistema determina automáticamente si la caja está **Cuadrada**, con **Sobrante** o con **Faltante**.

### 6. 📊 Reportes y Anulación de Ventas
* Filtro por períodos: *Hoy*, *Últimos 7 días*, *Este Mes* y *Este Año*.
* KPIs comerciales: Ventas totales, Cantidad de operaciones, Ticket promedio y unidades/peso despachado.
* Gráfico proporcional de ventas por medio de pago y ranking de los 5 productos más vendidos.
* **Anulación Lógica de Ventas:** Permite seleccionar una venta confirmada, ingresar un motivo obligatorio y revertir en cascada el stock al inventario, el dinero a la caja y la deuda al fiado.

### 7. 🔄 Reinicio Rápido de Demo
* Botón persistente en el banner superior para restablecer la base de datos a sus valores iniciales limpios con un solo clic.

---

## 💻 Ejecución Local en Windows (PowerShell)

Para probar la demo en tu máquina local:

### 1. Clonar o abrir la carpeta del proyecto
Abre una terminal de **PowerShell** y navega hasta la carpeta:
```powershell
cd "para produccion"
```

### 2. Crear un entorno virtual aislado
El entorno virtual garantiza que las dependencias de Flask no interfieran con otros proyectos de tu sistema:
```powershell
python -m venv venv
```

### 3. Activar el entorno virtual
```powershell
.\venv\Scripts\Activate.ps1
```
*(Si PowerShell te advierte sobre la directiva de ejecución de scripts, puedes habilitarla temporalmente con: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process`)*

### 4. Instalar las dependencias
Instala Flask y Gunicorn:
```powershell
pip install -r requirements.txt
```

### 5. Iniciar la aplicación
Ejecuta el servidor web local:
```powershell
python app.py
```

### 6. Abrir en el navegador
Abre tu navegador web e ingresa a:
👉 **`http://localhost:5000`**

---

## ☁️ Despliegue en Render (Paso a Paso)

El proyecto está 100% preparado para desplegarse como **Web Service** independiente y gratuito en [Render](https://render.com):

1. **Subir a un repositorio nuevo en GitHub:**
   Crea un repositorio en tu cuenta de GitHub (por ejemplo, `almacen-de-barrio-demo`) y sube únicamente el contenido de esta carpeta:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: demo web Almacen de Barrio"
   git branch -M main
   git remote add origin https://github.com/TU-USUARIO/almacen-de-barrio-demo.git
   git push -u origin main
   ```

2. **Crear el Web Service en Render:**
   * Inicia sesión en [dashboard.render.com](https://dashboard.render.com).
   * Haz clic en **New +** y selecciona **Web Service**.
   * Conecta tu repositorio `almacen-de-barrio-demo`.
   * Completa los campos de configuración:
     * **Name:** `almacen-de-barrio-demo` (o el nombre que prefieras).
     * **Region:** Ohio / Frankfurt / la más cercana.
     * **Runtime:** `Python 3`.
     * **Build Command:** `pip install -r requirements.txt`
     * **Start Command:** `gunicorn app:app`
     * **Plan Instance:** `Free`.

3. **Desplegar:**
   Haz clic en **Create Web Service**. Render instalará las dependencias y ejecutará la aplicación con Gunicorn en cuestión de minutos.

4. **URL Pública Obtenida:**
   Render te asignará una URL pública similar a:
   `https://almacen-de-barrio-demo.onrender.com`

---

## 🔗 Integración con tu Portfolio Django

En tu proyecto principal de portfolio (Django), no necesitas instalar nada ni tocar bases de datos. Simplemente agrega un enlace en tu plantilla HTML o tarjeta de proyectos:

```html
<a href="https://almacen-de-barrio-demo.onrender.com" 
   target="_blank" 
   rel="noopener noreferrer" 
   class="btn btn-primary">
   Ver demo en vivo ➔
</a>
```

De esta manera, los reclutadores y clientes potenciales podrán interactuar plenamente con el sistema POS en tiempo real desde cualquier dispositivo sin riesgo alguno para tu portfolio.
