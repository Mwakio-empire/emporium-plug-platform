(() => {
  const body = document.body;
  const openButton = document.querySelector('[data-sidebar-open]');
  const closeButtons = document.querySelectorAll('[data-sidebar-close]');
  const scrim = document.querySelector('.ep-sidebar-scrim');
  const setOpen = (open) => {
    body.classList.toggle('ep-sidebar-open', open);
    if (openButton) openButton.setAttribute('aria-expanded', String(open));
    if (scrim) scrim.hidden = !open;
  };
  openButton?.addEventListener('click', () => setOpen(true));
  closeButtons.forEach(button => button.addEventListener('click', () => setOpen(false)));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') setOpen(false); });
})();
