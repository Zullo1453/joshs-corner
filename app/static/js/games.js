(() => {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const filterNames = ["q", "status"];
  let activeDetail = null;
  let navigationRequest = 0;

  const hasDirtyDraft = () => Boolean(activeDetail && (activeDetail.gameDirty || activeDetail.playDirty) && !activeDetail.submitting);
  const confirmLeavingDirtyDetail = () => !hasDirtyDraft() || window.confirm("You have unsaved changes. Leave without saving?");

  const setSelectedGame = (gameId) => {
    document.querySelectorAll(".game-card").forEach((card) => {
      const link = card.querySelector(".game-card-link");
      const selected = link && new URL(link.href).searchParams.get("game_id") === String(gameId);
      card.classList.toggle("active", selected);
      if (selected) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  };

  const updateSidebarCard = (result) => {
    if (!result?.sidebar_card_html || !Number.isInteger(Number(result.game_id))) return;
    const current = document.querySelector(`[data-game-card-id="${Number(result.game_id)}"]`);
    const list = current?.closest("[data-sidebar-list]");
    if (!current || !list) return;
    const template = document.createElement("template");
    template.innerHTML = result.sidebar_card_html.trim();
    const replacement = template.content.querySelector(".game-card");
    if (!replacement) return;
    const scrollTop = list.scrollTop;
    current.replaceWith(replacement);
    list.scrollTop = scrollTop;
    setSelectedGame(result.game_id);
  };

  const syncRichText = (scope) => scope?.querySelectorAll("[data-rich-editor]").forEach((root) => {
    const body = root.querySelector("[data-rich-body]");
    const input = root.querySelector("[data-rich-input]");
    if (body && input) input.value = body.innerHTML;
  });

  const destroyGameDetail = (detail = activeDetail) => {
    if (!detail) return;
    clearTimeout(detail.gameTimer);
    detail.destroyed = true;
    if (activeDetail === detail) activeDetail = null;
  };

  const initialiseGameDetail = (panel) => {
    const form = panel?.querySelector("[data-game-editor]");
    if (!form || form.dataset.gameDetailReady) return activeDetail;
    form.dataset.gameDetailReady = "1";

    const saveState = form.querySelector("[data-save-state]");
    const notesInput = form.querySelector('input[name="notes"]');
    const notesBody = form.querySelector("[data-rich-body]");
    const notesToken = form.querySelector('input[name="notes_attachment_token"]');
    const detail = { form, gameDirty: Boolean(panel.querySelector(".game-error")), playDirty: Boolean(panel.querySelector(".game-error")), submitting: false, destroyed: false, gameTimer: null, gameWorker: null, gameMenuDirty: false };
    const setSaveState = (text, kind = "") => {
      if (!saveState) return;
      saveState.textContent = text;
      saveState.classList.remove("saving", "failed", "retrying");
      if (kind) saveState.classList.add(kind);
    };
    const syncNotes = () => { if (notesInput && notesBody) notesInput.value = notesBody.innerHTML; };
    syncNotes();
    let gameSnapshot = { title: form.elements.title?.value || "", notes: notesInput?.value || "" };
    const gamePayload = () => ({
      title: gameSnapshot.title,
      status: form.elements.status?.value || "",
      rating: form.elements.rating?.value || "0",
      platform: form.elements.platform?.value || "",
      hours_played: form.elements.hours_played?.value || "",
      notes: gameSnapshot.notes,
      notes_attachment_token: notesToken?.value || "",
      q: form.elements.q?.value || "",
      filter_status: form.elements.filter_status?.value || "all",
    });
    const runGameMenuSave = async () => {
      while (detail.gameMenuDirty && !detail.destroyed) {
        detail.gameMenuDirty = false;
        setSaveState("Saving…", "saving");
        try {
          const response = await fetch(form.dataset.autosaveUrl, {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
            body: JSON.stringify(gamePayload()),
          });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(result.error || "Save failed.");
          if (detail.destroyed || activeDetail !== detail || !form.isConnected) return;
          updateSidebarCard(result);
          if (!detail.gameMenuDirty) setSaveState(detail.gameDirty || detail.playDirty ? "Unsaved changes" : "Saved");
        } catch (_) {
          if (!detail.destroyed) { detail.gameMenuDirty = true; setSaveState("Save failed", "failed"); }
          break;
        }
      }
    };
    const saveGameMenu = () => {
      if (!form.dataset.autosaveUrl) { setSaveState("Unsaved changes"); return; }
      detail.gameMenuDirty = true;
      clearTimeout(detail.gameTimer);
      detail.gameTimer = setTimeout(() => {
        if (!detail.gameWorker) detail.gameWorker = runGameMenuSave().finally(() => { detail.gameWorker = null; });
      }, 0);
    };
    const markGameDirty = () => { detail.gameDirty = true; setSaveState("Unsaved changes"); };
    const markPlayDirty = () => { detail.playDirty = true; setSaveState("Unsaved changes"); };

    const stars = form.querySelectorAll("[data-rating-stars] .rating-star");
    const ratingInput = form.querySelector("[data-rating-input]");
    const ratingDisplay = form.querySelector("[data-rating-value]");
    const setRating = (rating) => {
      if (!ratingInput) return;
      ratingInput.value = rating === 0 ? "0" : rating.toFixed(1);
      stars.forEach((star) => {
        const value = Number(star.dataset.star);
        star.style.setProperty("--fill", rating >= value ? 100 : rating === value - 0.5 ? 50 : 0);
        star.setAttribute("aria-pressed", String(rating === value || rating === value - 0.5));
      });
      if (ratingDisplay) ratingDisplay.textContent = rating ? `${rating.toFixed(1)} / 5` : "Not rated";
      saveGameMenu();
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
    form.querySelectorAll('[name="status"], [name="platform"], [name="hours_played"]').forEach((field) => field.addEventListener("change", saveGameMenu));
    form.querySelector('[name="title"]')?.addEventListener("input", markGameDirty);
    notesBody?.addEventListener("input", markGameDirty);
    const newPlay = form.querySelector("[data-new-play-entry]");
    newPlay?.querySelectorAll('input, [data-rich-body]').forEach((field) => field.addEventListener(field.matches('[type="date"]') ? "change" : "input", markPlayDirty));

    form.addEventListener("submit", async (event) => {
      const submitter = event.submitter;
      if (!form.dataset.gameId || submitter?.hasAttribute("data-add-play-entry")) {
        if (submitter?.hasAttribute("data-add-play-entry") && detail.gameDirty && !window.confirm("Your game journal has unsaved changes. Add this play entry without saving them?")) event.preventDefault();
        return;
      }
      event.preventDefault();
      syncRichText(form);
      detail.submitting = true;
      setSaveState("Saving…", "saving");
      try {
        const response = await fetch(form.getAttribute("action"), {
          method: "POST", credentials: "same-origin",
          headers: { "X-Requested-With": "JoshCornerPartial", "X-CSRFToken": csrfToken() },
          body: new FormData(form),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || "Save failed.");
        if (detail.destroyed || activeDetail !== detail) return;
        gameSnapshot = { title: form.elements.title?.value || "", notes: notesInput?.value || "" };
        detail.gameDirty = false;
        detail.playDirty = false;
        updateSidebarCard(result);
        setSaveState("Saved");
        const current = new URL(window.location.href);
        await window.JoshsCornerGames?.load(current, false, true);
      } catch (_) {
        if (!detail.destroyed) setSaveState("Save failed", "failed");
      } finally {
        detail.submitting = false;
      }
    });

    panel.querySelectorAll("[data-play-entry-editor]").forEach((playForm) => {
      if (playForm.dataset.gamePlayReady) return;
      playForm.dataset.gamePlayReady = "1";
      const playState = playForm.querySelector("[data-play-save-state]");
      const bodyInput = playForm.querySelector('input[name="body"]');
      const body = playForm.querySelector("[data-rich-body]");
      const attachmentToken = playForm.querySelector('input[name="body_attachment_token"]');
      const setPlayState = (text, kind = "") => { if (!playState) return; playState.textContent = text; playState.classList.remove("saving", "failed"); if (kind) playState.classList.add(kind); };
      const syncBody = () => { if (bodyInput && body) bodyInput.value = body.innerHTML; };
      syncBody();
      let snapshot = { played_on: playForm.elements.played_on?.value || "", title: playForm.elements.title?.value || "", body: bodyInput?.value || "" };
      let timer = null, pending = false, worker = null;
      const payload = () => ({ ...snapshot, played_on: playForm.elements.played_on?.value || "", body_attachment_token: attachmentToken?.value || "" });
      const run = async () => {
        while (pending && !detail.destroyed) {
          pending = false; setPlayState("Saving…", "saving");
          try {
            const response = await fetch(playForm.dataset.autosaveUrl, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify(payload()) });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Save failed.");
            if (detail.destroyed || activeDetail !== detail || !playForm.isConnected) return;
            if (!pending) setPlayState(detail.playDirty ? "Unsaved changes" : "Saved");
          } catch (_) { if (!detail.destroyed) { pending = true; setPlayState("Save failed", "failed"); } break; }
        }
      };
      playForm.querySelector('[name="played_on"]')?.addEventListener("change", () => { pending = true; clearTimeout(timer); timer = setTimeout(() => { if (!worker) worker = run().finally(() => { worker = null; }); }, 0); });
      playForm.querySelector('[name="title"]')?.addEventListener("input", markPlayDirty);
      body?.addEventListener("input", markPlayDirty);
      playForm.addEventListener("submit", (event) => {
        syncBody();
        if (detail.gameDirty && !window.confirm("Your game journal has unsaved changes. Save this play entry without saving them?")) event.preventDefault();
      });
    });
    const deleteTrigger = panel.querySelector("[data-game-delete]");
    const deleteForm = panel.querySelector("[data-game-delete-form]");
    deleteTrigger?.addEventListener("click", () => {
      if (!confirmLeavingDirtyDetail()) return;
      if (window.confirm("Delete this game journal permanently?")) deleteForm?.requestSubmit();
    });
    panel.querySelectorAll("[data-play-delete]").forEach((deleteForm) => deleteForm.addEventListener("submit", (event) => {
      if (!confirmLeavingDirtyDetail() || !window.confirm("Delete this play entry permanently?")) event.preventDefault();
    }));
    activeDetail = detail;
    return detail;
  };

  const partialUrlFor = (destination) => {
    const gameId = destination.searchParams.get("game_id");
    if (!gameId || !/^\d+$/.test(gameId)) return null;
    const partial = new URL(`/games/detail/${gameId}`, window.location.origin);
    filterNames.forEach((name) => { const value = destination.searchParams.get(name); if (value !== null) partial.searchParams.set(name, value); });
    return partial;
  };
  const eligibleClick = (event, link, sidebar) => event.button === 0 && !event.defaultPrevented && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && !link.target && !link.hasAttribute("download") && sidebar.contains(link) && new URL(link.href).origin === window.location.origin;

  document.addEventListener("DOMContentLoaded", () => {
    const filters = document.querySelector("[data-game-filters]");
    const search = document.querySelector("[data-game-search]");
    const status = document.querySelector("[data-game-status]");
    const sidebar = document.querySelector("[data-sidebar-module='games']");
    const slot = document.querySelector("[data-game-detail-slot]");
    let searchTimer;
    let currentUrl = window.location.pathname + window.location.search;
    if (search && filters) search.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => filters.requestSubmit(), 350); });
    status?.addEventListener("change", () => filters?.requestSubmit());
    window.JoshsCornerRichText?.initialise(slot);
    initialiseGameDetail(slot);
    window.addEventListener("beforeunload", (event) => { if (hasDirtyDraft()) { event.preventDefault(); event.returnValue = ""; } });
    const showNavigationError = (destination, retry) => {
      slot?.querySelector("[data-game-navigation-error]")?.remove();
      const message = document.createElement("div");
      message.dataset.gameNavigationError = "";
      message.className = "game-navigation-error";
      message.setAttribute("role", "alert");
      message.append("Could not open that game. Your current editor is still available. ");
      const retryButton = document.createElement("button"); retryButton.type = "button"; retryButton.textContent = "Retry"; retryButton.addEventListener("click", retry, { once: true });
      const fallback = document.createElement("a"); fallback.href = destination.pathname + destination.search; fallback.textContent = "Open normally";
      message.append(retryButton, " ", fallback);
      slot?.prepend(message);
    };
    const load = async (destination, push = false, skipDirtyCheck = false) => {
      const partial = partialUrlFor(destination);
      if (!partial || !slot) return false;
      if (!skipDirtyCheck && !confirmLeavingDirtyDetail()) return false;
      const requestId = ++navigationRequest;
      slot.classList.add("is-loading");
      try {
        const response = await fetch(partial, { credentials: "same-origin", headers: { "X-Requested-With": "JoshCornerPartial" } });
        if (!response.ok) throw new Error("Fragment request failed.");
        const html = await response.text();
        if (requestId !== navigationRequest) return false;
        destroyGameDetail();
        window.JoshsCornerRichText?.destroy(slot);
        slot.innerHTML = html;
        window.JoshsCornerRichText?.initialise(slot);
        initialiseGameDetail(slot);
        const gameId = destination.searchParams.get("game_id");
        setSelectedGame(gameId);
        currentUrl = destination.pathname + destination.search;
        if (push) window.history.pushState({ gameId }, "", currentUrl);
        return true;
      } catch (_) {
        if (requestId === navigationRequest) showNavigationError(destination, () => load(destination, push, true));
        return false;
      } finally {
        if (requestId === navigationRequest) slot.classList.remove("is-loading");
      }
    };
    sidebar?.addEventListener("click", (event) => {
      const link = event.target.closest(".game-card-link");
      if (!link || !eligibleClick(event, link, sidebar)) return;
      event.preventDefault();
      load(new URL(link.href), true);
    });
    sidebar?.querySelector(".new-game")?.addEventListener("click", (event) => { if (eligibleClick(event, event.currentTarget, sidebar) && !confirmLeavingDirtyDetail()) event.preventDefault(); });
    window.addEventListener("popstate", () => {
      const destination = new URL(window.location.href);
      if (!partialUrlFor(destination)) { window.location.assign(destination); return; }
      if (!confirmLeavingDirtyDetail()) { window.history.pushState({}, "", currentUrl); return; }
      load(destination, false, true);
    });
    window.JoshsCornerGames = { initialiseGameDetail, destroyGameDetail, load };
  });
})();
