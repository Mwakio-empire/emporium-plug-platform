(() => {
    'use strict';

    const form = document.getElementById('checkout-form');
    if (!form) return;

    const slots = JSON.parse(document.getElementById('pickup-slots-data').textContent);
    const fields = {
        branch: document.getElementById('branch'),
        fulfilmentChoices: [...document.querySelectorAll('[name="fulfilment_choice"]')],
        slot: document.getElementById('pickup-slot'),
        phone: document.getElementById('phone'),
        name: document.getElementById('customer-name'),
        email: document.getElementById('customer-email'),
        coupon: document.getElementById('coupon'),
        payment: document.getElementById('payment-method'),
        confirmation: document.getElementById('confirm-order'),
        quoteCounty: document.getElementById('quote-county'),
        quoteTown: document.getElementById('quote-town'),
        quoteArea: document.getElementById('quote-area'),
        quoteNotes: document.getElementById('quote-notes'),
    };
    const message = document.getElementById('checkout-message');
    const submit = document.getElementById('submit-checkout');
    const fallbackForm = document.getElementById('fallback-form');
    const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
    let activeOrder = null;
    let guestToken = null;
    let quoteRequestVersion = 0;

    function selectedFulfilment() {
        return fields.fulfilmentChoices.find(field => field.checked)?.value || '';
    }

    function deliveryQuoteSelected() {
        return selectedFulfilment() === 'DELIVERY_QUOTE';
    }

    function showNextActions(order) {
        const container = document.getElementById('checkout-next-actions');
        const trackingLink = document.getElementById('tracking-link');
        const accountLink = document.getElementById('create-account-link');
        trackingLink.href = order.tracking_url || `/orders/track/${encodeURIComponent(order.order_number)}/`;
        if (order.account_creation_url) {
            accountLink.href = order.account_creation_url;
            accountLink.classList.remove('hidden');
        }
        container.classList.remove('hidden');
    }

    function setMessage(text, kind = 'info') {
        const styles = {
            info: 'bg-blue-50 text-blue-900',
            success: 'bg-green-50 text-green-900',
            error: 'bg-red-50 text-red-900',
            pending: 'bg-amber-50 text-amber-950',
        };
        message.className = `rounded-lg p-3 text-sm ${styles[kind]}`;
        message.textContent = text;
        message.focus({preventScroll: true});
    }

    function setCouponFeedback(text, kind) {
        const feedback = document.getElementById('coupon-feedback');
        feedback.textContent = text;
        feedback.className = `mt-2 text-sm ${kind === 'success' ? 'text-emerald-700' : 'text-rose-700'}`;
    }

    function clearCouponFeedback() {
        const feedback = document.getElementById('coupon-feedback');
        feedback.textContent = '';
        feedback.className = 'mt-2 hidden text-sm';
    }

    function resetDisplayedDiscount() {
        const subtotal = Number(document.getElementById('summary-subtotal').textContent.replace(/[^0-9.]/g, '')) || 0;
        const delivery = Number(document.getElementById('summary-delivery').textContent.replace(/[^0-9.]/g, '')) || 0;
        document.getElementById('summary-discount').textContent = 'KES 0.00';
        const productSaving = document.getElementById('summary-product-discount');
        productSaving.textContent = `KES ${productSaving.dataset.initial || '0.00'}`;
        document.getElementById('summary-total').textContent = `KES ${(subtotal + delivery).toFixed(2)}`;
    }

    function addOption(select, value, label) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
    }

    function refreshOptions() {
        fields.slot.replaceChildren();
        addOption(fields.slot, '', 'Select a pickup arrangement');
        const matchingSlots = slots.filter(slot => String(slot.branch_id) === fields.branch.value);
        matchingSlots.forEach(slot => {
            addOption(fields.slot, slot.id, slot.label);
        });
        if (matchingSlots.length === 1) fields.slot.value = matchingSlots[0].id;
    }

    function refreshFulfilmentFields() {
        const isQuote = deliveryQuoteSelected();
        const pickupHasOptions = slots.some(
            slot => String(slot.branch_id) === fields.branch.value,
        );
        document.getElementById('summary-fulfilment').textContent = isQuote ? 'Town parcel quote request' : 'S18 pickup';
        document.getElementById('pickup-fields').classList.toggle('hidden', isQuote);
        document.getElementById('delivery-quote-fields').classList.toggle('hidden', !isQuote);
        document.getElementById('order-payment-fields').classList.toggle('hidden', isQuote);
        document.getElementById('order-confirmation').classList.toggle('hidden', isQuote);
        fields.slot.required = !isQuote;
        fields.slot.disabled = isQuote || !pickupHasOptions;
        fields.name.required = isQuote;
        fields.quoteCounty.required = isQuote;
        fields.quoteCounty.disabled = !isQuote;
        fields.quoteTown.required = isQuote;
        fields.quoteTown.disabled = !isQuote;
        fields.quoteArea.disabled = !isQuote;
        fields.quoteNotes.disabled = !isQuote;
        fields.quoteArea.required = isQuote;
        fields.payment.disabled = isQuote;
        fields.coupon.disabled = isQuote;
        fields.confirmation.required = !isQuote;
        submit.textContent = isQuote ? 'Request delivery quote' : 'Confirm pickup order';
        submit.disabled = !isQuote && !pickupHasOptions;
        if (isQuote) {
            document.getElementById('summary-delivery').textContent = 'Confirmed after review';
            document.getElementById('summary-total').textContent = document.getElementById('summary-subtotal').textContent;
        } else {
            document.getElementById('summary-delivery').textContent = 'KES 0.00';
        }
    }

    function quoteSelectionIsComplete() {
        return selectedFulfilment() === 'PICKUP' && Boolean(fields.slot.value);
    }

    function payload() {
        return {
            branch_id: fields.branch.value,
            order_type: 'ONLINE_PICKUP',
            customer_phone: fields.phone.value.trim(),
            customer_name: fields.name.value.trim(),
            customer_email: fields.email.value.trim(),
            parcel_destination_id: null,
            delivery_address: '',
            pickup_slot_id: fields.slot.value || null,
            payment_method: fields.payment.value,
            coupon_code: fields.coupon.value.trim(),
            confirmed: fields.confirmation.checked,
        };
    }

    function deliveryQuotePayload() {
        return {
            customer_phone: fields.phone.value.trim(),
            customer_name: fields.name.value.trim(),
            customer_email: fields.email.value.trim(),
            county: fields.quoteCounty.value.trim(),
            town: fields.quoteTown.value.trim(),
            preferred_collection_area: fields.quoteArea.value.trim(),
            notes: fields.quoteNotes.value.trim(),
        };
    }

    async function jsonRequest(url, body, extraHeaders = {}) {
        const response = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...extraHeaders},
            body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const message = response.status === 429
                ? 'Too many attempts were made in a short time. Please wait a moment and try again.'
                : (data.error || data.detail || 'The request could not be completed. Please refresh the page and try again.');
            const error = new Error(message);
            error.payload = data;
            error.status = response.status;
            throw error;
        }
        return data;
    }

    async function reviewTotal({announce = true, couponFeedback = false} = {}) {
        const requestVersion = ++quoteRequestVersion;
        const quote = await jsonRequest('/api/checkout/preview/', payload());
        if (requestVersion !== quoteRequestVersion) return quote;
        document.getElementById('summary-subtotal').textContent = `KES ${quote.subtotal}`;
        document.getElementById('summary-product-discount').textContent = `KES ${quote.product_discount_amount || '0.00'}`;
        document.getElementById('summary-discount').textContent = `KES ${quote.discount_amount}`;
        document.getElementById('summary-delivery').textContent = `KES ${quote.delivery_fee}`;
        document.getElementById('summary-total').textContent = `KES ${quote.total_payable}`;
        const notice = document.getElementById('price-change-notice');
        if (quote.price_changes.length) {
            notice.textContent = 'A product price changed. The updated amount is shown above; please review it before confirming.';
            notice.classList.remove('hidden');
            fields.confirmation.checked = false;
        } else {
            notice.classList.add('hidden');
        }
        if (couponFeedback) {
            const code = fields.coupon.value.trim().toUpperCase();
            if (code) {
                setCouponFeedback(`Coupon ${code} is valid. You save KES ${quote.discount_amount}.`, 'success');
            } else {
                setCouponFeedback('No coupon code entered. Your total has still been refreshed.', 'success');
            }
        }
        if (announce) setMessage('Your stock, prices and final amount are up to date.', 'success');
        return quote;
    }

    async function pollOrderStatus(orderNumber, token) {
        for (let attempt = 0; attempt < 20; attempt += 1) {
            await new Promise(resolve => window.setTimeout(resolve, 3000));
            const response = await fetch(`/api/orders/${encodeURIComponent(orderNumber)}/status/`, {
                credentials: 'same-origin',
                headers: token ? {'X-Guest-Order-Token': token} : {},
            });
            if (!response.ok) continue;
            const order = await response.json();
            if (order.status !== 'PENDING') {
                setMessage(`Payment confirmed. Order ${orderNumber} is now ${order.status.toLowerCase().replaceAll('_', ' ')}.`, 'success');
                submit.disabled = true;
                return;
            }
        }
        setMessage(`Order ${orderNumber} is still awaiting payment confirmation. Do not place it again; use your tracking link or contact support if the status does not update.`, 'pending');
    }

    fields.branch.addEventListener('change', () => {
        refreshOptions();
        fields.confirmation.checked = false;
    });
    fields.fulfilmentChoices.forEach(field => field.addEventListener('change', async () => {
        refreshFulfilmentFields();
        fields.confirmation.checked = false;
        clearCouponFeedback();
        resetDisplayedDiscount();
        if (quoteSelectionIsComplete()) {
            try { await reviewTotal({announce: false}); } catch (error) { setMessage(error.message, 'error'); }
        }
    }));
    fields.slot.addEventListener('change', async () => {
        fields.confirmation.checked = false;
        if (!fields.slot.value) return;
        try { await reviewTotal({announce: false}); } catch (error) { setMessage(error.message, 'error'); }
    });
    fields.coupon.addEventListener('input', () => {
        fields.confirmation.checked = false;
        clearCouponFeedback();
        resetDisplayedDiscount();
    });
    document.getElementById('review-total').addEventListener('click', async () => {
        if (!quoteSelectionIsComplete()) {
            setCouponFeedback(
                'Choose a pickup arrangement before applying a coupon.',
                'error',
            );
            return;
        }
        try {
            await reviewTotal({couponFeedback: true});
        } catch (error) {
            resetDisplayedDiscount();
            setCouponFeedback(error.message, 'error');
        }
    });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        submit.disabled = true;
        fallbackForm.classList.add('hidden');
        if (deliveryQuoteSelected()) {
            setMessage('Sending your delivery quote request…');
            try {
                const quote = await jsonRequest('/api/checkout/delivery-quotes/', deliveryQuotePayload());
                const token = quote.access_token ? `#${quote.access_token}` : '';
                window.location.assign(`${quote.status_url}${token}`);
            } catch (error) {
                setMessage(error.message, 'error');
                submit.disabled = false;
            }
            return;
        }
        setMessage('Checking stock, prices and your final amount…');
        try {
            await reviewTotal({announce: false});
            if (!fields.confirmation.checked) {
                throw new Error('Review the updated total and confirm the order before continuing.');
            }
            setMessage('Creating your order…');
            const order = await jsonRequest('/api/checkout/init/', payload(), {
                'Idempotency-Key': form.dataset.idempotencyKey,
            });
            activeOrder = order.order_number;
            guestToken = order.guest_access_token || null;
            showNextActions(order);

            if (order.next_step !== 'initiate_payment') {
                setMessage(`Order ${activeOrder} is confirmed. Payment will be collected during fulfilment.`, 'success');
                window.location.assign(order.tracking_url);
                return;
            }

            setMessage(`Order ${activeOrder} was created. Sending the M-Pesa request…`);
            try {
                const payment = await jsonRequest('/api/checkout/pay/', {
                    order_number: activeOrder,
                    phone: fields.phone.value.trim(),
                    access_token: guestToken,
                });
                setMessage(`${payment.message} Opening your live order status…`, 'pending');
                window.location.assign(order.tracking_url);
            } catch (error) {
                if (error.payload && error.payload.fallback) {
                    setMessage(error.payload.message, 'pending');
                    fallbackForm.classList.remove('hidden');
                } else {
                    throw error;
                }
            }
        } catch (error) {
            setMessage(error.message, 'error');
            submit.disabled = false;
        }
    });

    fallbackForm.addEventListener('submit', async event => {
        event.preventDefault();
        const reference = document.getElementById('mpesa-reference').value.trim();
        if (!reference) return;
        try {
            const result = await jsonRequest('/api/checkout/pay/fallback/', {
                order_number: activeOrder,
                mpesa_reference: reference,
                access_token: guestToken,
            });
            setMessage(result.message, 'pending');
            fallbackForm.classList.add('hidden');
        } catch (error) {
            setMessage(error.message, 'error');
        }
    });

    refreshOptions();
    refreshFulfilmentFields();
})();
