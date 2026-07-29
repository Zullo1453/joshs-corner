document.addEventListener("DOMContentLoaded", () => {
  const filters = document.querySelector("[data-book-filters]");
  const search = document.querySelector("[data-book-search]");
  let searchTimer;
  if (search && filters) {
    search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => filters.requestSubmit(), 350);
    });
  }
  document.querySelectorAll("[data-book-filter]").forEach((filter) => {
    filter.addEventListener("change", () => filters.requestSubmit());
  });

  const form = document.querySelector("[data-book-editor]");
  const saveState = document.querySelector("[data-save-state]");
  const autosaveUrl = form?.dataset.autosaveUrl;
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const notesInput = form?.querySelector('input[name="notes"]');
  const notesBody = form?.querySelector("[data-rich-body]");
  const attachmentToken = form?.querySelector('input[name="notes_attachment_token"]');
  let autosaveTimer;
  let worker = null;
  let dirty = false;

  const setSaveState = (text, state = "") => {
    if (!saveState) return;
    saveState.textContent = text;
    saveState.classList.remove("saving", "failed", "retrying");
    if (state) saveState.classList.add(state);
  };
  const syncNotes = () => {
    if (notesInput && notesBody) notesInput.value = notesBody.innerHTML;
  };
  const payload = () => {
    syncNotes();
    return {
      title: form.elements.title.value,
      format: form.elements.format.value,
      book_type: form.elements.book_type.value,
      status: form.elements.status.value,
      release_date: form.elements.release_date.value,
      rating: form.elements.rating.value,
      notes: notesInput?.value || "",
      notes_attachment_token: attachmentToken?.value || "",
    };
  };
  const runQueue = async () => {
    let succeeded = true;
    while (dirty) {
      dirty = false;
      setSaveState("Saving…", "saving");
      try {
        const response = await fetch(autosaveUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
          body: JSON.stringify(payload()),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || "Save failed.");
        if (!dirty) setSaveState("Saved");
      } catch (error) {
        dirty = true;
        succeeded = false;
        setSaveState(navigator.onLine ? "Save failed" : "Offline / retrying", navigator.onLine ? "failed" : "retrying");
        break;
      }
    }
    return succeeded;
  };
  const flushAutosave = () => {
    clearTimeout(autosaveTimer);
    if (!autosaveUrl) return Promise.resolve(true);
    if (!worker) {
      worker = runQueue().finally(() => { worker = null; });
    }
    return worker;
  };
  const scheduleAutosave = (delay) => {
    if (!autosaveUrl) {
      setSaveState("Unsaved changes");
      return;
    }
    dirty = true;
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(flushAutosave, delay);
  };

  const stars = document.querySelectorAll("[data-book-stars] .book-star");
  const ratingInput = document.querySelector("[data-rating-input]");
  const ratingDisplay = document.querySelector("[data-rating-value]");
  const setRating = (rating) => {
    if (!ratingInput) return;
    ratingInput.value = rating === 0 ? "0" : rating.toFixed(1);
    stars.forEach((star) => {
      const value = Number(star.dataset.star);
      star.style.setProperty("--fill", rating >= value ? 100 : rating === value - 0.5 ? 50 : 0);
    });
    if (ratingDisplay) ratingDisplay.textContent = rating ? `${rating.toFixed(1)} / 5` : "Not rated";
    scheduleAutosave(0);
  };
  stars.forEach((star) => {
    star.addEventListener("click", (event) => {
      const box = star.getBoundingClientRect();
      setRating(Number(star.dataset.star) - (event.clientX - box.left < box.width / 2 ? 0.5 : 0));
    });
    star.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") { event.preventDefault(); setRating(Number(star.dataset.star) - 0.5); }
      if (["Enter", " ", "ArrowRight"].includes(event.key)) { event.preventDefault(); setRating(Number(star.dataset.star)); }
    });
  });

  form?.querySelectorAll('[name="format"], [name="book_type"], [name="status"], [name="release_date"]').forEach((field) => {
    field.addEventListener("change", () => scheduleAutosave(0));
  });
  notesBody?.addEventListener("input", () => scheduleAutosave(1000));
  form?.querySelector('[name="title"]')?.addEventListener("input", () => setSaveState("Unsaved changes"));

  form?.addEventListener("submit", async (event) => {
    if (!autosaveUrl) return;
    event.preventDefault();
    syncNotes();
    await flushAutosave();
    form.submit();
  });
  document.querySelectorAll(".book-card-link, .new-book").forEach((link) => {
    link.addEventListener("click", async (event) => {
      if (!autosaveUrl || (!dirty && !worker) || event.defaultPrevented) return;
      event.preventDefault();
      syncNotes();
      if (await flushAutosave()) window.location.assign(link.href);
    });
  });
  window.addEventListener("pagehide", () => {
    if (dirty || worker) flushAutosave();
  });

  const deleteButton = document.querySelector("[data-book-delete]");
  const deleteForm = document.querySelector("[data-book-delete-form]");
  if (deleteButton && deleteForm) {
    deleteButton.addEventListener("click", () => {
      if (confirm("Delete this book permanently?")) deleteForm.requestSubmit();
    });
  }
});
