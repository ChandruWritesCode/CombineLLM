"use strict";
let catalog = [], selected = null, saved = null;
function link(label, href) {
  const a = node("a", label); a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; return a;
}
function render() {
  $("catalog").replaceChildren();
  const query = $("search").value.toLowerCase();
  for (const item of catalog.filter(p => `${p.name} ${p.offer}`.toLowerCase().includes(query))) {
    const card = node("section", null, "panel");
    card.append(node("h2", item.name), node("p", `${item.offer} · Reviewed ${item.checked}`), node("p", item.guide));
    card.append(link("Official account / keys", item.signup), node("span", " · "), link("Offer and documentation", item.source));
    const button = node("button", "Set up this provider", "primary");
    button.onclick = () => {
      selected = item; $("setup-form").reset(); $("setup-error").textContent = "";
      $("setup-title").textContent = `Connect ${item.name}`; $("walkthrough").textContent = item.guide;
      $("name").value = item.name; $("model").value = item.model;
      $("url").value = item.base_url || (item.kind === "gemini" ? "https://generativelanguage.googleapis.com/v1beta" : "https://openrouter.ai/api/v1");
      $("url").readOnly = ["gemini", "openrouter"].includes(item.kind);
      $("key").required = item.kind !== "ollama" && item.kind !== "openrouter";
      $("setup").showModal();
    };
    card.append(node("p"), button); $("catalog").append(card);
  }
  if (!$("catalog").children.length) $("catalog").append(node("p", "No matching providers."));
}
$("search").oninput = render;
$("cancel").onclick = () => $("setup").close();
$("setup").addEventListener("close", () => { $("key").value = ""; });
$("setup-form").onsubmit = async event => {
  event.preventDefault(); $("save").disabled = true; $("setup-error").textContent = "";
  try {
    if ($("url").value.includes("ACCOUNT_ID")) throw new Error("Replace ACCOUNT_ID with your Cloudflare account ID.");
    const body = {name: $("name").value, kind: selected.kind, model: $("model").value, base_url: $("url").value, api_key: $("key").value || null, include_usage: selected.id === "groq" || selected.kind === "openrouter", token_parameter: selected.id === "groq" ? "max_completion_tokens" : "max_tokens"};
    saved = await api("/models", {method: "POST", body: JSON.stringify(body)});
    $("setup").close();
    notice(`${saved.name} saved. Select it in chat. Manage keys, OpenRouter login, defaults and limits in Settings.`);
    if (saved.has_key || saved.kind === "ollama") $("test-dialog").showModal();
  } catch (e) { $("setup-error").textContent = e.message; }
  finally { $("save").disabled = false; }
};
$("test-cancel").onclick = () => $("test-dialog").close();
$("test-run").onclick = async () => {
  $("test-run").disabled = true;
  try { await api(`/models/${saved.id}/test`, {method: "POST"}); notice(`${saved.name}: live response verified. Select it in chat.`); }
  catch (e) { notice(`${saved.name}: ${e.message} The connection remains saved; check its model, key and quota in Settings.`); }
  finally { $("test-run").disabled = false; $("test-dialog").close(); }
};
fetch("/static/provider-catalog.json").then(r => { if (!r.ok) throw new Error("Could not load provider directory"); return r.json(); }).then(data => { catalog = data; render(); }).catch(e => notice(e.message));
