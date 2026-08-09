(function () {
    "use strict";

    document.documentElement.dataset.productDetailJs = "ready";
    let returnFocus = null;
    let countdownTimer = null;

    const drawer = () => document.getElementById("shopping-cart-drawer-panel");

    function replaceMainImage(image, url, alt) {
        if (window.EmporiumImages) {
            window.EmporiumImages.replace(image, url, alt);
            return;
        }
        image.src = url;
        image.alt = alt;
    }

    function openCart(trigger) {
        const panel = drawer();
        if (!panel) return;
        returnFocus = trigger || document.activeElement;
        panel.hidden = false;
        panel.classList.remove("translate-x-full");
        panel.setAttribute("aria-hidden", "false");
        panel.removeAttribute("inert");
        document.getElementById("product-cart-close")?.focus();
    }

    function closeCart() {
        const panel = drawer();
        if (!panel) return;
        panel.classList.add("translate-x-full");
        panel.setAttribute("aria-hidden", "true");
        panel.setAttribute("inert", "");
        panel.hidden = true;
        returnFocus?.focus();
    }

    function updateCountdown(endIso) {
        const box = document.getElementById("flash-countdown");
        if (!box) return;
        if (countdownTimer) clearInterval(countdownTimer);
        if (!endIso) {
            box.classList.add("hidden");
            return;
        }
        box.classList.remove("hidden");
        const endTime = new Date(endIso).getTime();
        const tick = () => {
            const diff = endTime - Date.now();
            if (diff <= 0) {
                box.classList.add("hidden");
                clearInterval(countdownTimer);
                return;
            }
            const hours = String(Math.floor(diff / 3600000)).padStart(2, "0");
            const minutes = String(Math.floor((diff % 3600000) / 60000)).padStart(2, "0");
            const seconds = String(Math.floor((diff % 60000) / 1000)).padStart(2, "0");
            document.getElementById("countdown-text").textContent = `${hours}:${minutes}:${seconds}`;
        };
        tick();
        countdownTimer = setInterval(tick, 1000);
    }

    function initialiseVariantPicker() {
        const dataNode = document.getElementById("variant-matrix-data");
        const groups = Array.from(document.querySelectorAll("[data-option-group]"));
        if (!dataNode || !groups.length) return;

        const variants = JSON.parse(dataNode.textContent);
        const selected = new Map();
        const valueToGroup = new Map();
        groups.forEach(group => {
            group.querySelectorAll("[data-option-value]").forEach(button => {
                valueToGroup.set(Number(button.dataset.optionValue), group.dataset.optionId);
            });
            group.querySelectorAll("option").forEach(option => {
                valueToGroup.set(Number(option.value), group.dataset.optionId);
            });
        });

        const initial = variants.find(variant => variant.stock > 0) || variants[0];
        if (!initial) return;
        initial.values.forEach(valueId => selected.set(valueToGroup.get(Number(valueId)), Number(valueId)));

        function matchesSelection(variant, omittedGroup) {
            return Array.from(selected.entries()).every(([groupId, valueId]) => (
                groupId === omittedGroup || variant.values.includes(valueId)
            ));
        }

        function exactVariant() {
            if (selected.size !== groups.length) return null;
            return variants.find(variant => matchesSelection(variant, null)) || null;
        }

        function applyVariant(variant) {
            const hidden = document.getElementById("selected-variant-id");
            const price = document.getElementById("display-price");
            const stockNote = document.getElementById("stock-note");
            const button = document.getElementById("add-to-bag-btn");
            const quantity = document.getElementById("product-quantity");
            const message = document.getElementById("variant-selection-message");
            const messageText = message?.querySelector("[data-variant-message]");
            const sku = document.getElementById("variant-sku");
            const regularPrice = document.getElementById("variant-regular-price");
            const restockPanel = document.querySelector("[data-restock-panel]");
            const restockVariant = document.getElementById("restock-variant-id");
            if (!variant) {
                hidden.value = "";
                if (restockVariant) restockVariant.value = "";
                button.disabled = true;
                quantity.disabled = true;
                button.textContent = "Choose available options";
                message.dataset.state = "unavailable";
                messageText.textContent = "That combination is unavailable. Choose another option.";
                stockNote.textContent = "Combination unavailable";
                stockNote.className = "text-xs text-rose-600 font-semibold";
                return;
            }
            hidden.value = variant.id;
            if (restockVariant) restockVariant.value = variant.id;
            price.textContent = `KES ${variant.price}`;
            if (regularPrice) {
                regularPrice.textContent = `KES ${variant.regular_price}`;
                regularPrice.classList.toggle("hidden", !variant.on_sale);
            }
            quantity.max = Math.max(variant.stock, 1);
            if (Number.parseInt(quantity.value, 10) > variant.stock) quantity.value = variant.stock || 1;
            const available = variant.stock > 0;
            quantity.disabled = !available;
            restockPanel?.classList.toggle("hidden", available);
            stockNote.textContent = available ? "In stock and ready to order" : "This combination is currently sold out";
            stockNote.className = available
                ? "text-xs text-emerald-600 font-semibold"
                : "text-xs text-rose-600 font-semibold";
            button.disabled = !available;
            button.textContent = available ? "Add to cart" : "Out of stock";
            message.dataset.state = available ? "available" : "sold-out";
            messageText.textContent = available
                ? `${variant.stock} available across our shops.`
                : "Choose another combination to continue.";
            if (sku) sku.textContent = `SKU: ${variant.sku}`;
            if (variant.image) {
                const image = document.getElementById("main-product-image");
                if (image) {
                    replaceMainImage(image, variant.image, variant.image_alt);
                }
            }
            updateCountdown(variant.flash_end);
        }

        function render() {
            groups.forEach(group => {
                const groupId = group.dataset.optionId;
                const selectedValue = selected.get(groupId);
                const label = group.querySelector("[data-selected-option-label]");
                const selectedControl = group.querySelector(`[data-option-value="${selectedValue}"]`);
                const select = group.querySelector("[data-option-select]");
                if (select) {
                    select.value = String(selectedValue);
                    label.textContent = select.selectedOptions[0]?.textContent || "";
                    Array.from(select.options).forEach(option => {
                        const valueId = Number(option.value);
                        const possible = variants.some(variant => (
                            variant.values.includes(valueId) && matchesSelection(variant, groupId)
                        ));
                        option.disabled = !possible;
                    });
                } else {
                    label.textContent = selectedControl?.dataset.optionLabel || "";
                    group.querySelectorAll("[data-option-value]").forEach(control => {
                        const valueId = Number(control.dataset.optionValue);
                        const isSelected = valueId === selectedValue;
                        const compatible = variants.filter(variant => (
                            variant.values.includes(valueId) && matchesSelection(variant, groupId)
                        ));
                        const exists = compatible.length > 0;
                        const hasStock = compatible.some(variant => variant.stock > 0);
                        control.disabled = !exists;
                        control.setAttribute("aria-pressed", String(isSelected));
                        control.dataset.selected = String(isSelected);
                        control.dataset.stockState = hasStock ? "available" : "sold-out";
                        control.title = exists && !hasStock ? "Sold out in this combination" : "";
                    });
                }
            });
            applyVariant(exactVariant());
        }

        groups.forEach(group => {
            group.addEventListener("click", event => {
                const control = event.target.closest("[data-option-value]");
                if (!control || control.disabled) return;
                selected.set(group.dataset.optionId, Number(control.dataset.optionValue));
                render();
            });
            group.querySelector("[data-option-select]")?.addEventListener("change", event => {
                selected.set(group.dataset.optionId, Number(event.target.value));
                render();
            });
        });
        render();
    }

    document.addEventListener("click", event => {
        const imageOption = event.target.closest(".product-image-option");
        if (imageOption) {
            const image = document.getElementById("main-product-image");
            if (image) {
                replaceMainImage(image, imageOption.dataset.imageUrl, imageOption.dataset.imageAlt);
            }
        }
        if (event.target.closest("[data-cart-close]")) closeCart();
        const htmxTrigger = event.target.closest("[data-cart-open-on-htmx]");
        if (htmxTrigger && window.htmx) openCart(htmxTrigger);
    });
    document.addEventListener("change", event => {
        const select = event.target.closest("[data-submit-on-change]");
        if (select) select.form.submit();
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && drawer()?.getAttribute("aria-hidden") === "false") closeCart();
    });
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialiseVariantPicker, {once: true});
    } else {
        initialiseVariantPicker();
    }
}());
