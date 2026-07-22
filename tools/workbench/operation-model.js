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

const state = { relations: null };

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
  $("#project").value = facts.context.erpnext_project || "";
  $("#warehouse").value = facts.context.warehouse || "";
  $("#scheduleDate").value = facts.user.schedule_date || "";
  const item = facts.items[0] || {};
  $("#itemCode").value = item.item_code || "";
  $("#qty").value = item.qty ?? "";
  $("#uom").value = item.uom || "";
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
      <td><code>${esc(slot.target_path)}</code></td>
      <td>${esc(displayValue(slot))}</td>
      <td><span class="status ${slot.status}">${slot.status === "resolved" ? "已就绪" : slot.status === "missing" ? "缺失" : slot.status === "blocked" ? "等待上游" : "无效"}</span><small>${esc(slot.reason)}</small></td>
    </tr>`).join("");
  const ready = evaluation.status === "ready";
  $("#readiness").className = `readiness ${ready ? "ready" : "blocked"}`;
  $("#readiness").innerHTML = ready
    ? `<strong>可以编译</strong><span>所有必填槽位已满足，Runtime 可以生成精确 ToolCall。</span>`
    : `<strong>暂不能编译</strong><span>请先处理：${esc([...evaluation.missing, ...evaluation.invalid].join("、"))}</span>`;
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
    setFacts(payload.facts);
    render(payload.evaluation);
    $("#relations").textContent = JSON.stringify(payload.relations, null, 2);
  } catch (error) {
    $("#operationTitle").textContent = `加载失败：${error.message}`;
  }
}

$("#compile").addEventListener("click", compile);
$("#clearResolver").addEventListener("click", () => {
  $("#project").value = "";
  $("#warehouse").value = "";
  $("#itemCode").value = "";
  compile();
});

bootstrap();
