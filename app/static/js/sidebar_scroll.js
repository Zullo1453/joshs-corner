(() => {
  const fallback = document.body.classList.contains("watchlist-page")
    ? { module: "watchlist", sidebar: ".watch-sidebar", list: ".watch-list", filters: "[data-watch-filters]", select: ".watch-card-link", detail: ".watch-editor" }
    : null;
  const sidebar = document.querySelector("[data-sidebar-module]") || (fallback ? document.querySelector(fallback.sidebar) : null);
  const list = sidebar?.querySelector("[data-sidebar-list]") || sidebar?.querySelector(fallback?.list);
  if (!sidebar || !list) return;

  const moduleName = sidebar.dataset.sidebarModule || fallback?.module;
  const scrollKey = `joshs-corner:sidebar-scroll:${moduleName}`;
  const selectionKey = `joshs-corner:sidebar-selection:${moduleName}`;
  const clamp = (value) => Math.min(Math.max(0, value), Math.max(0, list.scrollHeight - list.clientHeight));
  const savePosition = () => sessionStorage.setItem(scrollKey, String(Math.round(list.scrollTop)));
  const restorePosition = () => {
    const rawValue = sessionStorage.getItem(scrollKey);
    if (rawValue === null) return false;
    const stored = Number(rawValue);
    if (!Number.isFinite(stored)) return false;
    sidebar.classList.add("sidebar-restoring");
    list.scrollTop = clamp(stored);
    sidebar.classList.remove("sidebar-restoring");
    return true;
  };

  // This deferred script runs immediately after parsing, before normal first paint.
  restorePosition();
  list.addEventListener("scroll", savePosition, { passive: true });

  sidebar.querySelectorAll(fallback?.select || "[data-sidebar-select]").forEach((link) => {
    link.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") sessionStorage.setItem(`${selectionKey}:keyboard`, "1");
    });
    link.addEventListener("click", () => {
      savePosition();
      sessionStorage.setItem(selectionKey, "1");
    });
  });
  sidebar.querySelectorAll(fallback?.filters || "[data-sidebar-filters]").forEach((form) => {
    form.addEventListener("submit", () => sessionStorage.removeItem(scrollKey));
  });

  if (sessionStorage.getItem(selectionKey) === "1") {
    sessionStorage.removeItem(selectionKey);
    const keyboardSelection = sessionStorage.getItem(`${selectionKey}:keyboard`) === "1";
    sessionStorage.removeItem(`${selectionKey}:keyboard`);
    if (keyboardSelection) requestAnimationFrame(() => document.querySelector("[data-detail-focus-target], input[name=title], [data-rich-body]")?.focus({ preventScroll: true }));
  }
})();
