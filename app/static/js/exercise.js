// Confirmation is limited to explicit destructive Exercise forms.
document.addEventListener("submit", event => {
  const message = event.target.dataset.exerciseConfirm;
  if (message && !window.confirm(message)) event.preventDefault();
});

// Only explicit workout targets are scrolled; ordinary navigation is unchanged.
function focusWorkoutTarget() {
  if (!/^#(?:exercise|set-entry|saved-set)-\d+$/.test(location.hash)) return;
  const target = document.getElementById(location.hash.slice(1));
  if (target) {
    target.scrollIntoView({block: 'start', behavior: 'instant'});
    if (target.matches('form')) target.querySelector('input:not([type=hidden])')?.focus({preventScroll:true});
  }
}
window.addEventListener('load', focusWorkoutTarget);
window.addEventListener('hashchange', focusWorkoutTarget);
document.addEventListener('change', event => {
  if (!event.target.matches('[data-route-picker]')) return;
  const distance = event.target.selectedOptions[0]?.dataset.distance;
  if (distance) event.target.form.querySelector('[name=distance_km]').value = distance;
});
