(function () {
    "use strict";

    document.documentElement.classList.add("progressive-images-enabled");

    function finish(image, state) {
        const shell = image.closest("[data-image-shell]");
        if (!shell) return;
        shell.classList.remove("is-loaded", "is-error");
        shell.classList.add(state);
    }

    function prepare(image) {
        if (!image || image.dataset.progressiveBound === "true") return;
        image.dataset.progressiveBound = "true";
        const reveal = () => {
            const decoded = typeof image.decode === "function" ? image.decode() : Promise.resolve();
            decoded.catch(() => undefined).finally(() => finish(image, "is-loaded"));
        };
        image.addEventListener("load", reveal, {once: true});
        image.addEventListener("error", () => finish(image, "is-error"), {once: true});
        if (image.complete) {
            if (image.naturalWidth > 0) reveal();
            else finish(image, "is-error");
        }
    }

    function prepareAll(root) {
        root.querySelectorAll("[data-progressive-image]").forEach(prepare);
    }

    function replace(image, url, alt) {
        if (!image) return;
        const shell = image.closest("[data-image-shell]");
        shell?.classList.remove("is-loaded", "is-error");
        delete image.dataset.progressiveBound;
        image.src = url;
        image.removeAttribute("srcset");
        image.alt = alt || "Product image";
        prepare(image);
    }

    window.EmporiumImages = {prepare, prepareAll, replace};
    document.addEventListener("DOMContentLoaded", () => prepareAll(document));
    document.addEventListener("htmx:afterSwap", event => prepareAll(event.detail.target));
}());
