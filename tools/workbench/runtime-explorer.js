const LAYERS = [
  {
    id: "request",
    index: "01",
    title: "员工表达",
    subtitle: "目标与现场语境",
    kind: "model",
    responsibility: "接收员工的人话、当前项目、岗位、时间要求和历史对话。",
    boundary: "员工不应填写 ERPNext 主键、JSON 或底层字段。",
    friction: "简称、土名、缺数量和省略上下文会造成歧义。",
  },
  {
    id: "planner",
    index: "02",
    title: "DeepSeek 规划",
    subtitle: "理解下一步目标",
    kind: "model",
    responsibility: "理解业务目标，决定查询、追问、提出业务动作或完成回复。",
    boundary: "不直接写 ERPNext，也不能编造物料编码、仓库和单号。",
    friction: "规划轮次过多、问题拆得过碎时，交流会显得机械。",
  },
  {
    id: "capability",
    index: "03",
    title: "Capability Skill",
    subtitle: "按需披露业务能力",
    kind: "runtime",
    responsibility: "从岗位可用能力中最多发现 5 项，并按需加载完整 Guide。",
    boundary: "约 160 个底层 ToolCall 不会一次性塞给模型。",
    friction: "能力召回不准会导致反复发现或找不到合法下一步。",
  },
  {
    id: "resolver",
    index: "04",
    title: "Resolver",
    subtitle: "把人话变成真实实体",
    kind: "runtime",
    responsibility: "解析真实物料、项目、仓库、供应商、员工和业务单号。",
    boundary: "多候选必须交给员工选择，不能凭猜测填主键。",
    friction: "候选展示不充分或重复解析，会让助理显得迟钝。",
  },
  {
    id: "compiler",
    index: "05",
    title: "确定性编译器",
    subtitle: "生成精确 ToolCall",
    kind: "runtime",
    responsibility: "按字段来源、业务默认值和 Pydantic 契约编译精确参数。",
    boundary: "日期、数量、来源单据关系等由程序校验，不交给模型自由发挥。",
    friction: "契约缺字段或错误信息太技术化，会产生僵硬追问。",
  },
  {
    id: "gateway",
    index: "06",
    title: "ToolGateway",
    subtitle: "身份、权限与确认",
    kind: "runtime",
    responsibility: "检查岗位暴露、员工身份、幂等、防绕过和写操作确认。",
    boundary: "确认后执行原 ToolCall，不重新让模型规划。",
    friction: "确认点过多或状态没有及时回显，会让流程像在反复申请许可。",
  },
  {
    id: "erpnext",
    index: "07",
    title: "ERPNext",
    subtitle: "业务事实与最终执行",
    kind: "erp",
    responsibility: "执行权限、库存、工作流、会计和单据业务规则。",
    boundary: "ERPNext 是唯一业务事实来源，Runtime 不复制业务状态。",
    friction: "接口慢、权限不足或错误消息晦涩，会直接影响助理体验。",
  },
  {
    id: "answer",
    index: "08",
    title: "回复与会话",
    subtitle: "解释结果并记住事实",
    kind: "model",
    responsibility: "用自然语言说明真实结果，并保存已确认实体和最近单号。",
    boundary: "单号、数量、金额和状态必须来自 ToolResult。",
    friction: "技术错误泄露、旧上下文污染或假成功，会最明显地破坏信任。",
  },
];

const SAMPLE = {
  updated_at: "示例轨迹",
  turns: [
    {
      user_text: "帮我申请 100 双帆布手套，明天到货",
      result: {
        status: "needs_confirmation",
        message: "已准备好材料申请草稿，等待确认后写入 ERPNext。",
        steps: [
          { label: "DeepSeek规划", action: "discover_capabilities", payload: { query: "创建劳保用品材料申请", modules: ["buying"] }, result: { summary: "查找材料申请能力" } },
          { label: "发现业务能力", action: "discover_capabilities", payload: { query: "创建劳保用品材料申请" }, result: { capabilities: [{ capability_id: "buying.material_request.prepare", purpose: "准备材料申请草稿" }], summary: "命中材料申请能力并自动加载 Guide" } },
          { label: "解析真实实体", action: "resolve_entities", payload: { item_text: "帆布手套", project_text: "当前项目", warehouse_text: "项目仓库" }, result: { item_code: "SAFE-000005", project: "PRJ-HL-13", warehouse: "合流1.3标仓库 - SD", summary: "物料、项目和仓库已解析" } },
          { label: "DeepSeek规划", action: "propose_business_action", payload: { capability_id: "buying.material_request.prepare", intent: { qty: 100, uom: "双", schedule_date: "明天" } }, result: { summary: "提出材料申请业务动作" } },
          { label: "确定性编译", action: "compile_capability", payload: { capability_id: "buying.material_request.prepare" }, result: { tool: "erpnext.buying.create_material_request_draft", validation: "passed", summary: "字段来源与业务约束通过" } },
          { label: "等待员工确认", action: "request_confirmation", payload: { project: "合流1.3标", item: "帆布手套", qty: 100, warehouse: "合流1.3标仓库" }, result: { summary: "写操作尚未执行" } },
        ],
      },
    },
  ],
};

const $ = (selector) => document.querySelector(selector);
const state = { bootstrap: null, trace: null, selectedLayer: "planner" };

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function pretty(value) {
  return JSON.stringify(value ?? {}, null, 2);
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `请求失败：${response.status}`);
  return payload;
}

function renderFlow() {
  $("#flowMap").innerHTML = LAYERS.map((layer) => `
    <button class="flow-node ${layer.kind} ${layer.id === state.selectedLayer ? "active" : ""}" data-layer="${layer.id}">
      <span class="node-index">${layer.index}</span>
      <strong>${layer.title}</strong>
      <small>${layer.subtitle}</small>
    </button>`).join("");
  document.querySelectorAll("[data-layer]").forEach((button) => button.addEventListener("click", () => {
    state.selectedLayer = button.dataset.layer;
    renderFlow();
    renderLayerDetail();
  }));
}

function renderLayerDetail() {
  const layer = LAYERS.find((item) => item.id === state.selectedLayer) || LAYERS[0];
  $("#layerDetail").innerHTML = `
    <div><span>这一层负责</span><strong>${esc(layer.responsibility)}</strong></div>
    <div><span>明确边界</span><strong>${esc(layer.boundary)}</strong></div>
    <div><span>可能的笨拙来源</span><strong>${esc(layer.friction)}</strong></div>`;
}

function projectEmployees(project) {
  if (!project) return [];
  return project.employees || project.team || [];
}

function selectedProject() {
  return state.bootstrap?.projects?.find((item) => (item.project_code || item.code) === $("#projectSelect").value);
}

function selectedEmployee() {
  const project = selectedProject();
  return projectEmployees(project).find((item) => (item.user_email || item.email) === $("#employeeSelect").value);
}

function conversationKey() {
  return `nexterp-conversation:${$("#employeeSelect").value}:${$("#projectSelect").value}`;
}

function syncConversationId() {
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get("conversation_id");
  $("#conversationId").value = fromUrl || localStorage.getItem(conversationKey()) || "";
}

function fillEmployees() {
  const employees = projectEmployees(selectedProject());
  $("#employeeSelect").innerHTML = employees.map((employee) => {
    const email = employee.user_email || employee.email || "";
    const name = employee.employee_name || employee.name || email;
    const role = employee.project_position || employee.position || employee.designation || employee.role || "";
    return `<option value="${esc(email)}">${esc(name)}${role ? ` · ${esc(role)}` : ""}</option>`;
  }).join("");
  const requested = new URLSearchParams(location.search).get("user");
  if (requested && employees.some((item) => (item.user_email || item.email) === requested)) $("#employeeSelect").value = requested;
  else {
    const materialClerk = employees.find((item) => item.employee_name === "毛晓泉" || item.name === "毛晓泉");
    if (materialClerk) $("#employeeSelect").value = materialClerk.user_email || materialClerk.email;
  }
  syncConversationId();
}

async function bootstrap() {
  try {
    const [health, data] = await Promise.all([fetchJson("/api/health"), fetchJson("/api/workbench/bootstrap")]);
    state.bootstrap = data;
    $("#health").textContent = health.ok ? "Runtime 与 ERPNext 已连接" : "服务异常";
    $("#health").classList.toggle("ok", Boolean(health.ok));
    const projects = data.projects || [];
    $("#projectSelect").innerHTML = projects.map((project) => {
      const code = project.project_code || project.code;
      const label = project.project_short_name || project.short_name || project.project_name || code;
      return `<option value="${esc(code)}">${esc(label)}</option>`;
    }).join("");
    const requestedProject = new URLSearchParams(location.search).get("project");
    if (requestedProject && projects.some((item) => (item.project_code || item.code) === requestedProject)) $("#projectSelect").value = requestedProject;
    else if (projects.some((item) => (item.project_code || item.code) === "PRJ-HL-13")) $("#projectSelect").value = "PRJ-HL-13";
    fillEmployees();
  } catch (error) {
    $("#health").textContent = `连接失败：${error.message}`;
  }
}

function classifyStep(step) {
  const label = String(step.label || "");
  const action = String(step.action || "");
  if (label === "DeepSeek规划") return { kind: "model", layer: "planner", name: "模型决定下一动作" };
  if (/发现业务能力|加载.*Guide|capabilit/i.test(`${label} ${action}`)) return { kind: "runtime", layer: "capability", name: "筛选并加载业务能力" };
  if (/解析|resolve/i.test(`${label} ${action}`)) return { kind: "runtime", layer: "resolver", name: "解析真实业务实体" };
  if (/编译|契约|预检|compile|validate/i.test(`${label} ${action}`)) return { kind: "runtime", layer: "compiler", name: "编译并校验精确参数" };
  if (/确认|权限|身份|幂等|重复|gateway|confirmation/i.test(`${label} ${action}`)) return { kind: "runtime", layer: "gateway", name: "执行边界检查" };
  if (/ERPNext|执行工具|回读|execute_tool|verify/i.test(`${label} ${action}`)) return { kind: "erp", layer: "erpnext", name: "读取或写入 ERPNext" };
  if (/finish|回复|完成/i.test(`${label} ${action}`)) return { kind: "model", layer: "answer", name: "组织员工回复" };
  return { kind: "runtime", layer: "compiler", name: label || action || "Runtime 处理" };
}

function stepSummary(step) {
  const result = step.result || {};
  return result.summary || result.message || result.type || step.summary || "已完成该步骤；点击查看输入和结果。";
}

function latestTurn(trace) {
  if (trace?.latest_result) {
    return {
      user_text: trace.latest_user_text || trace.turns?.[trace.turns.length - 1]?.user_text || "",
      result: trace.latest_result,
    };
  }
  const turns = trace?.turns || [];
  return turns[turns.length - 1] || null;
}

function renderTrace(trace) {
  state.trace = trace;
  const turn = latestTurn(trace);
  if (!turn) {
    $("#traceTitle").textContent = "该会话还没有请求记录";
    $("#traceStatus").textContent = "空会话";
    $("#traceSummary").innerHTML = "";
    $("#traceTimeline").innerHTML = '<div class="empty">先在工作台发送一条消息，再回来读取轨迹；也可以查看示例。</div>';
    renderDiagnosis(null);
    return;
  }
  const result = turn.result || {};
  const steps = result.steps || [];
  const modelCalls = steps.filter((step) => classifyStep(step).kind === "model").length;
  const runtimeCalls = steps.filter((step) => classifyStep(step).kind === "runtime").length;
  const erpCalls = steps.filter((step) => classifyStep(step).kind === "erp").length;
  $("#traceTitle").textContent = turn.user_text || "最近一次请求";
  $("#traceStatus").textContent = statusLabel(result.status);
  $("#traceStatus").dataset.status = result.status || "unknown";
  $("#traceSummary").innerHTML = [
    ["模型决策", modelCalls], ["程序步骤", runtimeCalls], ["ERPNext 调用", erpCalls], ["总步骤", steps.length],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
  $("#traceTimeline").innerHTML = steps.length ? steps.map((step, index) => {
    const info = classifyStep(step);
    return `<button class="timeline-step ${info.kind}" data-step="${index}">
      <span class="step-dot"></span>
      <span class="step-index">${String(index + 1).padStart(2, "0")}</span>
      <span class="step-copy"><strong>${esc(info.name)}</strong><small>${esc(step.label || step.action || "")}</small><p>${esc(stepSummary(step))}</p></span>
      <span class="step-layer">${esc(LAYERS.find((layer) => layer.id === info.layer)?.title || "Runtime")}</span>
    </button>`;
  }).join("") : '<div class="empty">本轮没有记录可审计步骤。</div>';
  document.querySelectorAll("[data-step]").forEach((button) => button.addEventListener("click", () => openStep(steps[Number(button.dataset.step)])));
  const employee = selectedEmployee();
  $("#sessionMeta").innerHTML = `<strong>${esc(employee?.employee_name || employee?.name || $("#employeeSelect").value)}</strong><span>${esc($("#projectSelect").value)} · ${esc($("#conversationId").value || "示例")}</span><span>${esc(trace.updated_at || "")}</span>`;
  renderDiagnosis(turn);
}

function statusLabel(status) {
  return ({ completed: "已完成", needs_clarification: "需要补充", needs_confirmation: "等待确认", failed: "失败", running: "处理中" })[status] || status || "未知";
}

function includesFailure(step) {
  const value = `${step.label || ""} ${step.action || ""} ${pretty(step.result || {})}`.toLowerCase();
  return /error|failed|失败|无进展|no_progress|validation/.test(value);
}

function renderDiagnosis(turn) {
  if (!turn) {
    $("#diagnosis").innerHTML = '<div class="diagnostic neutral"><strong>等待真实轨迹</strong><p>读入一轮会话后，这里会根据步骤数量、重复动作、修复和追问给出体验诊断。</p></div>';
    return;
  }
  const result = turn.result || {};
  const steps = result.steps || [];
  const modelCalls = steps.filter((step) => step.label === "DeepSeek规划").length;
  const resolverCalls = steps.filter((step) => /resolve|解析/i.test(`${step.action || ""} ${step.label || ""}`)).length;
  const questions = steps.filter((step) => /ask_user|追问|需要补充/i.test(`${step.action || ""} ${step.label || ""}`)).length + (result.questions?.length || 0);
  const failures = steps.filter(includesFailure).length;
  const fingerprints = steps.map((step) => `${step.action || ""}:${JSON.stringify(step.payload || {})}`);
  const repeats = fingerprints.filter((value, index) => fingerprints.indexOf(value) !== index).length;
  const items = [];
  if (modelCalls > 4) items.push(["warn", "规划往返偏多", `DeepSeek 本轮决策 ${modelCalls} 次。模型每多走一轮都会增加延迟，也更容易丢失注意力。`]);
  else items.push(["good", "规划轮次可控", `DeepSeek 本轮决策 ${modelCalls} 次，其余工作交给了确定性程序。`]);
  if (repeats) items.push(["bad", "存在重复动作", `发现 ${repeats} 个输入完全相同的动作，这是最典型的“笨拙感”来源。`]);
  if (resolverCalls > 2) items.push(["warn", "实体被反复解析", `Resolver 执行 ${resolverCalls} 次，可考虑一次返回同一任务所需的全部实体。`]);
  if (questions > 1) items.push(["warn", "追问可能过碎", `本轮出现 ${questions} 次追问。可以合并问题或将候选与库存一起展示。`]);
  if (failures) items.push(["bad", "发生修复或失败", `轨迹中检测到 ${failures} 个错误/校验步骤；点击时间线可看具体字段。`]);
  if (result.status === "needs_confirmation") items.push(["neutral", "停在安全确认点", "这不是模型卡住：写操作已经编译完成，正等待员工确认后使用原 ToolCall 执行。"]);
  if (result.status === "needs_clarification") items.push(["neutral", "信息仍不够明确", "检查候选卡是否同时提供了关键规格、单位和实时库存；只说“请选择”通常会显得不够像助理。"]);
  if (result.status === "failed") items.push(["bad", "本轮最终失败", "优先检查最后一个有效步骤：是模型格式、能力召回、字段契约，还是 ERPNext 拒绝。"]);
  $("#diagnosis").innerHTML = items.map(([kind, title, body]) => `<div class="diagnostic ${kind}"><strong>${title}</strong><p>${body}</p></div>`).join("");
}

function openStep(step) {
  const info = classifyStep(step);
  $("#dialogKind").textContent = `${info.kind === "model" ? "模型决策" : info.kind === "erp" ? "ERPNext" : "确定性程序"} · ${step.action || "步骤"}`;
  $("#dialogTitle").textContent = step.label || info.name;
  $("#dialogBody").innerHTML = `<div class="dialog-grid">
    <section><h3>输入</h3><pre>${esc(pretty(step.payload || {}))}</pre></section>
    <section><h3>结果</h3><pre>${esc(pretty(step.result || {}))}</pre></section>
  </div><p class="audit-note">这里展示的是可审计动作及结构化数据，不包含模型隐藏思维过程。</p>`;
  $("#stepDialog").showModal();
}

async function loadTrace() {
  const user = $("#employeeSelect").value;
  const project = $("#projectSelect").value;
  const conversation = $("#conversationId").value.trim();
  if (!user || !project || !conversation) {
    renderTrace({ turns: [] });
    $("#traceTitle").textContent = "缺少会话 ID";
    return;
  }
  $("#loadTrace").disabled = true;
  $("#traceTitle").textContent = "正在读取真实轨迹";
  try {
    const trace = await fetchJson(`/api/session?user=${encodeURIComponent(user)}&project=${encodeURIComponent(project)}&conversation_id=${encodeURIComponent(conversation)}`);
    renderTrace(trace);
  } catch (error) {
    $("#traceTitle").textContent = "轨迹读取失败";
    $("#traceTimeline").innerHTML = `<div class="empty error">${esc(error.message)}</div>`;
  } finally {
    $("#loadTrace").disabled = false;
  }
}

$("#projectSelect").addEventListener("change", fillEmployees);
$("#employeeSelect").addEventListener("change", syncConversationId);
$("#loadTrace").addEventListener("click", loadTrace);
$("#useSample").addEventListener("click", () => renderTrace(SAMPLE));
$("#dialogClose").addEventListener("click", () => $("#stepDialog").close());
$("#stepDialog").addEventListener("click", (event) => { if (event.target === $("#stepDialog")) $("#stepDialog").close(); });

renderFlow();
renderLayerDetail();
renderDiagnosis(null);
bootstrap();
