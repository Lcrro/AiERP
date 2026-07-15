      const state = {
        projects: [], project: null, employees: [], user: null,
        preview: null, documents: null, inbox: null, procurement: null, procurementPreparation: null, lastText: "", executeId: null,
        panel: "inbox", technicalView: "toolcall", documentDetail: null, quotationContext: null, historyToken: 0,
        conversationId: "default", developerMode: false,
        procurementFilters: {scope:"project", urgency:"", family:"", supplier:"", before:"", view:"rows"},
        procurementSelected: new Set(),
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
        transaction_date:"业务日期", schedule_date:"需求日期", valid_till:"报价有效期", posting_date:"过账日期", posting_time:"过账时间",
        supplier:"供应商", supplier_name:"供应商名称", project:"项目", cost_center:"成本中心", warehouse:"仓库",
        grand_total:"含税总额", net_total:"未税总额", currency:"币种", party:"往来方", payment_type:"收付类型",
        paid_amount:"支付金额", subject:"主题", priority:"优先级", purpose:"用途", stock_entry_type:"库存移动类型",
        per_ordered:"已转订单比例", per_received:"已收货比例", buying_price_list:"采购价格表",
      };
      const PRIMARY_FIELDS = {
        "Material Request": ["material_request_type","company","transaction_date","schedule_date","status","project","owner","modified","per_ordered","per_received"],
        "Request for Quotation": ["company","transaction_date","schedule_date","status","owner","modified"],
        "Supplier Quotation": ["supplier","company","transaction_date","valid_till","status","currency","grand_total","owner","modified"],
        "Purchase Order": ["supplier","company","transaction_date","schedule_date","status","currency","grand_total","owner","modified"],
        "Purchase Receipt": ["supplier","company","posting_date","status","currency","grand_total","owner","modified"],
        "Purchase Invoice": ["supplier","company","posting_date","status","currency","grand_total","owner","modified"],
        "Payment Entry": ["payment_type","party","company","posting_date","paid_amount","status","owner","modified"],
        "Stock Entry": ["stock_entry_type","purpose","company","posting_date","project","owner","modified"],
        "Task": ["subject","status","priority","project","owner","modified"],
        "ToDo": ["description","status","reference_type","reference_name","owner","modified"],
      };
      const ITEM_COLUMNS = ["item_code","item_name","description","qty","received_qty","returned_qty","uom","rate","amount","warehouse","project","schedule_date"];
      const ITEM_LABELS = {item_code:"物料编码",item_name:"物料名称",description:"描述",qty:"数量",received_qty:"已收数量",returned_qty:"已退数量",uom:"单位",rate:"单价",amount:"金额",warehouse:"仓库",project:"项目",schedule_date:"需求日期"};

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
        state.procurement = null;
        state.procurementPreparation = null;
        state.procurementSelected.clear();
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
        state.panel = employee?.workbench_view?.default_panel || "inbox";
        document.querySelectorAll(".operations-tab").forEach(button => button.classList.toggle("recommended", (employee?.workbench_view?.recommended_panels || []).includes(button.dataset.panel)));
        $("assistantName").textContent = employee ? `${employee.employee_name}的工作助理` : "员工工作助理";
        $("assistantContext").textContent = employee ? `${state.project.project_short_name} · ${position}` : "该项目暂未配置员工";
        $("actorLabel").textContent = employee ? `${state.project.project_short_name} · ${employee.employee_name} · ${position}` : "请选择员工";
        ensureConversation();
        renderContextSummary();
        loadHistory(historyToken);
        loadInbox();
        loadDocuments();
      }

      async function loadPendingProcurement({preserve = false} = {}) {
        if (!state.user || !state.project) { state.procurement = null; renderOperations(); return; }
        state.procurement = preserve && state.procurement?.rows
          ? {...state.procurement, refreshing:true}
          : {loading:true};
        renderOperations();
        try {
          const filters = state.procurementFilters;
          state.procurement = await api(`/api/procurement/pending?user=${encodeURIComponent(state.user.user_email)}&project=${encodeURIComponent(state.project.project_code)}&scope=${encodeURIComponent(filters.scope)}&limit=500`);
          state.procurementSelected.clear();
          state.procurementPreparation = null;
        } catch (error) {
          state.procurement = {error:error.message, rows:[], aggregate:[]};
        }
        renderOperations();
      }

      function renderContextSummary() {
        $("contextSummary").innerHTML = `
          <div class="metric"><span>当前项目</span><strong>${esc(state.project?.project_short_name || "-")}</strong></div>
          <div class="metric"><span>当前身份</span><strong>${esc(state.user?.employee_name || "-")}</strong></div>
          <div class="metric"><span>岗位重点</span><strong>${esc(state.user?.workbench_view?.focus || "本人工作")}</strong></div>
          <div class="metric"><span>数据范围</span><strong>ERPNext 本人权限</strong></div>`;
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
          const priceText = Number(row.estimated_rate) > 0 ? ` · 测试参考价：${formatNumber(row.estimated_rate)}${row.currency === "CNY" ? "元" : row.currency || ""}/${row.stock_uom || "单位"}` : "";
          return `<button class="candidate-card" data-code="${esc(row.item_code)}" data-name="${esc(row.sku_name || row.item_name || row.item_code)}"><span class="candidate-title"><strong>${esc(row.sku_name || row.item_name || row.item_code)}</strong><span>${esc(row.item_code)}</span></span><span class="candidate-specs">${esc(row.required_specs || "暂无更多规格")} · 单位：${esc(row.stock_uom || "-")}${esc(priceText)}</span><span class="candidate-stock">${esc(stockText)} · 点击选择</span></button>`;
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
        if (state.panel === "pending") return renderPendingProcurement();
        if (["mine","progress","recent","exceptions"].includes(state.panel)) return renderDocuments(state.panel);
        if (state.panel === "steps") return renderSteps();
        return renderTechnical();
      }

      function filteredProcurementRows() {
        const filters = state.procurementFilters;
        return (state.procurement?.rows || []).filter(row => {
          if (filters.urgency && row.urgency !== filters.urgency) return false;
          if (filters.family && row.material_family !== filters.family) return false;
          if (filters.supplier && !(row.supplier_suggestions || []).some(supplier => supplier.supplier_name === filters.supplier)) return false;
          if (filters.before && String(row.schedule_date || "").slice(0, 10) > filters.before) return false;
          return true;
        });
      }

      function procurementRowKey(row) {
        return `${row.material_request || ""}:${row.material_request_item || row.item_code || ""}`;
      }

      function procurementInventory(row) {
        const stocks = (row.inventory || []).filter(stock => Number(stock.available_qty || 0) !== 0);
        if (!stocks.length) return `<span class="stock-chip empty">相关仓库无可用库存</span>`;
        return stocks.map(stock => `<span class="stock-chip">${esc(String(stock.warehouse || "").replace(/ - [A-Z]+$/, ""))}<strong>${esc(formatNumber(stock.available_qty))}</strong></span>`).join("");
      }

      function renderPendingProcurement() {
        if (!state.procurement || state.procurement.loading) {
          $("operationsBody").innerHTML = `<div class="empty-state">正在汇总已批准的待采购需求...</div>`;
          return;
        }
        if (state.procurement.error) {
          $("operationsBody").innerHTML = `<div class="message error">${esc(state.procurement.error)}</div>`;
          return;
        }
        const filters = state.procurementFilters;
        const rows = filteredProcurementRows();
        const summary = state.procurement.summary || {};
        const families = state.procurement.filters?.families || [];
        const suppliers = state.procurement.filters?.suppliers || [];
        const aggregate = new Map();
        rows.forEach(row => {
          const current = aggregate.get(row.item_code) || {...row, total_remaining_qty:0, request_count:0, projects:new Set(), source_rows:[]};
          current.total_remaining_qty += Number(row.remaining_qty || 0);
          current.request_count += 1;
          if (row.project) current.projects.add(row.project);
          current.source_rows.push(row);
          if (!current.schedule_date || String(row.schedule_date || "") < String(current.schedule_date)) current.schedule_date = row.schedule_date;
          aggregate.set(row.item_code, current);
        });
        const aggregateRows = [...aggregate.values()].map(row => ({...row, projects:[...row.projects]}));
        const visibleRows = filters.view === "aggregate" ? aggregateRows : rows;
        const urgencyLabels = {overdue:"已逾期",urgent:"紧急",soon:"近期",normal:"正常",unknown:"日期待确认"};
        const options = (values, selected, labels = {}) => values.map(value => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(labels[value] || value)}</option>`).join("");
        const cards = visibleRows.map(row => {
          const sourceRows = row.source_rows || [row];
          const keys = sourceRows.map(procurementRowKey);
          const checked = keys.every(key => state.procurementSelected.has(key));
          const remaining = filters.view === "aggregate" ? row.total_remaining_qty : row.remaining_qty;
          const requestText = filters.view === "aggregate" ? `${row.request_count} 条申请 · ${row.projects.length} 个项目` : `${row.material_request} · ${row.project || "未指定项目"}`;
          const suppliersText = (row.supplier_suggestions || []).map(supplier => `${supplier.supplier_name}${supplier.lead_time_days ? ` · ${supplier.lead_time_days}天` : ""}`).join("；") || "暂无建议供应商";
          return `<article class="procurement-card ${row.inventory_coverage === "shortage" ? "shortage" : ""}">
            <label class="procurement-select"><input type="checkbox" data-procurement-keys="${esc(keys.join("|"))}" ${checked ? "checked" : ""}><span></span></label>
            <div class="procurement-main"><div class="procurement-title"><strong>${esc(row.sku_name || row.item_name || row.item_code)}</strong><span class="urgency ${esc(row.urgency)}">${esc(row.urgency_label)}</span></div>
              <div class="procurement-spec">${esc(row.required_specs || row.item_code)} · ${esc(row.item_code)}</div>
              <div class="procurement-qty"><span>申请 ${esc(formatNumber(row.qty ?? remaining))}</span><span>已订 ${esc(formatNumber(row.ordered_qty || 0))}</span><strong>待采 ${esc(formatNumber(remaining))} ${esc(row.uom || "")}</strong></div>
              <div class="procurement-meta"><span>${esc(requestText)}</span><span>需求 ${esc(String(row.schedule_date || "待确认").slice(0, 10))}</span><span>${esc(row.warehouse || "未指定仓库")}</span></div>
              <div class="stock-row">${procurementInventory(row)}</div>
              <div class="supplier-hint">建议供应商：${esc(suppliersText)}</div>
            </div></article>`;
        }).join("");
        const prep = state.procurementPreparation;
        $("operationsBody").innerHTML = `
          <div class="panel-toolbar"><strong>待采购${state.procurement.refreshing ? " · 正在同步" : ""}</strong><span><button id="refreshProcurement">刷新</button></span></div>
          <div class="procurement-summary"><span><strong>${esc(summary.row_count || rows.length)}</strong>需求行</span><span><strong>${esc(summary.urgent_rows || 0)}</strong>紧急</span><span><strong>${esc(summary.shortage_rows || 0)}</strong>库存不足</span></div>
          <div class="procurement-filters">
            <select id="procurementScope"><option value="project" ${filters.scope === "project" ? "selected" : ""}>当前项目</option><option value="all" ${filters.scope === "all" ? "selected" : ""}>全部项目</option></select>
            <select id="procurementUrgency"><option value="">全部紧急度</option>${options(["overdue","urgent","soon","normal","unknown"], filters.urgency, urgencyLabels)}</select>
            <select id="procurementFamily"><option value="">全部物料族</option>${options(families, filters.family)}</select>
            <select id="procurementSupplier"><option value="">全部供应商</option>${options(suppliers, filters.supplier)}</select>
            <input id="procurementBefore" type="date" value="${esc(filters.before)}" title="最晚需求日期">
            <div class="view-switch"><button data-procurement-view="rows" class="${filters.view === "rows" ? "active" : ""}">逐行</button><button data-procurement-view="aggregate" class="${filters.view === "aggregate" ? "active" : ""}">合并</button></div>
          </div>
          ${state.procurement.inventory_error ? `<p class="section-note warning-note">部分库存读取失败：${esc(state.procurement.inventory_error)}</p>` : ""}
          ${cards || `<div class="empty-state">当前筛选条件下没有待采购需求。</div>`}
          ${prep ? procurementPreparationHtml(prep) : ""}
          <div class="procurement-actions"><span>已选择 <strong id="procurementSelectedCount">${state.procurementSelected.size}</strong> 行</span><div><button id="prepareRfq">准备询价</button><button id="prepareDirect" class="primary">准备直接采购</button></div></div>`;
        $("refreshProcurement")?.addEventListener("click", () => loadPendingProcurement({preserve:true}));
        $("procurementScope").onchange = event => { filters.scope = event.target.value; loadPendingProcurement(); };
        $("procurementUrgency").onchange = event => { filters.urgency = event.target.value; renderPendingProcurement(); };
        $("procurementFamily").onchange = event => { filters.family = event.target.value; renderPendingProcurement(); };
        $("procurementSupplier").onchange = event => { filters.supplier = event.target.value; renderPendingProcurement(); };
        $("procurementBefore").onchange = event => { filters.before = event.target.value; renderPendingProcurement(); };
        document.querySelectorAll("[data-procurement-view]").forEach(button => button.onclick = () => { filters.view = button.dataset.procurementView; renderPendingProcurement(); });
        document.querySelectorAll("[data-procurement-keys]").forEach(input => input.onchange = () => {
          input.dataset.procurementKeys.split("|").filter(Boolean).forEach(key => input.checked ? state.procurementSelected.add(key) : state.procurementSelected.delete(key));
          state.procurementPreparation = null;
          renderPendingProcurement();
        });
        $("prepareRfq")?.addEventListener("click", () => prepareProcurementSelection("rfq"));
        $("prepareDirect")?.addEventListener("click", () => prepareProcurementSelection("direct"));
        $("createRfqDraft")?.addEventListener("click", createRfqDraft);
      }

      function prepareProcurementSelection(mode) {
        const rows = (state.procurement?.rows || []).filter(row => state.procurementSelected.has(procurementRowKey(row)));
        if (!rows.length) { window.alert("请先选择至少一条待采购需求。"); return; }
        state.procurementPreparation = {mode, rows, itemCount:new Set(rows.map(row => row.item_code)).size};
        renderPendingProcurement();
      }

      function procurementPreparationHtml(prep) {
        if (prep.mode !== "rfq") return `<div class="procurement-preparation"><strong>直接采购准备</strong><span>已选择 ${prep.rows.length} 条需求、${prep.itemCount} 种物料。采购订单将在下一阶段接通；当前尚未写入 ERPNext。</span></div>`;
        const suppliers = state.procurement?.available_suppliers || [];
        const earliest = prep.rows.map(row => String(row.schedule_date || "").slice(0,10)).filter(Boolean).sort()[0] || "";
        return `<div class="procurement-preparation rfq-form"><strong>创建询价单</strong><span>已选择 ${prep.rows.length} 条需求、${prep.itemCount} 种物料。请选择真实供应商，创建后仍是 ERPNext 草稿。</span>
          <div class="supplier-options">${suppliers.map(supplier => `<label><input type="checkbox" data-rfq-supplier="${esc(supplier.supplier_code)}"><span><b>${esc(supplier.supplier_name)}</b><small>${esc(supplier.primary_category || supplier.supplier_group || "")}</small></span></label>`).join("") || `<span>没有可用供应商，请先完善供应商主数据。</span>`}</div>
          <label class="form-field"><span>期望回复/到货日期</span><input id="rfqScheduleDate" type="date" value="${esc(earliest)}"></label>
          <label class="form-field"><span>询价说明</span><textarea id="rfqMessage" rows="3">请按清单报价，并说明含税单价、交货期、付款条件和报价有效期。</textarea></label>
          <button id="createRfqDraft" class="primary" ${suppliers.length ? "" : "disabled"}>创建询价草稿</button>
        </div>`;
      }

      async function createRfqDraft() {
        const prep = state.procurementPreparation;
        if (!prep || prep.mode !== "rfq") return;
        const supplierCodes = [...document.querySelectorAll("[data-rfq-supplier]:checked")].map(input => input.dataset.rfqSupplier);
        if (!supplierCodes.length) { window.alert("请至少选择一家供应商。"); return; }
        if (!window.confirm(`确认创建询价草稿？\n需求行：${prep.rows.length}\n供应商：${supplierCodes.length} 家`)) return;
        const button = $("createRfqDraft");
        button.disabled = true;
        button.textContent = "正在创建...";
        try {
          const result = await api("/api/procurement/rfq", {
            method:"POST",
            body:JSON.stringify({
              user:state.user.user_email,
              project_code:state.project.project_code,
              conversation_id:state.conversationId,
              request_id:crypto.randomUUID(),
              selected_rows:prep.rows.map(procurementRowKey),
              supplier_codes:supplierCodes,
              schedule_date:$("rfqScheduleDate")?.value || "",
              message_for_supplier:$("rfqMessage")?.value || "",
            }),
          });
          state.procurementPreparation = null;
          await Promise.all([loadPendingProcurement({preserve:true}), loadDocuments({preserve:true})]);
          await openDocument(result.doctype, result.name);
        } catch (error) {
          window.alert(error.message);
          button.disabled = false;
          button.textContent = "创建询价草稿";
        }
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
        const comment = action.includes("驳回") ? window.prompt("请填写驳回原因。该原因会写入 ERPNext 单据记录：") : "";
        if (action.includes("驳回") && !String(comment || "").trim()) return;
        if (!window.confirm(`确认对 ${name} 执行“${action}”？`)) return;
        try {
          await api("/api/workflow/action", {
            method:"POST",
            body:JSON.stringify({user:state.user.user_email, doctype, name, action, comment:String(comment || "").trim(), project_code:state.project.project_code, conversation_id:state.conversationId, request_id:crypto.randomUUID()}),
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
          if (mode === "progress") return ["Request for Quotation","Supplier Quotation","Purchase Order","Purchase Receipt"].includes(group.doctype) || (group.doctype === "Material Request" && Number(document.docstatus) === 1);
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
        return ({"材料申请":"Material Request","询价单":"Request for Quotation","供应商报价":"Supplier Quotation","采购订单":"Purchase Order","采购收货":"Purchase Receipt","库存移动":"Stock Entry","采购发票":"Purchase Invoice","付款单":"Payment Entry","任务":"Task","待办":"ToDo"})[label] || "";
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
        state.quotationContext = null;
        state.documentDetail = {loading:true, doctype, name};
        showDrawer();
        renderDocumentDrawer();
        try {
          state.documentDetail = await api(`/api/document?user=${encodeURIComponent(state.user.user_email)}&doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(name)}`);
        } catch (error) {
          state.documentDetail = {error:error.message, doctype, name};
        }
        if (state.documentDetail?.doctype === "Request for Quotation" && Number(state.documentDetail.document?.docstatus) === 1) {
          try {
            state.quotationContext = await api(`/api/procurement/quotations?user=${encodeURIComponent(state.user.user_email)}&request_for_quotation=${encodeURIComponent(name)}`);
          } catch (error) {
            state.quotationContext = {error:error.message, quotations:[]};
          }
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
        const workflowHistory = Array.isArray(process.history) ? process.history : [];
        const workflowComments = Array.isArray(process.comments) ? process.comments : [];
        $("drawerBody").innerHTML = `
          <div class="process-card"><div><strong>流程状态：${esc(process.state || status)}</strong><span>${esc(process.description || "暂无流程信息")}</span><span>${esc(process.assignees?.length ? `当前处理人：${process.assignees.join("、")}` : process.notification || "")}</span></div><div>${(process.available_actions || []).map(action => `<button class="workflow-action" data-action="${esc(action)}">${esc(action)}</button>`).join("")}${process.can_submit ? `<button id="submitDocumentDraft">提交单据</button>` : ""}</div></div>
          <div class="field-grid">${fields.map(key => `<div class="field"><span>${esc(FIELD_LABELS[key] || key)}</span><strong>${esc(formatField(key, doc[key]))}</strong></div>`).join("")}</div>
          ${workflowHistory.length ? `<h3 class="drawer-section-title">审批记录</h3><div class="workflow-history">${workflowHistory.map(row => `<div class="workflow-history-row"><span class="workflow-dot"></span><div><strong>${esc(row.workflow_state || row.status || "流程动作")}</strong><span>${esc(row.completed_by || row.user || "系统")} · ${esc(row.completed_by_role || "")}</span><small>${esc(dateShort(row.modified || row.creation))}</small></div></div>`).join("")}</div>` : ""}
          ${workflowComments.length ? `<h3 class="drawer-section-title">审批备注</h3><div class="workflow-comments">${workflowComments.map(row => `<div class="workflow-comment"><strong>${esc(row.comment_by || row.comment_email || row.owner || "系统")}</strong><p>${esc(row.content || "")}</p><small>${esc(dateShort(row.creation))}</small></div>`).join("")}</div>` : ""}
          ${childRows.length ? `<h3 class="drawer-section-title">明细行 · ${childRows.length}</h3>${detail.doctype === "Material Request" ? `<p class="section-note">材料申请中的价格是测试参考价，用于预计需求金额；供应商报价和采购订单价格才是正式采购价格。</p>` : ""}<div class="items-wrap"><table class="items-table"><thead><tr>${columns.map(key => `<th>${esc(itemColumnLabel(detail.doctype, key))}</th>`).join("")}</tr></thead><tbody>${childRows.map(row => `<tr>${columns.map(key => `<td>${esc(formatItemField(detail.doctype, key, row[key], row))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : ""}
          ${purchaseReceiptPreparationHtml(detail)}
          ${purchaseReturnPreparationHtml(detail)}
          ${rfqQuotationHtml(detail)}
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
          const comment = action.includes("驳回") ? window.prompt("请填写驳回原因。该原因会写入 ERPNext 单据记录：") : "";
          if (action.includes("驳回") && !String(comment || "").trim()) return;
          if (!window.confirm(`确认对 ${detail.name} 执行“${action}”？`)) return;
          button.disabled = true;
          button.textContent = "处理中...";
          try {
            state.documentDetail = await api("/api/workflow/action", {
              method:"POST",
              body:JSON.stringify({user:state.user.user_email, doctype:detail.doctype, name:detail.name, action, comment:String(comment || "").trim(), project_code:state.project?.project_code, conversation_id:state.conversationId, request_id:crypto.randomUUID()}),
            });
            renderDocumentDrawer();
            await Promise.all([loadInbox({preserve:true}), loadDocuments({preserve:true})]);
          } catch (error) {
            window.alert(error.message);
            await openDocument(detail.doctype, detail.name);
          }
        }));
        $("createSupplierQuotation")?.addEventListener("click", createSupplierQuotation);
        $("compareSupplierQuotations")?.addEventListener("click", compareSupplierQuotations);
        document.querySelectorAll("[data-open-quotation]").forEach(button => button.onclick = () => openDocument("Supplier Quotation", button.dataset.openQuotation));
        document.querySelectorAll("[data-create-purchase-order]").forEach(button => button.onclick = () => createPurchaseOrderFromQuotation(button.dataset.createPurchaseOrder));
        document.querySelectorAll("[data-open-purchase-order]").forEach(button => button.onclick = () => openDocument("Purchase Order", button.dataset.openPurchaseOrder));
        $("createPurchaseReceipt")?.addEventListener("click", createPurchaseReceiptFromOrder);
        $("recordReceiptDiscrepancy")?.addEventListener("click", recordReceiptDiscrepancy);
        $("createPurchaseReturn")?.addEventListener("click", createPurchaseReturn);
      }

      function purchaseReceiptPreparationHtml(detail) {
        if (detail.doctype !== "Purchase Order" || Number(detail.document?.docstatus) !== 1) return "";
        const rows = (detail.document.items || [])
          .map(row => ({...row, remaining_qty:Math.max(Number(row.qty || 0) - Number(row.received_qty || 0), 0)}))
          .filter(row => row.remaining_qty > 0);
        if (!rows.length) return `<section class="receipt-section"><h3 class="drawer-section-title">采购收货</h3><div class="message success">这张采购订单已全部收货。</div></section>`;
        return `<section class="receipt-section"><h3 class="drawer-section-title">办理收货</h3><p class="section-note">按实际到货数量填写。本次只创建收货草稿，复核并提交后才会增加 ERPNext 库存。</p><div class="receipt-grid">${rows.map(row => `<div class="receipt-row"><span><strong>${esc(row.item_name || row.item_code)}</strong><small>订单 ${esc(formatNumber(row.qty))} ${esc(row.uom || "")} · 已收 ${esc(formatNumber(row.received_qty || 0))} · 待收 ${esc(formatNumber(row.remaining_qty))}</small></span><label>本次<input type="number" min="0" max="${esc(row.remaining_qty)}" step="0.001" value="${esc(row.remaining_qty)}" data-receipt-qty data-po-item="${esc(row.name)}" data-item-code="${esc(row.item_code)}" data-warehouse="${esc(row.warehouse || "")}"></label><label>入库仓库<input type="text" value="${esc(row.warehouse || "")}" data-receipt-warehouse="${esc(row.name)}"></label></div>`).join("")}</div><button id="createPurchaseReceipt" class="primary">创建采购收货草稿</button></section>`;
      }

      async function createPurchaseReceiptFromOrder() {
        const rows = [...document.querySelectorAll("[data-receipt-qty]")].map(input => ({
          purchase_order_item:input.dataset.poItem,
          item_code:input.dataset.itemCode,
          qty:Number(input.value || 0),
          warehouse:document.querySelector(`[data-receipt-warehouse="${CSS.escape(input.dataset.poItem)}"]`)?.value || input.dataset.warehouse,
        })).filter(row => row.qty > 0);
        if (!rows.length) { window.alert("请至少填写一条大于 0 的本次收货数量。"); return; }
        if (!window.confirm(`确认按当前 ${rows.length} 条明细创建采购收货草稿？\n\n草稿提交后才会正式增加库存。`)) return;
        const button = $("createPurchaseReceipt");
        button.disabled = true;
        button.textContent = "正在创建...";
        try {
          const result = await api("/api/procurement/purchase-receipt", {method:"POST", body:JSON.stringify({
            user:state.user.user_email,
            project_code:state.project.project_code,
            conversation_id:state.conversationId,
            request_id:crypto.randomUUID(),
            purchase_order:state.documentDetail.name,
            selected_items:rows,
          })});
          await loadDocuments({preserve:true});
          await openDocument("Purchase Receipt", result.name);
        } catch (error) {
          window.alert(error.message);
          button.disabled = false;
          button.textContent = "创建采购收货草稿";
        }
      }

      function purchaseReturnPreparationHtml(detail) {
        const doc = detail.document || {};
        if (detail.doctype !== "Purchase Receipt" || Number(doc.docstatus) !== 1 || Number(doc.is_return) === 1) return "";
        const rows = (doc.items || [])
          .map(row => ({...row, returnable_qty:Math.max(Number(row.qty || 0) - Number(row.returned_qty || 0), 0)}))
          .filter(row => row.returnable_qty > 0);
        if (!rows.length) return `<section class="receipt-section"><h3 class="drawer-section-title">到货差异与退货</h3><div class="message success">这张收货单已无可退数量。</div></section>`;
        return `<section class="receipt-section"><h3 class="drawer-section-title">到货差异与退货</h3><p class="section-note">先记录规格、质量或数量差异，再按实际退货数量创建退货草稿。提交退货单后库存才会回减。</p><div class="return-form"><label class="form-field"><span>差异类型</span><select id="receiptDiscrepancyType"><option value="spec_mismatch">规格不符</option><option value="quality_issue">质量问题</option><option value="quantity_mismatch">数量差异</option><option value="damaged">运输损坏</option></select></label><label class="form-field"><span>严重程度</span><select id="receiptDiscrepancySeverity"><option>Medium</option><option>High</option><option>Low</option></select></label><label class="form-field return-reason"><span>问题说明 / 退货原因</span><textarea id="receiptReturnReason" rows="2" placeholder="例如：到货水泥强度等级与采购订单不一致，整批退回"></textarea></label></div><div class="receipt-grid">${rows.map(row => `<div class="receipt-row"><span><strong>${esc(row.item_name || row.item_code)}</strong><small>已收 ${esc(formatNumber(row.qty))} ${esc(row.uom || "")} · 已退 ${esc(formatNumber(row.returned_qty || 0))} · 可退 ${esc(formatNumber(row.returnable_qty))}</small></span><label>本次退货<input type="number" min="0" max="${esc(row.returnable_qty)}" step="0.001" value="${esc(row.returnable_qty)}" data-return-qty data-receipt-item="${esc(row.name)}" data-item-code="${esc(row.item_code)}" data-warehouse="${esc(row.warehouse || "")}"></label><span><small>${esc(row.warehouse || "")}</small></span></div>`).join("")}</div><div class="return-actions"><button id="recordReceiptDiscrepancy">只记录差异</button><button id="createPurchaseReturn" class="danger">创建退货草稿</button></div></section>`;
      }

      function receiptReturnRows() {
        return [...document.querySelectorAll("[data-return-qty]")].map(input => ({
          purchase_receipt_item:input.dataset.receiptItem,
          item_code:input.dataset.itemCode,
          qty:Number(input.value || 0),
          warehouse:input.dataset.warehouse,
        })).filter(row => row.qty > 0);
      }

      async function recordReceiptDiscrepancy() {
        const description = String($("receiptReturnReason")?.value || "").trim();
        if (!description) { window.alert("请填写问题说明。"); return; }
        const assigned = state.employees.find(employee => /材料设备主管/.test(employee.position || ""))?.user_email || state.user.user_email;
        if (!window.confirm("确认把这条到货差异写入 ERPNext 评论并创建跟进待办？")) return;
        try {
          await api("/api/procurement/discrepancy", {method:"POST", body:JSON.stringify({
            user:state.user.user_email, project_code:state.project.project_code, conversation_id:state.conversationId,
            request_id:crypto.randomUUID(), purchase_receipt:state.documentDetail.name, description,
            discrepancy_type:$("receiptDiscrepancyType")?.value || "spec_mismatch",
            severity:$("receiptDiscrepancySeverity")?.value || "Medium", assigned_to:assigned, items:receiptReturnRows(),
          })});
          window.alert("到货差异已记录，并已创建跟进待办。");
          await openDocument("Purchase Receipt", state.documentDetail.name);
        } catch (error) { window.alert(error.message); }
      }

      async function createPurchaseReturn() {
        const reason = String($("receiptReturnReason")?.value || "").trim();
        const items = receiptReturnRows();
        if (!reason) { window.alert("请填写退货原因。"); return; }
        if (!items.length) { window.alert("请至少填写一条大于 0 的退货数量。"); return; }
        if (!window.confirm(`确认创建 ${items.length} 条明细的采购退货草稿？\n\n草稿提交后才会回减库存。`)) return;
        try {
          const result = await api("/api/procurement/purchase-return", {method:"POST", body:JSON.stringify({
            user:state.user.user_email, project_code:state.project.project_code, conversation_id:state.conversationId,
            request_id:crypto.randomUUID(), purchase_receipt:state.documentDetail.name, reason, items,
          })});
          await loadDocuments({preserve:true});
          await openDocument("Purchase Receipt", result.name);
        } catch (error) { window.alert(error.message); }
      }

      function rfqQuotationHtml(detail) {
        if (detail.doctype !== "Request for Quotation" || Number(detail.document?.docstatus) !== 1) return "";
        const doc = detail.document || {};
        const suppliers = (doc.suppliers || []).map(row => row.supplier || row.supplier_name).filter(Boolean);
        const rows = Array.isArray(doc.items) ? doc.items : [];
        const context = state.quotationContext || {quotations:[]};
        const quotations = context.quotations || [];
        const comparison = context.comparison;
        return `<section class="quotation-section">
          <h3 class="drawer-section-title">供应商报价</h3>
          <p class="section-note">询价单已提交。逐家录入供应商的真实报价，提交至少两张报价后可以比较；系统不会自动选中供应商。</p>
          ${context.error ? `<div class="message error">${esc(context.error)}</div>` : ""}
          <div class="quotation-list">${quotations.length ? quotations.map(quote => `<div class="quotation-list-row"><button data-open-quotation="${esc(quote.name)}"><span><strong>${esc(quote.name)}</strong><small>${esc(quote.supplier || "-")} · ${Number(quote.docstatus) === 1 ? "已提交" : "草稿"}${quote.purchase_orders?.length ? ` · 已生成 ${quote.purchase_orders.length} 张订单` : ""}</small></span><b>${esc(formatNumber(quote.grand_total || quote.net_total || 0))} ${esc(quote.currency || "CNY")}</b></button>${Number(quote.docstatus) === 1 && Number(quote.remaining_qty || 0) > 0 ? `<button class="quotation-award" data-create-purchase-order="${esc(quote.name)}">据此下单</button>` : quote.purchase_orders?.length ? `<button class="quotation-award" data-open-purchase-order="${esc(quote.purchase_orders[0])}">查看订单</button>` : ""}</div>`).join("") : `<div class="empty-state">尚未录入供应商报价。</div>`}</div>
          <div class="quotation-entry">
            <div class="quotation-entry-head"><strong>录入一份报价</strong><select id="quotationSupplier"><option value="">选择供应商</option>${suppliers.map(supplier => `<option value="${esc(supplier)}">${esc(supplier)}</option>`).join("")}</select></div>
            <div class="quotation-rate-grid">${rows.map((row,index) => `<label><span>${esc(row.item_name || row.item_code)} · ${esc(formatNumber(row.qty))} ${esc(row.uom || "")}</span><input type="number" min="0.000001" step="0.01" placeholder="含税单价" data-rfq-rate="${index}" data-rfq-item="${esc(row.name || row.item_code)}"></label>`).join("")}</div>
            <div class="quotation-form-grid"><label class="form-field"><span>报价有效期</span><input id="quotationValidTill" type="date"></label><label class="form-field"><span>交付与付款条款</span><textarea id="quotationTerms" rows="2" placeholder="例如：7月20日前到货；月结30天；含税含运费"></textarea></label></div>
            <button id="createSupplierQuotation" class="primary">创建报价草稿</button>
          </div>
          ${quotations.length >= 2 ? `<button id="compareSupplierQuotations">比较已提交报价</button>` : ""}
          ${comparison ? quotationComparisonHtml(comparison) : ""}
        </section>`;
      }

      async function createSupplierQuotation() {
        const supplier = $("quotationSupplier")?.value || "";
        if (!supplier) { window.alert("请选择供应商。"); return; }
        const offers = [...document.querySelectorAll("[data-rfq-rate]")].map(input => ({request_for_quotation_item:input.dataset.rfqItem, rate:Number(input.value || 0)}));
        if (offers.some(offer => offer.rate <= 0)) { window.alert("请为每条物料填写大于 0 的单价。"); return; }
        if (!window.confirm(`确认录入 ${supplier} 的报价草稿？`)) return;
        const button = $("createSupplierQuotation");
        button.disabled = true;
        button.textContent = "正在创建...";
        try {
          await api("/api/procurement/quotation", {method:"POST", body:JSON.stringify({
            user:state.user.user_email,
            project_code:state.project.project_code,
            conversation_id:state.conversationId,
            request_id:crypto.randomUUID(),
            request_for_quotation:state.documentDetail.name,
            supplier_code:supplier,
            offers,
            valid_till:$("quotationValidTill")?.value || "",
            terms:$("quotationTerms")?.value || "",
          })});
          await Promise.all([loadDocuments({preserve:true}), openDocument("Request for Quotation", state.documentDetail.name)]);
        } catch (error) {
          window.alert(error.message);
          button.disabled = false;
          button.textContent = "创建报价草稿";
        }
      }

      async function compareSupplierQuotations() {
        const submitted = (state.quotationContext?.quotations || []).filter(row => Number(row.docstatus) === 1).map(row => row.name);
        if (submitted.length < 2) { window.alert("请先提交至少两张供应商报价。"); return; }
        try {
          const comparison = await api("/api/procurement/compare", {method:"POST", body:JSON.stringify({user:state.user.user_email, supplier_quotations:submitted})});
          state.quotationContext.comparison = comparison;
          renderDocumentDrawer();
        } catch (error) {
          window.alert(error.message);
        }
      }

      async function createPurchaseOrderFromQuotation(supplierQuotation) {
        const quote = (state.quotationContext?.quotations || []).find(row => row.name === supplierQuotation) || {};
        const amount = `${formatNumber(quote.grand_total || quote.net_total || 0)} ${quote.currency || "CNY"}`;
        if (!window.confirm(`确认选择 ${quote.supplier || supplierQuotation} 的报价 ${amount}，并创建采购订单草稿？\n\n这一步不会提交采购订单，创建后仍需复核并提交。`)) return;
        try {
          const result = await api("/api/procurement/purchase-order", {method:"POST", body:JSON.stringify({
            user:state.user.user_email,
            project_code:state.project.project_code,
            conversation_id:state.conversationId,
            request_id:crypto.randomUUID(),
            supplier_quotation:supplierQuotation,
          })});
          await loadDocuments({preserve:true});
          await openDocument("Purchase Order", result.name);
        } catch (error) {
          window.alert(error.message);
        }
      }

      function quotationComparisonHtml(comparison) {
        const recommendation = comparison.recommendation || {};
        return `<div class="quotation-comparison"><strong>比价结果</strong><p>当前最低可比总价：${esc(recommendation.supplier || recommendation.supplier_quotation || "-")} · ${esc(formatNumber(recommendation.total_amount || 0))} ${esc(recommendation.currency || "")}</p><p>该结果只按当前报价金额排序。交期、质量、付款条款仍需采购人员复核后决定。</p>${(comparison.total_ranking || []).map((row,index) => `<div><span>${index + 1}. ${esc(row.supplier || row.name)}</span><b>${esc(formatNumber(row.total_amount))} ${esc(row.currency || "")}</b></div>`).join("")}</div>`;
      }

      function formatField(key, value) {
        if (key === "docstatus") return Number(value) === 1 ? "已提交" : Number(value) === 2 ? "已取消" : "草稿";
        if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
        if (typeof value === "object") return pretty(value);
        return String(value ?? "-");
      }

      function itemColumnLabel(doctype, key) {
        if (doctype === "Material Request" && key === "rate") return "预计单价";
        if (doctype === "Material Request" && key === "amount") return "预计金额";
        return ITEM_LABELS[key] || key;
      }

      function formatItemField(doctype, key, value, row) {
        if (doctype === "Material Request" && key === "rate" && Number(value || 0) <= 0) return "暂无参考价";
        if (doctype === "Material Request" && key === "amount" && Number(value || 0) <= 0) {
          const estimated = Number(row.rate || 0) * Number(row.qty || 0);
          return estimated > 0 ? formatNumber(estimated) : "—";
        }
        return formatField(key, value);
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
      document.querySelectorAll(".operations-tab").forEach(button => button.onclick = () => {
        state.panel = button.dataset.panel;
        if (state.panel === "pending" && !state.procurement) loadPendingProcurement();
        else renderOperations();
      });
      $("input").addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          if (!$("previewBtn").disabled) run(false);
        }
      });
      document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
      boot();
