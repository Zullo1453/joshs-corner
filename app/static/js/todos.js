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
