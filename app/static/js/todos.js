const archive = document.querySelector("[data-archive]");
const archiveToggle = document.querySelector("[data-archive-toggle]");

archiveToggle?.addEventListener("click", () => {
  const isOpen = archive.classList.toggle("open");
  archiveToggle.setAttribute("aria-expanded", String(isOpen));
});

document.querySelectorAll("[data-delete-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm("Delete this to-do? This cannot be undone.")) {
      event.preventDefault();
    }
  });
});
