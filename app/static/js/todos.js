document.querySelectorAll("[data-archive-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm("Archive this task? Its history will be retained.")) event.preventDefault();
  });
});

document.querySelectorAll(".add-row").forEach((form) => {
  form.addEventListener("submit", () => {
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
  });
});

document.querySelectorAll("[data-project-archive]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm("Archive this project and suspend its unfinished tasks? Historical activity will be retained.")) event.preventDefault();
  });
});

document.querySelectorAll("[data-task-edit]").forEach((button) => {
  const card = button.closest(".task");
  const form = card?.querySelector("[data-task-edit-form]");
  const input = form?.querySelector('input[name="text"]');
  const cancel = form?.querySelector("[data-task-edit-cancel]");
  const save = form?.querySelector("[data-task-edit-save]");
  if (!card || !form || !input) return;

  const close = () => { form.reset(); form.hidden = true; card.classList.remove("is-editing"); };
  button.addEventListener("click", () => {
    form.hidden = false; card.classList.add("is-editing"); input.focus({ preventScroll: true }); input.select();
  });
  cancel?.addEventListener("click", close);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); close(); button.focus({ preventScroll: true }); }
    if (event.key === "Enter") { event.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting) { event.preventDefault(); return; }
    const value = input.value.trim();
    if (!value) { event.preventDefault(); input.setCustomValidity("A task title is required."); input.reportValidity(); return; }
    input.setCustomValidity(""); input.value = value; form.dataset.submitting = "1"; if (save) save.disabled = true;
  });
});
