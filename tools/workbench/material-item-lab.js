(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const state = {projects:[], project:null, employee:null, conversationId:crypto.randomUUID(), requestId:null, latest:null, pollToken:0};
  const api = async (url, options={}) => {
    const response = await fetch(url, {headers:{"Content-Type":"application/json"}, ...options});
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || "请求失败");
    return data;
  };
  const employeeAllowed = employee => ["ROLE-MAT-EQP-MGR","ROLE-SYSTEM-MANAGER"].includes(employee.role_code);

  async function boot() {
    try {
      const data = await api("/api/workbench/bootstrap");
      state.projects = data.projects || [];
      $("project").innerHTML = state.projects.map(p => `<option value="${esc(p.project_code)}">${esc(p.project_short_name)} · ${esc(p.operating_status)}</option>`).join("");
      const preferred = state.projects.find(p => p.project_code === "PRJ-WCL-BASE") || state.projects[0];
      $("project").value = preferred?.project_code || "";
      selectProject();
      $("health").textContent = "DeepSeek 与 ERPNext 已连接";
    } catch (error) {
      $("health").textContent = `连接失败：${error.message}`;
      addMessage("error", error.message);
    }
  }

  function selectProject() {
    state.project = state.projects.find(p => p.project_code === $("project").value) || state.projects[0];
    const employees = (state.project?.employees || []).filter(employeeAllowed);
    $("employee").innerHTML = employees.map(e => `<option value="${esc(e.user_email)}">${esc(e.employee_name)} · ${esc(e.position)}</option>`).join("");
    const preferred = employees.find(e => e.role_code === "ROLE-MAT-EQP-MGR") || employees[0];
    $("employee").value = preferred?.user_email || "";
    selectEmployee();
  }

  function selectEmployee() {
    state.employee = (state.project?.employees || []).find(e => e.user_email === $("employee").value) || null;
    $("identity").innerHTML = state.employee
      ? `<strong>${esc(state.employee.employee_name)}</strong><br>${esc(state.employee.position)}<br>${esc(state.project.project_short_name)} · ${esc(state.project.warehouse_code)}`
      : "当前项目没有物料建档测试身份";
    $("actor").textContent = state.employee ? `${state.employee.employee_name} · ${state.employee.position} · ${state.project.project_short_name}` : "请选择身份";
  }

  function addMessage(kind, text, extra="") {
    $("messages").querySelector(".welcome")?.remove();
    const node = document.createElement("article");
    node.className = `message ${kind}`;
    node.innerHTML = `<div>${esc(text)}</div>${extra}`;
    $("messages").appendChild(node);
    $("messages").scrollTop = $("messages").scrollHeight;
  }

  function setBusy(busy, label="") {
    $("send").disabled = busy;
    $("confirm").disabled = busy;
    $("stage").classList.toggle("running", busy);
    $("stage").querySelector("span").textContent = label || (busy ? "小助理正在处理..." : "等待测试");
  }

  async function runPreview() {
    const text = $("input").value.trim();
    if (!text || !state.employee) return;
    state.requestId = crypto.randomUUID();
    addMessage("user", text);
    setBusy(true, "小助理正在理解物料并查阅说明书...");
    try {
      const payload = {user:state.employee.user_email, project_code:state.project.project_code, warehouse:state.project.warehouse_code, conversation_id:state.conversationId, text, execute:false};
      const started = await api("/api/agent/turn/start", {method:"POST", body:JSON.stringify(payload)});
      const runId = (started.run || started).run_id;
      const token = ++state.pollToken;
      while (token === state.pollToken) {
        const query = new URLSearchParams({run_id:runId,user:payload.user,project_code:payload.project_code,conversation_id:payload.conversation_id});
        const status = (await api(`/api/agent/run?${query}`)).run;
        setBusy(true, status.stage_label || "小助理正在处理...");
        if (status.status !== "running") {
          if (!status.result) throw new Error(status.error || "助理没有返回结果");
          renderResult(status.result);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 650));
      }
    } catch (error) {
      addMessage("error", error.message);
      $("stage").classList.add("failed");
    } finally { setBusy(false, "本轮处理完成"); }
  }

  function confirmation(result) { return result.confirmation || result.pending_tool_call?.summary || null; }
  function confirmHtml(summary) {
    if (!summary) return "";
    const fields = [["标准名称",summary.standard_name],["SKU 名称",summary.sku_name],["物料编码",summary.item_code],["物料分组",summary.item_group],["库存单位",summary.stock_uom],["必填规格",summary.required_specs],["辅助规格",summary.optional_specs]];
    return `<section class="confirm-card"><strong>${esc(summary.title || "标准物料建档确认")}</strong><div class="confirm-grid">${fields.filter(([,v])=>v).map(([k,v])=>`<span><b>${esc(k)}</b>${esc(v)}</span>`).join("")}</div></section>`;
  }

  function renderResult(result) {
    state.latest = result;
    const summary = confirmation(result);
    addMessage(result.status === "failed" ? "error" : "agent", result.message || result.status, confirmHtml(summary));
    $("pending").hidden = !(result.status === "needs_confirmation" && (result.pending_tool_call || result.tool_call));
    const classification = result.classification || result.business_result || {};
    $("summary").innerHTML = `<h3>${esc(result.status || "unknown")}</h3><p>${esc(result.message || "")}</p>${summary ? confirmHtml(summary) : ""}`;
    const steps = result.steps || [];
    $("steps").className = steps.length ? "steps" : "steps empty";
    $("steps").innerHTML = steps.length ? steps.map((step,index)=>`<div class="step"><b>${index+1}. ${esc(step.summary || step.action || step.stage || "处理")}</b><span>${esc(step.action || step.status || "")}</span></div>`).join("") : "暂无步骤";
    $("json").textContent = JSON.stringify(result, null, 2);
  }

  async function confirmCreate() {
    if (!state.latest || !state.employee) return;
    setBusy(true, "正在使用当前员工身份创建并回读 Item...");
    try {
      const data = await api("/api/agent/confirm", {method:"POST", body:JSON.stringify({user:state.employee.user_email,project_code:state.project.project_code,warehouse:state.project.warehouse_code,conversation_id:state.conversationId,text:$("input").value.trim(),execute:true,request_id:state.requestId})});
      renderResult(data.result);
      $("pending").hidden = true;
    } catch (error) { addMessage("error", error.message); }
    finally { setBusy(false, "执行完成"); }
  }

  async function reset() {
    state.pollToken += 1;
    if (state.employee) {
      try { await api("/api/session/reset", {method:"POST", body:JSON.stringify({user:state.employee.user_email,project_code:state.project.project_code,conversation_id:state.conversationId})}); } catch (_) {}
    }
    state.conversationId = crypto.randomUUID(); state.latest=null; state.requestId=null;
    $("messages").innerHTML = `<div class="welcome"><strong>新测试已开始</strong><p>旧会话上下文已清除，ERPNext 业务数据不会被删除。</p></div>`;
    $("pending").hidden = true; $("summary").innerHTML = "<p>发送一条物料建档请求后，这里会显示分类状态和确认字段。</p>"; $("steps").innerHTML="暂无步骤"; $("steps").className="steps empty"; $("json").textContent="{}";
  }

  $("project").onchange = selectProject;
  $("employee").onchange = selectEmployee;
  $("send").onclick = runPreview;
  $("confirm").onclick = confirmCreate;
  $("cancel").onclick = () => { $("pending").hidden=true; };
  $("reset").onclick = reset;
  document.addEventListener("click", event => { const b=event.target.closest("[data-example]"); if (b) { $("input").value=b.dataset.example; $("input").focus(); } });
  $("input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); runPreview(); } });
  boot();
})();
