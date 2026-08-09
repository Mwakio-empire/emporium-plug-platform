(function () {
    'use strict';

    const dialog = document.getElementById('shopper-location-dialog');
    const form = document.getElementById('shopper-location-form');
    if (!dialog || !form) return;

    const county = document.getElementById('shopper-location-county');
    const town = document.getElementById('shopper-location-town');
    const customField = document.getElementById('shopper-location-custom-field');
    const customTown = document.getElementById('shopper-location-custom');
    const status = document.getElementById('shopper-location-status');
    const retry = document.getElementById('shopper-location-retry');
    const message = document.getElementById('shopper-location-message');
    const save = document.getElementById('shopper-location-save');
    let requestController = null;
    let requestVersion = 0;
    let restoreFocus = null;

    function humanize(value) {
        return String(value || '')
            .trim()
            .toLocaleLowerCase('en-KE')
            .replace(/(^|[\s\-/])([a-z])/g, (_, boundary, letter) => `${boundary}${letter.toUpperCase()}`);
    }

    function addOption(value, label) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        town.appendChild(option);
    }

    function showMessage(text, kind = 'error') {
        message.hidden = false;
        message.textContent = text;
        message.className = `rounded-lg p-3 text-sm ${kind === 'success' ? 'bg-emerald-50 text-emerald-900' : 'bg-red-50 text-red-900'}`;
        message.focus({preventScroll: true});
    }

    function clearMessage() {
        message.hidden = true;
        message.textContent = '';
    }

    function showCustomField(show, preferredValue = '') {
        customField.hidden = !show;
        customTown.disabled = !show;
        customTown.required = show;
        customTown.value = show ? preferredValue : '';
    }

    function resetTown(messageText = 'Select a county to see its listed cities and areas.') {
        if (requestController) requestController.abort();
        requestController = null;
        requestVersion += 1;
        town.replaceChildren();
        addOption('', county.value ? 'Select city / area' : 'Select a county first');
        town.disabled = true;
        status.textContent = messageText;
        retry.hidden = true;
        showCustomField(false);
    }

    async function loadLocations(preferredTownId = '', preferredCustomTown = '') {
        resetTown();
        if (!county.value) return;

        const selectedCounty = county.value;
        const version = ++requestVersion;
        requestController = new AbortController();
        town.replaceChildren();
        addOption('', 'Loading cities and areas…');
        status.textContent = 'Loading locations for the selected county…';
        retry.hidden = true;
        save.disabled = true;

        try {
            const url = new URL(form.dataset.townsUrl, window.location.origin);
            url.searchParams.set('county', selectedCounty);
            const response = await fetch(url, {
                credentials: 'same-origin',
                signal: requestController.signal,
            });
            const locations = await response.json().catch(() => null);
            if (!response.ok || !Array.isArray(locations)) throw new Error('Location lookup failed.');
            if (version !== requestVersion || selectedCounty !== county.value) return;

            town.replaceChildren();
            addOption('', locations.length ? 'Select city / area' : 'No listed locations found');
            locations.forEach(location => addOption(String(location.id), humanize(location.name)));
            addOption('__OTHER__', "My city / area isn't listed");
            town.disabled = false;
            save.disabled = false;
            status.textContent = locations.length
                ? 'Choose a listed location, or use the unlisted-area option.'
                : 'No listed locations were found. Use the unlisted-area option to continue.';

            if (preferredCustomTown) {
                town.value = '__OTHER__';
                showCustomField(true, preferredCustomTown);
            } else if (preferredTownId && town.querySelector(`option[value="${CSS.escape(String(preferredTownId))}"]`)) {
                town.value = String(preferredTownId);
            }
        } catch (error) {
            if (error.name === 'AbortError' || version !== requestVersion) return;
            town.replaceChildren();
            addOption('', 'Location list unavailable');
            addOption('__OTHER__', "My city / area isn't listed");
            town.disabled = false;
            save.disabled = false;
            retry.hidden = false;
            status.textContent = 'We could not load the location list. Retry, or enter an unlisted city or area.';
        } finally {
            if (version === requestVersion) requestController = null;
        }
    }

    async function openDialog(trigger) {
        restoreFocus = trigger;
        clearMessage();
        dialog.showModal();
        county.value = form.dataset.savedCounty || '';
        if (county.value) {
            await loadLocations(
                form.dataset.savedTownId || '',
                form.dataset.savedCustomTown || '',
            );
            town.focus();
        } else {
            resetTown();
            county.focus();
        }
    }

    function closeDialog() {
        dialog.close();
        if (restoreFocus && typeof restoreFocus.focus === 'function') restoreFocus.focus();
    }

    document.querySelectorAll('[data-shopper-location-open]').forEach(button => {
        button.addEventListener('click', () => { void openDialog(button); });
    });
    document.querySelectorAll('[data-shopper-location-close]').forEach(button => {
        button.addEventListener('click', closeDialog);
    });
    dialog.addEventListener('click', event => {
        if (event.target === dialog) closeDialog();
    });
    county.addEventListener('change', () => { clearMessage(); void loadLocations(); });
    town.addEventListener('change', () => {
        clearMessage();
        showCustomField(town.value === '__OTHER__');
    });
    retry.addEventListener('click', () => { clearMessage(); void loadLocations(); });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        save.disabled = true;
        clearMessage();
        const data = new FormData(form);
        const customSelected = town.value === '__OTHER__';
        data.set('town_id', customSelected ? '' : town.value);
        data.set('use_custom_town', String(customSelected));
        data.set('custom_town', customSelected ? customTown.value.trim() : '');

        try {
            const response = await fetch(form.dataset.saveUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                body: data,
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || 'We could not save that location. Please try again.');

            form.dataset.savedCounty = result.location.county_code;
            form.dataset.savedTownId = result.location.town_id || '';
            form.dataset.savedCustomTown = result.location.use_custom_town ? result.location.town_name : '';
            document.querySelectorAll('[data-shopper-location-summary]').forEach(element => {
                element.textContent = result.location_label;
            });
            document.querySelectorAll('[data-shopper-location-open]').forEach(button => {
                if (button.textContent.trim() === 'Select' || button.textContent.trim() === 'Select location') {
                    button.textContent = 'Change';
                }
            });
            window.dispatchEvent(new CustomEvent('shopper-location-saved', {detail: result.location}));
            showMessage('Location saved. We will use it to prepare your transport quote.', 'success');
            window.setTimeout(closeDialog, 650);
        } catch (error) {
            showMessage(error.message);
        } finally {
            save.disabled = false;
        }
    });
}());
