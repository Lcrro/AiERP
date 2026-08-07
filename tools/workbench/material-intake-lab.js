(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const state = {decisions:[], filter:"all"};
  const sample = `材料\t规格\t采购数量\t单位
500A型二保焊枪\t带线6m\t1\t把
422型2.5焊条\t\t1\t箱
药芯焊丝Φ1.2\t\t2\t盘
世达剥线钳\t\t2\t把
活动扳手12寸\t\t1\t把
铁丝14#\t\t10\t卷
切割片100\t\t1\t盒
打磨片100\t\t2\t盒
导电咀1.2\t\t2\t盒
氧气表\t\t3\t只
氟胶骨架密封\t120*95*12\t5\t件
麻花钻头\tφ3.2\t1\t盒
浮球开关带线\t\t1\t只
透明钢丝管50\t\t10\t米
T型套筒扳手\t8mm\t2\t个`;

  function parseRows() {
    const lines = $("source").value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);
    const rows = [];
    lines.forEach((line,index) => {
      let parts = line.includes("\t") ? line.split("\t") : line.split("|");
      parts = parts.map(v=>v.trim());
      if (index === 0 && /材料|名称/.test(parts[0]) && /数量/.test(parts[2] || "")) return;
      const [raw_name,raw_spec="",qtyText="",uom=""] = parts;
      const qty = Number(qtyText);
      if (!raw_name || !Number.isFinite(qty) || qty <= 0 || !uom) throw new Error(`第 ${index+1} 行格式不完整：需要材料、正数数量和单位`);
      rows.push({row_id:String(index+1),raw_name,raw_spec,qty,uom});
    });
    if (!rows.length) throw new Error("没有可分析的采购行");
    if (rows.length > 50) throw new Error("首版每批最多分析 50 行");
    return rows;
  }

  function setPipeline(mode, activeIndex = -1, result = null) {
    document.querySelectorAll(".stage").forEach((node, index) => {
      node.classList.remove("active", "done", "blocked");
      if (mode === "running" && index === activeIndex) node.classList.add("active");
      if (mode === "running" && index < activeIndex) node.classList.add("done");
      if (mode === "complete") node.classList.add("done");
      if (mode === "error" && index <= Math.max(0, activeIndex)) node.classList.add(index === activeIndex ? "blocked" : "done");
    });
    const stateNode = $("pipeline-state");
    stateNode.className = `pipeline-state ${mode === "running" ? "running" : mode === "complete" ? "complete" : mode === "error" ? "error" : ""}`;
    stateNode.textContent = mode === "running" ? "处理中" : mode === "complete" ? "已完成" : mode === "error" ? "需检查" : "未开始";
    if (mode === "running") $("pipeline-summary").textContent = "DeepSeek 正在提取现场事实，随后由标准目录继续处理";
    if (mode === "error") {
      $("pipeline-summary").textContent = "处理在此阶段停止，未写入 ERPNext";
      renderProcessingTrace([]);
    }
    if (mode === "complete" && result) {
      const rows = result.decisions || [];
      const extracted = rows.filter(row => Object.keys(row.normalized_attributes || {}).length).length;
      const matched = rows.filter(row => row.standard_name || row.type_id).length;
      const completed = rows.filter(row => row.standard_completion_note && row.standard_completion_note.includes("补齐")).length;
      $("pipeline-summary").textContent = `已完成 ${result.total_rows} 行，未写入 ERPNext`;
      $("trace-input").textContent = `读取 ${result.total_rows} 行`;
      $("trace-extracted").textContent = `提取事实 ${extracted} 行`;
      $("trace-matched").textContent = `匹配标准类型 ${matched} 行`;
      $("trace-completed").textContent = completed ? `标准补齐 ${completed} 行` : "无需标准补齐";
      $("trace-queued").textContent = `生成队列 ${result.total_rows} 行`;
      document.querySelectorAll(".pipeline-facts span").forEach(node => node.classList.add("ready"));
      renderProcessingTrace(result.processing_trace || []);
    } else if (mode === "idle") {
      $("pipeline-summary").textContent = "等待开始";
      $("trace-input").textContent = "等待读取";
      $("trace-extracted").textContent = "未提取事实";
      $("trace-matched").textContent = "未匹配目录";
      $("trace-completed").textContent = "未补齐属性";
      $("trace-queued").textContent = "未生成结论";
      document.querySelectorAll(".pipeline-facts span").forEach(node => node.classList.remove("ready"));
      renderProcessingTrace([]);
    }
  }

  function renderProcessingTrace(trace) {
    const detail = $("trace-detail");
    const target = $("batch-trace");
    if (!detail || !target) return;
    if (!trace.length) {
      detail.hidden = true;
      target.innerHTML = "";
      return;
    }
    const statusLabel = {completed:"完成", partial:"部分待处理", failed:"失败"};
    const durationLabel = value => {
      const ms = Number(value || 0);
      return ms >= 1000 ? `${(ms / 1000).toFixed(1)} 秒` : `${ms} 毫秒`;
    };
    detail.hidden = false;
    target.innerHTML = trace.map((step, index) => `<div class="trace-card ${esc(step.status)}">
      <div class="trace-card-head"><b>${index + 1}</b><strong>${esc(step.title)}</strong><em>${esc(statusLabel[step.status] || step.status)}</em></div>
      <div class="trace-meta"><span>输入 ${esc(step.input_rows)} 行</span><span>输出 ${esc(step.output_rows)} 行</span><span>耗时 ${esc(durationLabel(step.duration_ms))}</span></div>
      <ul>${(step.details || []).map(item => `<li>${esc(item)}</li>`).join("")}</ul>
    </div>`).join("");
  }

  function traceForRow(row) {
    const hasFacts = Object.keys(row.normalized_attributes || {}).length > 0;
    const hasType = Boolean(row.standard_name || row.type_id);
    const hasDefaults = Boolean(row.standard_completion_note && row.standard_completion_note.includes("补齐"));
    const canCompleteAttributes = hasDefaults || hasType || row.queue === "existing_sku";
    return [
      ["读取现场原文", true, `${row.raw_name}${row.raw_spec ? ` · ${row.raw_spec}` : ""}`],
      ["DeepSeek 提取事实", hasFacts, hasFacts ? `${Object.keys(row.normalized_attributes).length} 个属性` : "没有明确属性"],
      ["标准名称匹配", hasType, hasType ? row.standard_name : "尚未确定"],
      ["标准属性补齐", canCompleteAttributes, hasDefaults ? "采用企业标准默认值" : canCompleteAttributes ? "无需补齐" : "等待标准类型确认"],
      ["生成准入结论", true, row.queue_label || row.queue],
    ];
  }

  async function analyze() {
    try {
      const rows = parseRows();
      $("analyze").disabled = true; $("progress").hidden = false; $("parse-status").textContent = `已读取 ${rows.length} 行，正在分析...`;
      setPipeline("running", 1);
      const response = await fetch("/api/material-intake/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({rows})});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "分析失败");
      state.decisions = data.result.decisions || [];
      Object.entries(data.result.queue_counts || {}).forEach(([key,value]) => { const node=$("count-"+key); if(node) node.textContent=value; });
      $("count-all").textContent = data.result.total_rows;
      $("parse-status").textContent = `分析完成：${data.result.total_rows} 行，未写入 ERPNext`;
      setPipeline("complete", -1, data.result);
      render();
    } catch (error) {
      $("parse-status").textContent = error.message;
      setPipeline("error", 1);
      $("results").innerHTML = `<tr><td colspan="5" class="empty">${esc(error.message)}</td></tr>`;
    } finally { $("analyze").disabled=false; $("progress").hidden=true; }
  }

  function render() {
    const rows = state.decisions.filter(row => state.filter === "all" || row.queue === state.filter);
    $("results").innerHTML = rows.length ? rows.map(row => `<tr data-row="${esc(row.row_id)}">
      <td class="raw"><strong>${esc(row.raw_name)}</strong><small>${esc(row.raw_spec || "无单独规格")} · ${esc(row.qty)} ${esc(row.uom)}</small></td>
      <td><span class="badge ${esc(row.queue)}">${esc(row.queue_label)}</span>${row.item_code ? `<div>${esc(row.item_code)}</div>`:""}</td>
      <td><strong>${esc(row.standard_name || row.sku_name || "尚未确定")}</strong><div>${esc(row.sku_name || row.type_id || "")}</div></td>
      <td><div class="specs">${Object.entries(row.normalized_attributes || {}).map(([k,v])=>`<span title="${esc((row.attribute_sources||{})[k]||'')}">${esc(k)}: ${esc(v)}</span>`).join("") || "未提取"}</div></td>
      <td class="reason">${esc(row.reason)}${row.standard_completion_note ? `<small>${esc(row.standard_completion_note)}</small>`:""}${row.questions?.length ? `<small>${esc(row.questions.join("；"))}</small>`:""}</td>
    </tr>`).join("") : `<tr><td colspan="5" class="empty">这个队列暂时没有项目</td></tr>`;
  }

  function showDetail(id) {
    const row = state.decisions.find(item=>item.row_id===id); if(!row) return;
    $("detail-title").textContent = row.raw_name; $("detail-subtitle").textContent = `${row.queue_label} · 原始第 ${row.row_id} 行`;
    const attrs = Object.entries(row.normalized_attributes || {});
    $("detail-body").innerHTML = `<section><h3>治理结论</h3><dl><dt>标准名称</dt><dd>${esc(row.standard_name || "未确定")}</dd><dt>类型编号</dt><dd>${esc(row.type_id || "无")}</dd><dt>现有物料编码</dt><dd>${esc(row.item_code || "无")}</dd><dt>判断依据</dt><dd>${esc(row.reason)}</dd><dt>歧义提醒</dt><dd>${esc(row.ambiguity_note || "无")}</dd></dl></section>
      <section><h3>物料属性</h3><dl>${attrs.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)} <small>${esc((row.attribute_sources||{})[k]||'')}</small></dd>`).join("") || "<dt>状态</dt><dd>没有可用规格事实</dd>"}${row.standard_completion_note ? `<dt>标准补齐</dt><dd>${esc(row.standard_completion_note)}</dd>`:""}</dl></section>
      <section><h3>处理路径</h3><div class="row-trace">${traceForRow(row).map(([label,done,detail], index)=>`<div class="row-trace-step ${done ? "done" : "blocked"}"><b>${index+1}</b><div><strong>${esc(label)}</strong><small>${esc(detail)}</small></div></div>`).join("")}</div></section>
      <section><h3>下一步</h3>${(row.questions || []).map(q=>`<div class="candidate">${esc(q)}</div>`).join("") || "当前不需要员工补充。"}</section>
      <section><h3>候选证据（最多 5 项）</h3>${(row.candidates || []).map(c=>`<div class="candidate"><strong>${esc(c.sku_name || c.standard_name || c.item_name || c.item_code || c.type_id)}</strong><div>${esc(c.required_specs || c.definition || c.match_reason || "")}</div></div>`).join("") || "没有候选。"}</section>`;
    $("detail").hidden=false;
  }

  $("sample").onclick=()=>{$("source").value=sample;$("parse-status").textContent="已载入 15 行测试样例";setPipeline("idle")};
  $("analyze").onclick=analyze; $("close").onclick=()=>{$("detail").hidden=true};
  document.addEventListener("click",event=>{const filter=event.target.closest("[data-queue]");if(filter){state.filter=filter.dataset.queue;document.querySelectorAll("[data-queue]").forEach(n=>n.classList.toggle("active",n===filter));render();return}const row=event.target.closest("tr[data-row]");if(row)showDetail(row.dataset.row)});
  $("source").value=sample; $("parse-status").textContent="已载入 15 行测试样例";setPipeline("idle");
})();
