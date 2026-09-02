(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const dialog = document.querySelector("[data-universal-search]");
    if (!dialog) return;
    const input = dialog.querySelector("[data-search-input]");
    const results = dialog.querySelector("[data-search-results]");
    const status = dialog.querySelector("[data-search-status]");
    let trigger = null, timer = null, controller = null, sequence = 0, selected = -1;
    let links = [];

    const resetResults = () => {
      links = [];
      selected = -1;
      input.removeAttribute("aria-activedescendant");
      results.replaceChildren();
    };
    const cancel = () => {
      clearTimeout(timer);
      controller?.abort();
      controller = null;
      sequence += 1;
    };
    const close = () => dialog.close();
    const open = (origin) => {
      if (dialog.open) { input.focus(); return; }
      trigger = origin || document.activeElement;
      input.value = "";
      resetResults();
      status.textContent = "Start typing to search Josh's Corner";
      dialog.showModal();
      document.documentElement.classList.add("search-open");
      input.focus();
    };
    document.querySelectorAll("[data-search-open]").forEach(button =>
      button.addEventListener("click", () => open(button)));
    dialog.querySelector("[data-search-close]").addEventListener("click", close);
    dialog.addEventListener("close", () => {
      cancel();
      input.value = "";
      resetResults();
      document.documentElement.classList.remove("search-open");
      if (trigger?.isConnected) trigger.focus();
    });
    dialog.addEventListener("click", event => {
      if (event.target === dialog) {
        const box = dialog.getBoundingClientRect();
        if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close();
      }
      // Real links retain the app's normal navigation, beforeunload guards and history.
      if (event.target.closest("a") && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) close();
    });
    document.addEventListener("keydown", event => {
      if (dialog.open && event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation(); // Do not also close the navigation drawer.
        close();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
        const editing = event.target.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])");
        if (event.defaultPrevented || (editing && !dialog.open)) return;
        event.preventDefault();
        open();
      }
    }, true);

    const select = index => {
      selected = index;
      links.forEach((link, i) => link.setAttribute("aria-selected", String(i === index)));
      if (links[index]) {
        input.setAttribute("aria-activedescendant", links[index].id);
        links[index].scrollIntoView({ block: "nearest" });
      }
    };
    input.addEventListener("keydown", event => {
      if (event.isComposing) return;
      if (["ArrowDown", "ArrowUp"].includes(event.key) && links.length) {
        event.preventDefault();
        select(event.key === "ArrowDown" ? (selected + 1) % links.length : (selected <= 0 ? links.length - 1 : selected - 1));
      } else if (event.key === "Enter" && links[selected]) {
        event.preventDefault();
        links[selected].click();
      }
    });

    const render = payload => {
      resetResults();
      const groups = new Map();
      payload.results.forEach(item => {
        if (!groups.has(item.result_type)) groups.set(item.result_type, []);
        groups.get(item.result_type).push(item);
      });
      for (const [type, items] of groups) {
        const group = document.createElement("div");
        group.setAttribute("role", "group");
        group.setAttribute("aria-label", type);
        const heading = document.createElement("h3");
        heading.textContent = type + " (" + items.length + ")";
        heading.setAttribute("aria-hidden", "true");
        group.append(heading);
        for (const item of items) {
          const link = document.createElement("a");
          link.href = item.destination_url;
          link.className = "search-result";
          link.id = "search-result-" + links.length;
          link.setAttribute("role", "option");
          link.setAttribute("aria-selected", "false");
          link.setAttribute("aria-label", item.title + ". " + item.subtitle);
          for (const [style, text] of [["search-result__title", item.title], ["search-result__meta", item.subtitle], ["search-result__snippet", item.snippet]]) {
            if (!text) continue;
            const span = document.createElement("span");
            span.className = style;
            span.textContent = text;
            link.append(span);
          }
          const index = links.length;
          link.addEventListener("focus", () => select(index));
          links.push(link);
          group.append(link);
        }
        results.append(group);
      }
      const count = payload.results.length;
      status.textContent = count ? (count === payload.limit ? "Showing the top " : "") + count + " result" + (count === 1 ? "" : "s") : 'No results for "' + input.value.trim() + '"';
      if (payload.unavailable.length) status.textContent += ". Some sections are temporarily unavailable.";
    };
    input.addEventListener("input", () => {
      cancel();
      resetResults();
      const query = input.value.trim();
      if (query.replace(/[^\p{L}\p{N}]/gu, "").length < 2) {
        status.textContent = "Type at least 2 characters to search";
        return;
      }
      status.textContent = "Searching…";
      const ticket = sequence;
      timer = setTimeout(async () => {
        controller = new AbortController();
        try {
          const response = await fetch(dialog.dataset.searchUrl, {
            method: "POST", credentials: "same-origin", cache: "no-store",
            headers: { "Content-Type": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content },
            body: JSON.stringify({ query }), signal: controller.signal,
          });
          if (!response.ok) throw new Error("Search unavailable");
          const payload = await response.json();
          if (dialog.open && ticket === sequence) render(payload);
        } catch (error) {
          if (error.name !== "AbortError" && dialog.open && ticket === sequence)
            status.textContent = "Search is temporarily unavailable. Please try again.";
        }
      }, 180);
    });
  });
})();
