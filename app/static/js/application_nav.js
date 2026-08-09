document.addEventListener("DOMContentLoaded", () => {
  const navigation = document.querySelector("[data-application-nav]");
  const toggle = navigation?.querySelector("[data-nav-toggle]");
  if (!navigation || !toggle) return;

  const close = ({ restoreFocus = false } = {}) => {
    if (!navigation.classList.contains("is-open")) return;
    navigation.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open main navigation");
    document.documentElement.classList.remove("navigation-open");
    if (restoreFocus) toggle.focus();
  };

  const open = () => {
    navigation.classList.add("is-open");
    toggle.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-label", "Close main navigation");
    document.documentElement.classList.add("navigation-open");
  };

  toggle.addEventListener("click", () => navigation.classList.contains("is-open") ? close() : open());
  navigation.querySelector("[data-nav-close]")?.addEventListener("click", () => close({ restoreFocus: true }));
  navigation.querySelector("[data-nav-dismiss]")?.addEventListener("click", () => close({ restoreFocus: true }));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navigation.classList.contains("is-open")) {
      event.preventDefault();
      close({ restoreFocus: true });
    }
  });
});
