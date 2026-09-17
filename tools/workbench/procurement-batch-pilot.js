(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  const stages = [["read","读取原表"],["cluster","去重聚类"],["facts","抽取事实"],["retrieve","检索 GPC"],["judge","受限判定"],["complete","生成候选"]];
  const state = {jobId:"", timer:null, result:null, review:null, filter:"needs_review"};
  const queueLabels = {
    existing_candidate:"已整理候选", ready_new_sku:"新增 SKU 候选", ready_new_type:"新增类型候选",
    needs_review:"边界项审阅", excluded_non_material:"非物料服务"
  };
  const actionLabels = {approved:"确认", revised:"修订", deferred:"暂缓", excluded:"排除"};
  const materializationLabels = {ready:"可形成物料",split_ready:"拆为多个实际 SKU",hold:"只确认规则，暂不建 SKU",excluded:"不进入物料库"};

  function renderStages(current, status) {
    const index = stages.findIndex(([code]) => code === current);
    $("stage-list").innerHTML = stages.map(([code,label],i) => `<div class="stage ${i<index||status==='completed'?'done':''} ${i===index&&status!=='completed'?'active':''}">${esc(label)}</div>`).join("");
  }

  function renderJob(job) {
    state.jobId = job.job_id || state.jobId;
    const percent = Number(job.percent || 0);
    $("job-id").textContent = state.jobId || "—";
    $("progress-percent").textContent = `${percent}%`;
    $("progress-stage").textContent = stages.find(([code]) => code === job.stage)?.[1] || job.status || "等待";
    $("progress-message").textContent = job.message || "等待任务";
    $("progress-bar").style.width = `${percent}%`;
    $("progress-ring").style.setProperty("--p", percent);
    renderStages(job.stage, job.status);
    const active = ["queued","running"].includes(job.status);
    $("start-button").disabled = active;
    $("cancel-button").disabled = !active;
    $("error-message").hidden = job.status !== "failed";
    $("error-message").textContent = job.error || "";
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  async function start() {
    try {
      const data = await request("/api/procurement-batch-pilot/jobs", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({limit:100,use_deepseek:$("use-deepseek").checked})
      });
      state.result = null; state.review = null; renderResults(); renderReviewOverview();
      renderJob(data.job); poll();
    } catch (error) { showError(error); }
  }

  async function poll() {
    clearTimeout(state.timer);
    if (!state.jobId) return;
    try {
      const data = await request(`/api/procurement-batch-pilot/job?job_id=${encodeURIComponent(state.jobId)}`);
      renderJob(data.job);
      if (data.job.status === "completed") await loadResult(state.jobId);
      else if (["queued","running"].includes(data.job.status)) state.timer = setTimeout(poll, 900);
    } catch (error) { showError(error); }
  }

  async function cancel() {
    if (!state.jobId) return;
    try {
      const data = await request("/api/procurement-batch-pilot/jobs/cancel", {
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({job_id:state.jobId})
      });
      renderJob(data.job);
    } catch (error) { showError(error); }
  }

  async function loadResult(jobId) {
    const [result, review] = await Promise.all([
      request(`/api/procurement-batch-pilot/result?job_id=${encodeURIComponent(jobId)}`),
      request(`/api/procurement-batch-pilot/review?job_id=${encodeURIComponent(jobId)}`)
    ]);
    state.result = result; state.review = review;
    renderMetrics(result.audit || {}); renderReviewOverview(); renderResults();
  }

  function renderMetrics(audit) {
    $("metric-rows").textContent = audit.row_count ?? "—";
    $("metric-unique").textContent = audit.exact_unique_count ?? "—";
    $("metric-clusters").textContent = audit.cluster_count ?? "—";
    $("metric-calls").textContent = audit.deepseek?.call_count ?? "—";
    const usage = audit.deepseek?.usage || {};
    $("metric-tokens").textContent = usage.total_tokens != null ? `${Number(usage.total_tokens).toLocaleString()} Token` : "真实 usage";
    const cost = audit.deepseek?.estimated_cost_cny;
    $("metric-cost").textContent = cost == null ? "待计价" : `¥${Number(cost).toFixed(4)}`;
  }

  function renderReviewOverview() {
    const review = state.review;
    $("review-overview").hidden = !review;
    $("rules-card").hidden = !review;
    if (!review) return;
    const summary = review.summary;
    $("reviewed-count").textContent = summary.reviewed;
    $("review-total").textContent = summary.total;
    $("review-bar").style.width = `${summary.total ? summary.reviewed / summary.total * 100 : 0}%`;
    $("review-state").textContent = summary.frozen ? `已冻结 · ${review.release.release_sha256.slice(0,12)}` : summary.complete ? "全部审完，可冻结" : `还剩 ${summary.remaining} 项`;
    $("review-scope").textContent = `只包含源表第 ${review.scope.selected_start_row}–${review.scope.selected_end_row} 行；第 101–300 条业务记录未处理；ERPNext 零写入。`;
    $("freeze-review").disabled = !summary.complete || summary.frozen;
    $("freeze-review").textContent = summary.frozen ? "本轮审阅已冻结" : "冻结本轮审阅与规则";
    $("rule-count").textContent = review.rules.rules.length;
    $("rule-principles").innerHTML = `<ul>${review.rules.principles.map(value=>`<li>${esc(value)}</li>`).join("")}</ul>`;
  }

  function renderFilters(counts) {
    const entries = [["all","全部",Object.values(counts).reduce((a,b)=>a+Number(b||0),0)], ...Object.entries(counts).map(([key,value])=>[key,queueLabels[key]||key,value])];
    $("filters").innerHTML = entries.map(([key,label,count]) => `<button class="filter ${state.filter===key?'active':''}" data-filter="${esc(key)}">${esc(label)} ${count}</button>`).join("");
    $("filters").querySelectorAll("button").forEach(button => button.addEventListener("click", () => {state.filter=button.dataset.filter;renderResults();}));
  }

  function reviewItem(clusterId) {
    return (state.review?.items || []).find(row => row.cluster_id === clusterId) || null;
  }

  function reviewForm(row, item) {
    const review = item?.review || {};
    const material = item?.review ? (review.final_material || {}) : (row.material_candidate || {});
    const matchedRuleIds = (item?.matched_rules || []).map(rule => rule.rule_id);
    const ruleIds = review.rule_ids || matchedRuleIds;
    const frozen = Boolean(state.review?.summary?.frozen);
    const action = review.action || (row.gpc_brick_code ? "revised" : "deferred");
    const materialization = review.materialization || (row.gpc_brick_code ? "ready" : "hold");
    const rationale = review.rationale || row.reason || "";
    const rules = (item?.matched_rules || []).map(rule => `<span title="${esc(rule.guidance)}">${esc(rule.rule_id)} · ${esc(rule.title)}</span>`).join("");
    const variants = review.variants || [];
    return `<div class="review-panel ${review.action?'reviewed':''}">
      <div class="review-title"><strong>${review.action ? `已${esc(actionLabels[review.action] || review.action)}` : "等待逐项审阅"}</strong><span>候选哈希 ${esc((item?.source_decision_sha256||"").slice(0,12))}</span></div>
      ${rules ? `<div class="matched-rules">${rules}</div>` : ""}
      <div class="review-fields">
        <label>结论<select data-field="action" ${frozen?'disabled':''}>${Object.entries(actionLabels).map(([key,label])=>`<option value="${key}" ${key===action?'selected':''}>${label}</option>`).join("")}</select></label>
        <label>物料化<select data-field="materialization" ${frozen?'disabled':''}>${Object.entries(materializationLabels).map(([key,label])=>`<option value="${key}" ${key===materialization?'selected':''}>${label}</option>`).join("")}</select></label>
        <label>标准类型<input data-field="standard_type" value="${esc(material.standard_type || (!item?.review ? row.standard_type : ''))}" ${frozen?'disabled':''}></label>
        <label>GPC Brick<input data-field="gpc_brick_code" value="${esc(material.gpc_brick_code || (!item?.review ? row.gpc_brick_code : ''))}" ${frozen?'disabled':''}></label>
        <label>主模板<input data-field="main_template_id" value="${esc(material.main_template_id || (!item?.review ? row.main_template_id : ''))}" ${frozen?'disabled':''}></label>
        <label>库存单位<input data-field="stock_uom" value="${esc(material.stock_uom || (!item?.review ? (row.material_candidate?.stock_uom || '件') : ''))}" ${frozen?'disabled':''}></label>
        <label class="wide">约束（逗号分隔）<input data-field="constraint_ids" value="${esc((material.constraint_ids || (!item?.review ? row.constraint_ids : []) || []).join(','))}" ${frozen?'disabled':''}></label>
        <label class="wide">规则编号（逗号分隔）<input data-field="rule_ids" value="${esc(ruleIds.join(','))}" ${frozen?'disabled':''}></label>
        <label class="wide">审阅依据<textarea data-field="rationale" ${frozen?'disabled':''}>${esc(rationale)}</textarea></label>
      </div>
      ${variants.length ? `<details><summary>已拆分 ${variants.length} 个实际发生 SKU</summary><pre>${esc(JSON.stringify(variants,null,2))}</pre></details>` : ""}
      ${frozen ? "" : `<button class="save-review" type="button" data-cluster="${esc(row.cluster_id)}">保存这一项</button>`}
    </div>`;
  }

  function renderResults() {
    const decisions = state.result?.decisions || [];
    const counts = state.result?.audit?.queue_counts || {};
    renderFilters(counts);
    if (!decisions.length) { $("result-summary").textContent="尚无完成结果。"; $("decision-list").innerHTML=""; return; }
    const shown = state.filter === "all" ? decisions : decisions.filter(row => row.queue === state.filter);
    const summary = state.review?.summary;
    $("result-summary").textContent = `共 ${decisions.length} 个分析簇，当前显示 ${shown.length} 个。${summary ? `34 个边界项已审 ${summary.reviewed} 个。` : ""}所有内容仍在本地候选区。`;
    $("decision-list").innerHTML = shown.map(row => {
      const material = row.material_candidate || {};
      const css = row.queue === "needs_review" ? "review" : row.queue === "excluded_non_material" ? "excluded" : "";
      const item = row.queue === "needs_review" ? reviewItem(row.cluster_id) : null;
      return `<article class="decision ${css}" data-cluster="${esc(row.cluster_id)}"><span class="badge">${esc(row.queue_label||queueLabels[row.queue]||row.queue)}</span>
        <h3>${esc(row.standard_name||row.standard_type||row.raw_names?.[0]||"未命名")}</h3>
        <div class="raw">原文：${esc((row.raw_names||[]).join("；"))}</div>
        <dl><dt>来源行</dt><dd>${esc((row.source_rows||[]).join(", "))}</dd><dt>GPC Brick</dt><dd>${esc(row.gpc_brick_code||"未判定")} ${esc(row.gpc_brick_name||"")}</dd><dt>主模板</dt><dd>${esc(row.main_template_id||"未判定")}</dd><dt>置信度</dt><dd>${esc(row.confidence||"")}</dd><dt>原判依据</dt><dd>${esc(row.reason||"")}</dd></dl>
        ${Object.keys(material.procurement_attributes||{}).length ? `<details><summary>查看精简采购字段</summary><pre>${esc(JSON.stringify({采购必选:material.procurement_attributes,价格关键:material.price_drivers},null,2))}</pre></details>`:""}
        ${row.queue === "needs_review" && item ? reviewForm(row,item) : ""}
      </article>`;
    }).join("");
    $("decision-list").querySelectorAll(".save-review").forEach(button => button.addEventListener("click", () => saveReview(button.closest("article"))));
  }

  async function saveReview(card) {
    const item = reviewItem(card.dataset.cluster);
    const value = name => card.querySelector(`[data-field="${name}"]`)?.value.trim() || "";
    const list = name => value(name).split(/[,，]/).map(v=>v.trim()).filter(Boolean);
    const payload = {
      job_id:state.jobId, cluster_id:card.dataset.cluster, source_decision_sha256:item.source_decision_sha256,
      action:value("action"), materialization:value("materialization"), rule_ids:list("rule_ids"), rationale:value("rationale"),
      final_material:{standard_type:value("standard_type"),gpc_brick_code:value("gpc_brick_code"),main_template_id:value("main_template_id"),stock_uom:value("stock_uom"),constraint_ids:list("constraint_ids")},
      variants:item.review?.variants || []
    };
    try {
      const data = await request("/api/procurement-batch-pilot/review", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      state.review = data.status; renderReviewOverview(); renderResults();
    } catch (error) { showError(error); }
  }

  async function freezeReview() {
    if (!state.review?.summary?.complete || state.review.summary.frozen) return;
    try {
      await request("/api/procurement-batch-pilot/review/freeze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({job_id:state.jobId})});
      state.review = await request(`/api/procurement-batch-pilot/review?job_id=${encodeURIComponent(state.jobId)}`);
      renderReviewOverview(); renderResults();
    } catch (error) { showError(error); }
  }

  function showError(error) {
    $("error-message").hidden = false;
    $("error-message").textContent = error.message || String(error);
    $("start-button").disabled = false;
  }

  async function loadLatest() {
    renderStages("queued", "idle");
    try {
      const data = await request("/api/procurement-batch-pilot/latest");
      if (!data.available) { $("progress-message").textContent=data.message; return; }
      state.jobId = data.job_id;
      const status = await request(`/api/procurement-batch-pilot/job?job_id=${encodeURIComponent(state.jobId)}`);
      renderJob(status.job);
      if (status.job.status === "completed") await loadResult(state.jobId); else if (["queued","running"].includes(status.job.status)) poll();
    } catch (error) { $("progress-message").textContent="尚无可读取的最近任务"; showError(error); }
  }

  $("start-button").addEventListener("click", start);
  $("cancel-button").addEventListener("click", cancel);
  $("freeze-review").addEventListener("click", freezeReview);
  loadLatest();
})();
