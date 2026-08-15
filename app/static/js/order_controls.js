(() => {
  const control = (target) => target.closest("[data-shift-action]");
  const setAction = (button, shifted) => {
    button.value = shifted ? button.dataset.shiftAction : button.dataset.normalAction;
  };
  document.addEventListener("click", (event) => {
    const button = control(event.target);
    if (button && !button.disabled) {
      const shifted = event.shiftKey || button.dataset.keyboardShift === "true";
      delete button.dataset.keyboardShift;
      setAction(button, shifted);
    }
  });
  document.addEventListener("keydown", (event) => {
    const button = control(event.target);
    if (button && event.shiftKey && (event.key === "Enter" || event.key === " ")) {
      button.dataset.keyboardShift = "true";
      setAction(button, true);
    }
  });
})();
