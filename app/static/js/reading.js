(() => {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const filterParameters = ["q", "format", "type", "status", "rating"];
  let activeDetail = null;

  const isDirty = () => Boolean(activeDetail?.textDirty && !activeDetail.submitting);
  const confirmLeavingDirtyDetail = () => !isDirty() || window.confirm("You have unsaved changes. Leave without saving?");

  const setSelectedBook = (bookId) => {
    document.querySelectorAll(".book-card").forEach((card) => {
      const link = card.querySelector(".book-card-link");
      const selected = link && new URL(link.href).searchParams.get("book_id") === String(bookId);
      card.classList.toggle("active", selected);
      if (selected) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  };

  const updateSidebarCard = (result) => {
    if (!result?.sidebar_card_html || !Number.isInteger(Number(result.book_id))) return;
    const current = document.querySelector(`[data-book-card-id="${Number(result.book_id)}"]`);
    const list = current?.closest("[data-sidebar-list]");
    if (!current || !list) return;
    const template = document.createElement("template");
    template.innerHTML = result.sidebar_card_html.trim();
    const replacement = template.content.querySelector(".book-card");
    if (!replacement) return;
    const scrollTop = list.scrollTop;
    current.replaceWith(replacement);
    list.scrollTop = scrollTop;
    setSelectedBook(result.book_id);
  };

  const initialiseReadingDetail = (panel) => {
    const form = panel?.querySelector("[data-book-editor]");
    if (!form || form.dataset.readingDetailReady) return activeDetail;
    form.dataset.readingDetailReady = "1";
    const saveState = form.querySelector("[data-save-state]");
    const autosaveUrl = form.dataset.autosaveUrl;
    const notesInput = form.querySelector('input[name="notes"]');
    const notesBody = form.querySelector("[data-rich-body]");
    const attachmentToken = form.querySelector('input[name="notes_attachment_token"]');
    const detail = { form, textDirty: Boolean(panel.querySelector(".book-error")), submitting: false, menuDirty: false, autosaveTimer: null, worker: null };
    const setSaveState = (text, state = "") => {
      if (!saveState) return;
      saveState.textContent = text;
      saveState.classList.remove("saving", "failed", "retrying");
      if (state) saveState.classList.add(state);
    };
    const syncNotes = () => { if (notesInput && notesBody) notesInput.value = notesBody.innerHTML; };
    syncNotes();
    let manualSnapshot = { title: form.elements.title?.value || "", notes: notesInput?.value || "" };
    const payload = () => ({
      title: manualSnapshot.title,
      format: form.elements.format.value,
      book_type: form.elements.book_type.value,
      status: form.elements.status.value,
      release_date: form.elements.release_date.value,
      rating: form.elements.rating.value,
      notes: manualSnapshot.notes,
      notes_attachment_token: attachmentToken?.value || "",
      q: form.elements.q?.value || "",
      filter_format: form.elements.filter_format?.value || "all",
      filter_type: form.elements.filter_type?.value || "all",
      filter_status: form.elements.filter_status?.value || "all",
      filter_rating: form.elements.filter_rating?.value || "all",
    });
    const runQueue = async () => {
      let succeeded = true;
      while (detail.menuDirty) {
        detail.menuDirty = false;
        setSaveState("Saving…", "saving");
        try {
          const response = await fetch(autosaveUrl, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify(payload()) });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(result.error || "Save failed.");
          updateSidebarCard(result);
          if (!detail.menuDirty) setSaveState(detail.textDirty ? "Unsaved changes" : "Saved");
        } catch (error) {
          detail.menuDirty = true;
          succeeded = false;
          setSaveState(navigator.onLine ? "Save failed" : "Offline / retrying", navigator.onLine ? "failed" : "retrying");
          break;
        }
      }
      return succeeded;
    };
    const flushAutosave = () => {
      clearTimeout(detail.autosaveTimer);
      if (!autosaveUrl) return Promise.resolve(true);
      if (!detail.worker) detail.worker = runQueue().finally(() => { detail.worker = null; });
      return detail.worker;
    };
    const scheduleAutosave = (delay = 0) => {
      if (!autosaveUrl) { setSaveState("Unsaved changes"); return; }
      detail.menuDirty = true;
      clearTimeout(detail.autosaveTimer);
      detail.autosaveTimer = setTimeout(flushAutosave, delay);
    };
    const markTextDirty = () => { detail.textDirty = true; setSaveState("Unsaved changes"); };
    const stars = form.querySelectorAll("[data-book-stars] .book-star");
    const ratingInput = form.querySelector("[data-rating-input]");
    const ratingDisplay = form.querySelector("[data-rating-value]");
    const setRating = (rating) => {
      if (!ratingInput) return;
      ratingInput.value = rating === 0 ? "0" : rating.toFixed(1);
      stars.forEach((star) => {
        const value = Number(star.dataset.star);
        star.style.setProperty("--fill", rating >= value ? 100 : rating === value - 0.5 ? 50 : 0);
      });
      if (ratingDisplay) ratingDisplay.textContent = rating ? `${rating.toFixed(1)} / 5` : "Not rated";
      scheduleAutosave();
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
    form.querySelectorAll('[name="format"], [name="book_type"], [name="status"], [name="release_date"]').forEach((field) => field.addEventListener("change", scheduleAutosave));
    notesBody?.addEventListener("input", markTextDirty);
    form.querySelector('[name="title"]')?.addEventListener("input", markTextDirty);
    const saveManually = async () => {
      syncNotes();
      detail.submitting = true;
      setSaveState("Saving…", "saving");
      try {
        const response = await fetch(form.action, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-Requested-With": "JoshCornerPartial", "X-CSRFToken": csrfToken() },
          body: new FormData(form),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || "Save failed.");
        manualSnapshot = { title: form.elements.title?.value || "", notes: notesInput?.value || "" };
        detail.textDirty = false;
        updateSidebarCard(result);
        setSaveState("Saved");
      } catch (error) {
        setSaveState("Save failed", "failed");
      } finally {
        detail.submitting = false;
      }
    };
    form.addEventListener("submit", (event) => {
      syncNotes();
      if (!form.dataset.bookId) return;
      event.preventDefault();
      saveManually();
    });
    const deleteButton = panel.querySelector("[data-book-delete]");
    const deleteForm = panel.querySelector("[data-book-delete-form]");
    if (deleteButton && deleteForm) deleteButton.addEventListener("click", () => { if (window.confirm("Delete this book permanently?")) deleteForm.requestSubmit(); });
    activeDetail = detail;
    return detail;
  };

  const partialUrlFor = (destination) => {
    const bookId = destination.searchParams.get("book_id");
    if (!bookId || !/^\d+$/.test(bookId)) return null;
    const partial = new URL(`/reading/detail/${bookId}`, window.location.origin);
    filterParameters.forEach((name) => {
      const value = destination.searchParams.get(name);
      if (value !== null) partial.searchParams.set(name, value);
    });
    return partial;
  };

  const isOrdinarySidebarClick = (event, link, sidebar) => event.button === 0 && !event.defaultPrevented && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && !link.target && !link.hasAttribute("download") && sidebar.contains(link) && new URL(link.href, window.location.href).origin === window.location.origin;

  document.addEventListener("DOMContentLoaded", () => {
    const filters = document.querySelector("[data-book-filters]");
    const search = document.querySelector("[data-book-search]");
    const sidebar = document.querySelector("[data-sidebar-module='reading']");
    const slot = document.querySelector("[data-reading-detail-slot]");
    let searchTimer;
    let currentUrl = window.location.pathname + window.location.search;
    if (search && filters) search.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => filters.requestSubmit(), 350); });
    document.querySelectorAll("[data-book-filter]").forEach((filter) => filter.addEventListener("change", () => filters.requestSubmit()));
    window.JoshsCornerRichText?.initialise(slot);
    initialiseReadingDetail(slot);
    window.addEventListener("beforeunload", (event) => { if (isDirty()) { event.preventDefault(); event.returnValue = ""; } });

    const addDetailError = (destination, retry) => {
      slot.querySelector("[data-reading-navigation-error]")?.remove();
      const error = document.createElement("div");
      error.className = "reading-navigation-error";
      error.dataset.readingNavigationError = "";
      error.setAttribute("role", "alert");
      error.innerHTML = "<span>Could not open that book. Your current editor is still available.</span>";
      const retryButton = document.createElement("button"); retryButton.type = "button"; retryButton.textContent = "Retry"; retryButton.addEventListener("click", retry, { once: true });
      const fallback = document.createElement("a"); fallback.href = destination.pathname + destination.search; fallback.textContent = "Open normally";
      error.append(" ", retryButton, " ", fallback); slot.prepend(error);
    };
    const loadBook = async (destination, { push = false } = {}) => {
      const partial = partialUrlFor(destination);
      if (!partial || !slot) return false;
      slot.classList.add("is-loading");
      slot.querySelector("[data-reading-navigation-error]")?.remove();
      try {
        const response = await fetch(partial, { credentials: "same-origin", headers: { "X-Requested-With": "JoshCornerPartial" } });
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        const fragment = await response.text();
        window.JoshsCornerRichText?.destroy(slot);
        slot.innerHTML = fragment;
        window.JoshsCornerRichText?.initialise(slot);
        activeDetail = null;
        initialiseReadingDetail(slot);
        const bookId = destination.searchParams.get("book_id");
        setSelectedBook(bookId);
        currentUrl = destination.pathname + destination.search;
        if (push) history.pushState({ readingBookId: bookId }, "", currentUrl);
        return true;
      } catch (error) {
        addDetailError(destination, () => loadBook(destination, { push }));
        return false;
      } finally { slot.classList.remove("is-loading"); }
    };
    sidebar?.addEventListener("click", (event) => {
      const link = event.target.closest(".book-card-link");
      if (!link || !isOrdinarySidebarClick(event, link, sidebar)) return;
      if (!confirmLeavingDirtyDetail()) { event.preventDefault(); return; }
      event.preventDefault();
      loadBook(new URL(link.href, window.location.href), { push: true });
    });
    sidebar?.querySelector(".new-book")?.addEventListener("click", (event) => {
      if (isOrdinarySidebarClick(event, event.currentTarget, sidebar) && !confirmLeavingDirtyDetail()) event.preventDefault();
    });
    window.addEventListener("popstate", () => {
      const destination = new URL(window.location.href);
      if (!partialUrlFor(destination)) { window.location.assign(destination); return; }
      if (!confirmLeavingDirtyDetail()) { history.pushState({ readingBookId: activeDetail?.form?.dataset.bookId }, "", currentUrl); return; }
      loadBook(destination);
    });
    window.JoshsCornerReading = { initialiseReadingDetail, isOrdinarySidebarClick, loadBook };
  });
})();
