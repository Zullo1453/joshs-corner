(() => {
  const empty = (html) => !html.replace(/<br\s*\/?>/gi, "").replace(/<\/?(?:p|div)>/gi, "").replace(/&nbsp;/gi, "").trim();
  document.querySelectorAll('textarea[name="notes"]').forEach((textarea) => {
    const root = document.createElement("div"); root.className = "rich-editor"; root.dataset.richEditor = "";
    root.innerHTML = `<input type="hidden" name="notes" data-rich-input><div class="rich-toolbar" role="toolbar" aria-label="Formatting toolbar"><select class="rich-tool-select" aria-label="Text style" data-rich-block><option value="p">Paragraph</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option></select><button type="button" class="rich-tool-button" data-rich-command="bold" aria-label="Bold"><b>B</b></button><button type="button" class="rich-tool-button" data-rich-command="italic" aria-label="Italic"><i>I</i></button><button type="button" class="rich-tool-button" data-rich-command="underline" aria-label="Underline"><u>U</u></button><button type="button" class="rich-tool-button" data-rich-command="insertUnorderedList" aria-label="Bulleted list">• List</button><button type="button" class="rich-tool-button" data-rich-command="insertOrderedList" aria-label="Numbered list">1. List</button><button type="button" class="rich-tool-button" data-rich-quote aria-label="Toggle quote" aria-pressed="false">“ Quote</button><button type="button" class="rich-tool-button" data-rich-command="undo" aria-label="Undo">↶</button><button type="button" class="rich-tool-button" data-rich-command="redo" aria-label="Redo">↷</button></div><div class="rich-editor-body" contenteditable="true" role="textbox" aria-multiline="true" data-rich-body></div>`;
    root.querySelector("[data-rich-body]").innerHTML = textarea.value; textarea.replaceWith(root);
  });
  document.querySelectorAll("[data-rich-editor]").forEach((root) => {
    if (root.dataset.ready) return; root.dataset.ready = "1";
    const body = root.querySelector("[data-rich-body]"), input = root.querySelector("[data-rich-input]"), form = root.closest("form");
    const sync = () => { input.value = empty(body.innerHTML) ? "" : body.innerHTML; };
    const quote = root.querySelector("[data-rich-quote]");
    const quoteActive = () => { const node = window.getSelection()?.anchorNode; const el = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement; return Boolean(el?.closest("blockquote")); };
    const updateQuote = () => { if (quote) { const active = quoteActive(); quote.setAttribute("aria-pressed", String(active)); quote.classList.toggle("active", active); } };
    root.querySelectorAll("[data-rich-command]").forEach((button) => button.addEventListener("click", () => { body.focus(); document.execCommand(button.dataset.richCommand, false, null); sync(); updateQuote(); }));
    root.querySelector("[data-rich-block]")?.addEventListener("change", (event) => { body.focus(); document.execCommand("formatBlock", false, event.target.value); sync(); });
    quote?.addEventListener("mousedown", (event) => event.preventDefault());
    quote?.addEventListener("click", () => { body.focus(); document.execCommand("formatBlock", false, quoteActive() ? "p" : "blockquote"); sync(); updateQuote(); });
    body.addEventListener("input", sync); body.addEventListener("keyup", updateQuote); body.addEventListener("mouseup", updateQuote);
    form?.addEventListener("submit", sync); document.addEventListener("selectionchange", updateQuote);
  });
})();
