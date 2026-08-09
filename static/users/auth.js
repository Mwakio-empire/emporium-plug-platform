document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('input[type="password"]').forEach((input) => {
    if (!input.id || document.querySelector(`[data-password-toggle-for="${input.id}"]`)) {
      return;
    }

    const wrapper = document.createElement('span');
    wrapper.className = 'relative block';
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);
    input.style.paddingRight = '3rem';

    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.passwordToggleFor = input.id;
    button.className = 'absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg text-slate-500 transition hover:text-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500';
    button.setAttribute('aria-label', 'Show password');
    button.setAttribute('title', 'Show password');
    button.setAttribute('aria-controls', input.id);
    button.setAttribute('aria-pressed', 'false');
    const setIcon = (showing) => {
      button.innerHTML = showing
        ? '<svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>'
        : '<svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18"/><path d="M10.6 10.7a2 2 0 0 0 2.7 2.7"/><path d="M9.9 4.2A10.5 10.5 0 0 1 12 4c5.5 0 9 5 9 5a16.7 16.7 0 0 1-2.2 2.8"/><path d="M6.6 6.6C4.4 8.1 3 10 3 10s3.5 5 9 5c1 0 2-.2 2.9-.5"/></svg>';
    };
    setIcon(false);
    button.addEventListener('click', () => {
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      const label = showing ? 'Show password' : 'Hide password';
      button.setAttribute('aria-label', label);
      button.setAttribute('title', label);
      button.setAttribute('aria-pressed', String(!showing));
      setIcon(!showing);
    });
    wrapper.appendChild(button);
  });

  document.querySelectorAll('[data-password-policy-input="true"]').forEach((input) => {
    const policy = input.closest('div')?.querySelector('[data-password-policy]');
    if (!policy) {
      return;
    }
    const update = () => {
      const length = Array.from(input.value).length;
      policy.textContent = length
        ? `${length} of at least 15 characters. A memorable passphrase works well.`
        : 'Use at least 15 characters. A memorable passphrase works well.';
    };
    input.addEventListener('input', update);
    update();
  });
});
