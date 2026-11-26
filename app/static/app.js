"use strict";
const $ = (id) => document.getElementById(id);
let selected = null,
  activeMessage = null,
  stream = null,
  sending = false,
  providerReady = false;
let viewVersion = 0;
let modelConnections = [],
  workspacePreferences = {};

function notice(text = "") {
  $("notice").textContent = text;
  $("notice").hidden = !text;
}
async function api(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      data.error?.message ||
        (typeof data.detail === "string"
          ? data.detail
          : `Request failed (${response.status}).`),
    );
  }
  return response.status === 204 ? null : response.json();
}
let budgetRefresh = 0;
async function refreshBudgets() {
  const version = ++budgetRefresh;
  try {
    const data = await api("/budgets");
    if (version !== budgetRefresh) return;
    const selectedBudget = data.models.find(m => m.model_id === $("chat-model").value);
    const warnings = [{name: "Workspace", ...data.workspace}, ...(selectedBudget ? [selectedBudget] : [])]
      .filter(b => b.budget_usd !== null && (["warning", "exceeded"].includes(b.status) || b.unknown_cost_requests > 0));
    $("budget-notice").textContent = warnings.map(b => `${b.name}: ${b.status === "below" ? "budget estimate incomplete" : "budget " + b.status}, $${b.estimated_cost_usd} estimated; ${b.unknown_cost_requests} unknown-cost requests.`).join(" ") + (warnings.length ? " Advisory only — requests remain enabled. See Usage." : "");
    $("budget-notice").hidden = !warnings.length;
  } catch {
    if (version !== budgetRefresh) return;
    $("budget-notice").textContent = "Budget information is unavailable. Requests remain enabled.";
    $("budget-notice").hidden = false;
  }
}
function controls() {
  providerReady = !!modelConnections.find(
    (m) => m.id === $("chat-model").value && m.enabled,
  );
  $("chat-model").disabled = sending || !!activeMessage;
  $("local-only").disabled = sending || !!activeMessage;
  const fallbackIds = workspacePreferences.fallback_model_ids || [];
  $("use-fallback").disabled = sending || !!activeMessage || !fallbackIds.length;
  $("provider-state").textContent = $("use-fallback").checked ? "Ordered fallback enabled" : "Manual selection";
  $("fallback-description").textContent = fallbackIds.length
    ? `After the selected model: ${fallbackIds.map(id => modelConnections.find(m => m.id === id)?.name || "Unavailable model").join(" → ")}. Enabling this can send history to each provider and use credits. No fallback after partial text.`
    : "Manual selection only. Configure an optional fallback order in Settings.";
  $("send").disabled = sending || !!activeMessage || !providerReady;
  $("stop").hidden = !activeMessage;
  $("rename").disabled = !selected || sending;
  $("delete").disabled = !selected || sending;
  $("new-chat").disabled = sending;
  document.querySelectorAll("#conversations button").forEach((button) => {
    button.disabled = sending;
  });
}
function closeStream() {
  if (stream) stream.close();
  stream = null;
}
async function listChats() {
  const chats = await api("/conversations");
  $("chat-count").textContent = chats.length;
  $("conversations").replaceChildren();
  if (!chats.length) {
    const p = document.createElement("p");
    p.className = "empty-list";
    p.textContent =
      "Your next idea starts here. Saved chats will appear in this space.";
    $("conversations").append(p);
  }
  for (const chat of chats) {
    const button = document.createElement("button");
    button.textContent = chat.title;
    button.className = chat.id === selected ? "active" : "";
    button.setAttribute(
      "aria-current",
      chat.id === selected ? "page" : "false",
    );
    button.disabled = sending;
    button.onclick = () => openChat(chat.id).catch((e) => notice(e.message));
    $("conversations").append(button);
  }
}
function drawMessage(message) {
  let article = document.getElementById(`message-${message.id}`);
  if (!article) {
    article = document.createElement("article");
    article.id = `message-${message.id}`;
    $("messages").append(article);
  }
  article.className = `message ${message.role}`;
  article.replaceChildren();
  const head = document.createElement("div");
  head.className = "message-head";
  const name = document.createElement("span");
  name.textContent = message.role === "user" ? "You" : "CombineLLM";
  const meta = document.createElement("span");
  meta.textContent =
    message.role === "assistant"
      ? `${message.provider || "Model"} / ${message.model || "Unknown"} · ${message.status}`
      : "";
  head.append(name, meta);
  const content = document.createElement("div");
  content.className = "message-content";
  content.textContent =
    message.content ||
    (message.status === "streaming" ? "Thinking…" : "No answer was generated.");
  article.append(head, content);
  if (message.attempts?.length) {
    const attempts = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = `Model attempts (${message.attempts.length})`;
    attempts.append(summary);
    for (const attempt of message.attempts) {
      const line = document.createElement("p");
      line.textContent = `${attempt.attempt_number}. ${attempt.label} (${attempt.model}): ${attempt.status}${attempt.error_code ? " — " + attempt.error_code.replaceAll("_", " ") : ""}`;
      attempts.append(line);
    }
    article.append(attempts);
  }
  if (message.error) {
    const error = document.createElement("div");
    error.className = "message-error";
    error.textContent = message.error;
    article.append(error);
  }
  if (message.usage || message.finish_reason === "MAX_TOKENS") {
    const usage = document.createElement("div");
    usage.className = "message-meta";
    usage.textContent =
      message.finish_reason === "MAX_TOKENS"
        ? "Output limit reached. This answer may be incomplete. "
        : "";
    if (message.usage?.total_tokens != null)
      usage.textContent += `${message.usage.total_tokens} total tokens reported by provider`;
    article.append(usage);
  }
  if (message.role === "user") {
    const reuse = document.createElement("button");
    reuse.className = "quiet";
    reuse.textContent = "Reuse prompt";
    reuse.onclick = () => {
      $("prompt").value = message.content;
      $("prompt").focus();
    };
    article.append(reuse);
  }
}
function attach(conversationId, messageId) {
  closeStream();
  activeMessage = messageId;
  controls();
  const source = new EventSource(
    `/api/v1/conversations/${conversationId}/messages/${messageId}/events`,
  );
  stream = source;
  source.addEventListener("message", (event) => {
    if (selected !== conversationId || stream !== source) return;
    const nearBottom =
      $("thread").scrollHeight -
        $("thread").scrollTop -
        $("thread").clientHeight <
      140;
    drawMessage(JSON.parse(event.data));
    if (nearBottom) $("thread").scrollTop = $("thread").scrollHeight;
  });
  source.addEventListener("done", () => {
    if (stream !== source) return;
    closeStream();
    activeMessage = null;
    controls();
    refreshBudgets();
    listChats().catch((e) => notice(e.message));
  });
  source.addEventListener("removed", () => {
    if (stream !== source) return;
    closeStream();
    activeMessage = null;
    controls();
    notice("This conversation was removed.");
  });
  source.onerror = () => {
    if (stream !== source) return;
    notice("Connection interrupted. Reconnecting to the saved response…");
  };
  source.onopen = () => {
    if (stream === source) notice();
  };
}
async function openChat(id) {
  const version = ++viewVersion;
  const chat = await api(`/conversations/${id}`);
  if (version !== viewVersion) return;
  closeStream();
  if (selected !== id) $("use-fallback").checked = false;
  selected = id;
  activeMessage = null;
  localStorage.setItem("combinellm-selected", id);
  $("chat-title").textContent = chat.title;
  $("chat-model").value =
    chat.model_id || workspacePreferences.default_model_id || "";
  if (
    chat.model_id &&
    !modelConnections.some((m) => m.id === chat.model_id && m.enabled)
  ) {
    $("chat-model").value = "";
    notice(
      "The previous model is unavailable or disabled. Select another model to continue.",
    );
  }
  $("messages").replaceChildren();
  $("welcome").hidden = !!chat.messages.length;
  chat.messages.forEach(drawMessage);
  refreshBudgets();
  const running = chat.messages.find((m) => m.status === "streaming");
  if (running) attach(id, running.id);
  controls();
  await listChats();
  $("thread").scrollTop = $("thread").scrollHeight;
}
$("new-chat").onclick = async () => {
  try {
    const chat = await api("/conversations", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await openChat(chat.id);
    $("prompt").focus();
    notice();
  } catch (e) {
    notice(e.message);
  }
};
$("composer").onsubmit = async (event) => {
  event.preventDefault();
  const content = $("prompt").value.trim();
  if (!content || sending || activeMessage || !providerReady) return;
  sending = true;
  controls();
  notice();
  try {
    if (!selected) {
      const chat = await api("/conversations", { method: "POST", body: "{}" });
      selected = chat.id;
    }
    const id = selected;
    await api(`/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, model_id: $("chat-model").value, fallback: $("use-fallback").checked, local_only: $("local-only").checked }),
    });
    $("prompt").value = "";
    await openChat(id);
  } catch (e) {
    notice(e.message);
  } finally {
    sending = false;
    controls();
    refreshBudgets();
    listChats().catch((e) => notice(e.message));
  }
};
$("prompt").onkeydown = (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
};
$("stop").onclick = async () => {
  const id = selected,
    message = activeMessage;
  if (!message) return;
  try {
    await api(`/conversations/${id}/messages/${message}/cancel`, {
      method: "POST",
    });
    if (selected === id) await openChat(id);
  } catch (e) {
    notice(e.message);
  }
};
let dialogAction = null,
  dialogConversation = null;
function showDialog(action) {
  dialogAction = action;
  dialogConversation = selected;
  const rename = action === "rename";
  $("dialog-title").textContent = rename
    ? "Rename conversation"
    : "Delete conversation?";
  $("dialog-description").textContent = rename
    ? "Give this conversation a name you will recognize."
    : "This permanently removes its messages and stops any active response. This cannot be undone.";
  $("name-label").hidden = !rename;
  $("conversation-name").hidden = !rename;
  $("conversation-name").required = rename;
  $("conversation-name").value = $("chat-title").textContent;
  $("dialog-confirm").textContent = rename
    ? "Save name"
    : "Delete conversation";
  $("action-dialog").showModal();
  if (rename) $("conversation-name").focus();
  else $("dialog-cancel").focus();
}
$("rename").onclick = () => showDialog("rename");
$("delete").onclick = () => showDialog("delete");
$("dialog-cancel").onclick = () => $("action-dialog").close();
$("action-form").onsubmit = async (event) => {
  event.preventDefault();
  const id = dialogConversation,
    action = dialogAction;
  const title = $("conversation-name").value.trim();
  if (action === "rename" && !title) return;
  $("dialog-confirm").disabled = true;
  try {
    if (action === "rename") {
      await api(`/conversations/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
      await openChat(id);
    } else {
      await api(`/conversations/${id}`, { method: "DELETE" });
      closeStream();
      ++viewVersion;
      selected = null;
      activeMessage = null;
      localStorage.removeItem("combinellm-selected");
      $("messages").replaceChildren();
      $("welcome").hidden = false;
      $("chat-title").textContent = "A little space to think.";
      controls();
      await listChats();
    }
    $("action-dialog").close();
    notice();
  } catch (e) {
    $("action-dialog").close();
    notice(e.message);
  } finally {
    $("dialog-confirm").disabled = false;
  }
};
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.onclick = () => {
    $("prompt").value = button.dataset.prompt;
    $("prompt").focus();
  };
});
async function init() {
  try {
    [modelConnections, workspacePreferences] = await Promise.all([
      api("/models"),
      api("/settings"),
    ]);
    $("chat-model").replaceChildren(new Option("Choose a model", ""));
    for (const model of modelConnections.filter((m) => m.enabled))
      $("chat-model").append(
        new Option(`${model.name} · ${model.model}`, model.id),
      );
    $("chat-model").value = workspacePreferences.default_model_id || "";
    if (!modelConnections.some((m) => m.enabled))
      notice("Add an enabled model in Settings to start chatting.");
    await listChats();
    const last = localStorage.getItem("combinellm-selected");
    if (last) {
      try {
        await openChat(last);
      } catch {
        localStorage.removeItem("combinellm-selected");
      }
    }
  } catch (e) {
    notice(`Unable to load the workspace: ${e.message}`);
  }
  controls();
  refreshBudgets();
}
$("use-fallback").onchange = controls;
$("chat-model").onchange = () => {
  refreshBudgets();
  controls();
  notice(
    "The selected model will receive the completed conversation history on your next message.",
  );
};
init();
