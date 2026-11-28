"use strict";
// Shared accessibility and navigation enhancements; no provider requests.
const mainRegion = document.querySelector("main");
if (mainRegion) {
  mainRegion.id = "main-content";
  mainRegion.tabIndex = -1;
  const skip = document.createElement("a");
  skip.href = "#main-content";
  skip.className = "skip-link";
  skip.textContent = "Skip to main content";
  document.body.prepend(skip);
}
for (const link of document.querySelectorAll(".page-nav a, .chat-links a")) {
  if (new URL(link.href).pathname === location.pathname) {
    link.setAttribute("aria-current", "page");
    link.classList.add("active");
  }
}
