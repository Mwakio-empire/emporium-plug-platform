(function () {
    "use strict";

    document.documentElement.dataset.productDetailJs = "ready";

    let returnFocus = null;
    let countdownTimer = null;

    function drawer() {
        return document.getElementById("shopping-cart-drawer-panel");
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

    function selectVariant(option) {
        document.querySelectorAll(".variant-option").forEach(item => {
            item.classList.remove("border-brand-600", "bg-brand-50", "text-brand-700");
            item.classList.add("border-gray-200", "text-gray-600");
        });
        option.classList.add("border-brand-600", "bg-brand-50", "text-brand-700");
        option.classList.remove("border-gray-200", "text-gray-600");
        document.getElementById("selected-variant-id").value = option.dataset.variantId;
        document.getElementById("display-price").textContent = `KES ${option.dataset.price}`;

        const stock = Number.parseInt(option.dataset.stock, 10);
        const stockNote = document.getElementById("stock-note");
        const button = document.getElementById("add-to-bag-btn");
        const quantity = document.getElementById("product-quantity");
        quantity.max = stock;
        if (Number.parseInt(quantity.value, 10) > stock) quantity.value = stock || 1;
        stockNote.textContent = stock > 0 ? "In stock and ready to ship" : "Currently out of stock";
        stockNote.className = stock > 0
            ? "text-xs text-emerald-600 font-semibold"
            : "text-xs text-rose-600 font-semibold";
        button.disabled = stock <= 0;
        button.textContent = stock > 0 ? "Add to cart" : "Out of stock";
        updateCountdown(option.dataset.flashEnd);
    }

    document.addEventListener("click", event => {
        const imageOption = event.target.closest(".product-image-option");
        if (imageOption) {
            const image = document.getElementById("main-product-image");
            if (image) {
                image.src = imageOption.dataset.imageUrl;
                image.alt = imageOption.dataset.imageAlt;
            }
        }
        const variant = event.target.closest("[data-variant-select]");
        if (variant) selectVariant(variant);
        if (event.target.closest("[data-cart-close]")) closeCart();
        const htmxTrigger = event.target.closest("[data-cart-open-on-htmx]");
        if (htmxTrigger && window.htmx) openCart(htmxTrigger);
    });
    document.addEventListener("change", event => {
        const select = event.target.closest("[data-submit-on-change]");
        if (select) select.form.submit();
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && drawer()?.getAttribute("aria-hidden") === "false") {
            closeCart();
        }
    });

    const firstOption = document.querySelector("[data-variant-select]");
    if (firstOption) updateCountdown(firstOption.dataset.flashEnd);
}());
