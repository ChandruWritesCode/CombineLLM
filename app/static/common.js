"use strict";
const $ = (id) => document.getElementById(id);
function notice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}
async function api(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = Array.isArray(data.detail)
      ? data.detail.map((e) => e.msg).join("; ")
      : data.detail;
    throw new Error(
      data.error?.message || detail || `Request failed (${response.status})`,
    );
  }
  return response.status === 204 ? null : response.json();
}
function node(tag, text, className) {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  if (className) e.className = className;
  return e;
}
