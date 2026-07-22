const $ = (selector) => document.querySelector(selector);
const SOURCE_LABELS = {
  user_input: "员工输入",
  user_choice: "员工选择",
  runtime_context: "当前上下文",
  resolver: "Resolver",
  source_document: "来源单据",
  erp_default: "ERP 默认",
  system_generated: "系统生成",
  derived: "派生",
  fixed: "固定值",
};
const CONTROL_LABELS = {
  read_only: "自动带出",
  select: "查表选择",
  search_select: "检索后选择",
  date: "日期格式",
  number: "数值约束",
  derived: "自动继承",
  fixed: "模板固定",
};

const state = { relations: null, facts: null, itemOptions: [] };

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `请求失败：${response.status}`);
  return payload;
}

function formFacts() {
  return {
    context: {
      company: $("#company").value.trim(),
      erpnext_project: $("#project").value.trim(),
      warehouse: $("#warehouse").value.trim(),
    },
    user: { schedule_date: $("#scheduleDate").value },
    items: [{
      item_code: $("#itemCode").value.trim(),
      qty: $("#qty").value === "" ? null : Number($("#qty").value),
      uom: $("#uom").value.trim(),
    }],
  };
}

function setFacts(facts) {
  $("#company").value = facts.context.company || "";
  $("#scheduleDate").value = facts.user.schedule_date || "";
  const item = facts.items[0] || {};
  $("#qty").value = item.qty ?? "";
}

function optionLabel(option) {
  return option.meta ? `${option.label} · ${option.meta}` : option.label;
}

function populateSelect(element, options, selected, placeholder = "请选择") {
  element.innerHTML = `<option value="">${esc(placeholder)}</option>${options.map((option) =>
    `<option value="${esc(option.value)}"${option.value === selected ? " selected" : ""}>${esc(optionLabel(option))}</option>`
  ).join("")}`;
  if (selected && !options.some((option) => option.value === selected)) {
    element.insertAdjacentHTML("beforeend", `<option value="${esc(selected)}" selected>${esc(selected)}</option>`);
  }
}

async function loadOptions(entity, params = {}) {
  const query = new URLSearchParams({ entity, ...params });
  const payload = await fetchJson(`/api/operation-model/options?${query}`);
  return payload.options || [];
}

async function loadProjects(selected) {
  const options = await loadOptions("project");
  populateSelect($("#project"), options, selected, "选择项目");
}

async function loadWarehouses(selected) {
  const options = await loadOptions("warehouse", { project: $("#project").value });
  const preferred = selected || options.find((option) => option.project)?.value || options[0]?.value || "";
  populateSelect($("#warehouse"), options, preferred, "选择项目仓库");
}

async function loadItems(query, selected = "") {
  state.itemOptions = await loadOptions("item", { q: query });
  populateSelect($("#itemCode"), state.itemOptions, selected, "选择标准物料");
  updateItemMeta();
}

async function loadUoms(selected = "") {
  const options = await loadOptions("uom", { item_code: $("#itemCode").value });
  const preferred = selected || options[0]?.value || "";
  populateSelect($("#uom"), options, preferred, "选择单位");
}

function updateItemMeta() {
  const selected = state.itemOptions.find((option) => option.value === $("#itemCode").value);
  $("#itemMeta").textContent = selected?.meta || "必须选择 Item 表中的真实编码";
}

function displayValue(slot) {
  if (slot.scope === "item") return slot.values.length ? slot.values.join("；") : "未提供";
  return slot.value === null || slot.value === "" ? "未提供" : String(slot.value);
}

function render(evaluation) {
  const operation = evaluation.operation;
  $("#operationTitle").textContent = `${operation.label} · ${operation.operation_id}`;
  $("#summary").innerHTML = `
    <span><b>${evaluation.slots.length}</b> 个字段槽位</span>
    <span><b>${evaluation.missing.length}</b> 个缺失</span>
    <span><b>${evaluation.invalid.length}</b> 个非法</span>
    <span><b>${evaluation.blocked.length}</b> 个等待上游</span>`;
  $("#slotRows").innerHTML = evaluation.slots.map((slot) => `
    <tr class="${slot.status}">
      <td><b>${String(slot.serial).padStart(2, "0")}</b></td>
      <td><strong>${esc(slot.label)}</strong><small>${esc(slot.slot_id)}</small></td>
      <td>${esc(SOURCE_LABELS[slot.source] || slot.source)}</td>
      <td><strong>${esc(CONTROL_LABELS[slot.control] || slot.control)}</strong><small>${esc(slot.lookup_doctype ? `关联 ${slot.lookup_doctype}` : slot.format_hint || slot.default_strategy || "")}</small></td>
      <td><code>${esc(slot.target_path)}</code></td>
      <td>${esc(displayValue(slot))}</td>
      <td><span class="status ${slot.status}">${slot.status === "resolved" ? "已就绪" : slot.status === "missing" ? "缺失" : slot.status === "blocked" ? "等待上游" : "无效"}</span><small>${esc(slot.reason)}</small></td>
    </tr>`).join("");
  const ready = evaluation.status === "ready";
  $("#readiness").className = `readiness ${ready ? "ready" : "blocked"}`;
  $("#readiness").innerHTML = ready
    ? `<strong>可以编译</strong><span>所有必填槽位已满足，Runtime 可以生成精确 ToolCall。</span>`
    : `<strong>暂不能编译</strong><span>请先处理：${esc([...evaluation.missing, ...evaluation.invalid, ...evaluation.blocked].join("、"))}</span>`;
  $("#toolCall").textContent = evaluation.tool_call
    ? JSON.stringify(evaluation.tool_call, null, 2)
    : "ToolCall 尚未生成。补齐左侧字段后再试。";
  $("#rules").innerHTML = evaluation.rules.map((rule) => `<article><strong>${esc(rule.label)}</strong><code>${esc(rule.expression)}</code><span>${esc(rule.message)}</span></article>`).join("");
}

async function compile() {
  $("#compile").disabled = true;
  try {
    const payload = await fetchJson("/api/operation-model/compile", { method: "POST", body: JSON.stringify(formFacts()) });
    render(payload.evaluation);
  } catch (error) {
    $("#toolCall").textContent = error.message;
  } finally {
    $("#compile").disabled = false;
  }
}

async function bootstrap() {
  try {
    const payload = await fetchJson("/api/operation-model/material-request");
    state.relations = payload.relations;
    state.facts = payload.facts;
    setFacts(payload.facts);
    const item = payload.facts.items[0] || {};
    await loadProjects(payload.facts.context.erpnext_project || "");
    await loadWarehouses(payload.facts.context.warehouse || "");
    $("#itemSearch").value = item.item_code || "";
    await loadItems(item.item_code || "", item.item_code || "");
    await loadUoms(item.uom || "");
    render(payload.evaluation);
    $("#relations").textContent = JSON.stringify(payload.relations, null, 2);
  } catch (error) {
    $("#operationTitle").textContent = `加载失败：${error.message}`;
  }
}

$("#compile").addEventListener("click", compile);
$("#project").addEventListener("change", async () => {
  await loadWarehouses();
  compile();
});
$("#warehouse").addEventListener("change", compile);
$("#scheduleDate").addEventListener("change", compile);
$("#qty").addEventListener("change", compile);
$("#uom").addEventListener("change", compile);
$("#searchItem").addEventListener("click", async () => {
  await loadItems($("#itemSearch").value.trim());
});
$("#itemSearch").addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  await loadItems($("#itemSearch").value.trim());
});
$("#itemCode").addEventListener("change", async () => {
  updateItemMeta();
  await loadUoms();
  compile();
});
$("#clearResolver").addEventListener("click", () => {
  $("#project").value = "";
  $("#warehouse").value = "";
  $("#itemCode").value = "";
  compile();
});

bootstrap();
