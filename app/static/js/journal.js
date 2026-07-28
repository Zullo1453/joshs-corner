const deleteTrigger = document.querySelector("[data-delete-trigger]");
const deleteForm = document.querySelector("[data-delete-form]");

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
