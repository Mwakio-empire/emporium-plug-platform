document.addEventListener('DOMContentLoaded', function () {
  'use strict';
  const button = document.getElementById('add-intake-line');
  const container = document.getElementById('intake-lines');
  if (!button || !container) return;
  button.addEventListener('click', function () {
    const row = container.querySelector('.intake-line');
    if (!row) return;
    const clone = row.cloneNode(true);
    clone.querySelectorAll('select,input').forEach(function (field) { field.value = ''; });
    container.appendChild(clone);
  });
});
