(() => {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const richInputs = (form) => form.querySelectorAll("[data-rich-editor]").forEach((root) => {
    const body = root.querySelector("[data-rich-body]");
    const input = root.querySelector("[data-rich-input]");
    if (body && input) input.value = body.innerHTML;
  });

  class AutosaveController {
    constructor(form) {
      this.form = form;
      this.url = form.dataset.autosaveUrl;
      this.state = form.querySelector("[data-save-state]");
      this.timer = null;
      this.worker = null;
      this.dirty = false;
      if (!this.url) return;
      form.querySelectorAll("select, input[type=date], input[type=number], input[type=checkbox], [data-autosave-immediate]").forEach((field) => field.addEventListener("change", () => this.schedule(0)));
      form.querySelectorAll("input[type=text], input:not([type]), [data-autosave-text], [data-rich-body]").forEach((field) => field.addEventListener("input", () => this.schedule(1000)));
      form.addEventListener("submit", async (event) => {
        if (event.submitter?.matches("[data-autosave-skip]")) return;
        event.preventDefault();
        richInputs(form);
        await this.flush();
        form.submit();
      });
      document.querySelectorAll("[data-sidebar-select]").forEach((link) => link.addEventListener("click", async (event) => {
        if ((!this.dirty && !this.worker) || event.defaultPrevented) return;
        event.preventDefault();
        richInputs(form);
        if (await this.flush()) window.location.assign(link.href);
      }));
      window.addEventListener("pagehide", () => { if (this.dirty || this.worker) this.flush(); });
    }

    setState(text, kind = "") {
      if (!this.state) return;
      this.state.textContent = text;
      this.state.classList.remove("saving", "failed", "retrying");
      if (kind) this.state.classList.add(kind);
    }

    data() {
      richInputs(this.form);
      return Object.fromEntries(new FormData(this.form).entries());
    }

    schedule(delay) {
      this.dirty = true;
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.flush(), delay);
    }

    async saveQueued() {
      let success = true;
      while (this.dirty) {
        this.dirty = false;
        this.setState("Saving…", "saving");
        try {
          const response = await fetch(this.url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify(this.data()) });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(result.error || "Save failed.");
          if (!this.dirty) this.setState("Saved");
        } catch (_) {
          this.dirty = true;
          success = false;
          this.setState(navigator.onLine ? "Save failed" : "Retrying", navigator.onLine ? "failed" : "retrying");
          break;
        }
      }
      return success;
    }

    flush() {
      clearTimeout(this.timer);
      if (!this.worker) this.worker = this.saveQueued().finally(() => { this.worker = null; });
      return this.worker;
    }
  }

  window.JoshsCornerAutosave = {
    initialise(selector = "[data-autosave-url]") { return [...document.querySelectorAll(selector)].map((form) => new AutosaveController(form)); },
  };
})();
