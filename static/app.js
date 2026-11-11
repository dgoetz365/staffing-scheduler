"use strict";

let workspace = null;
let busy = false;
const byId = (id) => document.getElementById(id);
const time = (minutes) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
const range = (shift) => `${time(shift.start)}–${time(shift.end)}`;
const date = (value) => new Date(value).toLocaleString([], {dateStyle: "medium", timeStyle: "short"});
const person = (id) => workspace.volunteers.find((item) => item.id === id);
const shiftById = (id) => workspace.shifts.find((item) => item.id === id);

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function message(text, error = false) {
  const node = byId("feedback");
  node.className = error ? "feedback error" : "feedback";
  node.setAttribute("role", error ? "alert" : "status");
  node.textContent = text;
}

function option(value, label) {
  const node = element("option", label);
  node.value = String(value);
  return node;
}

function lock(value) {
  busy = value;
  byId("workspace").setAttribute("aria-busy", String(value));
  document.querySelectorAll("button:not([role=tab]), form select, form textarea").forEach((node) => { node.disabled = value || !workspace; });
  byId("refresh").disabled = value;
  if (workspace && !value) {
    byId("publish").disabled = workspace.shifts.some((shift) => workspace.assignments.filter((a) => a.shift_id === shift.id).length !== shift.capacity);
    byId("request-form").querySelector("button").disabled = workspace.assignments.length === 0;
  }
}

async function load() {
  const response = await fetch("/api/state", {cache: "no-store"});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Could not read the workspace.");
  workspace = result;
  render();
}

async function refresh() {
  if (busy) return;
  lock(true);
  try {
    await load();
    message("Workspace refreshed. Choose an open shift or review a change request.");
  } catch (error) {
    message(`${error.message} Check that the local server is running, then refresh.`, true);
  } finally { lock(false); }
}

async function act(action, fields) {
  if (busy || !workspace) return;
  lock(true);
  try {
    const response = await fetch(`/api/${action}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({version: workspace.version, ...fields})
    });
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 409) await load();
      throw new Error(result.error || "The change was not accepted.");
    }
    try {
      await load();
      message(result.message);
      if (action === "request") byId("reason").value = "";
    } catch (error) {
      message(`Change saved, but the workspace could not refresh. Refresh before making another change. ${error.message}`, true);
    }
  } catch (error) {
    message(error.message, true);
  } finally { lock(false); }
}

function renderDraft() {
  const filled = workspace.assignments.length;
  const capacity = workspace.shifts.reduce((sum, s) => sum + s.capacity, 0);
  byId("coverage").textContent = `${filled} of ${capacity} places filled. ${filled === capacity ? "Ready to publish a fixed schedule issue." : "Fill every place to publish."}`;
  const list = byId("shift-list");
  list.replaceChildren();
  workspace.shifts.forEach((shift) => {
    const assigned = workspace.assignments.filter((a) => a.shift_id === shift.id);
    const row = element("article", undefined, "shift");
    row.setAttribute("aria-label", `${shift.station}, ${range(shift)}`);
    row.append(element("div", range(shift), "shift-time"));
    const description = element("div");
    description.append(element("h3", shift.station), element("span", shift.role, "shift-role"), element("span", assigned.length === shift.capacity ? "Filled" : `${shift.capacity - assigned.length} open place`, assigned.length === shift.capacity ? "badge" : "badge open"));
    row.append(description);
    const assignment = element("div", undefined, "shift-assignment");
    const names = element("ul", undefined, "assignees");
    assigned.forEach((a) => {
      const item = element("li");
      const remove = element("button", "Remove", "remove");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove ${person(a.volunteer_id).name} from ${shift.station} at ${time(shift.start)}`);
      remove.addEventListener("click", () => act("remove", {shift_id: shift.id, volunteer_id: a.volunteer_id}));
      item.append(element("span", person(a.volunteer_id).name), remove);
      names.append(item);
    });
    assignment.append(names);
    if (assigned.length < shift.capacity) {
      const form = element("form", undefined, "assignment-form");
      const label = element("label", "Assign a volunteer");
      label.htmlFor = `volunteer-${shift.id}`;
      const select = element("select");
      select.id = label.htmlFor;
      select.required = true;
      select.append(option("", "Choose volunteer…"));
      workspace.volunteers.forEach((volunteer) => select.append(option(volunteer.id, volunteer.name)));
      const submit = element("button", "Assign");
      submit.type = "submit";
      form.append(label, select, submit);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        act("assign", {shift_id: shift.id, volunteer_id: Number(select.value)});
      });
      assignment.append(form);
    }
    row.append(assignment);
    list.append(row);
  });
  const roster = byId("roster-list");
  roster.replaceChildren();
  workspace.volunteers.forEach((volunteer) => {
    const item = element("li");
    item.append(element("strong", volunteer.name), element("span", volunteer.roles.join(" · "), "roles"), element("span", volunteer.windows.map(([start, end]) => `${time(start)}–${time(end)}`).join(", "), "window"));
    roster.append(item);
  });
}

function renderPublished() {
  const select = byId("snapshot");
  const selected = select.value;
  select.replaceChildren();
  workspace.publications.forEach((publication) => select.append(option(publication.id, `Issue ${publication.id} · ${date(publication.created)}`)));
  if (workspace.publications.some((p) => String(p.id) === selected)) select.value = selected;
  select.disabled = workspace.publications.length === 0;
  renderSnapshot();
}

function renderSnapshot() {
  const content = byId("snapshot-content");
  content.replaceChildren();
  const publication = workspace.publications.find((p) => String(p.id) === byId("snapshot").value);
  if (!publication) {
    content.append(element("p", "No schedule has been published yet. Fill the open places in the draft, then choose Publish schedule.", "empty"));
    return;
  }
  const data = publication.payload;
  content.append(element("p", `Issue ${publication.id} · Published ${date(publication.created)} from workspace version ${publication.draft_version}. This issue is immutable.`, "snapshot-heading"));
  const wrapper = element("div", undefined, "table-scroll");
  const table = element("table", undefined, "snapshot-table");
  const caption = element("caption", `Schedule issue ${publication.id}`);
  const head = element("thead");
  const tr = element("tr");
  ["Time", "Station", "Role", "Volunteer"].forEach((text) => { const th = element("th", text); th.scope = "col"; tr.append(th); });
  head.append(tr);
  const body = element("tbody");
  data.shifts.forEach((shift) => {
    const row = element("tr");
    const names = data.assignments.filter((a) => a.shift_id === shift.id).map((a) => data.volunteers.find((p) => p.id === a.volunteer_id).name).join(", ");
    [range(shift), shift.station, shift.role, names].forEach((text) => row.append(element("td", text)));
    body.append(row);
  });
  table.append(caption, head, body);
  wrapper.append(table);
  content.append(wrapper);
}

function renderRequests() {
  byId("request-count").textContent = String(workspace.requests.filter((r) => r.status === "pending").length);
  const assignment = byId("assignment");
  const previous = assignment.value;
  assignment.replaceChildren();
  workspace.assignments.forEach((a) => {
    const shift = shiftById(a.shift_id);
    assignment.append(option(`${a.shift_id}:${a.volunteer_id}`, `${time(shift.start)} ${shift.station} · ${person(a.volunteer_id).name}`));
  });
  if (Array.from(assignment.options).some((o) => o.value === previous)) assignment.value = previous;
  const replacement = byId("replacement");
  const priorReplacement = replacement.value;
  replacement.replaceChildren(option("", "Choose replacement…"));
  workspace.volunteers.forEach((p) => replacement.append(option(p.id, `${p.name} · ${p.roles.join(", ")}`)));
  replacement.value = priorReplacement;
  const list = byId("request-list");
  list.replaceChildren();
  if (!workspace.requests.length) list.append(element("p", "No changes requested yet. Propose a replacement using an existing draft assignment.", "empty"));
  workspace.requests.forEach((request) => {
    const shift = shiftById(request.shift_id);
    const item = element("article", undefined, "request-item");
    const header = element("header");
    header.append(element("h3", `${shift.station} · ${range(shift)}`), element("span", request.status, request.status === "pending" ? "badge open" : "badge"));
    item.append(header, element("p", `${person(request.from_id).name} → ${person(request.to_id).name}`), element("p", request.reason), element("small", `Request ${request.id} · ${date(request.created)}`));
    if (request.status === "pending") {
      const actions = element("div", undefined, "actions");
      ["approve", "decline"].forEach((decision) => {
        const button = element("button", decision === "approve" ? "Approve change" : "Decline", decision === "decline" ? "secondary" : undefined);
        button.type = "button";
        button.setAttribute("aria-label", `${decision} request ${request.id}`);
        button.addEventListener("click", () => act("review", {request_id: request.id, decision}));
        actions.append(button);
      });
      item.append(actions);
    }
    list.append(item);
  });
}

function render() {
  byId("revision").textContent = `Saved workspace · version ${workspace.version}`;
  renderDraft();
  renderPublished();
  renderRequests();
  const events = byId("event-list");
  events.replaceChildren();
  workspace.events.forEach((event) => {
    const item = element("li");
    const stamp = element("time", date(event.created));
    stamp.dateTime = event.created;
    item.append(stamp, element("span", event.detail), element("small", `v${event.version}`));
    events.append(item);
  });
}

const tabs = Array.from(document.querySelectorAll("[role=tab]"));
function activate(tab) {
  tabs.forEach((item) => {
    const active = item === tab;
    item.setAttribute("aria-selected", String(active));
    item.tabIndex = active ? 0 : -1;
    byId(item.getAttribute("aria-controls")).hidden = !active;
  });
}
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activate(tab));
  tab.addEventListener("keydown", (event) => {
    const keys = {ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1};
    if (Object.hasOwn(keys, event.key)) {
      event.preventDefault();
      const next = tabs[keys[event.key]];
      activate(next);
      next.focus();
    }
  });
});
byId("refresh").addEventListener("click", refresh);
byId("publish").addEventListener("click", () => act("publish", {}));
byId("snapshot").addEventListener("change", renderSnapshot);
byId("request-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const [shift_id, from_id] = byId("assignment").value.split(":").map(Number);
  act("request", {shift_id, from_id, to_id: Number(byId("replacement").value), reason: byId("reason").value});
});
refresh();
