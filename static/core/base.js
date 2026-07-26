(function () {
    "use strict";

    function readCookie(name) {
        const prefix = `${name}=`;
        const match = document.cookie
            .split(";")
            .map(value => value.trim())
            .find(value => value.startsWith(prefix));
        return match ? decodeURIComponent(match.slice(prefix.length)) : "";
    }

    document.body.addEventListener("htmx:configRequest", event => {
        const formToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
        event.detail.headers["X-CSRFToken"] = formToken || readCookie("csrftoken");
    });

    document.querySelectorAll("[data-auto-dismiss]").forEach(alert => {
        const delay = Number.parseInt(alert.dataset.autoDismiss, 10);
        if (Number.isFinite(delay) && delay > 0) {
            window.setTimeout(() => alert.remove(), delay);
        }
    });
    document.body.addEventListener("click", event => {
        const button = event.target.closest("[data-dismiss-alert]");
        if (button) button.closest("[role=alert]")?.remove();
    });
}());
