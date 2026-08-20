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

  const journalDate = integration.dataset.journalDate;
  const dateFieldFor = (kind) => integration.querySelector(
    kind === "deadline" ? '[name="deadline_due_date"]' : '[name="upcoming_event_date"]'
  );
  const setFieldsVisible = (kind, visible) => {
    const fields = integration.querySelector(`[data-link-fields="${kind}"]`);
    if (fields) fields.hidden = !visible;
  };
  const enableLink = (kind, title = "") => {
    const toggle = integration.querySelector(`[data-link-toggle="${kind}"]`);
    if (!toggle) return;
    toggle.checked = true;
    setFieldsVisible(kind, true);
    const titleField = integration.querySelector(
      kind === "deadline" ? '[name="deadline_title"]' : '[name="upcoming_title"]'
    );
    if (title) titleField.value = title;
    const dateField = dateFieldFor(kind);
    if (dateField && !dateField.value) dateField.value = journalDate;
  };

  for (const toggle of integration.querySelectorAll("[data-link-toggle]")) {
    const fields = integration.querySelector(`[data-link-fields="${toggle.dataset.linkToggle}"]`);
    const updateFields = () => {
      setFieldsVisible(toggle.dataset.linkToggle, toggle.checked);
      if (toggle.checked) {
        const dateField = dateFieldFor(toggle.dataset.linkToggle);
        if (dateField && !dateField.value) dateField.value = journalDate;
      }
    };
    toggle.addEventListener("change", updateFields);
    updateFields();
  }

  const editor = entryForm.querySelector("[data-rich-body]");
  const normaliseTitle = (value) => value.replace(/\s+/g, " ").trim().slice(0, 200);
  const selectionActions = document.createElement("div");
  selectionActions.className = "journal-selection-actions";
  selectionActions.hidden = true;
  selectionActions.setAttribute("role", "group");
  selectionActions.setAttribute("aria-label", "Add selected journal text to");
  selectionActions.innerHTML = '<button type="button" data-selection-link="deadline">Add to Deadline</button><button type="button" data-selection-link="upcoming">Add to Upcoming</button>';
  document.body.append(selectionActions);

  let selectedTitle = "";
  let retainingSelection = false;
  const selectedEditorText = () => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount || !editor) return null;
    const range = selection.getRangeAt(0);
    const ancestor = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
      ? range.commonAncestorContainer
      : range.commonAncestorContainer.parentElement;
    if (!ancestor || !editor.contains(ancestor)) return null;
    return { range, title: normaliseTitle(range.cloneContents().textContent || "") };
  };
  const hideSelectionActions = () => { selectionActions.hidden = true; selectedTitle = ""; delete selectionActions.dataset.selectedTitle; };
  const showSelectionActions = () => {
    const selected = selectedEditorText();
    if (!selected?.title) return hideSelectionActions();
    selectedTitle = selected.title;
    selectionActions.dataset.selectedTitle = selected.title;
    const rect = selected.range.getBoundingClientRect();
    selectionActions.hidden = false;
    selectionActions.style.left = `${Math.max(8, Math.min(window.innerWidth - selectionActions.offsetWidth - 8, rect.left))}px`;
    selectionActions.style.top = `${Math.max(8, rect.top - selectionActions.offsetHeight - 8)}px`;
  };

  for (const action of selectionActions.querySelectorAll("[data-selection-link]")) {
    const retainCurrentSelection = (event) => {
      retainingSelection = true;
      event.preventDefault();
    };
    action.addEventListener("pointerdown", retainCurrentSelection);
    action.addEventListener("mousedown", retainCurrentSelection);
    action.addEventListener("click", () => {
      enableLink(action.dataset.selectionLink, selectionActions.dataset.selectedTitle || selectedTitle);
      hideSelectionActions();
      retainingSelection = false;
    });
  }
  editor?.addEventListener("mouseup", () => requestAnimationFrame(showSelectionActions));
  editor?.addEventListener("keyup", () => requestAnimationFrame(showSelectionActions));
  editor?.addEventListener("touchend", () => requestAnimationFrame(showSelectionActions));
  document.addEventListener("selectionchange", () => {
    if (!retainingSelection) requestAnimationFrame(showSelectionActions);
  });
  document.addEventListener("pointerdown", (event) => {
    if (!selectionActions.contains(event.target) && !editor?.contains(event.target)) hideSelectionActions();
  });

  window.JoshsCornerJournalQuickCapture = { normaliseTitle };

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
