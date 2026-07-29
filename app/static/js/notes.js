const editor = document.querySelector("[data-note-editor]");
const editorForm = document.querySelector("[data-editor-form]");
const bodyInput = document.querySelector("[data-body-input]");
const titleInput = document.querySelector("[data-title-input]");
const saveState = document.querySelector("[data-save-state]");

window.JoshsCornerAutosave?.initialise();

function markUnsaved() {
  if (saveState) {
    saveState.textContent = "Unsaved changes";
  }
}

if (editor && editorForm && bodyInput) {
  editor.addEventListener("input", markUnsaved);
  titleInput?.addEventListener("input", markUnsaved);

  editorForm.addEventListener("submit", () => {
    bodyInput.value = editor.innerHTML;
  });

  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => {
      editor.focus();
      document.execCommand(
        button.dataset.command,
        false,
        button.dataset.value || null
      );
      markUnsaved();
    });
  });

  const quoteToggle = document.querySelector("[data-quote-toggle]");
  const quoteIsActive = () => {
    const selection = window.getSelection();
    const node = selection?.anchorNode;
    const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
    return Boolean(element?.closest("blockquote"));
  };
  const updateQuoteToggle = () => {
    if (!quoteToggle) return;
    const active = quoteIsActive();
    quoteToggle.setAttribute("aria-pressed", String(active));
    quoteToggle.classList.toggle("active", active);
  };

  quoteToggle?.addEventListener("mousedown", (event) => event.preventDefault());
  quoteToggle?.addEventListener("click", () => {
    document.execCommand("formatBlock", false, quoteIsActive() ? "p" : "blockquote");
    editor.focus({ preventScroll: true });
    updateQuoteToggle();
    markUnsaved();
  });
  document.addEventListener("selectionchange", updateQuoteToggle);
  editor.addEventListener("keyup", updateQuoteToggle);
  editor.addEventListener("mouseup", updateQuoteToggle);

  document.querySelector("[data-block-command]")?.addEventListener("change", (event) => {
    editor.focus();
    document.execCommand("formatBlock", false, event.target.value);
    markUnsaved();
  });
}

const deleteTrigger = document.querySelector("[data-delete-trigger]");
const deleteForm = document.querySelector("[data-delete-form]");

if (deleteTrigger && deleteForm) {
  deleteTrigger.addEventListener("click", () => {
    if (window.confirm("Delete this note? This cannot be undone.")) {
      deleteForm.submit();
    }
  });
}

const searchForm = document.querySelector("[data-search-form]");
const searchInput = document.querySelector("[data-search-input]");
let searchTimer;

searchInput?.addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => searchForm?.requestSubmit(), 300);
});
