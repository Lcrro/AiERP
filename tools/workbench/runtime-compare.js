const $ = (selector) => document.querySelector(selector);
const state = { bootstrap: null, progressTimer: null, progressStartedAt: 0, progressPhase: 0 };
const progressPhases = ["正在理解你的需求…", "正在查找相关业务能力…", "正在读取当前能力说明书…", "正在核对项目、物料和业务资料…", "正在准备操作摘要和回复…"];
const statusLabels = { ok: "已完成", completed: "已完成", failed: "失败", disabled: "已暂停", running: "运行中" };

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
  status.textContent = statusLabels[data.status] || data.status || "未知";
  status.className = `status ${data.status === "failed" ? "failed" : data.status === "disabled" ? "disabled" : "ok"}`;
  $(`.runtime-column[data-side="${side}"]`).classList.toggle("is-disabled", data.status === "disabled");
  const tools = data.tool_summary?.tools || [];
  $(`#${side}Metrics`).innerHTML = [
    metric("耗时", `${data.duration_ms || 0} ms`),
    metric("动作数", data.tool_summary?.calls ?? (data.steps || []).length),
    metric("追问数", data.question_count || 0),
    metric("模型", data.status === "disabled" ? "未调用" : data.model || "DeepSeek"),
  ].join("");
  const message = $(`#${side}Message`);
  message.textContent = data.message || "没有生成回复";
  message.classList.toggle("empty", !data.message);
  renderSteps(side, data);
  renderDetails(side, data);
}

function updateAssistantProgress() {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - state.progressStartedAt) / 1000));
  const nextPhase = Math.min(progressPhases.length - 1, Math.floor(elapsedSeconds / 4));
  state.progressPhase = nextPhase;
  $("#assistantPhase").textContent = progressPhases[nextPhase];
  $("#assistantElapsed").textContent = `${elapsedSeconds} 秒`;
}

function startAssistantProgress() {
  clearInterval(state.progressTimer);
  state.progressStartedAt = Date.now();
  state.progressPhase = 0;
  $("#assistantActivity").hidden = false;
  updateAssistantProgress();
  state.progressTimer = setInterval(updateAssistantProgress, 1000);
}

function stopAssistantProgress() {
  clearInterval(state.progressTimer);
  state.progressTimer = null;
  $("#assistantActivity").hidden = true;
}

function setRunning(running, includeExisting = false) {
  $("#runCompare").disabled = running;
  $("#runCompare").textContent = running ? "小助理处理中..." : includeExisting ? "开始对比" : "运行新版";
  $("#includeExisting").disabled = running;
  if (running) {
    const openclawStatus = $("#openclawStatus");
    openclawStatus.textContent = "运行中";
    openclawStatus.className = "status running";
    const existingStatus = $("#existingStatus");
    existingStatus.textContent = includeExisting ? "运行中" : "已暂停";
    existingStatus.className = includeExisting ? "status running" : "status disabled";
  }
}

function syncLegacyMode() {
  const enabled = $("#includeExisting").checked;
  const column = $('.runtime-column[data-side="existing"]');
  column.classList.toggle("is-disabled", !enabled);
  if (!enabled) {
    $("#existingStatus").textContent = "已暂停";
    $("#existingStatus").className = "status disabled";
    $("#existingMessage").textContent = "默认不调用旧版，避免额外消耗 Token";
  } else {
    $("#existingStatus").textContent = "等待对照";
    $("#existingStatus").className = "status";
    $("#existingMessage").textContent = "运行后显示旧版结果";
  }
  $("#runCompare").textContent = enabled ? "开始对比" : "运行新版";
}

$("#project").addEventListener("change", fillEmployees);
$("#includeExisting").addEventListener("change", syncLegacyMode);
$("#compareForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const includeExisting = $("#includeExisting").checked;
  setRunning(true, includeExisting);
  startAssistantProgress();
  $("#summary").hidden = true;
  try {
    const payload = await fetchJson("/api/agent-runtime/compare", {
      method: "POST",
      body: JSON.stringify({
        user: $("#employee").value,
        project_code: $("#project").value,
        text: $("#requestText").value.trim(),
        include_existing: includeExisting,
      }),
    });
    renderSide("existing", payload.existing);
    renderSide("openclaw", payload.openclaw);
    $("#summary").textContent = payload.notice;
    $("#summary").hidden = false;
  } catch (error) {
    $("#summary").textContent = error.message;
    $("#summary").hidden = false;
  } finally {
    stopAssistantProgress();
    setRunning(false, includeExisting);
  }
});

bootstrap().catch((error) => {
  $("#summary").textContent = `初始化失败：${error.message}`;
  $("#summary").hidden = false;
});

syncLegacyMode();
