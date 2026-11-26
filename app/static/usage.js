"use strict";
let refreshVersion = 0;
function formatCost(value) {
  const amount = Number(value);
  return amount > 0 && amount < 0.000001 ? "<0.000001" : amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6});
}
async function refresh() {
  const version = ++refreshVersion;
  const params = new URLSearchParams();
  for (const id of ["start", "end"])
    if ($(id).value) params.set(id, $(id).value);
  if ($("filter-model").value) params.set("model_id", $("filter-model").value);
  const [data, budgets] = await Promise.all([api(`/usage?${params}`), api("/budgets")]);
  if (version !== refreshVersion) return;
  $("export").href = `/api/v1/usage/export?${params}`;
  $("summary").replaceChildren();
  for (const [label, value] of [
    ["Requests", data.requests],
    ["Completed", data.complete],
    ["Failed", data.failed],
    ["Reported tokens", data.reported_tokens],
    ["Unknown usage", data.unknown_usage],
  ]) {
    const card = node("div", null, "stat");
    card.append(
      node("span", label),
      node("strong", Number(value).toLocaleString()),
    );
    $("summary").append(card);
  }
  const costCard = node("div", null, "stat");
  costCard.append(node("span", "Estimated cost (USD)"), node("strong", formatCost(data.estimated_cost_usd)), node("small", `${data.unknown_cost_requests} requests with unknown cost`));
  $("summary").append(costCard);
  $("budgets").replaceChildren();
  for (const budget of [{name: "Workspace", ...budgets.workspace}, ...budgets.models.filter(m => m.budget_usd !== null)]) {
    const text = `${budget.name} · ${budgets.month_utc}: $${formatCost(budget.estimated_cost_usd)} estimated / ${budget.budget_usd === null ? "no budget set" : "$" + budget.budget_usd + " target"} · ${budget.status.replace("_", " ")} · ${budget.unknown_cost_requests} unknown-cost requests`;
    $("budgets").append(node("p", text));
  }
  $("models-body").replaceChildren();
  $("empty").hidden = !!data.models.length;
  for (const model of data.models) {
    const row = node("tr");
    for (const value of [
      `${model.label} · ${model.provider} / ${model.model}`,
      model.requests,
      model.complete,
      model.failed,
      model.cancelled + model.interrupted,
      model.reported_tokens,
      model.unknown_usage,
      formatCost(model.estimated_cost_usd),
      model.unknown_cost_requests,
    ])
      row.append(node("td", value));
    $("models-body").append(row);
  }
  $("recent-body").replaceChildren();
  for (const event of data.recent) {
    const row = node("tr");
    for (const value of [
      new Date(event.started_at).toISOString().replace("T", " ").slice(0, 19),
      event.label,
      event.source,
      event.status,
      event.input_tokens ?? "Unknown",
      event.output_tokens ?? "Unknown",
      event.total_tokens ?? "Unknown",
      event.duration_ms == null ? "—" : `${event.duration_ms} ms`,
      event.estimated_cost_usd == null ? "Unknown" : formatCost(event.estimated_cost_usd),
    ])
      row.append(node("td", value));
    $("recent-body").append(row);
  }
  notice();
}
$("filters").onsubmit = (event) => {
  event.preventDefault();
  refresh().catch((e) => notice(e.message));
};
api("/models")
  .then((models) => {
    for (const model of models)
      $("filter-model").append(new Option(model.name, model.id));
    return refresh();
  })
  .catch((e) => notice(e.message));
