(() => {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const empty = (html) => {
    const holder = document.createElement("div"); holder.innerHTML = html || "";
    return !holder.querySelector("img") && !holder.textContent.replace(/\u00a0/g, " ").trim();
  };
  const newToken = () => (crypto.randomUUID ? crypto.randomUUID().replaceAll("-", "") : `${Date.now()}${Math.random()}`.replace(".", ""));
  document.querySelectorAll(".book-preview, .watch-preview").forEach((preview) => {
    const holder = document.createElement("div"); holder.innerHTML = preview.textContent;
    preview.textContent = holder.textContent.replace(/\s+/g, " ").trim();
  });
  const toolbar = (name) => `<input type="hidden" name="${name}" data-rich-input><input type="hidden" name="${name}_attachment_token" data-rich-token><div class="rich-toolbar" role="toolbar" aria-label="Formatting toolbar"><select class="rich-tool-select" aria-label="Text style" data-rich-block><option value="p">Paragraph</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option></select><button type="button" class="rich-tool-button" data-rich-command="bold" aria-label="Bold"><b>B</b></button><button type="button" class="rich-tool-button" data-rich-command="italic" aria-label="Italic"><i>I</i></button><button type="button" class="rich-tool-button" data-rich-command="underline" aria-label="Underline"><u>U</u></button><button type="button" class="rich-tool-button" data-rich-command="insertUnorderedList" aria-label="Bulleted list">• List</button><button type="button" class="rich-tool-button" data-rich-command="insertOrderedList" aria-label="Numbered list">1. List</button><button type="button" class="rich-tool-button" data-rich-quote aria-label="Toggle quote" aria-pressed="false">“ Quote</button><button type="button" class="rich-tool-button" data-rich-command="undo" aria-label="Undo">↶</button><button type="button" class="rich-tool-button" data-rich-command="redo" aria-label="Redo">↷</button><span class="rich-divider" aria-hidden="true"></span><button type="button" class="rich-tool-button" data-rich-image aria-label="Add image">▧ Image</button><button type="button" class="rich-tool-button" data-rich-remove-image aria-label="Remove selected image">Remove image</button><input type="file" accept="image/png,image/jpeg,image/webp" data-rich-file hidden></div>`;

  document.querySelectorAll('textarea[name="notes"]').forEach((textarea) => {
    const root = document.createElement("div"); root.className = "rich-editor"; root.dataset.richEditor = ""; root.dataset.uploadUrl = "/attachments/upload";
    root.innerHTML = `${toolbar("notes")}<div id="${textarea.id}" class="rich-editor-body" contenteditable="true" role="textbox" aria-multiline="true" data-rich-body data-placeholder="${textarea.placeholder}"></div><p class="rich-upload-message" data-rich-upload-message role="status" aria-live="polite"></p>`;
    root.querySelector("[data-rich-body]").innerHTML = textarea.value; textarea.replaceWith(root);
  });

  document.querySelectorAll("[data-rich-editor]").forEach((root) => {
    if (root.dataset.ready) return; root.dataset.ready = "1";
    const body = root.querySelector("[data-rich-body]"), input = root.querySelector("[data-rich-input]"), form = root.closest("form");
    const token = root.querySelector("[data-rich-token]"), message = root.querySelector("[data-rich-upload-message]");
    const file = root.querySelector("[data-rich-file]"), addImage = root.querySelector("[data-rich-image]"), removeImage = root.querySelector("[data-rich-remove-image]");
    let selectedImage = null, rememberedRange = null;
    if (!token.value) token.value = newToken();
    const sync = () => { input.value = empty(body.innerHTML) ? "" : body.innerHTML; };
    const announce = (text, error = false) => { message.textContent = text; message.classList.toggle("error", error); };
    const quote = root.querySelector("[data-rich-quote]");
    const quoteActive = () => { const node = window.getSelection()?.anchorNode; const el = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement; return Boolean(el?.closest("blockquote")); };
    const updateQuote = () => { if (quote) { const active = quoteActive(); quote.setAttribute("aria-pressed", String(active)); quote.classList.toggle("active", active); } };
    const rememberCaret = () => { const selection = window.getSelection(); if (selection?.rangeCount && body.contains(selection.anchorNode)) rememberedRange = selection.getRangeAt(0).cloneRange(); };
    const selectImage = (image) => { selectedImage?.classList.remove("rich-image-selected"); selectedImage = image; image?.classList.add("rich-image-selected"); };
    const insertImage = (details) => {
      body.focus(); const selection = window.getSelection();
      if (rememberedRange) { selection.removeAllRanges(); selection.addRange(rememberedRange); }
      const image = document.createElement("img"); image.src = details.url; image.alt = "Uploaded image"; image.width = details.width; image.height = details.height;
      const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
      if (range && body.contains(range.commonAncestorContainer)) { range.deleteContents(); range.insertNode(image); range.setStartAfter(image); range.collapse(true); selection.removeAllRanges(); selection.addRange(range); }
      else body.append(image);
      rememberCaret(); sync(); announce("Image added. Select it and use Remove image before saving if needed.");
    };
    const upload = async (image) => {
      if (!image) return;
      announce("Uploading image…");
      const data = new FormData(); data.append("image", image); data.append("draft_token", token.value);
      try {
        const response = await fetch(root.dataset.uploadUrl || "/attachments/upload", {method: "POST", body: data, credentials: "same-origin", headers: {"X-CSRFToken": csrfToken()}});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "The image could not be uploaded.");
        insertImage(result);
      } catch (error) { announce(error.message || "The image could not be uploaded.", true); }
      finally { file.value = ""; }
    };
    const removeSelected = async () => {
      if (!selectedImage) { announce("Select an image first.", true); return; }
      const match = selectedImage.getAttribute("src")?.match(/^\/attachments\/(\d+)$/); selectedImage.remove(); selectedImage = null; sync(); announce("Image removed.");
      if (match) fetch(`/attachments/${match[1]}/delete`, {method: "POST", credentials: "same-origin", headers: {"X-CSRFToken": csrfToken()}}).catch(() => {});
    };
    root.querySelectorAll("[data-rich-command]").forEach((button) => button.addEventListener("click", () => { body.focus(); document.execCommand(button.dataset.richCommand, false, null); sync(); updateQuote(); }));
    root.querySelector("[data-rich-block]")?.addEventListener("change", (event) => { body.focus(); document.execCommand("formatBlock", false, event.target.value); sync(); });
    quote?.addEventListener("mousedown", (event) => event.preventDefault());
    quote?.addEventListener("click", () => { body.focus(); document.execCommand("formatBlock", false, quoteActive() ? "p" : "blockquote"); sync(); updateQuote(); });
    addImage?.addEventListener("click", () => file.click()); file?.addEventListener("change", () => upload(file.files[0]));
    removeImage?.addEventListener("click", removeSelected);
    body.addEventListener("paste", (event) => { const image = [...event.clipboardData?.items || []].find((item) => item.type.startsWith("image/")); if (image) { event.preventDefault(); upload(image.getAsFile()); } });
    body.addEventListener("dragover", (event) => event.preventDefault());
    body.addEventListener("drop", (event) => { const image = [...event.dataTransfer?.files || []].find((item) => item.type.startsWith("image/")); if (image) { event.preventDefault(); upload(image); } });
    body.addEventListener("click", (event) => { if (event.target.tagName === "IMG") selectImage(event.target); else selectImage(null); rememberCaret(); });
    body.addEventListener("dblclick", (event) => { if (event.target.tagName === "IMG") window.open(event.target.src, "_blank", "noopener"); });
    body.addEventListener("keydown", (event) => { if ((event.key === "Delete" || event.key === "Backspace") && selectedImage) { event.preventDefault(); removeSelected(); } });
    body.addEventListener("input", () => { sync(); rememberCaret(); }); body.addEventListener("keyup", () => { rememberCaret(); updateQuote(); }); body.addEventListener("mouseup", () => { rememberCaret(); updateQuote(); });
    form?.addEventListener("submit", sync); document.addEventListener("selectionchange", updateQuote);
  });
})();
