"use strict";
(function () {
  const key = "combinellm-theme";
  const choices = new Set(["violet", "ocean", "ember", "daylight", "system"]);
  const preference = window.matchMedia("(prefers-color-scheme: light)");

  function savedChoice() {
    try {
      const value = localStorage.getItem(key);
      return choices.has(value) ? value : "violet";
    } catch {
      return "violet";
    }
  }

  function apply(choice) {
    const safe = choices.has(choice) ? choice : "violet";
    document.documentElement.dataset.themeChoice = safe;
    document.documentElement.dataset.theme =
      safe === "system" ? (preference.matches ? "daylight" : "violet") : safe;
    document.querySelectorAll('input[name="theme-choice"]').forEach((input) => {
      input.checked = input.value === safe;
    });
  }

  apply(savedChoice());
  preference.addEventListener("change", () => {
    if (savedChoice() === "system") apply("system");
  });
  window.addEventListener("storage", (event) => {
    if (event.key === key) apply(savedChoice());
  });
  document.addEventListener("DOMContentLoaded", () => {
    apply(savedChoice());
    document.querySelectorAll('input[name="theme-choice"]').forEach((input) => {
      input.addEventListener("change", () => {
        if (!input.checked) return;
        try {
          localStorage.setItem(key, input.value);
        } catch {
          // The theme still changes for this tab when storage is unavailable.
        }
        apply(input.value);
      });
    });
  });
})();
