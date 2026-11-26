"use strict";
let refreshVersion = 0;
async function refresh() {
  const version = ++refreshVersion;
  const params = new URLSearchParams();
  for (const id of ["start", "end"])
    if ($(id).value) params.set(id, $(id).value);
  if ($("filter-model").value) params.set("model_id", $("filter-model").value);
  const data = await api(`/usage?${params}`);
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
