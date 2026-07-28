document.addEventListener("DOMContentLoaded", () => {
  const filters = document.querySelector("[data-game-filters]");
  const search = document.querySelector("[data-game-search]");
  const status = document.querySelector("[data-game-status]");
  let searchTimer;
  if (search && filters) search.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => filters.requestSubmit(), 350); });
  if (status && filters) status.addEventListener("change", () => filters.requestSubmit());

  const stars = document.querySelectorAll("[data-rating-stars] .rating-star");
  const input = document.querySelector("[data-rating-input]");
  const display = document.querySelector("[data-rating-value]");
  const setRating = (rating) => {
    if (!input) return;
    input.value = rating === 0 ? "0" : rating.toFixed(1);
    stars.forEach((star) => {
      const value = Number(star.dataset.star);
      star.style.setProperty("--fill", rating >= value ? 100 : rating === value - 0.5 ? 50 : 0);
      star.setAttribute("aria-pressed", String(rating === value || rating === value - 0.5));
    });
    if (display) display.textContent = rating ? `${rating.toFixed(1)} / 5` : "Not rated";
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
  const form = document.querySelector("[data-game-editor]");
  const saveState = document.querySelector("[data-save-state]");
  if (form && saveState) form.addEventListener("input", () => { saveState.textContent = "Unsaved changes"; });
  const deleteTrigger = document.querySelector("[data-game-delete]");
  const deleteForm = document.querySelector("[data-game-delete-form]");
  if (deleteTrigger && deleteForm) deleteTrigger.addEventListener("click", () => { if (window.confirm("Delete this game journal permanently?")) deleteForm.requestSubmit(); });
  document.querySelectorAll("[data-play-delete]").forEach((form) => form.addEventListener("submit", (event) => { if (!window.confirm("Delete this play entry permanently?")) event.preventDefault(); }));
});
