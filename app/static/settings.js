"use strict";
let models = [],
  preferences = {},
  editing = null,
  pendingAction = null,
  editingProfile = null;
const endpoints = {
  gemini: "https://generativelanguage.googleapis.com/v1beta",
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  openrouter: "https://openrouter.ai/api/v1",
  ollama: "http://host.docker.internal:11434/v1",
  compatible: "https://",
};
function kindChanged() {
  const kind = $("model-kind").value;
  $("model-url").value = endpoints[kind];
  $("model-url").readOnly = !["compatible", "ollama"].includes(kind);
  $("model-token-parameter").value =
    kind === "openai" ? "max_completion_tokens" : "max_tokens";
  $("model-temperature").max = kind === "anthropic" ? "1" : "2";
}
function edit(model = null) {
  editing = model?.id || null;
  $("model-form").reset();
  $("model-error").hidden = true;
  $("model-dialog-title").textContent = model
    ? "Edit model connection"
    : "Add model connection";
  $("model-kind").value = model?.kind || "gemini";
  kindChanged();
  for (const [id, field] of [
    ["model-name", "name"],
    ["model-code", "model"],
    ["model-system", "system_prompt"],
  ])
    $(id).value = model?.[field] || "";
  if (model) $("model-url").value = model.base_url;
  $("model-timeout").value = model?.timeout_seconds || 60;
  $("model-tokens").value =
    model?.max_output_tokens || preferences.max_output_tokens || 2048;
  $("context-limit").value = model?.context_limit_chars ?? "";
  document.querySelectorAll('input[name="task-tag"]').forEach((input) => {
    input.checked = (model?.task_tags || []).includes(input.value);
  });
  $("model-temperature").value = model?.temperature ?? "";
  if (model) $("model-token-parameter").value = model.token_parameter;
  $("input-price").value = model?.input_price_per_million ?? "";
  $("output-price").value = model?.output_price_per_million ?? "";
  $("model-budget").value = model?.monthly_budget_usd ?? "";
  $("model-request-limit").value = model?.monthly_request_limit ?? "";
  $("usage-group").value = model?.usage_group || "";
  $("allow-fallback").checked = model?.allow_fallback ?? true;
  $("model-enabled").checked = model?.enabled ?? true;
  $("model-usage").checked = model?.include_usage ?? true;
  $("key-status").textContent = model?.has_key
    ? `Credential saved (${model.auth_method}). Leave blank to keep it.`
    : "No saved credential. OpenRouter can be connected after saving.";
  $("model-dialog").showModal();
  $("model-name").focus();
}
function confirmAction(title, description, action) {
  $("confirm-title").textContent = title;
  $("confirm-text").textContent = description;
  pendingAction = action;
  $("confirm-dialog").showModal();
}
function actionButton(text, action) {
  const b = node("button", text, "quiet");
  b.onclick = action;
  return b;
}
async function loadDiagnostics() {
  try {
    const report = await api("/diagnostics");
    const conversations = `${report.conversations} conversation${report.conversations === 1 ? "" : "s"}`;
    const connections = `${report.model_connections} model connection${report.model_connections === 1 ? "" : "s"}`;
    const replies = `${report.active_generations} active ${report.active_generations === 1 ? "reply" : "replies"}`;
    $("diagnostics-status").textContent = report.storage === "ready"
      ? `Saved data ready · ${conversations} · ${connections} (${report.enabled_models} enabled) · ${report.credential_key_present ? "Credential key present" : "Credential key missing"} · ${replies}. Cloud availability is not checked.`
      : "Saved data needs attention. See the backup and restore guide before making changes.";
  } catch (error) {
    $("diagnostics-status").textContent = `Local status unavailable: ${error.message}`;
  }
}
async function load() {
  [models, preferences] = await Promise.all([api("/models"), api("/settings")]);
  $("model-list").replaceChildren();
  $("default-model").replaceChildren(new Option("Choose in chat", ""));
  if (!models.length)
    $("model-list").append(
      node(
        "p",
        "No model connections yet. Add your first model to start chatting.",
        "empty-list",
      ),
    );
  for (const model of models) {
    const card = node("article", null, "model-card");
    const heading = node("div");
    heading.append(
      node("h3", model.name),
      node("p", `${model.kind} · ${model.model}`),
      node(
        "small",
        `${model.enabled ? "Enabled" : "Disabled"} · ${model.has_key ? "Credential saved" : "No credential"} · ${model.timeout_seconds}s timeout`,
      ),
      node("small", `${model.context_limit_chars ? `Context hint: ${model.context_limit_chars.toLocaleString()} characters` : "Context limit unknown"} · ${(model.task_tags || []).length ? `Tasks: ${model.task_tags.join(", ")}` : "No task labels"}`),
    );
    const actions = node("div", null, "model-actions");
    actions.append(actionButton("Edit", () => edit(model)));
    actions.append(
      actionButton(model.enabled ? "Disable" : "Enable", async () => {
        try {
          const { id, has_key, auth_method, created_at, ...config } = model;
          await api(`/models/${id}`, {
            method: "PUT",
            body: JSON.stringify({ ...config, enabled: !model.enabled }),
          });
          await load();
          notice("Model updated.");
        } catch (e) {
          notice(e.message);
        }
      }),
    );
    const test = actionButton("Test connection", () =>
      confirmAction(
        "Test this model?",
        "This sends a short greeting to the provider and may consume quota or credits. The test appears in Usage statistics.",
        async () => {
          test.disabled = true;
          try {
            await api(`/models/${model.id}/test`, { method: "POST" });
            notice(`${model.name}: response verified.`);
          } finally {
            test.disabled = false;
          }
        },
      ),
    );
    test.disabled = !model.enabled;
    actions.append(test);
    if (model.kind === "openrouter")
      actions.append(
        actionButton("Connect account", async () => {
          try {
            const result = await api(`/oauth/openrouter/${model.id}/start`, {
              method: "POST",
            });
            window.location.assign(result.url);
          } catch (e) {
            notice(e.message);
          }
        }),
      );
    actions.append(
      actionButton("Delete", () =>
        confirmAction(
          "Delete model connection?",
          "The saved credential will be removed. History and usage records remain. Chats using it will need another model selected. To revoke an issued key, also revoke it with the provider.",
          async () => {
            await api(`/models/${model.id}`, { method: "DELETE" });
            await load();
            notice("Model connection removed.");
          },
        ),
      ),
    );
    card.append(heading, actions);
    $("model-list").append(card);
    if (model.enabled)
      $("default-model").append(new Option(model.name, model.id));
  }
  $("default-model").value = preferences.default_model_id || "";
  $("default-tokens").value = preferences.max_output_tokens;
  $("workspace-budget").value = preferences.monthly_budget_usd ?? "";
  $("workspace-request-limit").value = preferences.monthly_request_limit ?? "";
  $("budget-warning").value = preferences.budget_warning_percent ?? 80;
  $("default-system").value = preferences.system_prompt;
  for (let index = 1; index <= 3; index++) {
    const select = $(`fallback-${index}`);
    select.replaceChildren(new Option("None", ""));
    for (const model of models) select.append(new Option(`${model.name}${model.enabled ? "" : " (disabled)"}`, model.id));
    select.value = preferences.fallback_model_ids?.[index - 1] || "";
  }
  renderProfiles();
}
function renderProfiles() {
  const list = $("profile-list");
  list.replaceChildren();
  const profiles = preferences.routing_profiles || [];
  if (!profiles.length) list.append(node("p", "No routing profiles yet.", "empty-list"));
  for (const profile of profiles) {
    const card = node("article", null, "model-card");
    const copy = node("div");
    copy.append(node("h3", profile.name), node("p", `${profile.mode} · ${profile.priority} · up to ${profile.max_calls} calls${profile.max_estimated_cost_usd == null ? "" : ` · $${profile.max_estimated_cost_usd} estimated limit`}`));
    const actions = node("div", null, "model-actions");
    actions.append(actionButton("Edit", () => {
      editingProfile = profile.name;
      $("profile-name").value = profile.name;
      $("profile-mode").value = profile.mode;
      $("profile-priority").value = profile.priority;
      $("profile-calls").value = profile.max_calls;
      $("profile-cost").value = profile.max_estimated_cost_usd ?? "";
      $("profile-save").textContent = "Save profile";
      $("profile-cancel").hidden = false;
      $("profile-name").focus();
    }));
    actions.append(actionButton("Delete", () => confirmAction("Delete routing profile?", "Chats using this profile will need another profile selected for their next message.", async () => {
      await saveProfiles(profiles.filter(p => p.name !== profile.name));
      notice("Routing profile deleted.");
    })));
    card.append(copy, actions);
    list.append(card);
  }
}
async function saveProfiles(profiles) {
  preferences = await api("/settings", { method: "PUT", body: JSON.stringify({ ...preferences, routing_profiles: profiles }) });
  renderProfiles();
}
$("profile-mode").onchange = () => { $("profile-calls").value = {single: 1, review: 3, split: 4}[$("profile-mode").value]; };
$("profile-cancel").onclick = () => {
  editingProfile = null;
  $("profile-form").reset();
  $("profile-save").textContent = "Add profile";
  $("profile-cancel").hidden = true;
};
$("profile-form").onsubmit = async event => {
  event.preventDefault();
  const profiles = (preferences.routing_profiles || []).filter(p => p.name !== editingProfile);
  profiles.push({ name: $("profile-name").value.trim(), mode: $("profile-mode").value,
    priority: $("profile-priority").value, max_calls: Number($("profile-calls").value),
    max_estimated_cost_usd: $("profile-cost").value || null });
  try {
    await saveProfiles(profiles);
    $("profile-cancel").click();
    notice("Routing profile saved.");
  } catch (e) { notice(e.message); }
};
$("add-model").onclick = () => edit();
$("refresh-diagnostics").onclick = loadDiagnostics;
$("model-kind").onchange = kindChanged;
$("model-cancel").onclick = () => $("model-dialog").close();
$("confirm-cancel").onclick = () => $("confirm-dialog").close();
$("confirm-action").onclick = async () => {
  const action = pendingAction;
  $("confirm-dialog").close();
  try {
    await action();
  } catch (e) {
    notice(e.message);
  }
};
$("model-form").onsubmit = async (event) => {
  event.preventDefault();
  $("model-save").disabled = true;
  $("model-error").hidden = true;
  const body = {
    input_price_per_million: $("input-price").value || null,
    output_price_per_million: $("output-price").value || null,
    monthly_budget_usd: $("model-budget").value || null,
    monthly_request_limit: $("model-request-limit").value ? Number($("model-request-limit").value) : null,
    usage_group: $("usage-group").value,
    allow_fallback: $("allow-fallback").checked,
    name: $("model-name").value,
    kind: $("model-kind").value,
    model: $("model-code").value,
    base_url: $("model-url").value,
    api_key: $("model-key").value || null,
    clear_key: $("clear-key").checked,
    enabled: $("model-enabled").checked,
    timeout_seconds: Number($("model-timeout").value),
    max_output_tokens: Number($("model-tokens").value),
    context_limit_chars: $("context-limit").value ? Number($("context-limit").value) : null,
    task_tags: [...document.querySelectorAll('input[name="task-tag"]:checked')].map(input => input.value),
    temperature:
      $("model-temperature").value === ""
        ? null
        : Number($("model-temperature").value),
    system_prompt: $("model-system").value,
    include_usage: $("model-usage").checked,
    token_parameter: $("model-token-parameter").value,
  };
  try {
    await api(editing ? `/models/${editing}` : "/models", {
      method: editing ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    $("model-key").value = "";
    $("model-dialog").close();
    await load();
    notice(
      "Model saved. Configuration alone does not verify provider availability.",
    );
  } catch (e) {
    $("model-error").textContent = e.message;
    $("model-error").hidden = false;
  } finally {
    $("model-save").disabled = false;
  }
};
$("defaults-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    preferences = await api("/settings", {
      method: "PUT",
      body: JSON.stringify({
        monthly_budget_usd: $("workspace-budget").value || null,
        monthly_request_limit: $("workspace-request-limit").value ? Number($("workspace-request-limit").value) : null,
        budget_warning_percent: Number($("budget-warning").value),
        fallback_model_ids: [1, 2, 3].map(i => $(`fallback-${i}`).value).filter(Boolean),
        default_model_id: $("default-model").value || null,
        max_output_tokens: Number($("default-tokens").value),
        system_prompt: $("default-system").value,
        routing_profiles: preferences.routing_profiles || [],
      }),
    });
    notice("Workspace defaults saved.");
  } catch (e) {
    notice(e.message);
  }
};
load()
  .then(() => {
    const result = new URLSearchParams(location.search).get("login");
    if (result) {
      notice(
        result === "connected"
          ? "OpenRouter account connected. Choose this model in chat or test the connection."
          : "Login was not completed. Start again from Connect account.",
      );
      history.replaceState(null, "", "/settings");
    }
  })
  .catch((e) => notice(e.message));
loadDiagnostics();
