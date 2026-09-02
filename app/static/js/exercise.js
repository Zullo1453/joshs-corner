// Confirmation is limited to explicit destructive Exercise forms.
document.addEventListener("submit", event => {
  const message = event.target.dataset.exerciseConfirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
