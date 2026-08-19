const deleteTrigger = document.querySelector("[data-delete-trigger]");
const deleteForm = document.querySelector("[data-delete-form]");

window.JoshsCornerAutosave?.initialise();

if (deleteTrigger && deleteForm) {
  deleteTrigger.addEventListener("click", () => {
    const confirmed = window.confirm(
      "Delete this journal entry? This cannot be undone."
    );
    if (confirmed) {
      deleteForm.submit();
    }
  });
}

const integration = document.querySelector("[data-journal-integration]");
const entryForm = document.querySelector(".entry-form");

if (integration && entryForm) {
  const linkedDeadline = integration.dataset.hasDeadlineLink === "true";
  const linkedUpcoming = integration.dataset.hasUpcomingLink === "true";
  const deadlineToggle = integration.querySelector('[data-link-toggle="deadline"]');
  const upcomingToggle = integration.querySelector('[data-link-toggle="upcoming"]');

  for (const toggle of integration.querySelectorAll("[data-link-toggle]")) {
    const fields = integration.querySelector(`[data-link-fields="${toggle.dataset.linkToggle}"]`);
    const updateFields = () => { fields.hidden = !toggle.checked; };
    toggle.addEventListener("change", updateFields);
    updateFields();
  }

  entryForm.addEventListener("submit", (event) => {
    const removals = [
      [linkedDeadline, deadlineToggle, "confirm_remove_deadline", "Remove linked Deadline? The Journal entry will be kept."],
      [linkedUpcoming, upcomingToggle, "confirm_remove_upcoming", "Remove linked Upcoming event? The Journal entry will be kept."],
    ];
    for (const [isLinked, toggle, name, message] of removals) {
      if (!isLinked || toggle.checked || entryForm.querySelector(`[name="${name}"]`)) continue;
      if (!window.confirm(message)) {
        event.preventDefault();
        toggle.checked = true;
        integration.querySelector(`[data-link-fields="${toggle.dataset.linkToggle}"]`).hidden = false;
        return;
      }
      const confirmation = document.createElement("input");
      confirmation.type = "hidden";
      confirmation.name = name;
      confirmation.value = "1";
      entryForm.append(confirmation);
    }
  });
}

const yearSelector = document.querySelector("[data-year-selector]");

yearSelector?.addEventListener("change", () => {
  yearSelector.form?.requestSubmit();
});
