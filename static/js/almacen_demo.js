/**
 * ALMACÉN DE BARRIO — LOGICA INTERACTIVA DEL FRONTEND (VANILLA JAVASCRIPT)
 * Arquitectura modular de aplicación POS para mostrador comercial.
 */

// Estado global de la aplicación
const POS = {
    cart: [],                  // Ítems en el carrito de compras actual
    discountCentavos: 0,       // Descuento global en centavos
    selectedClientId: 1,       // 1 = Consumidor Final
    catalog: [],               // Caché de productos
    categories: [],            // Lista de categorías
    clients: [],               // Padrón de clientes
    caja: null,                // Estado de la caja abierta
    currentView: 'ventas',     // 'ventas' | 'productos' | 'clientes' | 'caja' | 'reportes'
    selectedPaymentMethod: 'EFECTIVO',
    weighingProduct: null,     // Producto pendiente de pesaje
    activeClientDetailId: null,// Cliente inspeccionado en la pestaña clientes
    activeReportPeriod: 'hoy', // Período de reportes activo
    pendingAnulacionId: null,  // ID de venta pendiente de anulación
};

// --------------------------------------------------------------------------- //
// Utilidades de Dinero y Conversión
// --------------------------------------------------------------------------- //
function aCentavos(valor) {
    if (!valor) return 0;
    if (typeof valor === 'number') return Math.round(valor * 100);
    let str = String(valor).trim().replace('$', '').replace(/\s/g, '');
    if (str.includes(',') && str.includes('.')) {
        str = str.replace(/\./g, '').replace(',', '.');
    } else if (str.includes(',')) {
        str = str.replace(',', '.');
    }
    const num = parseFloat(str);
    return isNaN(num) ? 0 : Math.round(num * 100);
}

function formatearDinero(centavos) {
    centavos = Math.round(centavos || 0);
    const signo = centavos < 0 ? '-' : '';
    const abs = Math.abs(centavos);
    const entero = Math.floor(abs / 100);
    const resto = abs % 100;
    const miles = entero.toLocaleString('es-AR');
    const dec = resto < 10 ? '0' + resto : resto;
    return `${signo}$ ${miles},${dec}`;
}

function parsearPesoGramos(valor) {
    if (!valor) return 0;
    let str = String(valor).trim().toLowerCase().replace('kg', '').replace('g', '').replace(/\s/g, '');
    if (str.includes(',')) str = str.replace(',', '.');
    const num = parseFloat(str);
    if (isNaN(num) || num <= 0) return 0;
    // Si contiene punto o es menor a 20 asumimos que ingresó kg (ej 0.5 o 1.5)
    if (str.includes('.') || num < 20) {
        return Math.round(num * 1000);
    }
    return Math.round(num);
}

function formatearCantidad(cantidad, tipoVenta) {
    if (tipoVenta === 'PESO') {
        if (cantidad >= 1000) {
            const kg = (cantidad / 1000).toFixed(3).replace('.', ',');
            return `${kg} kg`;
        }
        return `${cantidad} g`;
    }
    return `${Math.round(cantidad)} u`;
}

// --------------------------------------------------------------------------- //
// Notificaciones Toasts
// --------------------------------------------------------------------------- //
function showToast(mensaje, tipo = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${tipo}`;
    
    let icono = 'ℹ';
    if (tipo === 'success') icono = '✓';
    if (tipo === 'error') icono = '⚠';
    if (tipo === 'warning') icono = '⚡';

    toast.innerHTML = `<span>${icono}</span><span>${mensaje}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        setTimeout(() => toast.remove(), 300);
    }, 3800);
}

// --------------------------------------------------------------------------- //
// Inicialización del DOM
// --------------------------------------------------------------------------- //
document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initNavigation();
    initModals();
    initPosKeyboardShortcuts();
    initVentasEvents();
    initProductosEvents();
    initClientesEvents();
    initCajaEvents();
    initReportesEvents();

    // Carga inicial de datos
    cargarEstadoGeneral();
    cargarCatalogo();
    cargarClientesSelector();
});

function initClock() {
    const clockEl = document.getElementById('pos-clock');
    function updateClock() {
        const now = new Date();
        if (clockEl) {
            clockEl.textContent = now.toLocaleTimeString('es-AR') + ' · ' + now.toLocaleDateString('es-AR');
        }
    }
    setInterval(updateClock, 1000);
    updateClock();
}

// --------------------------------------------------------------------------- //
// Navegación Modular (SPA sin recarga)
// --------------------------------------------------------------------------- //
function initNavigation() {
    const navButtons = document.querySelectorAll('.sidebar-nav .nav-item');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const viewId = btn.dataset.view;
            cambiarVista(viewId);
        });
    });

    // Botón reiniciar demo
    const btnReset = document.getElementById('btn-reset-demo');
    if (btnReset) {
        btnReset.addEventListener('click', reiniciarDemo);
    }
}

function cambiarVista(viewId) {
    POS.currentView = viewId;
    
    // Actualizar sidebar buttons
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(b => {
        b.classList.toggle('active', b.dataset.view === viewId);
    });

    // Actualizar paneles visibles
    document.querySelectorAll('.pos-view').forEach(panel => {
        panel.classList.remove('active');
    });
    const targetPanel = document.getElementById(`view-${viewId}`);
    if (targetPanel) {
        targetPanel.classList.add('active');
    }

    // Títulos de cabecera
    const titles = {
        ventas: { t: 'Punto de Venta — Mostrador', s: 'Registro de operaciones en mostrador y cobro rápido' },
        productos: { t: 'Catálogo de Productos e Inventario', s: 'Monitoreo de existencias, precios y stock mínimo' },
        clientes: { t: 'Clientes y Cuentas Corrientes', s: 'Administración de fiados, límites de crédito y cobros' },
        caja: { t: 'Control de Caja Diaria y Arqueo', s: 'Aperturas, movimientos manuales, gastos y cierre de jornada' },
        reportes: { t: 'Métricas, Desempeño y Reportes', s: 'Análisis de ventas por período, medios de pago y auditoría' }
    };
    if (titles[viewId]) {
        document.getElementById('module-title').textContent = titles[viewId].t;
        document.getElementById('module-subtitle').textContent = titles[viewId].s;
    }

    // Carga de datos correspondiente
    if (viewId === 'ventas') {
        const searchInput = document.getElementById('pos-search-input');
        if (searchInput) searchInput.focus();
    } else if (viewId === 'productos') {
        cargarTablaProductos();
    } else if (viewId === 'clientes') {
        cargarTablaClientes();
    } else if (viewId === 'caja') {
        cargarDatosCaja();
    } else if (viewId === 'reportes') {
        cargarReportes();
    }
}

// --------------------------------------------------------------------------- //
// Estado General y Header
// --------------------------------------------------------------------------- //
async function cargarEstadoGeneral() {
    try {
        const res = await fetch('/api/estado');
        const data = await res.json();
        POS.caja = data;

        const badgeEl = document.getElementById('header-caja-badge');
        const totalEl = document.getElementById('header-caja-total');
        const dotEl = badgeEl.querySelector('.indicator-dot');

        if (data.caja_abierta) {
            dotEl.className = 'indicator-dot open';
            totalEl.textContent = `Efectivo: ${data.efectivo_esperado_formateado}`;
        } else {
            dotEl.className = 'indicator-dot closed';
            totalEl.textContent = 'Caja Cerrada';
        }
    } catch (e) {
        console.error('Error al cargar estado de caja:', e);
    }
}

async function reiniciarDemo() {
    if (!confirm('¿Desea reiniciar la base de datos de la demo a sus valores iniciales?')) return;
    try {
        const res = await fetch('/api/demo/reset', { method: 'POST' });
        const data = await res.json();
        showToast(data.mensaje || 'Demo reiniciada con éxito', 'success');
        POS.cart = [];
        renderCart();
        cargarEstadoGeneral();
        cargarCatalogo();
        cambiarVista('ventas');
    } catch (e) {
        showToast('Error al reiniciar base de datos', 'error');
    }
}

// --------------------------------------------------------------------------- //
// Atajos de Teclado Profesionales POS
// --------------------------------------------------------------------------- //
function initPosKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
        // F2: Buscar en mostrador
        if (e.key === 'F2') {
            e.preventDefault();
            cambiarVista('ventas');
            const searchInput = document.getElementById('pos-search-input');
            if (searchInput) searchInput.focus();
        }
        // F4: Cobrar carrito
        if (e.key === 'F4') {
            e.preventDefault();
            if (POS.cart.length > 0) {
                abrirModalCobro();
            } else {
                showToast('El carrito está vacío', 'warning');
            }
        }
        // Escape: Cerrar modales abiertos
        if (e.key === 'Escape') {
            cerrarTodosModales();
        }
    });
}

// --------------------------------------------------------------------------- //
// MÓDULO 1: VENTAS Y MOSTRADOR
// --------------------------------------------------------------------------- //
function initVentasEvents() {
    const searchInput = document.getElementById('pos-search-input');
    const clearBtn = document.getElementById('btn-clear-search');
    const vaciarBtn = document.getElementById('btn-vaciar-carrito');
    const cobrarBtn = document.getElementById('btn-abrir-cobro');
    const descInput = document.getElementById('cart-discount-input');
    const clienteSelect = document.getElementById('venta-cliente-select');

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            filtrarCatalogo(searchInput.value);
        });
        // Si escanea un código de barras y presiona Enter
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const term = searchInput.value.trim();
                const exacto = POS.catalog.find(p => p.codigo_barras && p.codigo_barras === term);
                if (exacto) {
                    agregarProductoAlCarrito(exacto);
                    searchInput.value = '';
                    filtrarCatalogo('');
                }
            }
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (searchInput) {
                searchInput.value = '';
                searchInput.focus();
                filtrarCatalogo('');
            }
        });
    }

    // Chips de categorías
    document.querySelectorAll('#category-chips .chip-item').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('#category-chips .chip-item').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            cargarCatalogo(chip.dataset.cat);
        });
    });

    if (vaciarBtn) {
        vaciarBtn.addEventListener('click', () => {
            if (POS.cart.length === 0) return;
            if (confirm('¿Vaciar todos los artículos del carrito?')) {
                POS.cart = [];
                renderCart();
            }
        });
    }

    if (cobrarBtn) {
        cobrarBtn.addEventListener('click', abrirModalCobro);
    }

    if (descInput) {
        descInput.addEventListener('change', () => {
            POS.discountCentavos = aCentavos(descInput.value);
            descInput.value = (POS.discountCentavos / 100).toFixed(2).replace('.', ',');
            renderCartSummary();
        });
    }

    if (clienteSelect) {
        clienteSelect.addEventListener('change', () => {
            POS.selectedClientId = parseInt(clienteSelect.value, 10);
        });
    }
}

async function cargarClientesSelector() {
    try {
        const res = await fetch('/api/clientes');
        const clientes = await res.json();
        POS.clients = clientes;
        const select = document.getElementById('venta-cliente-select');
        if (!select) return;
        select.innerHTML = '<option value="1">Consumidor Final</option>';
        clientes.forEach(c => {
            if (c.id > 1) {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = `${c.nombre} (Deuda: ${c.saldo_formateado})`;
                select.appendChild(opt);
            }
        });
    } catch (e) {
        console.error('Error cargando clientes:', e);
    }
}

async function cargarCatalogo(catId = '') {
    const grid = document.getElementById('products-catalog-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="loading-spinner">Cargando productos...</div>';

    try {
        let url = '/api/productos';
        if (catId) url += `?cat=${catId}`;
        const res = await fetch(url);
        const prods = await res.json();
        POS.catalog = prods;
        renderCatalogo(prods);
    } catch (e) {
        grid.innerHTML = '<p class="text-danger">Error al cargar productos.</p>';
    }
}

function filtrarCatalogo(term) {
    if (!term || !term.trim()) {
        renderCatalogo(POS.catalog);
        return;
    }
    const t = term.toLowerCase().trim();
    const filtrados = POS.catalog.filter(p => 
        p.nombre.toLowerCase().includes(t) || (p.codigo_barras && p.codigo_barras.includes(t))
    );
    renderCatalogo(filtrados);
}

function renderCatalogo(productos) {
    const grid = document.getElementById('products-catalog-grid');
    if (!grid) return;
    if (productos.length === 0) {
        grid.innerHTML = '<p class="text-muted" style="grid-column: 1/-1; text-align: center; padding: 30px;">No se encontraron productos coincidentes.</p>';
        return;
    }

    grid.innerHTML = '';
    productos.forEach(p => {
        const card = document.createElement('div');
        card.className = 'pos-prod-card';

        const badgePeso = p.tipo_venta === 'PESO' ? '<span class="prod-badge-peso">X PESO</span>' : '';
        const badgeStock = p.stock_bajo ? '<span class="prod-badge-stock-bajo">⚠ STOCK BAJO</span>' : '';

        card.innerHTML = `
            ${badgePeso}
            ${badgeStock}
            <div class="prod-card-name">${p.nombre}</div>
            <div class="prod-card-cat">${p.categoria}</div>
            <div class="prod-card-bottom">
                <div class="prod-card-price">${p.precio_venta_formateado}${p.tipo_venta === 'PESO' ? '<small style="font-size:0.7rem; color:var(--text-muted);">/kg</small>' : ''}</div>
                <div class="prod-card-stock">${p.stock_formateado}</div>
            </div>
        `;

        card.addEventListener('click', () => {
            agregarProductoAlCarrito(p);
        });

        grid.appendChild(card);
    });
}

function agregarProductoAlCarrito(producto) {
    // Si es pesable, abrir modal de pesaje
    if (producto.tipo_venta === 'PESO') {
        abrirModalPesable(producto);
        return;
    }

    // Si es por unidad
    const existing = POS.cart.find(item => item.producto_id === producto.id);
    const cantActual = existing ? existing.cantidad : 0;
    
    if (cantActual + 1 > producto.stock) {
        showToast(`Stock insuficiente. Solo quedan ${producto.stock} unidades de ${producto.nombre}`, 'warning');
        return;
    }

    if (existing) {
        existing.cantidad += 1;
        existing.subtotal_centavos = existing.cantidad * existing.precio_unitario_centavos;
    } else {
        POS.cart.push({
            producto_id: producto.id,
            nombre: producto.nombre,
            tipo_venta: 'UNIDAD',
            precio_unitario_centavos: producto.precio_venta_centavos,
            cantidad: 1,
            descuento_centavos: 0,
            subtotal_centavos: producto.precio_venta_centavos,
            stock_maximo: producto.stock
        });
    }

    renderCart();
}

function abrirModalPesable(producto) {
    POS.weighingProduct = producto;
    const modal = document.getElementById('modal-peso');
    document.getElementById('modal-peso-producto-nombre').textContent = producto.nombre;
    document.getElementById('modal-peso-precio-kg').textContent = `${producto.precio_venta_formateado} / kg`;
    
    const pesoInput = document.getElementById('modal-peso-input');
    pesoInput.value = '';
    document.getElementById('modal-peso-subtotal-calc').textContent = '$ 0,00';
    
    pesoInput.oninput = () => {
        const gramos = parsearPesoGramos(pesoInput.value);
        const subtotal = Math.floor((producto.precio_venta_centavos * gramos) / 1000);
        document.getElementById('modal-peso-subtotal-calc').textContent = formatearDinero(subtotal);
    };

    abrirModal('modal-peso');
    setTimeout(() => pesoInput.focus(), 100);
}

// Confirmar pesaje
document.getElementById('btn-confirmar-peso')?.addEventListener('click', () => {
    const prod = POS.weighingProduct;
    if (!prod) return;
    const pesoInput = document.getElementById('modal-peso-input');
    const gramos = parsearPesoGramos(pesoInput.value);

    if (gramos <= 0) {
        showToast('Ingrese un peso válido mayor a cero', 'warning');
        return;
    }

    if (gramos > prod.stock) {
        showToast(`Stock insuficiente. En balanza quedan ${formatearCantidad(prod.stock, 'PESO')}`, 'warning');
        return;
    }

    const subtotal = Math.floor((prod.precio_venta_centavos * gramos) / 1000);

    // Agregar o sumar al carrito
    const existing = POS.cart.find(it => it.producto_id === prod.id);
    if (existing) {
        existing.cantidad += gramos;
        existing.subtotal_centavos = Math.floor((existing.precio_unitario_centavos * existing.cantidad) / 1000);
    } else {
        POS.cart.push({
            producto_id: prod.id,
            nombre: prod.nombre,
            tipo_venta: 'PESO',
            precio_unitario_centavos: prod.precio_venta_centavos,
            cantidad: gramos,
            descuento_centavos: 0,
            subtotal_centavos: subtotal,
            stock_maximo: prod.stock
        });
    }

    cerrarModal('modal-peso');
    renderCart();
});

function renderCart() {
    const tbody = document.getElementById('cart-table-body');
    const cobrarBtn = document.getElementById('btn-abrir-cobro');
    if (!tbody) return;

    if (POS.cart.length === 0) {
        tbody.innerHTML = `
            <tr class="cart-empty-row">
                <td colspan="5">El carrito está vacío.<br><small>Selecciona o busca productos a la izquierda.</small></td>
            </tr>
        `;
        if (cobrarBtn) cobrarBtn.disabled = true;
        renderCartSummary();
        return;
    }

    if (cobrarBtn) cobrarBtn.disabled = false;
    tbody.innerHTML = '';

    POS.cart.forEach((it, index) => {
        const tr = document.createElement('tr');
        
        const cantDisplay = it.tipo_venta === 'PESO' 
            ? formatearCantidad(it.cantidad, 'PESO')
            : it.cantidad;

        tr.innerHTML = `
            <td>
                <strong>${it.nombre}</strong>
                ${it.tipo_venta === 'PESO' ? '<br><small class="text-muted">Por peso</small>' : ''}
            </td>
            <td>
                <div class="cart-qty-ctrl">
                    <button class="btn-qty btn-minus" data-idx="${index}">-</button>
                    <span>${cantDisplay}</span>
                    <button class="btn-qty btn-plus" data-idx="${index}">+</button>
                </div>
            </td>
            <td style="font-family:var(--font-mono);">${formatearDinero(it.precio_unitario_centavos)}</td>
            <td style="font-family:var(--font-mono); font-weight:700;">${formatearDinero(it.subtotal_centavos)}</td>
            <td>
                <button class="cart-delete-btn" data-idx="${index}" title="Quitar">✕</button>
            </td>
        `;

        // Handlers de botones de cantidad
        tr.querySelector('.btn-plus').addEventListener('click', () => {
            if (it.tipo_venta === 'PESO') {
                it.cantidad += 100; // sumar 100g
                it.subtotal_centavos = Math.floor((it.precio_unitario_centavos * it.cantidad) / 1000);
            } else {
                if (it.cantidad + 1 > it.stock_maximo) {
                    showToast('Se alcanzó el límite de stock disponible', 'warning');
                    return;
                }
                it.cantidad += 1;
                it.subtotal_centavos = it.cantidad * it.precio_unitario_centavos;
            }
            renderCart();
        });

        tr.querySelector('.btn-minus').addEventListener('click', () => {
            if (it.tipo_venta === 'PESO') {
                if (it.cantidad <= 100) {
                    POS.cart.splice(index, 1);
                } else {
                    it.cantidad -= 100;
                    it.subtotal_centavos = Math.floor((it.precio_unitario_centavos * it.cantidad) / 1000);
                }
            } else {
                if (it.cantidad <= 1) {
                    POS.cart.splice(index, 1);
                } else {
                    it.cantidad -= 1;
                    it.subtotal_centavos = it.cantidad * it.precio_unitario_centavos;
                }
            }
            renderCart();
        });

        tr.querySelector('.cart-delete-btn').addEventListener('click', () => {
            POS.cart.splice(index, 1);
            renderCart();
        });

        tbody.appendChild(tr);
    });

    renderCartSummary();
}

function renderCartSummary() {
    const subtotal = POS.cart.reduce((acc, it) => acc + it.subtotal_centavos, 0);
    const total = Math.max(0, subtotal - POS.discountCentavos);

    const subEl = document.getElementById('cart-subtotal');
    const totEl = document.getElementById('cart-total');
    if (subEl) subEl.textContent = formatearDinero(subtotal);
    if (totEl) totEl.textContent = formatearDinero(total);
}

// --------------------------------------------------------------------------- //
// PASARELA DE COBRO Y MODAL
// --------------------------------------------------------------------------- //
function abrirModalCobro() {
    if (POS.cart.length === 0) return;
    const subtotal = POS.cart.reduce((acc, it) => acc + it.subtotal_centavos, 0);
    const total = Math.max(0, subtotal - POS.discountCentavos);

    document.getElementById('cobro-total-display').textContent = formatearDinero(total);
    document.getElementById('cobro-items-count').textContent = `${POS.cart.length} artículos`;

    // Resetear campos
    const inputEf = document.getElementById('cobro-efectivo-recibido');
    inputEf.value = (total / 100).toFixed(2).replace('.', ',');
    calcularVuelto();

    // Resetear mixto
    document.getElementById('mixto-efectivo').value = '';
    document.getElementById('mixto-debito').value = '';
    document.getElementById('mixto-transferencia').value = '';
    document.getElementById('mixto-mp').value = '';
    document.getElementById('mixto-fiado').value = '';
    actualizarBalanceMixto();

    // Actualizar datos fiado
    actualizarVistaFiado();

    // Seleccionar tab Efectivo por defecto
    seleccionarMedioCobro('EFECTIVO');

    abrirModal('modal-cobro');
    setTimeout(() => inputEf.focus(), 100);
}

function initModals() {
    // Cerrar con data-modal
    document.querySelectorAll('.btn-close-modal, [data-modal]').forEach(btn => {
        btn.addEventListener('click', () => {
            const modalId = btn.dataset.modal;
            if (modalId) cerrarModal(modalId);
        });
    });

    // Pestañas de cobro
    document.querySelectorAll('#payment-tabs .pay-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            seleccionarMedioCobro(tab.dataset.medio);
        });
    });

    // Eventos Efectivo
    const efInput = document.getElementById('cobro-efectivo-recibido');
    if (efInput) {
        efInput.addEventListener('input', calcularVuelto);
    }

    // Eventos Pago Mixto
    document.querySelectorAll('.mixto-input').forEach(inp => {
        inp.addEventListener('input', actualizarBalanceMixto);
    });

    // Confirmar venta
    const btnConfirmar = document.getElementById('btn-confirmar-venta');
    if (btnConfirmar) {
        btnConfirmar.addEventListener('click', ejecutarConfirmacionVenta);
    }

    // Botón nueva venta desde ticket
    document.getElementById('btn-nuevo-ticket')?.addEventListener('click', () => {
        cerrarModal('modal-ticket');
        cambiarVista('ventas');
    });
}

function seleccionarMedioCobro(medio) {
    POS.selectedPaymentMethod = medio;
    document.querySelectorAll('#payment-tabs .pay-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.medio === medio);
    });

    document.getElementById('pay-panel-efectivo').classList.toggle('active', medio === 'EFECTIVO');
    document.getElementById('pay-panel-fiado').classList.toggle('active', medio === 'FIADO');
    document.getElementById('pay-panel-mixto').classList.toggle('active', medio === 'MIXTO');

    const warningBox = document.getElementById('cobro-validation-msg');
    if (warningBox) warningBox.style.display = 'none';
}

function calcularVuelto() {
    const subtotal = POS.cart.reduce((acc, it) => acc + it.subtotal_centavos, 0);
    const total = Math.max(0, subtotal - POS.discountCentavos);
    const recibido = aCentavos(document.getElementById('cobro-efectivo-recibido').value);
    const vuelto = Math.max(0, recibido - total);
    
    const vueltoEl = document.getElementById('cobro-vuelto-amount');
    if (vueltoEl) {
        vueltoEl.textContent = formatearDinero(vuelto);
        if (recibido < total) {
            vueltoEl.style.color = '#ef4444';
        } else {
            vueltoEl.style.color = '#4ade80';
        }
    }
}

function actualizarVistaFiado() {
    const cli = POS.clients.find(c => c.id === POS.selectedClientId);
    const nameEl = document.getElementById('fiado-cli-name');
    const saldoEl = document.getElementById('fiado-cli-saldo');
    const limiteEl = document.getElementById('fiado-cli-limite');
    const dispEl = document.getElementById('fiado-cli-disponible');
    const errAlert = document.getElementById('fiado-alert-error');

    if (!cli || cli.id <= 1) {
        nameEl.textContent = 'Consumidor Final (No admite fiado)';
        saldoEl.textContent = '-';
        limiteEl.textContent = '$ 0,00';
        dispEl.textContent = '$ 0,00';
        errAlert.textContent = 'Debe seleccionar un cliente registrado para vender a fiado.';
        errAlert.style.display = 'block';
        return;
    }

    nameEl.textContent = cli.nombre;
    saldoEl.textContent = cli.saldo_formateado;
    limiteEl.textContent = cli.limite_formateado;
    dispEl.textContent = cli.credito_disponible_formateado;

    const subtotal = POS.cart.reduce((acc, it) => acc + it.subtotal_centavos, 0);
    const total = Math.max(0, subtotal - POS.discountCentavos);

    if (total > cli.credito_disponible_centavos) {
        errAlert.textContent = `El total de la venta (${formatearDinero(total)}) supera el crédito disponible del cliente (${cli.credito_disponible_formateado}).`;
        errAlert.style.display = 'block';
    } else {
        errAlert.style.display = 'none';
    }
}

function actualizarBalanceMixto() {
    const subtotal = POS.cart.reduce((acc, it) => acc + it.subtotal_centavos, 0);
    const total = Math.max(0, subtotal - POS.discountCentavos);

    const ef = aCentavos(document.getElementById('mixto-efectivo').value);
    const deb = aCentavos(document.getElementById('mixto-debito').value);
    const trans = aCentavos(document.getElementById('mixto-transferencia').value);
    const mp = aCentavos(document.getElementById('mixto-mp').value);
    const fiado = aCentavos(document.getElementById('mixto-fiado').value);

    const suma = ef + deb + trans + mp + fiado;
    const diff = total - suma;

    document.getElementById('mixto-suma').textContent = formatearDinero(suma);
    const diffEl = document.getElementById('mixto-diferencia');
    diffEl.textContent = formatearDinero(diff);

    if (diff === 0) {
        diffEl.className = 'text-success';
    } else {
        diffEl.className = 'text-danger';
    }
}

async function ejecutarConfirmacionVenta() {
    const subtotal = POS.cart.reduce((acc, it) => acc + it.subtotal_centavos, 0);
    const total = Math.max(0, subtotal - POS.discountCentavos);
    const medio = POS.selectedPaymentMethod;

    let pagos = [];

    if (medio === 'EFECTIVO') {
        const recibido = aCentavos(document.getElementById('cobro-efectivo-recibido').value);
        if (recibido < total) {
            showToast('El efectivo recibido es insuficiente para cubrir la venta', 'error');
            return;
        }
        pagos = [{ medio: 'EFECTIVO', monto_centavos: total }];
    } else if (medio === 'FIADO') {
        if (POS.selectedClientId <= 1) {
            showToast('Debe seleccionar un cliente registrado para la venta a fiado', 'error');
            return;
        }
        const cli = POS.clients.find(c => c.id === POS.selectedClientId);
        if (!cli || total > cli.credito_disponible_centavos) {
            showToast('El cliente no tiene crédito disponible suficiente', 'error');
            return;
        }
        pagos = [{ medio: 'FIADO', monto_centavos: total }];
    } else if (medio === 'MIXTO') {
        const ef = aCentavos(document.getElementById('mixto-efectivo').value);
        const deb = aCentavos(document.getElementById('mixto-debito').value);
        const trans = aCentavos(document.getElementById('mixto-transferencia').value);
        const mp = aCentavos(document.getElementById('mixto-mp').value);
        const fiado = aCentavos(document.getElementById('mixto-fiado').value);

        if (ef > 0) pagos.push({ medio: 'EFECTIVO', monto_centavos: ef });
        if (deb > 0) pagos.push({ medio: 'DEBITO', monto_centavos: deb });
        if (trans > 0) pagos.push({ medio: 'TRANSFERENCIA', monto_centavos: trans });
        if (mp > 0) pagos.push({ medio: 'MERCADO_PAGO', monto_centavos: mp });
        if (fiado > 0) {
            if (POS.selectedClientId <= 1) {
                showToast('Debe seleccionar un cliente para la porción a fiado', 'error');
                return;
            }
            pagos.push({ medio: 'FIADO', monto_centavos: fiado });
        }

        const suma = pagos.reduce((acc, p) => acc + p.monto_centavos, 0);
        if (suma !== total) {
            showToast(`El total de los pagos (${formatearDinero(suma)}) no coincide con el total de la venta (${formatearDinero(total)})`, 'error');
            return;
        }
    } else {
        // Débito, Transferencia o Mercado Pago directo
        pagos = [{ medio: medio, monto_centavos: total }];
    }

    // Armar payload
    const payload = {
        items: POS.cart.map(it => ({
            producto_id: it.producto_id,
            cantidad: it.cantidad,
            descuento_centavos: it.descuento_centavos
        })),
        pagos: pagos,
        cliente_id: POS.selectedClientId,
        descuento_centavos: POS.discountCentavos
    };

    try {
        const res = await fetch('/api/ventas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Error al procesar la venta', 'error');
            return;
        }

        // Éxito: cerrar modal de cobro y mostrar ticket
        cerrarModal('modal-cobro');
        mostrarTicketExito(data, pagos);

        // Limpiar carrito y actualizar estado
        POS.cart = [];
        POS.discountCentavos = 0;
        document.getElementById('cart-discount-input').value = '0,00';
        renderCart();
        cargarEstadoGeneral();
        cargarCatalogo(); // para refrescar stocks en vivo
        cargarClientesSelector(); // refrescar deudas
        showToast(`✓ Venta #${data.venta_numero} registrada con éxito`, 'success');
    } catch (e) {
        showToast('Error de conexión con el servidor', 'error');
    }
}

function mostrarTicketExito(ventaData, pagos) {
    document.getElementById('ticket-numero').textContent = `Venta #${ventaData.venta_numero}`;
    document.getElementById('ticket-fecha').textContent = new Date().toLocaleString('es-AR');
    
    const cli = POS.clients.find(c => c.id === POS.selectedClientId);
    document.getElementById('ticket-cliente').textContent = cli ? cli.nombre : 'Consumidor final';
    document.getElementById('ticket-total').textContent = ventaData.total_formateado;

    // Medios de pago
    const mediosTxt = pagos.map(p => `${p.medio} (${formatearDinero(p.monto_centavos)})`).join(', ');
    document.getElementById('ticket-medios').textContent = mediosTxt;

    // Vuelto si hubo efectivo
    const vueltoRow = document.getElementById('ticket-vuelto-row');
    if (POS.selectedPaymentMethod === 'EFECTIVO') {
        const recibido = aCentavos(document.getElementById('cobro-efectivo-recibido').value);
        const vuelto = Math.max(0, recibido - ventaData.total_centavos);
        document.getElementById('ticket-vuelto').textContent = formatearDinero(vuelto);
        vueltoRow.style.display = 'flex';
    } else {
        vueltoRow.style.display = 'none';
    }

    // Lista de ítems
    const itemsList = document.getElementById('ticket-items');
    itemsList.innerHTML = POS.cart.map(it => `
        <div class="ticket-row">
            <span>${it.nombre} x ${formatearCantidad(it.cantidad, it.tipo_venta)}</span>
            <span>${formatearDinero(it.subtotal_centavos)}</span>
        </div>
    `).join('');

    abrirModal('modal-ticket');
}

// --------------------------------------------------------------------------- //
// MÓDULO 2: PRODUCTOS Y STOCK
// --------------------------------------------------------------------------- //
function initProductosEvents() {
    const filterText = document.getElementById('filter-prod-text');
    const filterCat = document.getElementById('filter-prod-cat');
    const filterStockBajo = document.getElementById('filter-prod-stock-bajo');

    if (filterText) filterText.addEventListener('input', cargarTablaProductos);
    if (filterCat) filterCat.addEventListener('change', cargarTablaProductos);
    if (filterStockBajo) filterStockBajo.addEventListener('change', cargarTablaProductos);

    document.getElementById('btn-confirmar-stock')?.addEventListener('click', guardarAjusteStock);
}

async function cargarTablaProductos() {
    const tbody = document.getElementById('table-productos-body');
    if (!tbody) return;

    const q = document.getElementById('filter-prod-text')?.value || '';
    const cat = document.getElementById('filter-prod-cat')?.value || '';
    const bajo = document.getElementById('filter-prod-stock-bajo')?.checked ? '1' : '';

    let url = `/api/productos?q=${encodeURIComponent(q)}&stock_bajo=${bajo}`;
    if (cat) url += `&cat=${cat}`;

    try {
        const res = await fetch(url);
        const prods = await res.json();
        document.getElementById('prod-total-count').textContent = `${prods.length} productos`;

        if (prods.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">No se encontraron productos.</td></tr>';
            return;
        }

        tbody.innerHTML = prods.map(p => `
            <tr>
                <td>${p.id}</td>
                <td><strong>${p.nombre}</strong></td>
                <td>${p.categoria}</td>
                <td><code>${p.codigo_barras || '-'}</code></td>
                <td>${p.tipo_venta === 'PESO' ? 'Por Peso (kg)' : 'Por Unidad'}</td>
                <td style="font-family:var(--font-mono); font-weight:700;">${p.precio_venta_formateado}</td>
                <td style="font-family:var(--font-mono); font-weight:700; ${p.stock_bajo ? 'color:var(--danger);' : ''}">${p.stock_formateado}</td>
                <td style="font-family:var(--font-mono);">${p.stock_minimo_formateado}</td>
                <td>
                    ${p.stock_bajo ? '<span class="badge-status warning">Stock Bajo</span>' : '<span class="badge-status success">Normal</span>'}
                </td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="abrirAjusteStock(${p.id}, '${p.nombre.replace(/'/g, "\\'")}', '${p.stock_formateado}')">
                        Ajustar Stock
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-danger">Error al cargar productos.</td></tr>';
    }
}

let activeAjusteProdId = null;
window.abrirAjusteStock = function(id, nombre, stockActual) {
    activeAjusteProdId = id;
    document.getElementById('modal-stock-prod-name').value = nombre;
    document.getElementById('modal-stock-actual').value = stockActual;
    document.getElementById('modal-stock-delta').value = '';
    document.getElementById('modal-stock-motivo').value = 'Ingreso de mercadería';
    abrirModal('modal-stock');
    setTimeout(() => document.getElementById('modal-stock-delta').focus(), 100);
};

async function guardarAjusteStock() {
    if (!activeAjusteProdId) return;
    const delta = parseInt(document.getElementById('modal-stock-delta').value, 10);
    const motivo = document.getElementById('modal-stock-motivo').value.trim();

    if (isNaN(delta) || delta === 0) {
        showToast('Ingrese una cantidad válida distinta de cero', 'warning');
        return;
    }

    try {
        const res = await fetch(`/api/productos/${activeAjusteProdId}/stock`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ delta, motivo, tipo: delta > 0 ? 'INGRESO' : 'AJUSTE' })
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Error al ajustar stock', 'error');
            return;
        }

        cerrarModal('modal-stock');
        showToast('Stock actualizado correctamente', 'success');
        cargarTablaProductos();
        cargarCatalogo();
    } catch (e) {
        showToast('Error de conexión', 'error');
    }
}

// --------------------------------------------------------------------------- //
// MÓDULO 3: CLIENTES Y FIADOS
// --------------------------------------------------------------------------- //
function initClientesEvents() {
    const filterText = document.getElementById('filter-cliente-text');
    if (filterText) filterText.addEventListener('input', cargarTablaClientes);

    document.getElementById('btn-cobrar-deuda')?.addEventListener('click', abrirModalCobroCliente);
    document.getElementById('btn-confirmar-cobro-cli')?.addEventListener('click', guardarCobroCliente);
}

async function cargarTablaClientes() {
    const tbody = document.getElementById('table-clientes-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/clientes');
        const clientes = await res.json();
        POS.clients = clientes;

        const term = document.getElementById('filter-cliente-text')?.value.toLowerCase().trim() || '';
        const filtrados = clientes.filter(c => c.nombre.toLowerCase().includes(term));

        if (filtrados.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No se encontraron clientes.</td></tr>';
            return;
        }

        tbody.innerHTML = filtrados.map(c => `
            <tr style="cursor:pointer;" onclick="seleccionarFichaCliente(${c.id})">
                <td><strong>${c.nombre}</strong></td>
                <td>${c.telefono}</td>
                <td style="font-family:var(--font-mono); font-weight:700; ${c.saldo_centavos > 0 ? 'color:var(--danger);' : ''}">${c.saldo_formateado}</td>
                <td style="font-family:var(--font-mono);">${c.limite_formateado}</td>
                <td style="font-family:var(--font-mono); color:var(--success); font-weight:600;">${c.credito_disponible_formateado}</td>
                <td><button class="btn btn-sm btn-secondary">Ver Ficha</button></td>
            </tr>
        `).join('');

        // Si hay cliente seleccionado, refrescar su detalle
        if (POS.activeClientDetailId) {
            seleccionarFichaCliente(POS.activeClientDetailId);
        } else if (clientes.length > 1) {
            seleccionarFichaCliente(2); // Seleccionar a Juan Pérez por defecto
        }
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-danger">Error al cargar clientes.</td></tr>';
    }
}

window.seleccionarFichaCliente = async function(clienteId) {
    POS.activeClientDetailId = clienteId;
    try {
        const res = await fetch(`/api/clientes/${clienteId}`);
        const c = await res.json();
        if (!c) return;

        document.getElementById('detail-cli-nombre').textContent = c.nombre;
        document.getElementById('detail-cli-tel').textContent = `Tel: ${c.telefono}`;
        document.getElementById('detail-cli-saldo').textContent = c.saldo_formateado;
        document.getElementById('detail-cli-limite').textContent = c.limite_formateado;
        document.getElementById('detail-cli-disponible').textContent = c.credito_disponible_formateado;

        const btnCobrar = document.getElementById('btn-cobrar-deuda');
        btnCobrar.disabled = (c.saldo_centavos <= 0);

        const tbody = document.getElementById('table-cli-movs-body');
        if (c.movimientos.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No hay movimientos en la cuenta.</td></tr>';
            return;
        }

        tbody.innerHTML = c.movimientos.map(m => `
            <tr>
                <td>${m.fecha.split(' ')[0]}</td>
                <td><span class="badge-status ${m.tipo === 'FIADO' ? 'danger' : 'success'}">${m.tipo}</span></td>
                <td style="font-family:var(--font-mono); font-weight:700;">${m.tipo === 'FIADO' ? '+' : '-'}${m.monto_formateado}</td>
                <td style="font-family:var(--font-mono);">${m.saldo_resultante_formateado}</td>
                <td>${m.descripcion}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Error al cargar detalle cliente:', e);
    }
};

function abrirModalCobroCliente() {
    const cli = POS.clients.find(c => c.id === POS.activeClientDetailId);
    if (!cli) return;

    document.getElementById('cobro-cli-nombre').value = cli.nombre;
    document.getElementById('cobro-cli-deuda-actual').value = cli.saldo_formateado;
    const montoInput = document.getElementById('cobro-cli-monto');
    montoInput.value = (cli.saldo_centavos / 100).toFixed(2).replace('.', ',');
    abrirModal('modal-cobro-cliente');
    setTimeout(() => montoInput.focus(), 100);
}

async function guardarCobroCliente() {
    const cliId = POS.activeClientDetailId;
    if (!cliId) return;

    const montoCentavos = aCentavos(document.getElementById('cobro-cli-monto').value);
    const medio = document.getElementById('cobro-cli-medio').value;

    if (montoCentavos <= 0) {
        showToast('El monto a cobrar debe ser mayor a cero', 'warning');
        return;
    }

    try {
        const res = await fetch(`/api/clientes/${cliId}/cobrar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ monto_centavos: montoCentavos, medio })
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Error al registrar cobro', 'error');
            return;
        }

        cerrarModal('modal-cobro-cliente');
        showToast(`✓ Cobro de ${data.monto_cobrado_formateado} registrado correctamente`, 'success');
        cargarTablaClientes();
        cargarEstadoGeneral();
    } catch (e) {
        showToast('Error de conexión', 'error');
    }
}

// --------------------------------------------------------------------------- //
// MÓDULO 4: CAJA DIARIA
// --------------------------------------------------------------------------- //
function initCajaEvents() {
    document.getElementById('btn-caja-ingreso')?.addEventListener('click', () => abrirModalMovCaja('INGRESO', '+ Registrar Ingreso a Caja'));
    document.getElementById('btn-caja-retiro')?.addEventListener('click', () => abrirModalMovCaja('RETIRO', '- Registrar Retiro de Caja'));
    document.getElementById('btn-caja-gasto')?.addEventListener('click', () => abrirModalMovCaja('GASTO', '- Registrar Gasto de Caja'));
    document.getElementById('btn-caja-arqueo')?.addEventListener('click', abrirModalArqueoCierre);
    document.getElementById('btn-caja-cerrar')?.addEventListener('click', abrirModalArqueoCierre);
    document.getElementById('btn-confirmar-mov-caja')?.addEventListener('click', guardarMovCaja);
    document.getElementById('btn-confirmar-cierre-caja')?.addEventListener('click', ejecutarCierreCaja);
}

async function cargarDatosCaja() {
    try {
        const res = await fetch('/api/caja');
        const data = await res.json();

        const pill = document.getElementById('caja-status-pill');
        const btnAbrir = document.getElementById('btn-caja-abrir');
        const btnCerrar = document.getElementById('btn-caja-cerrar');

        if (!data.abierta) {
            pill.className = 'caja-status-pill closed';
            pill.textContent = '🔴 CAJA CERRADA';
            btnAbrir.style.display = 'inline-flex';
            btnCerrar.style.display = 'none';
            document.getElementById('caja-stat-inicial').textContent = '$ 0,00';
            document.getElementById('caja-stat-ventas').textContent = '$ 0,00';
            document.getElementById('caja-stat-esperado').textContent = '$ 0,00';
            return;
        }

        pill.className = 'caja-status-pill open';
        pill.textContent = '🟢 CAJA ABIERTA';
        btnAbrir.style.display = 'none';
        btnCerrar.style.display = 'inline-flex';

        document.getElementById('caja-fecha-apertura').textContent = `Abierta: ${data.abierta_en}`;
        document.getElementById('caja-stat-inicial').textContent = data.monto_inicial_formateado;
        document.getElementById('caja-stat-ventas').textContent = data.total_ventas_todas;
        document.getElementById('caja-stat-ingresos').textContent = data.ingresos_manuales;
        document.getElementById('caja-stat-gastos').textContent = data.gastos_manuales;
        document.getElementById('caja-stat-retiros').textContent = data.retiros_manuales;
        document.getElementById('caja-stat-esperado').textContent = data.efectivo_esperado_formateado;

        // Movimientos
        const tbody = document.getElementById('table-caja-movs-body');
        if (data.movimientos.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No hay movimientos en la jornada.</td></tr>';
            return;
        }

        tbody.innerHTML = data.movimientos.map(m => `
            <tr>
                <td>${m.fecha.split(' ')[1] || m.fecha}</td>
                <td><span class="badge-status ${m.monto_centavos > 0 ? 'success' : 'danger'}">${m.tipo}</span></td>
                <td>${m.medio_etiqueta}</td>
                <td style="font-family:var(--font-mono); font-weight:700; ${m.monto_centavos > 0 ? 'color:var(--success);' : 'color:var(--danger);'}">${m.monto_formateado}</td>
                <td>${m.motivo}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Error cargando caja:', e);
    }
}

function abrirModalMovCaja(tipo, titulo) {
    document.getElementById('modal-mov-caja-tipo').value = tipo;
    document.getElementById('modal-mov-caja-title').textContent = titulo;
    document.getElementById('modal-mov-caja-monto').value = '';
    document.getElementById('modal-mov-caja-motivo').value = '';
    abrirModal('modal-mov-caja');
    setTimeout(() => document.getElementById('modal-mov-caja-monto').focus(), 100);
}

async function guardarMovCaja() {
    const tipo = document.getElementById('modal-mov-caja-tipo').value;
    const monto = aCentavos(document.getElementById('modal-mov-caja-monto').value);
    const motivo = document.getElementById('modal-mov-caja-motivo').value.trim();

    if (monto <= 0) {
        showToast('Ingrese un importe mayor a cero', 'warning');
        return;
    }
    if (!motivo) {
        showToast('Ingrese el motivo del movimiento', 'warning');
        return;
    }

    try {
        const res = await fetch('/api/caja/movimiento', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tipo, monto_centavos: monto, motivo, medio: 'EFECTIVO' })
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Error al asentar movimiento', 'error');
            return;
        }

        cerrarModal('modal-mov-caja');
        showToast(`✓ ${tipo} por ${data.monto_formateado} registrado en caja`, 'success');
        cargarDatosCaja();
        cargarEstadoGeneral();
    } catch (e) {
        showToast('Error de conexión', 'error');
    }
}

function abrirModalArqueoCierre() {
    fetch('/api/caja').then(r => r.json()).then(data => {
        if (!data.abierta) {
            showToast('La caja se encuentra cerrada', 'warning');
            return;
        }
        document.getElementById('arqueo-esperado').textContent = data.efectivo_esperado_formateado;
        const contadoInput = document.getElementById('arqueo-contado-input');
        contadoInput.value = (data.efectivo_esperado_centavos / 100).toFixed(2).replace('.', ',');

        const diffBox = document.getElementById('arqueo-diff-box');
        const diffVal = document.getElementById('arqueo-diff-val');
        const diffStatus = document.getElementById('arqueo-diff-desc');

        function actualizarDiferencia() {
            const contado = aCentavos(contadoInput.value);
            const diff = contado - data.efectivo_esperado_centavos;
            diffVal.textContent = formatearDinero(diff);

            if (diff === 0) {
                diffBox.className = 'arqueo-diff-box cuadrada';
                diffStatus.textContent = '✓ Caja Cuadrada (Exacta)';
            } else if (diff > 0) {
                diffBox.className = 'arqueo-diff-box sobrante';
                diffStatus.textContent = '⚡ Sobrante de Efectivo';
            } else {
                diffBox.className = 'arqueo-diff-box faltante';
                diffStatus.textContent = '⚠ Faltante de Efectivo';
            }
        }

        contadoInput.oninput = actualizarDiferencia;
        actualizarDiferencia();

        abrirModal('modal-cierre-caja');
    });
}

async function ejecutarCierreCaja() {
    const contado = aCentavos(document.getElementById('arqueo-contado-input').value);
    const obs = document.getElementById('arqueo-obs').value.trim();

    if (!confirm('¿Confirma el cierre definitivo de la jornada de caja?')) return;

    try {
        const res = await fetch('/api/caja/cerrar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ contado_efectivo_centavos: contado, observaciones: obs })
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Error al cerrar caja', 'error');
            return;
        }

        cerrarModal('modal-cierre-caja');
        showToast('✓ Caja cerrada correctamente', 'success');
        cargarDatosCaja();
        cargarEstadoGeneral();
    } catch (e) {
        showToast('Error de conexión', 'error');
    }
}

// --------------------------------------------------------------------------- //
// MÓDULO 5: REPORTES, RANKINGS Y ANULACIÓN
// --------------------------------------------------------------------------- //
function initReportesEvents() {
    document.querySelectorAll('#periodo-tabs .period-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#periodo-tabs .period-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            POS.activeReportPeriod = tab.dataset.period;
            cargarReportes();
        });
    });

    document.getElementById('btn-confirmar-anulacion')?.addEventListener('click', ejecutarAnulacionVenta);
}

async function cargarReportes() {
    try {
        const res = await fetch(`/api/reportes?periodo=${POS.activeReportPeriod}`);
        const data = await res.json();

        document.getElementById('rep-kpi-total').textContent = data.total_ventas_formateado;
        document.getElementById('rep-kpi-cant').textContent = data.cantidad_ventas;
        document.getElementById('rep-kpi-promedio').textContent = data.ticket_promedio_formateado;
        document.getElementById('rep-kpi-articulos').textContent = `${data.total_despachado} despachados`;

        // Barras de medios de pago
        const mediosContainer = document.getElementById('rep-medios-list');
        if (data.ventas_por_medio.length === 0) {
            mediosContainer.innerHTML = '<p class="text-muted text-center" style="padding:20px;">Sin transacciones en este período.</p>';
        } else {
            mediosContainer.innerHTML = data.ventas_por_medio.map(m => `
                <div class="bar-item-row">
                    <div class="bar-header">
                        <span>${m.medio_etiqueta} (${m.transacciones} op.)</span>
                        <span style="font-family:var(--font-mono);">${m.total_formateado} (${m.porcentaje}%)</span>
                    </div>
                    <div class="bar-track">
                        <div class="bar-fill" style="width: ${m.porcentaje}%;"></div>
                    </div>
                </div>
            `).join('');
        }

        // Top 5 productos
        const topTbody = document.getElementById('table-rep-top-body');
        if (data.top_productos.length === 0) {
            topTbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">Sin datos.</td></tr>';
        } else {
            topTbody.innerHTML = data.top_productos.map(tp => `
                <tr>
                    <td><strong>${tp.descripcion}</strong></td>
                    <td>${tp.cantidad_formateada}</td>
                    <td style="font-family:var(--font-mono); font-weight:700;">${tp.total_formateado}</td>
                </tr>
            `).join('');
        }

        // Cargar tabla de ventas para anulación
        cargarTablaVentasReportes();
    } catch (e) {
        console.error('Error cargando reportes:', e);
    }
}

async function cargarTablaVentasReportes() {
    const tbody = document.getElementById('table-rep-ventas-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/ventas?limite=30');
        const ventas = await res.json();

        if (ventas.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No se registran ventas.</td></tr>';
            return;
        }

        tbody.innerHTML = ventas.map(v => `
            <tr>
                <td><strong>#${v.numero}</strong></td>
                <td>${v.fecha}</td>
                <td>${v.cliente}</td>
                <td style="font-family:var(--font-mono); font-weight:700;">${v.total_formateado}</td>
                <td><small>${v.medios_pago}</small></td>
                <td>
                    <span class="badge-status ${v.es_anulada ? 'danger' : 'success'}">${v.estado}</span>
                    ${v.motivo_anulacion ? `<br><small class="text-muted">${v.motivo_anulacion}</small>` : ''}
                </td>
                <td>
                    ${!v.es_anulada ? `
                        <button class="btn btn-sm btn-outline-danger" onclick="abrirModalAnularVenta(${v.id}, '${v.numero}')">
                            Anular
                        </button>
                    ` : '<span class="text-muted" style="font-size:0.75rem;">Anulada</span>'}
                </td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-danger">Error cargando ventas.</td></tr>';
    }
}

window.abrirModalAnularVenta = function(ventaId, ventaNumero) {
    POS.pendingAnulacionId = ventaId;
    document.getElementById('anular-venta-numero').textContent = `Venta #${ventaNumero}`;
    document.getElementById('anular-venta-motivo').value = '';
    abrirModal('modal-anular-venta');
    setTimeout(() => document.getElementById('anular-venta-motivo').focus(), 100);
};

async function ejecutarAnulacionVenta() {
    if (!POS.pendingAnulacionId) return;
    const motivo = document.getElementById('anular-venta-motivo').value.trim();

    if (!motivo) {
        showToast('Debe ingresar el motivo de anulación obligatorio', 'warning');
        return;
    }

    try {
        const res = await fetch(`/api/ventas/${POS.pendingAnulacionId}/anular`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motivo })
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Error al anular venta', 'error');
            return;
        }

        cerrarModal('modal-anular-venta');
        showToast('✓ Venta anulada y existencias devueltas correctamente', 'success');
        cargarReportes();
        cargarEstadoGeneral();
        cargarCatalogo();
    } catch (e) {
        showToast('Error de conexión', 'error');
    }
}

// --------------------------------------------------------------------------- //
// Helpers de Modales
// --------------------------------------------------------------------------- //
function abrirModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('open');
}

function cerrarModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('open');
}

function cerrarTodosModales() {
    document.querySelectorAll('.pos-modal').forEach(m => m.classList.remove('open'));
}
