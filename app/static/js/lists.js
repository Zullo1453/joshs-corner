(() => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  document.querySelectorAll('[data-list-toggle]').forEach((form) => form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const response = await fetch(form.action, {method: 'POST', headers: {'Accept': 'application/json', 'X-CSRFToken': token}});
    if (!response.ok) { form.submit(); return; }
    const item = form.closest('[data-list-item]'), data = await response.json();
    item.classList.toggle('is-completed', data.completed);
    form.querySelector('.check-button').textContent = data.completed ? '✓' : '';
    form.querySelector('.check-button').setAttribute('aria-label', data.completed ? 'Mark incomplete' : 'Mark complete');
    const target = data.completed ? document.querySelector('[data-completed-items]') : document.querySelector(`[data-active-items][data-section-id="${data.section_id || ''}"]`);
    if (target) target.append(item);
  }));
  document.querySelectorAll('[data-list-fast-add]').forEach((form) => form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'Accept': 'application/json', 'X-CSRFToken': token}});
    if (!response.ok) { form.submit(); return; }
    form.reset(); form.querySelector('[name="text"]').focus();
    // The server has persisted the item; refreshing only after an explicit add keeps the fast path reliable.
    window.location.reload();
  }));
})();
