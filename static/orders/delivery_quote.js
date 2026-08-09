(() => {
    'use strict';

    const page = document.getElementById('delivery-quote-page');
    if (!page) return;
    const reference = page.dataset.reference;
    const token = window.location.hash.slice(1);
    const csrf = page.querySelector('[name=csrfmiddlewaretoken]').value;
    let quote = null;
    let currentTotal = null;
    let orderToken = null;

    const byId = id => document.getElementById(id);
    const headers = () => token ? {'X-Delivery-Quote-Token': token} : {};

    function showError(text) {
        byId('quote-loading').classList.add('hidden');
        byId('quote-error').textContent = text;
        byId('quote-error').classList.remove('hidden');
    }

    function showAction(text, kind = 'info') {
        const box = byId('quote-action-message');
        const styles = {
            info: 'bg-blue-50 text-blue-900',
            error: 'bg-rose-50 text-rose-900',
            success: 'bg-emerald-50 text-emerald-900',
        };
        box.className = `rounded-xl p-4 text-sm ${styles[kind]}`;
        box.textContent = text;
    }

    async function request(url, {method = 'GET', body = null, orderAccessToken = null} = {}) {
        const response = await fetch(url, {
            method,
            credentials: 'same-origin',
            headers: {
                ...headers(),
                ...(orderAccessToken ? {'X-Guest-Order-Token': orderAccessToken} : {}),
                ...(body ? {'Content-Type': 'application/json', 'X-CSRFToken': csrf} : {}),
            },
            body: body ? JSON.stringify(body) : null,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = new Error(
                response.status === 429
                    ? 'Too many attempts were made. Wait a moment and try again.'
                    : (data.error || 'We could not complete that request.'),
            );
            error.data = data;
            error.status = response.status;
            throw error;
        }
        return data;
    }

    function money(value) {
        return `KES ${Number(value || 0).toFixed(2)}`;
    }

    function guidanceForStatus(status) {
        return {
            REQUESTED: 'Your request is in the queue. No order, payment or stock reservation exists yet.',
            REVIEWING: 'Our team is confirming the operator, collection point, fee and expected arrival.',
            QUOTED: 'Your transport details are ready. Review the current product total and accept before this quote expires.',
            ACCEPTED: 'You accepted this quote. Continue through the linked order tracking page.',
            DECLINED: 'You declined this quote. No order was created and no stock was reserved.',
            EXPIRED: 'This quote expired. Submit a new request so we can confirm current transport details.',
            CANCELLED: 'This quote was cancelled. Contact us if you still need the products sent.',
        }[status] || 'The quote status was updated.';
    }

    function renderCountdown() {
        if (!quote) return;
        const targetText = quote.status === 'QUOTED' ? quote.expires_at : quote.response_due_at;
        if (!targetText || !['REQUESTED', 'REVIEWING', 'QUOTED'].includes(quote.status)) {
            byId('quote-countdown').textContent = quote.status_label;
            return;
        }
        const remaining = new Date(targetText).getTime() - Date.now();
        if (remaining <= 0) {
            byId('quote-countdown').textContent = quote.status === 'QUOTED' ? 'Quote expired' : 'Response target passed';
            if (quote.status !== 'QUOTED') byId('quote-whatsapp').classList.remove('hidden');
            return;
        }
        const minutes = Math.ceil(remaining / 60000);
        const hours = Math.floor(minutes / 60);
        const rest = minutes % 60;
        byId('quote-countdown').textContent = quote.status === 'QUOTED'
            ? `Valid for ${hours ? `${hours}h ` : ''}${rest}m`
            : `Response target: ${hours ? `${hours}h ` : ''}${rest}m`;
    }

    function renderQuote(data) {
        quote = data;
        byId('quote-loading').classList.add('hidden');
        byId('quote-error').classList.add('hidden');
        byId('quote-content').classList.remove('hidden');
        byId('quote-status').textContent = data.status_label;
        byId('quote-destination').textContent = `${data.town}, ${data.county}`;
        byId('quote-guidance').textContent = guidanceForStatus(data.status);
        byId('quote-whatsapp').href = data.whatsapp_url;
        if (data.overdue) byId('quote-whatsapp').classList.remove('hidden');
        const items = byId('quote-items');
        items.replaceChildren();
        data.cart_snapshot.forEach(item => {
            const line = document.createElement('li');
            line.className = 'rounded-lg bg-slate-50 p-3';
            line.textContent = `${item.name}${item.variant ? ` · ${item.variant}` : ''} × ${item.quantity}`;
            items.appendChild(line);
        });
        if (data.transport_operator) byId('quote-operator').textContent = data.transport_operator;
        if (data.collection_point) byId('quote-collection').textContent = data.collection_point;
        if (data.expected_arrival) byId('quote-arrival').textContent = data.expected_arrival;
        byId('quote-payment').classList.toggle('hidden', data.status !== 'QUOTED');
        renderCountdown();
    }

    function renderTotals(data) {
        currentTotal = data.total_payable;
        byId('quote-regular-total').textContent = money(data.regular_price_total);
        byId('quote-product-saving').textContent = money(data.product_discount_amount);
        byId('quote-coupon-saving').textContent = money(data.discount_amount);
        byId('quote-fee').textContent = money(data.delivery_fee);
        byId('quote-total').textContent = money(data.total_payable);
        byId('quote-confirm').checked = false;
    }

    async function reviewTotal() {
        const coupon = byId('quote-coupon').value.trim();
        try {
            const totals = await request(
                `/api/orders/delivery-quotes/${encodeURIComponent(reference)}/accept/`,
                {method: 'POST', body: {preview_only: true, coupon_code: coupon}},
            );
            renderTotals(totals);
            byId('quote-coupon-feedback').textContent = coupon
                ? `Coupon ${coupon.toUpperCase()} is valid.`
                : '';
            byId('quote-coupon-feedback').className = 'mt-2 text-sm text-emerald-700';
        } catch (error) {
            byId('quote-coupon-feedback').textContent = error.message;
            byId('quote-coupon-feedback').className = 'mt-2 text-sm text-rose-700';
            throw error;
        }
    }

    async function loadQuote() {
        try {
            const data = await request(`/api/orders/delivery-quotes/${encodeURIComponent(reference)}/`);
            renderQuote(data);
            if (data.status === 'QUOTED') await reviewTotal();
        } catch (error) {
            showError(error.status === 404
                ? 'We could not open this quote. Sign in with the account that requested it or use the secure link sent to you.'
                : error.message);
        }
    }

    byId('quote-review-total').addEventListener('click', () => reviewTotal().catch(() => {}));
    byId('quote-coupon').addEventListener('input', () => {
        currentTotal = null;
        byId('quote-confirm').checked = false;
        byId('quote-coupon-feedback').textContent = 'Apply the code to refresh your total.';
        byId('quote-coupon-feedback').className = 'mt-2 text-sm text-slate-600';
    });
    byId('quote-accept').addEventListener('click', async () => {
        if (!byId('quote-confirm').checked) {
            showAction('Confirm that you reviewed the final amount before continuing.', 'error');
            return;
        }
        if (!currentTotal) {
            showAction('Refresh the current total before accepting this quote.', 'error');
            return;
        }
        const button = byId('quote-accept');
        button.disabled = true;
        showAction('Creating your order and reserving the available items…');
        try {
            const order = await request(
                `/api/orders/delivery-quotes/${encodeURIComponent(reference)}/accept/`,
                {method: 'POST', body: {
                    confirmed: true,
                    expected_total: currentTotal,
                    coupon_code: byId('quote-coupon').value.trim(),
                }},
            );
            orderToken = order.guest_access_token || null;
            showAction('Order created. Sending the M-Pesa request…');
            try {
                await request('/api/checkout/pay/', {
                    method: 'POST',
                    orderAccessToken: orderToken,
                    body: {
                        order_number: order.order_number,
                        phone: quote.customer_phone,
                        access_token: orderToken,
                    },
                });
            } finally {
                window.location.assign(order.tracking_url);
            }
        } catch (error) {
            if (error.data && error.data.requires_confirmation) {
                renderTotals(error.data);
            }
            showAction(error.message, 'error');
            button.disabled = false;
        }
    });
    byId('quote-decline').addEventListener('click', async () => {
        if (!window.confirm('Decline this delivery quote? No order will be created.')) return;
        try {
            const data = await request(
                `/api/orders/delivery-quotes/${encodeURIComponent(reference)}/decline/`,
                {method: 'POST', body: {confirmed: true}},
            );
            renderQuote(data);
            showAction('The quote was declined. No order was created.', 'success');
        } catch (error) {
            showAction(error.message, 'error');
        }
    });

    loadQuote();
    window.setInterval(renderCountdown, 30000);
})();
