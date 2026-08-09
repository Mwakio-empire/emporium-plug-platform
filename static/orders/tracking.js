(() => {
    'use strict';
    const root = document.getElementById('order-tracking');
    if (!root) return;
    const orderNumber = root.dataset.orderNumber;
    const tokenKey = `emporium-order-token:${orderNumber}`;
    let token = window.location.hash.slice(1);
    if (token) {
        try { window.sessionStorage.setItem(tokenKey, token); } catch (error) { /* Session storage may be unavailable. */ }
        history.replaceState(null, '', window.location.pathname);
    } else {
        try { token = window.sessionStorage.getItem(tokenKey) || ''; } catch (error) { token = ''; }
    }

    const headers = token ? {'X-Guest-Order-Token': token} : {};
    const labels = {
        PENDING: 'Awaiting M-Pesa payment', PAYMENT_CONFIRMED: 'Payment confirmed',
        PROCESSING: 'Order received', PACKING: 'Packing your order', PACKED: 'Packed',
        READY_FOR_PICKUP: 'Ready for pickup', COLLECTED: 'Collected',
        CANCELLED: 'Cancelled', ONLINE_PICKUP: 'Store pickup',
        ONLINE_DELIVERY: 'Town parcel', CUSTOMER_CONFIRMED: 'Order received', RETURNED: 'Returned',
    };
    const label = value => labels[value] || 'Order updated';
    const formatDate = value => new Intl.DateTimeFormat('en-KE', {
        dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Nairobi',
    }).format(new Date(value));

    const terminalStatuses = new Set(['CANCELLED', 'COLLECTED', 'CUSTOMER_CONFIRMED', 'RETURNED']);
    let countdownTimer = null;
    const cancelPanel = document.getElementById('cancel-order-panel');
    const cancelDialog = document.getElementById('cancel-order-dialog');
    const cancelError = document.getElementById('cancel-order-error');
    const confirmCancelButton = document.getElementById('confirm-cancel-order');

    document.getElementById('open-cancel-order').addEventListener('click', () => {
        cancelError.classList.add('hidden');
        cancelError.textContent = '';
        cancelDialog.showModal();
    });
    document.getElementById('keep-order').addEventListener('click', () => cancelDialog.close());

    async function cancelOrder() {
        confirmCancelButton.disabled = true;
        confirmCancelButton.textContent = 'Cancelling...';
        cancelError.classList.add('hidden');
        try {
            const csrfToken = cancelDialog.querySelector('input[name="csrfmiddlewaretoken"]').value;
            const response = await fetch(`/api/orders/${encodeURIComponent(orderNumber)}/cancel/`, {
                method: 'POST', credentials: 'same-origin', headers: {
                    ...headers, 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken,
                }, body: JSON.stringify({confirmed: true}),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'This order could not be cancelled. Please contact us for help.');
            cancelDialog.close();
            await loadStatus();
        } catch (error) {
            cancelError.textContent = error.message;
            cancelError.classList.remove('hidden');
        } finally {
            confirmCancelButton.disabled = false;
            confirmCancelButton.textContent = 'Yes, cancel order';
        }
    }
    confirmCancelButton.addEventListener('click', cancelOrder);

    function renderCountdown(expiresAt, status) {
        const box = document.getElementById('payment-countdown');
        const value = document.getElementById('payment-countdown-value');
        if (countdownTimer) window.clearInterval(countdownTimer);
        countdownTimer = null;
        if (!expiresAt || status !== 'PENDING') {
            box.classList.add('hidden');
            return;
        }
        box.classList.remove('hidden');
        const update = () => {
            const seconds = Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 1000));
            const minutes = Math.floor(seconds / 60);
            value.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
            if (seconds === 0) {
                value.textContent = 'Checking payment status…';
                window.clearInterval(countdownTimer);
                countdownTimer = null;
            }
        };
        update();
        if (!countdownTimer) countdownTimer = window.setInterval(update, 1000);
    }

    function statusMessage(data) {
        if (data.status === 'PENDING') return 'Check your phone for the M-Pesa prompt and enter your PIN once. We will confirm the payment here automatically.';
        if (data.status === 'CANCELLED' && data.cancelled_by_customer) return 'Your order was cancelled as requested and the reserved items were released.';
        if (data.status === 'CANCELLED') return 'Payment was not completed, so this order was cancelled and the items were released. You can shop again or ask us for help.';
        if (data.status === 'READY_FOR_PICKUP') return 'Your order is ready for collection at S18.';
        if (data.status === 'PACKING') return 'Your order is being packed.';
        if (data.status === 'PACKED') return 'Your order has been packed and is awaiting the next fulfilment step.';
        return `Current status: ${label(data.status)}.`;
    }

    async function loadStatus() {
        try {
            const response = await fetch(`/api/orders/${encodeURIComponent(orderNumber)}/status/`, {
                credentials: 'same-origin', headers, cache: 'no-store',
            });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error('This order link is invalid, expired, or belongs to another account.');
        document.getElementById('tracking-status').textContent = label(data.status);
        document.getElementById('tracking-branch').textContent = data.branch;
        document.getElementById('tracking-total').textContent = `KES ${data.total_payable}`;
        document.getElementById('tracking-type').textContent = label(data.order_type);
        renderCountdown(data.payment_expires_at, data.status);
        cancelPanel.classList.toggle('hidden', !data.can_cancel);
        document.getElementById('tracking-actions').classList.toggle('hidden', data.status !== 'CANCELLED');

        if (data.parcel) {
            const parcel = document.getElementById('tracking-parcel');
            parcel.textContent = `${data.parcel.town}, ${data.parcel.county} - collect at ${data.parcel.collection_point} through ${data.parcel.operator}${data.parcel.reference ? ` - reference ${data.parcel.reference}` : ''}.`;
            parcel.classList.remove('hidden');
        }

        if (data.pickup_expires_at && data.status === 'READY_FOR_PICKUP') {
            const deadline = document.getElementById('pickup-deadline');
            deadline.textContent = `Collect from Gaberone Plaza S18 by ${formatDate(data.pickup_expires_at)}. Bring the official payment message and inspect the item before leaving.`;
            deadline.classList.remove('hidden');
        }

        const timeline = document.getElementById('tracking-timeline');
        timeline.replaceChildren();
        const historyItems = data.status_history.length ? [...data.status_history].reverse() : [{
            status: data.status, message: 'Your order status was updated.', timestamp: null,
        }];
        historyItems.forEach((event, index) => {
            const row = document.createElement('li');
            row.className = 'flex gap-3';
            const marker = document.createElement('span');
            marker.className = index === historyItems.length - 1
                ? 'mt-1 h-3 w-3 shrink-0 rounded-full bg-brand-500 ring-4 ring-brand-100'
                : 'mt-1 h-3 w-3 shrink-0 rounded-full bg-slate-300';
            const copy = document.createElement('div');
            const title = document.createElement('p');
            title.className = 'font-semibold text-slate-900';
            title.textContent = label(event.status);
            copy.appendChild(title);
            if (event.timestamp) {
                const when = document.createElement('p');
                when.className = 'text-xs text-slate-500';
                when.textContent = formatDate(event.timestamp);
                copy.appendChild(when);
            }
            if (event.message) {
                const note = document.createElement('p');
                note.className = 'mt-1 text-sm text-slate-600';
                note.textContent = event.message;
                copy.appendChild(note);
            }
            row.append(marker, copy);
            timeline.appendChild(row);
        });

        const list = document.getElementById('tracking-items');
        list.replaceChildren();
        data.items.forEach(item => {
            const row = document.createElement('li');
            row.className = 'flex justify-between gap-4 py-3 text-sm';
            const itemLabel = document.createElement('span');
            itemLabel.textContent = `${item.name} x ${item.quantity}`;
            const total = document.createElement('span');
            total.className = 'font-semibold';
            total.textContent = `KES ${item.total}`;
            row.append(itemLabel, total);
            list.appendChild(row);
        });
        const message = document.getElementById('tracking-message');
        message.className = data.status === 'CANCELLED'
            ? 'mt-5 rounded-lg bg-red-50 p-3 text-sm text-red-900'
            : 'mt-5 rounded-lg bg-blue-50 p-3 text-sm text-blue-900';
        message.textContent = statusMessage(data);
        document.getElementById('tracking-details').classList.remove('hidden');
        if (!terminalStatuses.has(data.status)) {
            window.setTimeout(loadStatus, data.status === 'PENDING' ? 5000 : 15000);
        }
        } catch (error) {
            const message = document.getElementById('tracking-message');
            message.className = 'mt-5 rounded-lg bg-red-50 p-3 text-sm text-red-900';
            message.textContent = error.message;
        }
    }

    void loadStatus();
})();
