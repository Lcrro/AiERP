      const state = {
        projects: [], project: null, employees: [], user: null,
        preview: null, documents: null, inbox: null, lastText: "", executeId: null,
        panel: "inbox", technicalView: "toolcall", documentDetail: null, historyToken: 0,
        conversationId: "default", developerMode: false,
      };
      const $ = id => document.getElementById(id);
      const WELCOME_HTML = $("messages").innerHTML;
      const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
      const pretty = value => JSON.stringify(value ?? null, null, 2);
      const conversationKey = () => `nexterp-conversation:${state.user?.user_email || "none"}:${state.project?.project_code || "none"}`;
      const ensureConversation = () => {
        const key = conversationKey();
        state.conversationId = localStorage.getItem(key) || crypto.randomUUID();
        localStorage.setItem(key, state.conversationId);
        return state.conversationId;
      };
      const FIELD_LABELS = {
        name:"单号", owner:"创建人", creation:"创建时间", modified:"最后修改", modified_by:"最后修改人",
        docstatus:"提交状态", status:"状态", title:"标题", company:"公司", material_request_type:"申请类型",
        transaction_date:"业务日期", schedule_date:"需求日期", posting_date:"过账日期", posting_time:"过账时间",
        supplier:"供应商", supplier_name:"供应商名称", project:"项目", cost_center:"成本中心", warehouse:"仓库",
        grand_total:"含税总额", net_total:"未税总额", currency:"币种", party:"往来方", payment_type:"收付类型",
        paid_amount:"支付金额", subject:"主题", priority:"优先级", purpose:"用途", stock_entry_type:"库存移动类型",
        per_ordered:"已转订单比例", per_received:"已收货比例", buying_price_list:"采购价格表",
      };
      const PRIMARY_FIELDS = {
        "Material Request": ["material_request_type","company","transaction_date","schedule_date","status","project","owner","modified","per_ordered","per_received"],
        "Request for Quotation": ["company","transaction_date","schedule_date","status","owner","modified"],
        "Purchase Order": ["supplier","company","transaction_date","schedule_date","status","currency","grand_total","owner","modified"],
        "Purchase Receipt": ["supplier","company","posting_date","status","currency","grand_total","owner","modified"],
        "Purchase Invoice": ["supplier","company","posting_date","status","currency","grand_total","owner","modified"],
        "Payment Entry": ["payment_type","party","company","posting_date","paid_amount","status","owner","modified"],
        "Stock Entry": ["stock_entry_type","purpose","company","posting_date","project","owner","modified"],
        "Task": ["subject","status","priority","project","owner","modified"],
        "ToDo": ["description","status","reference_type","reference_name","owner","modified"],
      };
      const ITEM_COLUMNS = ["item_code","item_name","description","qty","uom","rate","amount","warehouse","project","schedule_date"];
      const ITEM_LABELS = {item_code:"物料编码",item_name:"物料名称",description:"描述",qty:"数量",uom:"单位",rate:"单价",amount:"金额",warehouse:"仓库",project:"项目",schedule_date:"需求日期"};

      async function api(path, options = {}) {
        const response = await fetch(path, {headers:{"Content-Type":"application/json"}, ...options});
        const data = await response.json();
        if (!response.ok || (data.ok === false && !data.result)) throw new Error(data.error || `HTTP ${response.status}`);
        return data;
      }

      function initials(name) { return String(name || "?").slice(0, 1); }
      function statusText(doc) {
        if (doc.workflow_state) return String(doc.workflow_state);
        if (doc.status) return String(doc.status);
        if (Number(doc.docstatus) === 1) return "已提交";
        if (Number(doc.docstatus) === 2) return "已取消";
        return "草稿";
      }
      function statusClass(doc) { return Number(doc.docstatus) === 1 || /Submitted|已提交/.test(statusText(doc)) ? "submitted" : "draft"; }
      function docSubtitle(doc) {
        return doc.title || doc.supplier || doc.party || doc.subject || doc.description || doc.stock_entry_type || doc.purpose || doc.owner || "";
      }
      function dateShort(value) { return value ? String(value).replace("T", " ").slice(0, 16) : ""; }
      function formatNumber(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return String(value ?? "-");
        return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
      }

      async function boot() {
        try {
          const [health, catalog] = await Promise.all([api("/api/health"), api("/api/workbench/bootstrap")]);
          $("healthText").classList.add("ok");
          $("healthText").textContent = `DeepSeek 与 ERPNext 已连接 · ${health.profile}`;
          state.projects = catalog.projects || [];
          $("projectSelect").innerHTML = state.projects.map(project => `<option value="${esc(project.project_code)}">${esc(project.project_short_name)} · ${esc(project.operating_status)}</option>`).join("");
          $("projectSelect").onchange = () => selectProject(state.projects.find(project => project.project_code === $("projectSelect").value));
          selectProject(state.projects.find(project => project.project_code === "PRJ-HL-13") || state.projects[0]);
        } catch (error) {
          $("healthText").textContent = error.message;
          addMessage("error", `工作台初始化失败：${error.message}`);
        }
      }

      function selectProject(project) {
        if (!project) return;
        state.project = project;
        state.employees = project.employees || [];
        state.documents = null;
        $("projectSelect").value = project.project_code;
        $("projectMeta").textContent = `${project.project_name}\n默认仓库：${project.warehouse_code || "未配置"}`;
        renderEmployees();
        selectEmployee(state.employees.find(employee => employee.employee_name === "毛晓泉") || state.employees[0] || null);
      }

      function renderEmployees() {
        $("employeeList").innerHTML = state.employees.length
          ? state.employees.map(employee => `<button class="employee" data-user="${esc(employee.user_email)}"><span class="avatar">${esc(initials(employee.employee_name))}</span><span><strong>${esc(employee.employee_name)}</strong><span>${esc(employee.project_position || employee.position)}</span></span></button>`).join("")
          : `<div class="empty-state">该项目尚未配置可登录员工。</div>`;
        document.querySelectorAll(".employee").forEach(button => button.onclick = () => selectEmployee(state.employees.find(employee => employee.user_email === button.dataset.user)));
      }

      function selectEmployee(employee) {
        state.user = employee;
        state.preview = null;
        state.historyToken += 1;
        const historyToken = state.historyToken;
        document.querySelectorAll(".employee").forEach(button => button.classList.toggle("active", employee && button.dataset.user === employee.user_email));
        const position = employee?.project_position || employee?.position || "";
        $("assistantName").textContent = employee ? `${employee.employee_name}的工作助理` : "员工工作助理";
        $("assistantContext").textContent = employee ? `${state.project.project_short_name} · ${position}` : "该项目暂未配置员工";
        $("actorLabel").textContent = employee ? `${state.project.project_short_name} · ${employee.employee_name} · ${position}` : "请选择员工";
        ensureConversation();
        renderContextSummary();
        loadHistory(historyToken);
        loadInbox();
        loadDocuments();
      }

      function renderContextSummary() {
        $("contextSummary").innerHTML = `
          <div class="metric"><span>当前项目</span><strong>${esc(state.project?.project_short_name || "-")}</strong></div>
          <div class="metric"><span>当前身份</span><strong>${esc(state.user?.employee_name || "-")}</strong></div>
          <div class="metric"><span>数据范围</span><strong>本人权限</strong></div>`;
      }

      async function loadDocuments({preserve = false} = {}) {
        if (!state.user || !state.project) { state.documents = null; renderOperations(); return; }
        state.documents = preserve && state.documents?.modules
          ? {...state.documents, refreshing:true}
          : {loading:true};
        renderOperations();
        try {
          state.documents = await api(`/api/documents?user=${encodeURIComponent(state.user.user_email)}&project=${encodeURIComponent(state.project.project_code)}&module=buying&page=1&page_size=20`);
        } catch (error) {
          state.documents = {error:error.message};
        }
        renderOperations();
      }

      async function loadInbox({preserve = false} = {}) {
        if (!state.user || !state.project) { state.inbox = null; renderOperations(); return; }
        state.inbox = preserve && state.inbox?.items ? {...state.inbox, refreshing:true} : {loading:true};
        renderOperations();
        try {
          state.inbox = await api(`/api/inbox?user=${encodeURIComponent(state.user.user_email)}&project=${encodeURIComponent(state.project.project_code)}&limit=30`);
        } catch (error) {
          state.inbox = {error:error.message, items:[]};
        }
        renderOperations();
      }

      function prependCreatedDocuments(links) {
        if (!state.documents?.modules) return;
        for (const link of links || []) {
          const group = state.documents.modules.flatMap(module => module.groups || []).find(candidate => candidate.doctype === link.doctype);
          if (!group || group.documents?.some(document => document.name === link.name)) continue;
          group.documents = [{name:link.name, status:"Draft", modified:new Date().toISOString()}, ...(group.documents || [])];
        }
      }

      async function loadHistory(token) {
        $("messages").innerHTML = WELCOME_HTML;
        $("confirmBar").classList.remove("visible");
        state.preview = null;
        state.lastText = "";
        if (!state.user) return;
        const requestedUser = state.user.user_email;
        try {
          const history = await api(`/api/session?user=${encodeURIComponent(requestedUser)}&project=${encodeURIComponent(state.project.project_code)}&conversation_id=${encodeURIComponent(state.conversationId)}`);
          if (token !== state.historyToken || state.user?.user_email !== requestedUser) return;
          for (const turn of history.turns || []) {
            if (turn.user_text) addMessage("user", turn.user_text);
            const result = turn.result || {};
            if (result.message) addMessage(result.status === "failed" ? "error" : "agent", result.message, result.document_links || [], result.candidates || []);
          }
          state.preview = history.latest_result || null;
          state.lastText = history.latest_user_text || "";
          state.executeId = crypto.randomUUID();
          const canExecute = state.preview?.status === "needs_confirmation" && (state.preview.pending_tool_call || state.preview.tool_call);
          $("confirmBar").classList.toggle("visible", Boolean(canExecute));
          renderOperations();
        } catch (error) {
          if (token === state.historyToken) addMessage("error", `读取会话记录失败：${error.message}`);
        }
      }

      async function startNewConversation() {
        if (!state.user || !window.confirm("将清除该员工 Agent 的聊天记录、已解析实体和待确认操作，但不会删除 ERPNext 单据。是否继续？")) return;
        setBusy(true);
        try {
          await api("/api/session/reset", {method:"POST", body:JSON.stringify({user:state.user.user_email, project_code:state.project.project_code, conversation_id:state.conversationId})});
          state.conversationId = crypto.randomUUID();
          localStorage.setItem(conversationKey(), state.conversationId);
          state.historyToken += 1;
          state.preview = null;
          state.lastText = "";
          state.executeId = null;
          $("input").value = "";
          $("messages").innerHTML = WELCOME_HTML;
          $("confirmBar").classList.remove("visible");
          renderOperations();
        } catch (error) {
          addMessage("error", `新建会话失败：${error.message}`);
        } finally {
          setBusy(false);
        }
      }

      async function clearProjectDocuments() {
        if (!state.user || !state.project) return;
        const scope = `${state.project.project_short_name}中当前员工有权限处理的测试业务单据`;
        if (!window.confirm(`将取消并删除${scope}。项目、仓库、物料和员工等基础主数据不会删除。是否继续？`)) return;
        const button = $("clearDocuments");
        if (button) { button.disabled = true; button.textContent = "清理中..."; }
        try {
          const result = await api("/api/documents/reset", {
            method:"POST",
            body:JSON.stringify({user:state.user.user_email, project:state.project.project_code}),
          });
          const message = result.failed_count
            ? `已删除 ${result.deleted_count} 张测试单据，另有 ${result.failed_count} 张因权限或关联关系未能删除。`
            : `已清空当前项目的 ${result.deleted_count} 张测试业务单据。`;
          addMessage(result.failed_count ? "error" : "agent", message);
          await loadDocuments();
        } catch (error) {
          addMessage("error", `清空测试单据失败：${error.message}`);
          await loadDocuments();
        }
      }

      function addMessage(kind, text, links = [], candidates = []) {
        $("welcome")?.remove();
        const node = document.createElement("div");
        node.className = `message ${kind}`;
        node.innerHTML = `<div>${esc(text)}</div>${candidateCards(candidates)}${links.map(link => `<button class="message-doc" data-doctype="${esc(link.doctype)}" data-name="${esc(link.name)}"><span><strong>${esc(link.name)}</strong><small>${esc(link.doctype)} · 在测试台查看</small></span><span>查看详情 ›</span></button>`).join("")}`;
        $("messages").appendChild(node);
        bindDocumentButtons(node);
        node.querySelectorAll(".candidate-card").forEach(button => button.onclick = () => selectCandidate(button.dataset.code, button.dataset.name));
        $("messages").scrollTop = $("messages").scrollHeight;
      }

      function candidateByCode(code) {
        const groups = state.preview?.candidates || [];
        const rows = groups.flatMap(group => Array.isArray(group?.candidates) ? group.candidates : group?.item_code ? [group] : []);
        return rows.find(row => row.item_code === code) || {item_code:code};
      }

      async function selectCandidate(code, name) {
        if (!state.user || !code) return;
        setBusy(true);
        addMessage("user", `选择 ${name}（${code}）`);
        try {
          const data = await api("/api/agent/turn", {
            method:"POST",
            body:JSON.stringify({
              user:state.user.user_email,
              project_code:state.project.project_code,
              warehouse:state.project.warehouse_code,
              conversation_id:state.conversationId,
              event:{type:"select_candidate", entity_id:"selected_item", candidate:candidateByCode(code)},
            }),
          });
          handleAgentResult(data.result, false);
        } catch (error) {
          addMessage("error", error.message);
        } finally {
          setBusy(false);
        }
      }

      function candidateCards(groups) {
        const rows = (groups || []).flatMap(group => Array.isArray(group?.candidates) ? group.candidates : group?.item_code ? [group] : []);
        const unique = [...new Map(rows.filter(row => row?.item_code).map(row => [row.item_code, row])).values()].slice(0, 5);
        if (!unique.length) return "";
        return `<div class="candidate-list">${unique.map(row => {
          const inventory = (row.inventory || []).map(stock => `${String(stock.warehouse || "").replace(/ - [A-Z]+$/, "")} ${formatNumber(stock.available_qty ?? 0)}${row.stock_uom || ""}`).join(" · ");
          const total = row.inventory_summary?.total_available_qty;
          const stockText = inventory || (total !== undefined ? `相关仓库可用库存 ${formatNumber(total)}${row.stock_uom || ""}` : "暂未取得相关仓库库存");
          return `<button class="candidate-card" data-code="${esc(row.item_code)}" data-name="${esc(row.sku_name || row.item_name || row.item_code)}"><span class="candidate-title"><strong>${esc(row.sku_name || row.item_name || row.item_code)}</strong><span>${esc(row.item_code)}</span></span><span class="candidate-specs">${esc(row.required_specs || "暂无更多规格")} · 单位：${esc(row.stock_uom || "-")}</span><span class="candidate-stock">${esc(stockText)} · 点击选择</span></button>`;
        }).join("")}</div>`;
      }

      function handleAgentResult(result, executed) {
        state.preview = result;
        addMessage(result.status === "failed" ? "error" : "agent", result.message, result.document_links || [], result.candidates || []);
        const canExecute = !executed && result.status === "needs_confirmation" && (result.pending_tool_call || result.tool_call);
        $("confirmBar").classList.toggle("visible", Boolean(canExecute));
        if (executed) {
          $("confirmBar").classList.remove("visible");
          prependCreatedDocuments(result.document_links || []);
          void loadDocuments({preserve:true});
          void loadInbox({preserve:true});
        }
        renderOperations();
      }

      async function run(execute) {
        const text = execute ? state.lastText : $("input").value.trim();
        if (!state.user || !text) return;
        setBusy(true);
        if (!execute) {
          state.lastText = text;
          state.executeId = crypto.randomUUID();
          addMessage("user", text);
        }
        try {
          const data = await api(execute ? "/api/agent/confirm" : "/api/agent/turn", {
            method:"POST",
            body:JSON.stringify({user:state.user.user_email, project_code:state.project?.project_code, warehouse:state.project?.warehouse_code, conversation_id:state.conversationId, text, execute, request_id:execute ? state.executeId : null}),
          });
          handleAgentResult(data.result, execute);
        } catch (error) {
          addMessage("error", error.message);
        } finally {
          setBusy(false);
        }
      }

      function setBusy(busy) {
        $("previewBtn").disabled = busy;
        $("executeBtn").disabled = busy;
        $("previewBtn").textContent = busy ? "助理处理中..." : "发送";
      }

      function renderOperations() {
        document.querySelectorAll(".operations-tab").forEach(button => button.classList.toggle("active", button.dataset.panel === state.panel));
        if (state.panel === "inbox") return renderInbox();
        if (["mine","progress","recent","exceptions"].includes(state.panel)) return renderDocuments(state.panel);
        if (state.panel === "steps") return renderSteps();
        return renderTechnical();
      }

      function renderInbox() {
        if (!state.inbox || state.inbox.loading) {
          $("operationsBody").innerHTML = `<div class="empty-state">正在读取 ERPNext 待办...</div>`;
          return;
        }
        if (state.inbox.error) {
          $("operationsBody").innerHTML = `<div class="message error">${esc(state.inbox.error)}</div>`;
          return;
        }
        const items = state.inbox.items || [];
        $("operationsBody").innerHTML = `<div class="panel-toolbar"><strong>待我处理${state.inbox.refreshing ? " · 正在同步" : ""}</strong><span><button id="refreshInbox">刷新</button></span></div><p class="section-note">直接来自 ERPNext Workflow Action，处理结果会进入原生审批记录。</p>${items.length ? `<div class="work-list">${items.map(item => `<div class="work-card" data-doctype="${esc(item.reference_doctype)}" data-name="${esc(item.reference_name)}"><span><strong>${esc(item.title || item.reference_name)}</strong><span>${esc(item.label)} · ${esc(item.workflow_state || "待处理")}</span><span>${esc(item.reference_name)} · ${esc(item.owner || "-")}</span>${item.actions?.length ? `<span class="work-card-actions">${item.actions.map(action => `<button data-workflow-action="${esc(action)}">${esc(action)}</button>`).join("")}</span>` : ""}</span><small>${esc(dateShort(item.modified))}</small></div>`).join("")}</div>` : `<div class="empty-state">当前没有需要你处理的审批。</div>`}`;
        $("refreshInbox")?.addEventListener("click", () => loadInbox());
        document.querySelectorAll(".work-card").forEach(card => card.addEventListener("click", event => {
          if (event.target.closest("[data-workflow-action]")) return;
          openDocument(card.dataset.doctype, card.dataset.name);
        }));
        document.querySelectorAll("[data-workflow-action]").forEach(button => button.addEventListener("click", event => {
          const card = event.target.closest(".work-card");
          performWorkflowAction(card.dataset.doctype, card.dataset.name, button.dataset.workflowAction);
        }));
      }

      async function performWorkflowAction(doctype, name, action) {
        if (!window.confirm(`确认对 ${name} 执行“${action}”？`)) return;
        try {
          await api("/api/workflow/action", {
            method:"POST",
            body:JSON.stringify({user:state.user.user_email, doctype, name, action, project_code:state.project.project_code, conversation_id:state.conversationId, request_id:crypto.randomUUID()}),
          });
          await Promise.all([loadInbox({preserve:true}), loadDocuments({preserve:true})]);
        } catch (error) {
          window.alert(error.message);
        }
      }

      function renderDocuments(mode = "recent") {
        if (!state.documents || state.documents.loading) {
          $("operationsBody").innerHTML = `<div class="empty-state">正在读取当前员工可见单据...</div>`;
          return;
        }
        if (state.documents.error) {
          $("operationsBody").innerHTML = `<div class="message error">${esc(state.documents.error)}</div>`;
          return;
        }
        const titles = {mine:"我的申请",progress:"采购进度",recent:"最近单据",exceptions:"异常与退回"};
        const modules = (state.documents.modules || []).map(module => ({...module, groups:(module.groups || []).map(group => ({...group, documents:(group.documents || []).filter(document => {
          if (mode === "mine") return group.doctype === "Material Request" && document.owner === state.user.user_email;
          if (mode === "progress") return ["Request for Quotation","Purchase Order","Purchase Receipt"].includes(group.doctype) || (group.doctype === "Material Request" && Number(document.docstatus) === 1);
          if (mode === "exceptions") return Boolean(document.is_return) || /驳回|取消|停止|异常|Rejected|Cancelled|Stopped/i.test(`${document.workflow_state || ""} ${document.status || ""}`);
          return true;
        })}))}));
        const visibleCount = modules.flatMap(module => module.groups).reduce((sum, group) => sum + group.documents.length, 0);
        $("operationsBody").innerHTML = `<div class="panel-toolbar"><strong>${titles[mode]}${state.documents.refreshing ? " · 正在同步" : ""}</strong><span><button id="refreshDocuments">刷新</button>${state.developerMode ? `<button id="clearDocuments">清空测试单据</button>` : ""}</span></div>${visibleCount ? modules.map(module => `<section>${module.groups.filter(group => group.documents.length || group.error).map(group => `<div class="doctype-group"><div class="doctype-head"><span>${esc(group.label)}</span><span>${group.documents.length}</span></div>${group.error ? `<div class="empty-state">${esc(group.error)}</div>` : group.documents.map(document => `<button class="doc-row" data-doctype="${esc(group.doctype || "")}" data-name="${esc(document.name)}"><span><strong>${esc(document.name)}</strong><small>${esc(docSubtitle(document))}</small></span><span class="doc-row-status"><span>${esc(statusText(document))}</span><small>${esc(dateShort(document.modified))}</small></span></button>`).join("")}</div>`).join("")}</section>`).join("") : `<div class="empty-state">当前没有${esc(titles[mode])}。</div>`}`;
        $("refreshDocuments")?.addEventListener("click", loadDocuments);
        $("clearDocuments")?.addEventListener("click", clearProjectDocuments);
        bindDocumentButtons($("operationsBody"));
      }

      function inferDoctype(label) {
        return ({"材料申请":"Material Request","询价单":"Request for Quotation","采购订单":"Purchase Order","采购收货":"Purchase Receipt","库存移动":"Stock Entry","采购发票":"Purchase Invoice","付款单":"Payment Entry","任务":"Task","待办":"ToDo"})[label] || "";
      }

      function renderSteps() {
        const steps = state.preview?.steps || [];
        $("operationsBody").innerHTML = steps.length
          ? `<div class="panel-toolbar"><strong>可审计执行轨迹</strong><span></span></div>${steps.map((step,index) => `<div class="step"><div class="step-head"><span>${index + 1}. ${esc(step.label)}</span><span>${esc(step.action)}</span></div><pre>${esc(pretty({payload:step.payload,result:step.result}))}</pre></div>`).join("")}`
          : `<div class="empty-state">发送一条业务请求后，这里会显示 Agent 的可审计动作。</div>`;
      }

      function renderTechnical() {
        const result = state.preview;
        const views = {
          toolcall: result?.tool_calls?.length ? result.tool_calls : (result?.pending_tool_call || result?.tool_call),
          toolresult: result?.tool_results?.length ? result.tool_results : result?.tool_result,
          raw: result,
        };
        $("operationsBody").innerHTML = `<div class="tech-switch"><button data-tech="toolcall">ToolCall</button><button data-tech="toolresult">ToolResult</button><button data-tech="raw">完整 JSON</button></div><div style="margin-top:10px"><pre>${esc(pretty(views[state.technicalView]))}</pre></div>`;
        document.querySelectorAll("[data-tech]").forEach(button => {
          button.classList.toggle("active", button.dataset.tech === state.technicalView);
          button.onclick = () => { state.technicalView = button.dataset.tech; renderTechnical(); };
        });
      }

      function bindDocumentButtons(root) {
        root.querySelectorAll("[data-doctype][data-name]").forEach(button => button.onclick = () => openDocument(button.dataset.doctype, button.dataset.name));
      }

      async function openDocument(doctype, name) {
        if (!state.user || !doctype || !name) return;
        state.documentDetail = {loading:true, doctype, name};
        showDrawer();
        renderDocumentDrawer();
        try {
          state.documentDetail = await api(`/api/document?user=${encodeURIComponent(state.user.user_email)}&doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(name)}`);
        } catch (error) {
          state.documentDetail = {error:error.message, doctype, name};
        }
        renderDocumentDrawer();
      }

      function showDrawer() {
        $("drawerShade").classList.add("visible");
        $("documentDrawer").classList.add("visible");
      }
      function closeDrawer() {
        $("drawerShade").classList.remove("visible");
        $("documentDrawer").classList.remove("visible");
      }

      function renderDocumentDrawer() {
        const detail = state.documentDetail;
        if (!detail || detail.loading) {
          $("drawerTitle").innerHTML = `<h2>${esc(detail?.name || "业务单据")}</h2><p>正在读取当前员工可见内容</p>`;
          $("drawerBody").innerHTML = `<div class="drawer-loading">正在加载单据...</div>`;
          return;
        }
        if (detail.error) {
          $("drawerTitle").innerHTML = `<h2>${esc(detail.name)}</h2><p>${esc(detail.doctype)}</p>`;
          $("drawerBody").innerHTML = `<div class="message error">${esc(detail.error)}</div>`;
          return;
        }
        const doc = detail.document || {};
        const process = detail.process || {};
        const status = statusText(doc);
        $("drawerTitle").innerHTML = `<h2>${esc(detail.name)} <span class="status-badge ${statusClass(doc)}">${esc(status)}</span></h2><p>${esc(detail.label)} · ${esc(doc.owner || "-")} · ${esc(dateShort(doc.modified || doc.creation))}</p>`;
        const fields = (PRIMARY_FIELDS[detail.doctype] || ["company","status","owner","modified"]).filter(key => doc[key] !== undefined && doc[key] !== null && doc[key] !== "");
        const childRows = Array.isArray(doc.items) ? doc.items : [];
        const columns = ITEM_COLUMNS.filter(key => childRows.some(row => row[key] !== undefined && row[key] !== null && row[key] !== ""));
        $("drawerBody").innerHTML = `
          <div class="process-card"><div><strong>流程状态：${esc(process.state || status)}</strong><span>${esc(process.description || "暂无流程信息")}</span><span>${esc(process.assignees?.length ? `当前处理人：${process.assignees.join("、")}` : process.notification || "")}</span></div><div>${(process.available_actions || []).map(action => `<button class="workflow-action" data-action="${esc(action)}">${esc(action)}</button>`).join("")}${process.can_submit ? `<button id="submitDocumentDraft">提交单据</button>` : ""}</div></div>
          <div class="field-grid">${fields.map(key => `<div class="field"><span>${esc(FIELD_LABELS[key] || key)}</span><strong>${esc(formatField(key, doc[key]))}</strong></div>`).join("")}</div>
          ${childRows.length ? `<h3 class="drawer-section-title">明细行 · ${childRows.length}</h3><div class="items-wrap"><table class="items-table"><thead><tr>${columns.map(key => `<th>${esc(ITEM_LABELS[key] || key)}</th>`).join("")}</tr></thead><tbody>${childRows.map(row => `<tr>${columns.map(key => `<td>${esc(formatField(key, row[key]))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : ""}
          ${state.developerMode ? `<details class="raw-details"><summary>查看完整单据 JSON</summary><pre>${esc(pretty(doc))}</pre></details>` : ""}`;
        $("submitDocumentDraft")?.addEventListener("click", async () => {
          if (!window.confirm(`确认提交 ${detail.name}？`)) return;
          const button = $("submitDocumentDraft");
          button.disabled = true;
          button.textContent = "提交中...";
          try {
            state.documentDetail = await api("/api/document/submit", {
              method:"POST",
              body:JSON.stringify({user:state.user.user_email, doctype:detail.doctype, name:detail.name, project_code:state.project?.project_code, conversation_id:state.conversationId, request_id:crypto.randomUUID()}),
            });
            renderDocumentDrawer();
            await Promise.all([loadInbox({preserve:true}), loadDocuments({preserve:true})]);
          } catch (error) {
            window.alert(error.message);
            await openDocument(detail.doctype, detail.name);
          }
        });
        document.querySelectorAll(".workflow-action").forEach(button => button.addEventListener("click", async () => {
          const action = button.dataset.action;
          if (!window.confirm(`确认对 ${detail.name} 执行“${action}”？`)) return;
          button.disabled = true;
          button.textContent = "处理中...";
          try {
            state.documentDetail = await api("/api/workflow/action", {
              method:"POST",
              body:JSON.stringify({user:state.user.user_email, doctype:detail.doctype, name:detail.name, action, project_code:state.project?.project_code, conversation_id:state.conversationId, request_id:crypto.randomUUID()}),
            });
            renderDocumentDrawer();
            await Promise.all([loadInbox({preserve:true}), loadDocuments({preserve:true})]);
          } catch (error) {
            window.alert(error.message);
            await openDocument(detail.doctype, detail.name);
          }
        }));
      }

      function formatField(key, value) {
        if (key === "docstatus") return Number(value) === 1 ? "已提交" : Number(value) === 2 ? "已取消" : "草稿";
        if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
        if (typeof value === "object") return pretty(value);
        return String(value ?? "-");
      }

      $("previewBtn").onclick = () => run(false);
      $("executeBtn").onclick = () => run(true);
      $("cancelConfirm").onclick = () => $("confirmBar").classList.remove("visible");
      $("clearBtn").onclick = startNewConversation;
      $("developerToggle").onclick = () => {
        state.developerMode = !state.developerMode;
        document.body.classList.toggle("developer-mode", state.developerMode);
        $("developerToggle").classList.toggle("active", state.developerMode);
        $("developerToggle").textContent = state.developerMode ? "退出开发者模式" : "开发者模式";
        if (!state.developerMode && ["steps", "technical"].includes(state.panel)) state.panel = "inbox";
        renderOperations();
        if (state.documentDetail) renderDocumentDrawer();
      };
      $("drawerClose").onclick = closeDrawer;
      $("drawerShade").onclick = closeDrawer;
      $("contextToggle").onclick = () => $("contextPanel").classList.toggle("open");
      $("operationsToggle").onclick = () => $("operationsPanel").classList.toggle("open");
      document.querySelectorAll("[data-example]").forEach(button => button.onclick = () => { $("input").value = button.dataset.example; $("input").focus(); });
      document.querySelectorAll(".operations-tab").forEach(button => button.onclick = () => { state.panel = button.dataset.panel; renderOperations(); });
      $("input").addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          if (!$("previewBtn").disabled) run(false);
        }
      });
      document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
      boot();