(() => {
    'use strict';
    const root = document.getElementById('order-tracking');
    if (!root) return;
    const orderNumber = root.dataset.orderNumber;
    const token = window.location.hash.slice(1);
    if (token) history.replaceState(null, '', window.location.pathname);

    const headers = token ? {'X-Guest-Order-Token': token} : {};
    const label = value => value.toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
    const formatDate = value => new Intl.DateTimeFormat('en-KE', {
        dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Nairobi',
    }).format(new Date(value));

    fetch(`/api/orders/${encodeURIComponent(orderNumber)}/status/`, {
        credentials: 'same-origin', headers,
    }).then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error('This order link is invalid, expired, or belongs to another account.');
        document.getElementById('tracking-status').textContent = label(data.status);
        document.getElementById('tracking-branch').textContent = data.branch;
        document.getElementById('tracking-total').textContent = `KES ${data.total_payable}`;
        document.getElementById('tracking-type').textContent = label(data.order_type);

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
        const historyItems = data.status_history.length ? [...data.status_history].reverse() : [{
            status: data.status, note: '', timestamp: null,
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
            if (event.note) {
                const note = document.createElement('p');
                note.className = 'mt-1 text-sm text-slate-600';
                note.textContent = event.note;
                copy.appendChild(note);
            }
            row.append(marker, copy);
            timeline.appendChild(row);
        });

        const list = document.getElementById('tracking-items');
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
        document.getElementById('tracking-message').classList.add('hidden');
        document.getElementById('tracking-details').classList.remove('hidden');
    }).catch(error => {
        const message = document.getElementById('tracking-message');
        message.className = 'mt-5 rounded-lg bg-red-50 p-3 text-sm text-red-900';
        message.textContent = error.message;
    });
})();
