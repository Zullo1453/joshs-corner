(() => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  const resizeTextarea = (field) => {
    field.style.height = 'auto';
    const height = Math.min(field.scrollHeight, 256);
    field.style.height = `${height}px`;
    field.style.overflowY = field.scrollHeight > 256 ? 'auto' : 'hidden';
  };
  document.querySelectorAll('.lists-page textarea').forEach((field) => {
    resizeTextarea(field);
    field.addEventListener('input', () => resizeTextarea(field));
  });
  document.querySelectorAll('.editor-panel').forEach((panel) => panel.addEventListener('toggle', () => {
    if (!panel.open) return;
    document.querySelectorAll('.editor-panel[open]').forEach((other) => {
      if (other !== panel) other.open = false;
    });
    panel.querySelectorAll('textarea').forEach(resizeTextarea);
  }));
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
    if (data.list_completed) window.location.assign('/lists/?completed=1');
  }));
  document.querySelectorAll('[data-list-fast-add]').forEach((form) => form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'Accept': 'application/json', 'X-CSRFToken': token}});
    if (!response.ok) { form.submit(); return; }
    form.reset(); form.querySelectorAll('textarea').forEach(resizeTextarea); form.querySelector('[name="text"]').focus();
    // The server has persisted the item; refreshing only after an explicit add keeps the fast path reliable.
    window.location.reload();
  }));
})();
