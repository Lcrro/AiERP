(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const conversationKey = "nexterp.material-intake.conversation-id";
  const conversationId = localStorage.getItem(conversationKey) || crypto.randomUUID();
  localStorage.setItem(conversationKey, conversationId);
  const state = {decisions: [], filter: "all", result: null, analysisId: null, draftBatch: null, execution: null, requestId: null, draftDirty: false};
  const stages = ["read", "extract", "retrieve", "compress", "judge", "validate", "queue", "draft"];
  const stageLabels = {
    read: "读取清单", extract: "提取现场事实", retrieve: "高召回检索", compress: "候选压缩",
    judge: "DeepSeek 判定", validate: "程序复核", queue: "生成处理结论", draft: "生成物料录入草稿"
  };

  const sample = `材料\t规格\t采购数量\t单位
500A型二保焊枪\t带线6m\t1\t把
422型2.5焊条\t\t1\t箱
药芯焊丝Φ1.2\t\t2\t盘
世达剥线钳\t\t2\t把
活动扳手12寸\t\t1\t把
铁丝14#\t\t10\t卷
切割片100\t\t1\t盒
打磨片100\t\t2\t盒
导电嘴1.2\t\t2\t盒
氧气表\t\t3\t只
氧气通针\t\t3\t盒
乙炔表\t\t3\t只
得力钢卷尺5m\t\t2\t把
得力钢卷尺10m\t\t1\t把
得力十字螺丝刀\t8*250\t3\t把
氟胶骨架密封\t120*95*12\t5\t件
麻花钻头\tΦ3.2\t1\t盒
浮球开关带线\t\t1\t只
透明钢丝管50\t\t10\t米
T型套筒扳手\t8mm\t2\t个`;

  function parseRows() {
    const lines = $("source").value.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
    const rows = [];
    lines.forEach((line, index) => {
      let parts = line.includes("\t") ? line.split("\t") : line.split("|");
      parts = parts.map(v => v.trim());
      if (index === 0 && /材料|名称/.test(parts[0]) && /数量/.test(parts[2] || "")) return;
      const [raw_name, raw_spec = "", qtyText = "", uom = ""] = parts;
      const qty = Number(qtyText);
      if (!raw_name || !Number.isFinite(qty) || qty <= 0 || !uom) {
        throw new Error(`第 ${index + 1} 行格式不完整：需要材料、正数采购数量和单位`);
      }
      rows.push({row_id: String(index + 1), raw_name, raw_spec, qty, uom});
    });
    if (!rows.length) throw new Error("没有可分析的采购清单");
    if (rows.length > 50) throw new Error("首版每批最多分析 50 行");
    return rows;
  }

  function setPipeline(mode, activeIndex = -1, result = null) {
    document.querySelectorAll(".stage").forEach((node, index) => {
      node.classList.remove("active", "done", "blocked");
      if (mode === "running" && index === activeIndex) node.classList.add("active");
      if (mode === "running" && index < activeIndex) node.classList.add("done");
      if (mode === "complete" && index < stages.length - 1) node.classList.add("done");
      if (mode === "draft-ready") node.classList.add("done");
      if (mode === "error" && index <= Math.max(0, activeIndex)) node.classList.add(index === activeIndex ? "blocked" : "done");
    });
    const stateNode = $("pipeline-state");
    stateNode.className = `pipeline-state ${mode === "running" ? "running" : mode === "complete" || mode === "draft-ready" ? "complete" : mode === "error" ? "error" : ""}`;
    stateNode.textContent = mode === "running" ? "处理中" : mode === "complete" ? "分析完成" : mode === "draft-ready" ? "草稿待确认" : mode === "error" ? "需检查" : "未开始";
    if (mode === "running") $("pipeline-summary").textContent = "DeepSeek 正在提取事实，服务端并行召回候选，随后进行整批比较";
    if (mode === "error") {
      $("pipeline-summary").textContent = "处理在此阶段停止，未写入 ERPNext";
      renderProcessingTrace([]);
    }
    if (mode === "draft-ready") {
      $("pipeline-summary").textContent = "物料录入草稿已生成，确认后才会写入 ERPNext";
      $("trace-queued").textContent = "已生成处理结论";
      $("trace-queued").classList.add("ready");
    }
    if (mode === "complete" && result) {
      const rows = result.decisions || [];
      const extracted = rows.filter(row => Object.keys(row.normalized_attributes || {}).length).length;
      const recalled = rows.reduce((sum, row) => sum + Number(row.candidate_count || 0), 0);
      const validated = rows.filter(row => row.program_validation && row.program_validation.valid).length;
      $("pipeline-summary").textContent = `已完成 ${result.total_rows} 行，分析阶段未写入 ERPNext`;
      $("trace-input").textContent = `读取 ${result.total_rows} 行`;
      $("trace-extracted").textContent = `提取事实 ${extracted} 行`;
      $("trace-matched").textContent = `召回候选 ${recalled} 项`;
      $("trace-completed").textContent = `程序复核 ${validated} 行`;
      $("trace-queued").textContent = `生成结论 ${rows.length} 行`;
      document.querySelectorAll(".pipeline-facts span").forEach(node => node.classList.add("ready"));
      renderProcessingTrace(result.processing_trace || []);
      if (mode === "complete") {
        const panel = $("draft-panel");
        if (panel) panel.hidden = false;
        renderDraftState();
      }
    } else if (mode === "idle") {
      $("pipeline-summary").textContent = "等待开始";
      $("trace-input").textContent = "等待读取";
      $("trace-extracted").textContent = "未提取事实";
      $("trace-matched").textContent = "未召回候选";
      $("trace-completed").textContent = "未完成复核";
      $("trace-queued").textContent = "未生成结论";
      document.querySelectorAll(".pipeline-facts span").forEach(node => node.classList.remove("ready"));
      renderProcessingTrace([]);
    }
  }

  function renderProcessingTrace(trace) {
    const detail = $("trace-detail");
    const target = $("batch-trace");
    if (!detail || !target) return;
    if (!trace.length) { detail.hidden = true; target.innerHTML = ""; return; }
    const statusLabel = {completed: "完成", partial: "部分完成", failed: "失败"};
    const durationLabel = value => {
      const ms = Number(value || 0);
      return ms >= 1000 ? `${(ms / 1000).toFixed(1)} 秒` : `${ms} 毫秒`;
    };
    detail.hidden = false;
    target.innerHTML = trace.map((step, index) => `<div class="trace-card ${esc(step.status)}">
      <div class="trace-card-head"><b>${index + 1}</b><strong>${esc(stageLabels[step.stage] || step.title)}</strong><em>${esc(statusLabel[step.status] || step.status)}</em></div>
      <div class="trace-meta"><span>输入 ${esc(step.input_rows)} 行</span><span>输出 ${esc(step.output_rows)} 项</span><span>耗时 ${esc(durationLabel(step.duration_ms))}</span></div>
      <ul>${(step.details || []).map(item => `<li>${esc(item)}</li>`).join("")}</ul>
    </div>`).join("");
  }

  function renderCandidate(candidate, row, compact = false) {
    const title = candidate.sku_name || candidate.standard_name || candidate.item_name || candidate.item_code || candidate.type_id || "候选";
    const id = candidate.item_code || candidate.type_id || "";
    const meta = [candidate.candidate_kind === "sku" ? "SKU" : "标准类型", id, `分数 ${candidate.score}`].filter(Boolean).join(" · ");
    const conflicts = (candidate.conflicts || []).map(v => `<span class="candidate-conflict">${esc(v)}</span>`).join("");
    const attrs = (candidate.matched_attributes || []).length ? `<div>命中规格：${esc(candidate.matched_attributes.join("、"))}</div>` : "";
    const aliases = (candidate.matched_aliases || []).length ? `<div>命中别名：${esc(candidate.matched_aliases.join("、"))}</div>` : "";
    const reason = (candidate.match_reasons || []).length ? `<div>匹配依据：${esc(candidate.match_reasons.join("、"))}</div>` : "";
    const confirm = candidate.candidate_kind === "type" && candidate.type_id ? `<button class="secondary confirm-alias" data-confirm-alias="${esc(candidate.type_id)}" data-row="${esc(row.row_id)}">确认“${esc(row.raw_name)}”是此类型别名</button>` : "";
    return `<div class="candidate ${compact ? "candidate-compact" : ""}">
      <strong>${esc(title)}</strong><span class="candidate-meta">${esc(meta)}</span>
      <div>${esc(candidate.required_specs || candidate.stock_uom || "")}</div>${attrs}${aliases}${reason}${conflicts}${confirm}
    </div>`;
  }

  function traceForRow(row) {
    const candidateCount = Number(row.candidate_count || 0);
    const validated = Boolean(row.program_validation && row.program_validation.valid);
    return [
      ["读取原始行", true, `${row.raw_name}${row.raw_spec ? `；${row.raw_spec}` : ""}；${row.qty} ${row.uom}`],
      ["提取现场事实", Object.keys(row.normalized_attributes || {}).length > 0, `${Object.keys(row.normalized_attributes || {}).length} 个规格字段`],
      ["高召回检索", candidateCount > 0, `${candidateCount} 个候选，动态门槛 ${row.retrieval_threshold}`],
      ["候选压缩", true, row.candidate_groups?.length ? `${row.candidate_groups.length} 个类型或 SKU 分组` : "候选未超过压缩阈值"],
      ["DeepSeek 判定", Boolean(Object.keys(row.deepseek_judgement || {}).length), row.deepseek_judgement?.decision || "未返回判定"],
      ["程序复核", validated, row.program_validation?.reason || "等待复核"],
      ["处理结论", true, row.queue_label || row.queue]
    ];
  }

  function renderDraftState() {
    const panel = $("draft-panel");
    if (!panel) return;
    panel.hidden = false;
    const batch = state.draftBatch;
    const prepareButton = $("prepare-drafts");
    const confirmButton = $("confirm-drafts");
    const reviseButton = $("revise-drafts");
    if (!batch) {
      $("draft-summary").textContent = "分析完成。点击“生成录入草稿”后，只会整理服务器保存的分析结论，不会写入 ERPNext。";
      $("draft-list").innerHTML = `<div class="empty">第八步尚未执行。</div>`;
      if (prepareButton) prepareButton.disabled = !state.analysisId;
      if (confirmButton) confirmButton.disabled = true;
      if (reviseButton) reviseButton.disabled = true;
      return;
    }
    const drafts = batch.drafts || [];
    const newTypes = drafts.filter(draft => draft.action === "create_type_and_sku").length;
    $("draft-summary").textContent = `已生成 ${drafts.length} 条草稿（新增标准类型及首个 SKU ${newTypes} 条）；跳过 ${Number(batch.skipped?.length || 0)} 行。确认前仍未写入 ERPNext。`;
    const statusLabels = {pending_confirmation: "待确认", created: "已创建并回读", verified_existing: "已存在且已验证", failed: "发布失败", readback_failed: "回读未通过"};
    $("draft-list").innerHTML = drafts.length ? drafts.map(draft => {
      const editable = draft.status === "pending_confirmation" || draft.status === "failed" || draft.status === "readback_failed";
      const type = draft.material_type || {};
      const typeEditor = draft.action === "create_type_and_sku" ? `<fieldset class="draft-editor"><legend>新增标准类型（请核对）</legend>
        <label>一级分类<input data-draft-field="top_group" value="${esc(type.top_group || "")}" ${editable ? "" : "disabled"}></label>
        <label>物料族<input data-draft-field="material_family" value="${esc(type.material_family || "")}" ${editable ? "" : "disabled"}></label>
        <label>标准名称<input data-draft-field="standard_name" value="${esc(type.standard_name || "")}" ${editable ? "" : "disabled"}></label>
        <label>ERPNext 物料组<input data-draft-field="item_group" value="${esc(type.item_group || draft.item_group || "")}" ${editable ? "" : "disabled"}></label>
        <label>编码前缀<input data-draft-field="code_prefix" value="${esc(type.code_prefix || "")}" ${editable ? "" : "disabled"}></label>
        <label class="wide">类型定义<input data-draft-field="definition" value="${esc(type.definition || "")}" ${editable ? "" : "disabled"}></label>
      </fieldset>` : `<div class="locked-type"><b>现有标准类型</b><span>${esc(draft.type_id)} · ${esc(draft.standard_name)}</span></div>`;
      const attributes = Object.entries(draft.normalized_attributes || {}).filter(([key]) => key !== "uom");
      const attributeEditor = `<fieldset class="draft-editor attributes"><legend>SKU 规格（服务器将重新编译名称和编码）</legend>${attributes.map(([key, value]) => `<label><span>${esc(key)}</span><input data-draft-attribute="${esc(key)}" value="${esc(value)}" ${editable ? "" : "disabled"}></label>`).join("")}<label><span>库存单位</span><input data-draft-field="stock_uom" value="${esc(draft.stock_uom || "")}" ${editable ? "" : "disabled"}></label></fieldset>`;
      const errors = draft.validation_errors?.length ? `<ul class="draft-errors">${draft.validation_errors.map(error => `<li>${esc(error)}</li>`).join("")}</ul>` : "";
      return `<article class="draft-card ${esc(draft.status)}" data-draft-id="${esc(draft.draft_id)}" data-action="${esc(draft.action)}">
        <div class="draft-card-head"><strong>${esc(draft.item_code)}</strong><span>${esc(statusLabels[draft.status] || draft.status)}</span></div>
        <h3>${esc(draft.item_name)}</h3>${typeEditor}${attributeEditor}${errors}
        <dl><dt>发布动作</dt><dd>${draft.action === "create_type_and_sku" ? "创建标准类型及首个 SKU" : "在现有标准类型下创建 SKU"}</dd><dt>必填规格</dt><dd>${esc(draft.required_specs || "无")}</dd><dt>辅助规格</dt><dd>${esc(draft.optional_specs || "无")}</dd><dt>来源行</dt><dd>${esc((draft.source_rows || []).join("、"))} · ${esc((draft.source_names || []).join("、"))}</dd><dt>冻结摘要</dt><dd>${esc((draft.frozen_hash || "").slice(0, 12))}</dd></dl>
      </article>`;
    }).join("") : `<div class="empty">没有可以安全生成的新增物料草稿。需要补充或选择的行请回到表格查看。</div>`;
    if (batch.skipped?.length) {
      $("draft-list").insertAdjacentHTML("beforeend", `<details class="draft-skipped"><summary>未生成草稿的 ${batch.skipped.length} 行</summary><ul>${batch.skipped.map(item => `<li>第 ${esc(item.row_id)} 行：${esc(item.reason)}</li>`).join("")}</ul></details>`);
    }
    if (prepareButton) prepareButton.disabled = true;
    if (reviseButton) reviseButton.disabled = !state.draftDirty;
    if (confirmButton) {
      confirmButton.disabled = state.draftDirty || !drafts.length || drafts.some(draft => draft.validation_errors?.length) || drafts.every(draft => ["created", "verified_existing"].includes(draft.status));
      confirmButton.textContent = "确认并一键发布";
    }
    if (state.execution) renderExecution(state.execution);
  }

  function renderExecution(execution) {
    const target = $("execution-result");
    if (!target || !execution) return;
    target.hidden = false;
    const renderRows = (rows, label, css) => rows?.length ? `<section class="execution-group ${css}"><strong>${esc(label)}（${rows.length}）</strong><ul>${rows.map(row => {
      const mismatch = Object.keys(row.readback?.mismatches || {});
      const detail = row.item_name || row.reason || row.user_message || row.error || "";
      return `<li><b>${esc(row.item_code || row.draft_id)}</b> ${esc(detail)}${mismatch.length ? `<small>不一致字段：${esc(mismatch.join("、"))}</small>` : row.readback?.verified ? "<small>ERPNext 回读一致</small>" : ""}</li>`;
    }).join("")}</ul></section>` : "";
    const writeState = execution.writes_erpnext ? (execution.readback_verified ? "已写入并通过 ERPNext 回读" : "有写入，但存在未通过回读的项目") : (execution.readback_verified ? "ERPNext 已有记录均回读一致" : "未写入 ERPNext");
    target.innerHTML = `<div class="execution-head"><strong>${execution.status === "completed" ? "物料发布闭环完成" : "物料发布部分完成"}</strong><span>${esc(writeState)}</span></div><div class="execution-request">request_id：${esc(execution.request_id || "")} ${execution.idempotent_replay ? "· 幂等重放" : ""}</div>${renderRows(execution.created, "已创建并回读验证", "success")}${renderRows(execution.verified_existing, "已存在且字段一致", "success")}${renderRows(execution.skipped, "已跳过", "skipped")}${renderRows(execution.failed, "失败或回读不一致", "failed")}`;
  }

  function collectDraftUpdates() {
    return [...document.querySelectorAll(".draft-card[data-draft-id]")].filter(card => {
      const draft = (state.draftBatch?.drafts || []).find(item => item.draft_id === card.dataset.draftId);
      return draft && !["created", "verified_existing"].includes(draft.status);
    }).map(card => {
      const draft = (state.draftBatch?.drafts || []).find(item => item.draft_id === card.dataset.draftId);
      const attributes = {...(draft?.normalized_attributes || {})};
      card.querySelectorAll("[data-draft-attribute]").forEach(input => {
        const value = input.value.trim();
        if (value) attributes[input.dataset.draftAttribute] = value;
        else delete attributes[input.dataset.draftAttribute];
      });
      delete attributes.uom;
      const update = {draft_id: card.dataset.draftId, normalized_attributes: attributes};
      card.querySelectorAll("[data-draft-field]").forEach(input => { update[input.dataset.draftField] = input.value.trim(); });
      return update;
    });
  }

  async function prepareDrafts() {
    if (!state.analysisId) return;
    const button = $("prepare-drafts");
    button.disabled = true;
    button.textContent = "正在生成草稿...";
    try {
      const response = await fetch("/api/material-intake/drafts", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({analysis_id: state.analysisId, user: $("operator").value.trim()})});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "生成物料录入草稿失败");
      state.draftBatch = data.drafts;
      state.execution = null;
      state.requestId = null;
      state.draftDirty = false;
      setPipeline("draft-ready");
      renderProcessingTrace([...(state.result?.processing_trace || []), state.draftBatch.processing_step]);
      renderDraftState();
    } catch (error) {
      button.disabled = false;
      button.textContent = "生成录入草稿";
      window.alert(error.message);
    }
  }

  async function reviseDrafts() {
    const batch = state.draftBatch;
    if (!batch?.drafts?.length) return;
    const user = $("operator").value.trim();
    if (!user) { window.alert("请填写录入账号"); return; }
    const button = $("revise-drafts");
    button.disabled = true;
    button.textContent = "正在重新编译...";
    try {
      const response = await fetch("/api/material-intake/drafts/revise", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
        analysis_id: batch.analysis_id,
        user,
        draft_updates: collectDraftUpdates()
      })});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "重新冻结草稿失败");
      state.draftBatch = data.drafts;
      state.execution = null;
      state.requestId = null;
      state.draftDirty = false;
      renderDraftState();
    } catch (error) {
      button.disabled = false;
      window.alert(error.message);
    } finally {
      button.textContent = "应用修改并刷新预览";
    }
  }

  async function confirmDrafts() {
    const batch = state.draftBatch;
    if (!batch?.drafts?.length) return;
    const user = $("operator").value.trim();
    if (!user) { window.alert("请填写录入账号"); return; }
    const pending = batch.drafts.filter(draft => !["created", "verified_existing"].includes(draft.status));
    const newTypeCount = pending.filter(draft => draft.action === "create_type_and_sku").length;
    if (!window.confirm(`确认发布 ${pending.length} 条物料（其中新增标准类型 ${newTypeCount} 条）？系统将使用当前员工身份写入 ERPNext，并逐条回读验证。`)) return;
    const button = $("confirm-drafts");
    button.disabled = true;
    button.textContent = "正在发布并回读...";
    state.requestId ||= crypto.randomUUID();
    try {
      const response = await fetch("/api/material-intake/drafts/confirm", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
        analysis_id: batch.analysis_id,
        user,
        request_id: state.requestId,
        conversation_id: conversationId,
        draft_ids: pending.map(draft => draft.draft_id),
        draft_hashes: pending.map(draft => ({draft_id: draft.draft_id, frozen_hash: draft.frozen_hash}))
      })});
      const data = await response.json();
      if (!response.ok || !data.ok && !data.execution) throw new Error(data.error || "物料录入失败");
      state.execution = data.execution;
      const byId = new Map((data.execution.created || []).map(row => [row.draft_id, "created"]));
      (data.execution.verified_existing || []).forEach(row => byId.set(row.draft_id, "verified_existing"));
      (data.execution.failed || []).forEach(row => byId.set(row.draft_id, row.error_type === "readback_mismatch" || row.error_type === "item_code_conflict" ? "readback_failed" : "failed"));
      const executionRows = new Map([...(data.execution.created || []), ...(data.execution.verified_existing || []), ...(data.execution.failed || [])].map(row => [row.draft_id, row]));
      batch.drafts.forEach(draft => {
        if (byId.has(draft.draft_id)) draft.status = byId.get(draft.draft_id);
        const row = executionRows.get(draft.draft_id);
        if (row?.item_code) draft.item_code = row.item_code;
        if (row?.item_name) draft.item_name = row.item_name;
        if (row?.type_id) draft.type_id = row.type_id;
      });
      state.requestId = null;
      renderDraftState();
      renderExecution(data.execution);
    } catch (error) {
      button.disabled = false;
      button.textContent = "确认并一键发布";
      window.alert(error.message);
    }
  }

  async function analyze() {
    try {
      const rows = parseRows();
      $("analyze").disabled = true;
      $("progress").hidden = false;
      $("parse-status").textContent = `已读取 ${rows.length} 行，正在分析...`;
      setPipeline("running", 1);
      const response = await fetch("/api/material-intake/analyze", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({rows})});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "分析失败");
      state.result = data.result;
      state.analysisId = data.result.analysis_id;
      state.draftBatch = null;
      state.execution = null;
      state.requestId = null;
      state.draftDirty = false;
      state.decisions = data.result.decisions || [];
      Object.entries(data.result.queue_counts || {}).forEach(([key, value]) => { const node = $("count-" + key); if (node) node.textContent = value; });
      $("count-all").textContent = data.result.total_rows;
      $("parse-status").textContent = `分析完成：${data.result.total_rows} 行，未写入 ERPNext`;
      setPipeline("complete", -1, data.result);
      render();
    } catch (error) {
      $("parse-status").textContent = error.message;
      setPipeline("error", 1);
      $("results").innerHTML = `<tr><td colspan="5" class="empty">${esc(error.message)}</td></tr>`;
    } finally {
      $("analyze").disabled = false;
      $("progress").hidden = true;
    }
  }

  function render() {
    const rows = state.decisions.filter(row => state.filter === "all" || row.queue === state.filter);
    $("results").innerHTML = rows.length ? rows.map(row => `<tr data-row="${esc(row.row_id)}">
      <td class="raw"><strong>${esc(row.raw_name)}</strong><small>${esc(row.raw_spec || "无单独规格")} · ${esc(row.qty)} ${esc(row.uom)}</small></td>
      <td><span class="badge ${esc(row.queue)}">${esc(row.queue_label)}</span>${row.item_code ? `<div>${esc(row.item_code)}</div>` : ""}</td>
      <td><strong>${esc(row.standard_name || row.sku_name || "尚未确定")}</strong><div>${esc(row.sku_name || row.type_id || "")}</div></td>
      <td><div class="specs">${Object.entries(row.normalized_attributes || {}).map(([k, v]) => `<span title="${esc((row.attribute_sources || {})[k] || "")}">${esc(k)}: ${esc(v)}</span>`).join("") || "未提取"}</div></td>
      <td class="reason"><strong>候选 ${esc(row.candidate_count || 0)} 项</strong><small>门槛 ${esc(row.retrieval_threshold || 0)}；分组 ${esc((row.candidate_groups || []).length)}</small><small>${esc(row.reason || "")}</small>${row.questions?.length ? `<small>${esc(row.questions.join("；"))}</small>` : ""}</td>
    </tr>`).join("") : `<tr><td colspan="5" class="empty">这个队列暂时没有项目</td></tr>`;
  }

  function showDetail(id) {
    const row = state.decisions.find(item => item.row_id === id);
    if (!row) return;
    $("detail-title").textContent = row.raw_name;
    $("detail-subtitle").textContent = `${row.queue_label} · 原始第 ${row.row_id} 行`;
    const attrs = Object.entries(row.normalized_attributes || {});
    const groups = (row.candidate_groups || []).map(group => `<div class="candidate-group"><strong>${esc(group.standard_name || group.group_key)}</strong><span>${esc(group.count)} 项 · ${esc(group.score_min)}-${esc(group.score_max)} 分 · 冲突 ${esc(group.conflict_count)}</span>${(group.representative_candidates || []).map(candidate => renderCandidate(candidate, row, true)).join("")}</div>`).join("");
    const allCandidates = (row.candidates || []).map(candidate => renderCandidate(candidate, row)).join("");
    const validation = row.program_validation || {};
    const judgement = row.deepseek_judgement || {};
    $("detail-body").innerHTML = `<section><h3>治理结论</h3><dl>
      <dt>标准名称</dt><dd>${esc(row.standard_name || "未确定")}</dd><dt>类型编号</dt><dd>${esc(row.type_id || "无")}</dd><dt>现有物料编码</dt><dd>${esc(row.item_code || "无")}</dd><dt>判断依据</dt><dd>${esc(row.reason || "无")}</dd><dt>动态门槛</dt><dd>${esc(row.retrieval_threshold || 0)} 分</dd><dt>候选总数</dt><dd>${esc(row.candidate_count || 0)} 项</dd>
    </dl></section>
    <section><h3>提取出的现场事实</h3><dl>${attrs.map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value)} <small>${esc((row.attribute_sources || {})[key] || "")}</small></dd>`).join("") || "<dd>没有明确规格</dd>"}</dl></section>
    <section><h3>处理过程</h3><div class="row-trace">${traceForRow(row).map(([label, done, detail], index) => `<div class="row-trace-step ${done ? "done" : "blocked"}"><b>${index + 1}</b><div><strong>${esc(label)}</strong><small>${esc(detail)}</small></div></div>`).join("")}</div></section>
    <section><h3>DeepSeek 判定</h3><pre>${esc(JSON.stringify(judgement, null, 2))}</pre></section>
    <section><h3>程序复核</h3><pre>${esc(JSON.stringify(validation, null, 2))}</pre></section>
    <section><h3>候选分组摘要</h3>${groups || "没有被压缩的候选分组。"}</section>
    <section><h3>完整召回候选（${esc(row.candidates?.length || 0)} 项）</h3>${allCandidates || "没有候选。"}</section>
    <section><h3>下一步</h3>${(row.questions || []).map(question => `<div class="candidate">${esc(question)}</div>`).join("") || "当前不需要员工补充。"}</section>`;
    $("detail").hidden = false;
  }

  async function confirmAlias(button) {
    const row = state.decisions.find(item => item.row_id === button.dataset.row);
    if (!row) return;
    const user = window.prompt("请输入确认员工账号", "mao.xiaoquan@stec-up.local");
    if (!user) return;
    button.disabled = true;
    try {
      const response = await fetch("/api/material-intake/confirm-alias", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
        alias: row.raw_name, target_kind: "type", target_id: button.dataset.confirmAlias, user, source_row: row.row_id
      })});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "别名确认失败");
      row.alias_learning = {status: "confirmed", ...data.alias};
      button.textContent = "已确认别名";
    } catch (error) {
      button.disabled = false;
      window.alert(error.message);
    }
  }

  $("sample").onclick = () => {
    $("source").value = sample;
    state.analysisId = null;
    state.draftBatch = null;
    state.execution = null;
    state.requestId = null;
    state.draftDirty = false;
    $("draft-panel").hidden = true;
    $("prepare-drafts").disabled = false;
    $("prepare-drafts").textContent = "生成录入草稿";
    $("revise-drafts").disabled = true;
    $("revise-drafts").textContent = "应用修改并刷新预览";
    $("confirm-drafts").disabled = true;
    $("confirm-drafts").textContent = "确认并一键发布";
    $("execution-result").hidden = true;
    $("parse-status").textContent = "已载入测试样例";
    setPipeline("idle");
  };
  $("analyze").onclick = analyze;
  $("prepare-drafts").onclick = prepareDrafts;
  $("revise-drafts").onclick = reviseDrafts;
  $("confirm-drafts").onclick = confirmDrafts;
  $("close").onclick = () => { $("detail").hidden = true; };
  document.addEventListener("click", event => {
    const filter = event.target.closest("[data-queue]");
    if (filter) { state.filter = filter.dataset.queue; document.querySelectorAll("[data-queue]").forEach(node => node.classList.toggle("active", node === filter)); render(); return; }
    const aliasButton = event.target.closest("[data-confirm-alias]");
    if (aliasButton) { event.stopPropagation(); confirmAlias(aliasButton); return; }
    const row = event.target.closest("tr[data-row]");
    if (row) showDetail(row.dataset.row);
  });
  document.addEventListener("input", event => {
    if (!event.target.closest(".draft-card[data-draft-id]")) return;
    state.draftDirty = true;
    state.requestId = null;
    $("revise-drafts").disabled = false;
    $("confirm-drafts").disabled = true;
  });
  $("source").value = sample;
  $("parse-status").textContent = "已载入测试样例";
  setPipeline("idle");
})();
