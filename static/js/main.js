// ========================================
// Smart Trolley - Main JavaScript
// Clean, robust, production-quality frontend controller
// ========================================

document.addEventListener('DOMContentLoaded', function() {
    // Initialize shared components
    initSidebar();
    initFlashMessages();

    // Page-specific initialization
    if (document.getElementById('dashboard-page') || document.getElementById('recent-scans') || document.getElementById('total-products')) {
        initDashboard();
    }
    if (document.getElementById('cart-page') || document.getElementById('cart-items') || document.getElementById('checkout-btn')) {
        initCart();
    }
});

// ==========================================================================
// 1. Sidebar & Mobile Navigation
// ==========================================================================

function initSidebar() {
    const toggleBtn = document.getElementById('menu-toggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (toggleBtn && sidebar && overlay) {
        toggleBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            sidebar.classList.toggle('active');
            overlay.classList.toggle('active');
        });

        overlay.addEventListener('click', function() {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
        });
    }

    // Auto-close mobile sidebar when resizing to desktop viewport
    window.addEventListener('resize', function() {
        if (window.innerWidth > 768) {
            if (sidebar) sidebar.classList.remove('active');
            if (overlay) overlay.classList.remove('active');
        }
    });
}

// ==========================================================================
// 2. Flash Messages
// ==========================================================================

function initFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash-msg');
    flashMessages.forEach(function(msg) {
        // Auto-hide flash messages after 5 seconds
        const timer = setTimeout(function() {
            dismissFlash(msg);
        }, 5000);

        // Click to dismiss immediately
        msg.addEventListener('click', function(e) {
            clearTimeout(timer);
            dismissFlash(msg);
        });

        const closeBtn = msg.querySelector('.flash-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                clearTimeout(timer);
                dismissFlash(msg);
            });
        }
    });
}

function dismissFlash(el) {
    if (!el) return;
    el.style.opacity = '0';
    el.style.transform = 'translateY(-10px)';
    el.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
    setTimeout(function() {
        if (el && el.parentElement) {
            el.remove();
        }
    }, 400);
}

// ==========================================================================
// 3. Modal Helpers
// ==========================================================================

function showModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove('hidden');
    }
}

function hideModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.add('hidden');
    }
}

// Global click-outside listener for all modals
document.addEventListener('click', function(e) {
    if (e.target && e.target.classList.contains('modal-overlay')) {
        e.target.classList.add('hidden');
    }
});

// ==========================================================================
// 4. Toast Notifications
// ==========================================================================

function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.querySelector('.toast-container');
    }
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';

    let icon = '<i class="bi bi-info-circle-fill" style="color: var(--info);"></i>';
    let borderColor = 'var(--info)';

    if (type === 'success') {
        icon = '<i class="bi bi-check-circle-fill" style="color: var(--success);"></i>';
        borderColor = 'var(--success)';
    } else if (type === 'error' || type === 'danger') {
        icon = '<i class="bi bi-x-circle-fill" style="color: var(--danger);"></i>';
        borderColor = 'var(--danger)';
    } else if (type === 'warning') {
        icon = '<i class="bi bi-exclamation-triangle-fill" style="color: var(--warning);"></i>';
        borderColor = 'var(--warning)';
    }

    toast.style.borderLeftColor = borderColor;
    toast.innerHTML = `
        <span style="font-size: 1.2rem; line-height: 1;">${icon}</span>
        <span style="flex: 1;">${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    // Auto-remove after 4 seconds with fade-out animation
    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(15px)';
        toast.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
        setTimeout(function() {
            toast.remove();
        }, 400);
    }, 4000);
}

// ==========================================================================
// 5. Utilities
// ==========================================================================

function formatCurrency(amount) {
    const val = parseFloat(amount || 0);
    return isNaN(val) ? '0.00' : val.toFixed(2);
}

function formatTime(timestamp) {
    if (!timestamp) return 'Just now';
    if (typeof timestamp === 'string' && (timestamp.includes(':') || timestamp.toLowerCase().includes('ago') || timestamp.toLowerCase().includes('just'))) {
        return timestamp;
    }
    const d = new Date(timestamp);
    if (isNaN(d.getTime())) return String(timestamp);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[&<>"']/g, function(m) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m];
    });
}

async function fetchJSON(url, options = {}) {
    try {
        const defaultHeaders = {
            'Accept': 'application/json'
        };

        if (options.body && typeof options.body === 'string') {
            defaultHeaders['Content-Type'] = 'application/json';
        }

        const mergedOptions = {
            ...options,
            headers: {
                ...defaultHeaders,
                ...(options.headers || {})
            }
        };

        const response = await fetch(url, mergedOptions);
        const data = await response.json();

        if (!response.ok) {
            const errorMsg = (data && (data.message || data.error)) || `HTTP ${response.status}: Request failed`;
            throw new Error(errorMsg);
        }

        return data;
    } catch (err) {
        console.error(`fetchJSON error at [${url}]:`, err);
        throw err;
    }
}

// ==========================================================================
// 6. Dashboard Controller
// ==========================================================================

let dashboardIntervalId = null;

function initDashboard() {
    // Initial fetch
    fetchDashboardData();

    // Clear any existing polling interval to avoid duplicates
    if (dashboardIntervalId) {
        clearInterval(dashboardIntervalId);
    }

    // Start polling every 2 seconds
    dashboardIntervalId = setInterval(fetchDashboardData, 2000);

    // Initialize demo controls
    initDemoControls();
}

async function fetchDashboardData() {
    try {
        const data = await fetchJSON('/api/dashboard-data');
        updateDashboardCards(data);

        if (data.recent_scans !== undefined) {
            updateRecentScans(data.recent_scans);
        }

        if (data.weight_status !== undefined) {
            updateWeightStatus(data.weight_status);
        }
    } catch (err) {
        console.warn('Dashboard poll warning:', err.message);
    }
}

function updateDashboardCards(data) {
    if (!data) return;

    // Total Products
    const prodEl = document.getElementById('total-products');
    if (prodEl && data.total_products !== undefined) {
        prodEl.textContent = data.total_products;
    }

    // Total Weight
    const weightEl = document.getElementById('total-weight');
    if (weightEl && data.total_weight !== undefined) {
        const rawWeight = data.total_weight;
        weightEl.textContent = String(rawWeight).endsWith('g') ? rawWeight : `${rawWeight}g`;
    }

    // Current Bill
    const billEl = document.getElementById('current-bill');
    if (billEl && data.current_bill !== undefined) {
        billEl.textContent = formatCurrency(data.current_bill);
    }

    // Trolley Status: green dot for connected, red for disconnected
    const trolleyStatusEl = document.getElementById('trolley-status');
    if (trolleyStatusEl && data.trolley_status !== undefined) {
        const isConnected = data.trolley_status === true || 
                            data.trolley_status === 'connected' || 
                            data.trolley_status === 'Connected';

        trolleyStatusEl.innerHTML = isConnected
            ? '<span class="status-dot status-connected"></span> Connected'
            : '<span class="status-dot status-disconnected"></span> Disconnected';
    }
}

function updateRecentScans(scans) {
    const tbody = document.getElementById('recent-scans');
    if (!tbody) return;

    if (!Array.isArray(scans) || scans.length === 0) {
        tbody.innerHTML = `
            <tr id="empty-scans-row">
                <td colspan="4" class="empty-table-message">No products scanned yet</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = scans.map(item => {
        const name = item.name || item.product_name || 'Unknown Item';
        const price = formatCurrency(item.price || item.unit_price || 0);
        const rfid = item.rfid_uid || '-';
        const time = formatTime(item.time || item.timestamp || item.scanned_at);

        return `
            <tr>
                <td><strong>${escapeHtml(name)}</strong></td>
                <td>₹${price}</td>
                <td><code>${escapeHtml(rfid)}</code></td>
                <td style="color: var(--text-light);">${escapeHtml(time)}</td>
            </tr>
        `;
    }).join('');
}

function updateWeightStatus(weightData) {
    const card = document.getElementById('weight-status-card');
    const badge = document.getElementById('weight-badge');
    const expEl = document.getElementById('expected-weight');
    const measEl = document.getElementById('measured-weight');
    const diffEl = document.getElementById('weight-diff');
    const msgEl = document.getElementById('weight-message');

    if (!card || !weightData) return;

    const expected = parseFloat(weightData.expected || 0);
    const measured = parseFloat(weightData.measured || 0);
    const diff = Math.abs(measured - expected);
    const status = (weightData.status || 'waiting').toLowerCase();

    if (expEl) expEl.textContent = `${expected}g`;
    if (measEl) measEl.textContent = `${measured}g`;
    if (diffEl) diffEl.textContent = `${diff}g`;

    card.className = 'weight-status';

    if (status === 'verified') {
        card.classList.add('weight-verified');
        if (badge) {
            badge.className = 'badge badge-success';
            badge.textContent = 'Verified';
        }
        if (msgEl) {
            msgEl.textContent = weightData.message || 'Weight match verified! Cart contents match RFID scans.';
        }
    } else if (status === 'mismatch') {
        card.classList.add('weight-mismatch');
        if (badge) {
            badge.className = 'badge badge-danger';
            badge.textContent = 'Mismatch';
        }
        if (msgEl) {
            msgEl.textContent = weightData.message || 'Warning: Weight discrepancy detected between scanned items and scale!';
        }
    } else {
        card.classList.add('weight-waiting');
        if (badge) {
            badge.className = 'badge badge-warning';
            badge.textContent = 'Waiting';
        }
        if (msgEl) {
            msgEl.textContent = weightData.message || 'Scale is ready. Place scanned items into the cart to verify weight.';
        }
    }
}

// Demo Controls handling
function initDemoControls() {
    const scanBtn = document.getElementById('demo-scan-btn');
    if (scanBtn) {
        scanBtn.onclick = function() { demoScan(); };
    }

    const weightBtn = document.getElementById('demo-weight-btn');
    if (weightBtn) {
        weightBtn.onclick = function() { demoWeight(); };
    }
}

async function demoScan() {
    const select = document.getElementById('demo-product-select');
    if (!select) return;

    const rfidUid = select.value;
    if (!rfidUid) {
        showToast('Please select a product to scan from the dropdown', 'warning');
        return;
    }

    const selectedOption = select.options[select.selectedIndex];
    const itemWeight = selectedOption.getAttribute('data-weight');

    try {
        const data = await fetchJSON('/api/demo/scan', {
            method: 'POST',
            body: JSON.stringify({ rfid_uid: rfidUid })
        });

        showToast(data.message || 'Product scanned successfully!', 'success');

        // Convenience: auto-fill simulated weight input if present
        const weightInput = document.getElementById('demo-weight-input');
        if (weightInput && itemWeight) {
            weightInput.value = itemWeight;
        }

        // Immediately refresh dashboard metrics
        fetchDashboardData();
    } catch (err) {
        showToast(err.message || 'Failed to simulate product scan', 'error');
    }
}

async function demoWeight() {
    const input = document.getElementById('demo-weight-input');
    if (!input || input.value === '') {
        showToast('Please enter a weight value in grams', 'warning');
        return;
    }

    const weightVal = parseFloat(input.value);
    if (isNaN(weightVal) || weightVal < 0) {
        showToast('Please enter a valid non-negative weight value', 'warning');
        return;
    }

    try {
        // Send both {value: weight} and {weight: weight} for maximum backend compatibility
        const data = await fetchJSON('/api/demo/weight', {
            method: 'POST',
            body: JSON.stringify({ value: weightVal, weight: weightVal })
        });

        showToast(data.message || `Weight reading updated: ${weightVal}g`, 'success');

        // Immediately refresh dashboard metrics
        fetchDashboardData();
    } catch (err) {
        showToast(err.message || 'Failed to update simulated weight', 'error');
    }
}

// Aliases for inline template handlers
window.triggerDemoScan = demoScan;
window.triggerDemoWeight = demoWeight;
window.demoScan = demoScan;
window.demoWeight = demoWeight;
window.fetchDashboardData = fetchDashboardData;

// ==========================================================================
// 7. Cart & Checkout Controller
// ==========================================================================

let currentCartTotal = 0;
let currentItemCount = 0;
let cartIntervalId = null;

function initCart() {
    // Initial load
    loadCart();

    // Refresh every 3 seconds to stay synced with trolley scans
    if (cartIntervalId) {
        clearInterval(cartIntervalId);
    }
    cartIntervalId = setInterval(loadCart, 3000);
}

async function loadCart() {
    try {
        const data = await fetchJSON('/api/cart');
        const items = data.items || data.cart_items || [];
        currentCartTotal = parseFloat(data.total || data.total_amount || 0);
        currentItemCount = items.reduce((acc, item) => acc + (parseInt(item.quantity || 1, 10)), 0);

        // Update total display
        const totalEl = document.getElementById('cart-total');
        if (totalEl) {
            totalEl.textContent = formatCurrency(currentCartTotal);
        }

        // Update item count badges
        const badgeEl = document.getElementById('cart-item-count');
        if (badgeEl) {
            badgeEl.textContent = `${currentItemCount} ${currentItemCount === 1 ? 'item' : 'items'}`;
        }

        const badgeTopEl = document.getElementById('cart-item-badge-top');
        if (badgeTopEl) {
            badgeTopEl.textContent = `${currentItemCount} ${currentItemCount === 1 ? 'item' : 'items'}`;
        }

        // Show/hide/disable checkout button based on items
        const checkoutBtn = document.getElementById('checkout-btn');
        if (checkoutBtn) {
            checkoutBtn.disabled = (currentItemCount === 0);
        }

        renderCartItems(items);
    } catch (err) {
        console.warn('Cart load warning:', err.message);
    }
}

function renderCartItems(items) {
    const tbody = document.getElementById('cart-items');
    if (!tbody) return;

    if (!Array.isArray(items) || items.length === 0) {
        tbody.innerHTML = `
            <tr id="empty-cart-row">
                <td colspan="6" class="empty-table-message">
                    Your cart is empty. Scan products to add them to your trolley.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = items.map((item, index) => {
        const name = item.name || item.product_name || 'Product';
        const price = parseFloat(item.price || item.unit_price || 0);
        const qty = parseInt(item.quantity || 1, 10);
        const subtotal = parseFloat(item.subtotal || (price * qty));
        const pid = item.product_id || item.id || '';
        const uid = item.rfid_uid || '';

        return `
            <tr>
                <td><strong>${index + 1}</strong></td>
                <td>
                    <div style="font-weight: 600; color: var(--text);">${escapeHtml(name)}</div>
                    ${item.weight ? `<small style="color: var(--text-light);">${item.weight}g per unit</small>` : ''}
                </td>
                <td>₹${formatCurrency(price)}</td>
                <td style="text-align: center;">
                    <span class="badge badge-info" style="font-size: 0.9rem; padding: 4px 10px;">${qty}</span>
                </td>
                <td><strong>₹${formatCurrency(subtotal)}</strong></td>
                <td style="text-align: center;">
                    <button 
                        type="button" 
                        class="btn btn-danger btn-sm" 
                        onclick="removeItem('${escapeHtml(String(pid))}', '${escapeHtml(uid)}')" 
                        title="Remove product"
                    >
                        <i class="bi bi-trash"></i> Remove
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

async function removeItem(productIdOrRfid, optionalRfid) {
    if (!confirm('Are you sure you want to remove this item from your cart?')) {
        return;
    }

    let productId = productIdOrRfid;
    let rfidUid = optionalRfid;

    // Handle argument flipping if called as (rfid, productId)
    if (optionalRfid && !isNaN(optionalRfid) && isNaN(productIdOrRfid)) {
        productId = optionalRfid;
        rfidUid = productIdOrRfid;
    }

    try {
        const payload = { product_id: productId };
        if (rfidUid) {
            payload.rfid_uid = rfidUid;
        }

        const data = await fetchJSON('/api/cart/remove', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        showToast(data.message || 'Item removed from cart', 'success');
        loadCart();
    } catch (err) {
        showToast(err.message || 'Failed to remove item from cart', 'error');
    }
}

let _checkoutInProgress = false;

async function processCheckout() {
    if (_checkoutInProgress) return;
    _checkoutInProgress = true;

    const payBtn = document.getElementById('pay-btn');
    const cancelBtn = document.getElementById('cancel-pay-btn');
    if (payBtn) {
        payBtn.disabled = true;
        payBtn.textContent = 'Processing Payment...';
    }
    if (cancelBtn) {
        cancelBtn.disabled = true;
    }

    try {
        const data = await fetchJSON('/api/checkout', {
            method: 'POST',
            body: JSON.stringify({ payment_method: 'Cash' })
        });

        hideModal('payment-modal');

        const successTxEl = document.getElementById('success-tx-id');
        if (successTxEl) {
            const txId = data.transaction_id || data.id || ('#' + Math.floor(100000 + Math.random() * 900000));
            successTxEl.textContent = typeof txId === 'string' && txId.startsWith('#') ? txId : `#${txId}`;
        }

        const emailMsgEl = document.getElementById('success-email-msg');
        if (emailMsgEl) {
            if (data.email_sent) {
                emailMsgEl.textContent = 'A detailed receipt has been sent to your registered email address.';
            } else {
                emailMsgEl.textContent = 'Bill generated successfully. (Configure SMTP in config.py for live email dispatch)';
            }
        }

        showModal('success-modal');
        showToast('Payment completed successfully!', 'success');

        // Refresh cart
        loadCart();
    } catch (err) {
        showToast(err.message || 'Payment processing failed. Please try again.', 'error');
        _checkoutInProgress = false;
    } finally {
        if (payBtn) {
            payBtn.disabled = false;
            payBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Pay with Cash';
        }
        if (cancelBtn) {
            cancelBtn.disabled = false;
        }
    }
}

// Aliases for global inline triggers
window.loadCart = loadCart;
window.fetchCartData = loadCart;
window.removeItem = removeItem;
window.openPaymentModal = function() {
    if (currentItemCount === 0 || currentCartTotal <= 0) {
        showToast('Your cart is empty. Scan products before checking out.', 'warning');
        return;
    }
    const modalAmountEl = document.getElementById('modal-pay-amount');
    if (modalAmountEl) {
        modalAmountEl.textContent = formatCurrency(currentCartTotal);
    }
    showModal('payment-modal');
};
window.closePaymentModal = function() { hideModal('payment-modal'); };
window.processCheckout = processCheckout;
window.showModal = showModal;
window.hideModal = hideModal;
window.showToast = showToast;
