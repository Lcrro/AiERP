const $ = (selector) => document.querySelector(selector);
const state = { bootstrap: null };

function esc(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json", Accept: "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.message || `请求失败：${response.status}`);
  return payload;
}

function employeesForProject() {
  return state.bootstrap.projects.find((row) => row.project_code === $("#project").value)?.employees || [];
}

function fillEmployees() {
  const employees = employeesForProject();
  $("#employee").innerHTML = employees.map((row) => `<option value="${esc(row.user_email)}">${esc(row.employee_name)} · ${esc(row.project_position || row.designation || "")}</option>`).join("");
  const materialClerk = employees.find((row) => row.employee_name === "毛晓泉");
  if (materialClerk) $("#employee").value = materialClerk.user_email;
}

async function bootstrap() {
  state.bootstrap = await fetchJson("/api/workbench/bootstrap");
  $("#project").innerHTML = state.bootstrap.projects.map((row) => `<option value="${esc(row.project_code)}">${esc(row.project_short_name)} · ${esc(row.project_operating_status)}</option>`).join("");
  const project = state.bootstrap.projects.find((row) => row.project_code === "PRJ-HL-13");
  if (project) $("#project").value = project.project_code;
  fillEmployees();
}

function metric(label, value) {
  return `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function renderSteps(side, data) {
  const target = $(`#${side}Steps`);
  const nodes = data.loaded_nodes || [];
  const steps = data.steps || [];
  const nodeHtml = nodes.length ? `<div class="node-list">${nodes.map((node) => `<span class="chip">${esc(node.label || node.node_id)}</span>`).join("")}</div>` : "";
  const stepHtml = steps.map((step, index) => {
    const title = step.tool || step.label || step.action || "步骤";
    const detail = step.summary || step.result?.status || step.action || "";
    return `<div class="step"><span class="step-index">${index + 1}</span><div><strong>${esc(title)}</strong><small>${esc(detail)}</small></div></div>`;
  }).join("");
  target.classList.toggle("empty", !nodes.length && !steps.length);
  target.innerHTML = nodeHtml + stepHtml || "本轮没有可审计步骤";
}

function renderDetails(side, data) {
  const target = $(`#${side}Details`);
  const questions = data.questions || [];
  const confirmation = data.confirmation;
  const questionHtml = questions.length ? `<div class="question-list">${questions.map((question) => `<span class="chip">${esc(question)}</span>`).join("")}</div>` : "";
  let confirmationHtml = "";
  if (confirmation) {
    const rows = Object.entries(confirmation).filter(([, value]) => value !== null && value !== undefined && typeof value !== "object");
    confirmationHtml = `<div class="confirmation">${rows.map(([key, value]) => `<div><span>${esc(key)}</span><strong>${esc(value)}</strong></div>`).join("")}</div>`;
    if (Array.isArray(confirmation.items)) confirmationHtml += `<div class="node-list">${confirmation.items.map((item) => `<span class="chip">${esc(item.item_code)} × ${esc(item.qty)} ${esc(item.uom)}</span>`).join("")}</div>`;
  }
  target.classList.toggle("empty", !questions.length && !confirmation);
  target.innerHTML = questionHtml + confirmationHtml || "本轮未提出追问，也未生成待确认动作";
}

function renderSide(side, data) {
  const status = $(`#${side}Status`);
  status.textContent = data.status || "未知";
  status.className = `status ${data.status === "failed" ? "failed" : "ok"}`;
  const tools = data.tool_summary?.tools || [];
  $(`#${side}Metrics`).innerHTML = [
    metric("耗时", `${data.duration_ms || 0} ms`),
    metric("动作数", data.tool_summary?.calls ?? (data.steps || []).length),
    metric("追问数", data.question_count || 0),
    metric("模型", data.model || "DeepSeek"),
  ].join("");
  const message = $(`#${side}Message`);
  message.textContent = data.message || "没有生成回复";
  message.classList.toggle("empty", !data.message);
  renderSteps(side, data);
  renderDetails(side, data);
}

function setRunning(running) {
  $("#runCompare").disabled = running;
  $("#runCompare").textContent = running ? "两侧运行中..." : "开始对比";
  if (running) {
    for (const side of ["existing", "openclaw"]) {
      const status = $(`#${side}Status`);
      status.textContent = "运行中";
      status.className = "status running";
    }
  }
}

$("#project").addEventListener("change", fillEmployees);
$("#compareForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  setRunning(true);
  $("#summary").hidden = true;
  try {
    const payload = await fetchJson("/api/agent-runtime/compare", {
      method: "POST",
      body: JSON.stringify({ user: $("#employee").value, project_code: $("#project").value, text: $("#requestText").value.trim() }),
    });
    renderSide("existing", payload.existing);
    renderSide("openclaw", payload.openclaw);
    $("#summary").textContent = payload.notice;
    $("#summary").hidden = false;
  } catch (error) {
    $("#summary").textContent = error.message;
    $("#summary").hidden = false;
  } finally {
    setRunning(false);
  }
});

bootstrap().catch((error) => {
  $("#summary").textContent = `初始化失败：${error.message}`;
  $("#summary").hidden = false;
});
