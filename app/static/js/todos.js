document.querySelectorAll("[data-archive-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm("Archive this task? Its history will be retained.")) event.preventDefault();
  });
});

document.querySelectorAll("form.add-row, [data-recurrence-create]").forEach((form) => {
  form.addEventListener("submit", () => {
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
  });
});

document.querySelectorAll("[data-rollover-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting) { event.preventDefault(); return; }
    form.dataset.submitting = "1";
    const button = form.querySelector("button[type=submit]");
    if (button) button.disabled = true;
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

document.querySelectorAll("[data-task-schedule]").forEach((button) => {
  const card = button.closest(".task");
  const form = card?.querySelector("[data-task-schedule-form]");
  const input = form?.querySelector('input[name="scheduled_date"]');
  const cancel = form?.querySelector("[data-task-schedule-cancel]");
  const save = form?.querySelector("[data-task-schedule-save]");
  if (!card || !form || !input) return;

  const close = () => { form.reset(); form.hidden = true; };
  button.addEventListener("click", () => {
    form.hidden = false; input.focus({ preventScroll: true });
  });
  cancel?.addEventListener("click", () => { close(); button.focus({ preventScroll: true }); });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); close(); button.focus({ preventScroll: true }); }
    if (event.key === "Enter") { event.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting) { event.preventDefault(); return; }
    form.dataset.submitting = "1"; if (save) save.disabled = true;
  });
});

document.querySelectorAll("[data-recurrence-create]").forEach((form) => {
  const type = form.querySelector("[data-recurrence-type]");
  const options = form.querySelector("[data-recurrence-options]");
  const sync = () => {
    const selected = type.value;
    options.hidden = selected === "none";
    options.querySelectorAll("[data-recurrence-for]").forEach((field) => {
      field.hidden = !field.dataset.recurrenceFor.split(" ").includes(selected);
    });
  };
  type.addEventListener("change", sync);
  sync();
});

document.querySelectorAll("[data-recurring-form]").forEach((form) => {
  const type = form.querySelector("[data-recurring-type]");
  const unit = form.querySelector("[data-interval-unit]");
  const fields = form.querySelectorAll("[data-recurring-for]");
  const sync = () => {
    const selected = type.value;
    unit.textContent = selected === "daily" ? "day" : selected === "weekly" ? "week" : "month";
    fields.forEach((field) => { field.hidden = field.dataset.recurringFor !== selected; });
  };
  type.addEventListener("change", sync);
  sync();
});
