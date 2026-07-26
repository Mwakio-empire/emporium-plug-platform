(function () {
    "use strict";

    document.documentElement.dataset.storefrontJs = "ready";

    let returnFocus = null;

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
        document.getElementById("cart-close-button")?.focus();
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

    document.addEventListener("click", event => {
        const openTrigger = event.target.closest("[data-cart-open]");
        if (openTrigger) openCart(openTrigger);
        if (event.target.closest("[data-cart-close]")) closeCart();

        const htmxTrigger = event.target.closest("[data-cart-open-on-htmx]");
        if (htmxTrigger && window.htmx) openCart(htmxTrigger);
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && drawer()?.getAttribute("aria-hidden") === "false") {
            closeCart();
        }
    });
}());
