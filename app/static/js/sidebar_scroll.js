document.addEventListener("DOMContentLoaded", () => {
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
    const stored = Number(sessionStorage.getItem(scrollKey));
    if (Number.isFinite(stored)) list.scrollTop = clamp(stored);
  };

  requestAnimationFrame(() => {
    restorePosition();
    requestAnimationFrame(restorePosition);
  });
  list.addEventListener("scroll", savePosition, { passive: true });

  sidebar.querySelectorAll(fallback?.select || "[data-sidebar-select]").forEach((link) => {
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
    const detail = document.querySelector("[data-sidebar-detail-focus]") || document.querySelector(fallback?.detail);
    if (detail) {
      detail.tabIndex = -1;
      requestAnimationFrame(() => detail.focus({ preventScroll: true }));
    }
  }
});
