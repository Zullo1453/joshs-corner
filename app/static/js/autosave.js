(() => {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const richInputs = (form) => form.querySelectorAll("[data-rich-editor]").forEach((root) => { const body = root.querySelector("[data-rich-body]"), input = root.querySelector("[data-rich-input]"); if (body && input) input.value = body.innerHTML; });
  class AutosaveController {
    constructor(form) {
      this.form = form; this.url = form.dataset.autosaveUrl; this.state = form.querySelector("[data-save-state]"); this.dirtyText = false;
      if (!this.url) return;
      richInputs(form); this.manualValues = this.manualFieldValues();
      form.querySelectorAll("select, input[type=date], input[type=number], input[type=checkbox], input[name=platform], input[name=genre], [data-autosave-immediate]").forEach((field) => field.addEventListener("change", () => this.saveMenu()));
      form.querySelectorAll("input[type=text]:not([name=platform]):not([name=genre]), input:not([type]), [data-manual-text], [data-rich-body]").forEach((field) => field.addEventListener("input", () => this.markDirty()));
      form.addEventListener("submit", () => { richInputs(form); this.dirtyText = false; });
      document.querySelectorAll("[data-sidebar-select]").forEach((link) => link.addEventListener("click", (event) => { if (this.dirtyText && !window.confirm("You have unsaved changes. Leave without saving?")) event.preventDefault(); }));
      window.addEventListener("beforeunload", (event) => { if (this.dirtyText) { event.preventDefault(); event.returnValue = ""; } });
    }
    setState(text, kind = "") { if (!this.state) return; this.state.textContent = text; this.state.classList.remove("saving", "failed", "retrying"); if (kind) this.state.classList.add(kind); }
    manualFieldValues() { const values = {}; this.form.querySelectorAll("input[type=text], input:not([type]), [data-rich-input]").forEach((field) => { values[field.name] = field.value; }); return values; }
    data(menuOnly = false) { richInputs(this.form); const values = Object.fromEntries(new FormData(this.form).entries()); return menuOnly ? { ...values, ...this.manualValues } : values; }
    markDirty() { this.dirtyText = true; this.setState("Unsaved changes"); }
    async saveMenu() { this.setState("Saving…", "saving"); try { const response = await fetch(this.url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify(this.data(true)) }); const result = await response.json().catch(() => ({})); if (!response.ok) throw new Error(result.error || "Save failed."); this.setState(this.dirtyText ? "Unsaved changes" : "Saved"); } catch (_) { this.setState("Save failed", "failed"); } }
  }
  window.JoshsCornerAutosave = { initialise(selector = "[data-autosave-url]") { return [...document.querySelectorAll(selector)].map((form) => new AutosaveController(form)); } };
})();
