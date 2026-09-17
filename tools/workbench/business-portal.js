(() => {
  const initialView = new URLSearchParams(location.search).get("view") || "home";
  const state = { bootstrap: null, dashboard: null, viewData: null, view: initialView, requestedView: initialView, loading: false, loadSequence: 0, viewCache: new Map(), lastFocused: null, filters: { query: "", status_scope: "active", date_from: "", date_to: "", inventory_item: "", inventory_warehouse: "" } };
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[c]));
  const api = async path => { const response = await fetch(path, { headers: { Accept: "application/json" } }); const payload = await response.json(); if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`); return payload; };
  const post = async (path, body) => { const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); const payload = await response.json(); if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`); return payload; };
  const count = value => Number(value || 0).toLocaleString("zh-CN");
  const statusLabel = value => ({ Draft: "草稿", Ordered: "已下单", "To Receive": "待收货", Completed: "已完成", Cancelled: "已取消", Submitted: "已提交", "To Bill": "待开票", Return: "退货", Open: "进行中", Closed: "已关闭", "Nexterp材料草稿": "申请草稿", "Nexterp主管审批": "待主管审批", "Nexterp项目审批": "待项目经理审批", "Nexterp已批准": "已批准" }[String(value || "")] || value || "已读取");
  const todoRank = row => {
    const urgency = String(row.urgency_label || row.urgency || "");
    if (/逾期|紧急/.test(urgency)) return 0;
    if (/高/.test(urgency)) return 1;
    return 2;
  };
  const dueValue = row => String(row.schedule_date || row.transaction_date || row.posting_date || "9999-12-31");
  const setToast = message => { $("toast").textContent = message; $("toast").classList.add("show"); setTimeout(() => $("toast").classList.remove("show"), 2600); };

  function applyContext() {
    const context = state.bootstrap?.context || {};
    const employee = context.employee || {};
    $("identityLabel").textContent = `${employee.employee_name || "当前员工"} · ${employee.position || "业务用户"}`;
    $("projectLabel").textContent = context.project?.project_short_name || context.project_code || "当前项目";
    const accountLabel = $("accountLabel");
    if (accountLabel) accountLabel.textContent = context.account?.label ? `账套：${context.account.label}` : "账套：未连接";
    const sourceSelect = $("classificationSource");
    const sources = state.bootstrap?.classification_sources || [];
    if (sourceSelect && sources.length) {
      sourceSelect.innerHTML = sources.map(source => `<option value="${esc(source.code)}" ${source.available === false ? "disabled" : ""}>${esc(source.label)}</option>`).join("");
      sourceSelect.value = context.classification_source || "original";
      sourceSelect.title = context.classification?.note || "选择物料分类版本";
    }
    const source = context.classification_source || "original";
    const catalogQuery = `?classification_source=${encodeURIComponent(source)}`;
    [$("catalogActionLink"), $("catalogSideLink")].filter(Boolean).forEach(link => { link.href = `/material-marketplace${catalogQuery}`; });
    const workbenchLink = $("classificationWorkbenchLink");
    if (workbenchLink) workbenchLink.href = `/tariff-taxonomy-browser?catalog=gpc&classification_source=${encodeURIComponent(source)}`;
    $("footerStatus").textContent = state.bootstrap?.features?.ai === false ? "业务门户已连接 · AI 未启用" : "已连接";
    const controls = $("devContextControls");
    if (state.bootstrap?.features?.developer_identity_switcher) {
      controls.hidden = false;
      const users = state.bootstrap.employees || [];
      const projects = state.bootstrap.projects || [];
      $("businessUser").innerHTML = users.map(row => `<option value="${esc(row.user_email)}">${esc(row.employee_name)} · ${esc(row.position)}</option>`).join("");
      $("businessProject").innerHTML = projects.map(row => `<option value="${esc(row.project_code)}">${esc(row.project_short_name || row.project_code)}</option>`).join("");
      $("businessUser").value = context.user || "";
      $("businessProject").value = context.project_code || "";
    }
    renderNav();
  }

  function renderNav() {
    const modules = state.bootstrap?.modules || [];
    const roles = new Set(["all", state.bootstrap?.context?.employee?.position || ""]);
    document.querySelectorAll(".nav-link[data-module]").forEach(link => {
      const module = modules.find(row => row.code === link.dataset.module);
      const allowed = !module || (module.roles || []).some(role => roles.has(role));
      link.hidden = !allowed;
      if (!allowed && link.dataset.view === state.view) state.view = "home";
    });
  }

  async function switchBusinessContext() {
    const response = await fetch("/api/business/context", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: $("businessUser").value, project_code: $("businessProject").value }),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) throw new Error(payload.error || "无法切换沙盘身份");
    const requestedView = state.requestedView || new URLSearchParams(location.search).get("view") || "home";
    await load();
    const requestedLink = document.querySelector(`.nav-link[data-view="${CSS.escape(requestedView)}"]`);
    if (requestedView !== "home" && requestedLink && !requestedLink.hidden) {
      state.view = requestedView;
      await loadView();
    }
  }

  async function switchClassificationSource() {
    const source = $("classificationSource")?.value || "original";
    const response = await fetch("/api/business/classification", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ classification_source: source }),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) throw new Error(payload.error || "无法切换分类版本");
    await load();
  }

  function sectionForView() {
    const map = {
      home: ["物资业务概览", "从物料申请到收货和项目用料，所有状态都以 ERPNext 回读为准。", "待处理事项"],
      requests: ["我的材料申请", "查看草稿、审批状态和被退回的申请。", "申请单据"],
      approvals: ["审批中心", "仅显示当前身份在 ERPNext 中可执行的审批动作。", "待我处理"],
      buying: ["采购中心", "把已批准需求转换为询价、报价和采购订单。", "待采购需求"],
      receiving: ["收货中心", "按采购订单记录到货、差异和退货。", "待收货单据"],
      inventory: ["库存中心", "实时查看仓库余额和库存流水。", "库存状态"],
      project: ["项目用料", "沿项目追踪申请、采购、到货和领退料。", "项目物资"],
      documents: ["单据中心", "按业务模块查看 ERPNext 正式单据和来源链。", "最近单据"],
    };
    return map[state.view] || map.home;
  }

  function renderMetrics() {
    const metrics = state.dashboard?.metrics || {};
    $("metricApprovals").textContent = count(metrics.approvals);
    $("metricPending").textContent = count(metrics.pending_procurement);
    $("metricReceiving").textContent = count(metrics.receiving);
    $("metricCatalog").textContent = count(metrics.catalog);
    $("metricCatalogNote").textContent = metrics.catalog_label ? `${metrics.catalog_label} · ${metrics.catalog_note || ""}` : "已发布且可申请";
    $("metricCatalogNote").title = metrics.catalog_note || "";
  }

  function rowsForView() {
    const sections = state.dashboard?.sections || {};
    if (state.view === "approvals") return (sections.approvals?.items || []).map(row => ({ title: row.title || row.reference_name, detail: `${row.reference_doctype} · ${row.workflow_state || "待处理"}`, status: "待处理", actions: row.actions || [], document: row, detailDoctype: row.reference_doctype, detailName: row.reference_name }));
    if (state.view === "buying") {
      const pendingRows = (sections.pending_procurement?.rows || []).map(row => ({ title: row.sku_name || row.item_code, detail: `${row.remaining_qty || 0} ${row.uom || ""} · ${row.schedule_date || "未定日期"}`, status: row.urgency_label || "待采购", warn: row.inventory_coverage === "shortage", actions: [{ label: "创建询价草稿", kind: "rfq.create", payload: { selected_rows: [`${row.material_request || ""}:${row.material_request_item || row.item_code || ""}`], supplier_codes: (row.supplier_suggestions || []).slice(0, 2).map(supplier => supplier.supplier_code).filter(Boolean), schedule_date: row.schedule_date || "" } }], detailDoctype: row.reference_doctype || "Material Request", detailName: row.reference_name || row.material_request }));
      const buyingDocs = (sections.documents?.modules || []).filter(module => module.code === "buying").flatMap(module => module.groups || []).flatMap(group => (group.documents || []).map(row => ({ title: row.supplier || row.name, detail: `${group.label || group.doctype} · ${row.name}`, status: statusLabel(row.status), detailDoctype: group.doctype, detailName: row.name })));
      return [...pendingRows, ...buyingDocs].slice(0, 30);
    }
    if (state.view === "requests") return (sections.documents?.modules?.flatMap(module => module.groups || []).find(group => group.doctype === "Material Request")?.documents || []).map(row => ({ title: row.title || row.name, detail: `${row.name} · ${row.workflow_state || statusLabel(row.status)}`, status: statusLabel(row.workflow_state || row.status), actions: Number(row.docstatus) === 0 && (!row.workflow_state || row.workflow_state === "Nexterp材料草稿") ? [{ label: "提交申请", kind: "submit", payload: { doctype: "Material Request", name: row.name } }] : [], detailDoctype: "Material Request", detailName: row.name }));
    if (state.view === "receiving") return (sections.receiving?.rows || []).map(row => ({ title: row.supplier || row.name, detail: `${row.name} · 剩余 ${row.remaining_receipt_percent == null ? "待核验" : `${row.remaining_receipt_percent}%`} `, status: "待收货", actions: [{ label: "创建收货草稿", kind: "purchase_receipt.create", payload: { purchase_order: row.name, selected_items: [] } }], detailDoctype: "Purchase Order", detailName: row.name }));
    if (state.view === "documents") return (sections.documents?.modules?.flatMap(module => module.groups || []).flatMap(group => (group.documents || []).map(row => ({ title: row.title || row.supplier || row.name, detail: `${group.label || group.doctype} · ${row.name}`, status: statusLabel(row.status), detailDoctype: group.doctype, detailName: row.name }))) || []);
    if (state.view === "inventory") return (state.viewData?.balances || []).map(row => ({ title: row.item_code, detail: `${row.warehouse || "未分配仓库"} · 实际 ${row.actual_qty ?? "—"} · 预留 ${row.reserved_qty ?? "—"} · 可用 ${row.available_qty ?? row.actual_qty ?? "—"} · 在途 ${row.projected_qty ?? "—"}`, status: "ERPNext 库存", detailDoctype: "Item", detailName: row.item_code }));
    if (state.view === "project") {
      const aggregates = state.viewData?.pending?.aggregate || sections.pending_procurement?.aggregate || [];
      const stock = state.viewData?.stock_documents?.modules?.flatMap(module => module.groups || []).flatMap(group => group.documents || []) || [];
      const projectWarehouse = state.viewData?.pending?.warehouses?.[0] || "";
      const projectRows = [
        ...aggregates.map(row => ({ title: row.sku_name || row.item_code, detail: `${row.request_count || 0} 条申请 · 剩余 ${row.total_remaining_qty || 0} ${row.uom || ""}`, status: "项目物资", actions: projectWarehouse ? [{ label: "项目领料", kind: "stock.project_issue.create", payload: { item_code: row.item_code, uom: row.uom || row.stock_uom, source_warehouse: projectWarehouse } }] : [] })),
        ...stock.slice(0, 8).map(row => ({ title: row.name, detail: `${row.stock_entry_type || row.purpose || "库存移动"} · ${row.posting_date || ""}`, status: "库存回读", detailDoctype: "Stock Entry", detailName: row.name })),
      ];
      const buying = state.viewData?.buying_documents?.modules?.flatMap(module => module.groups || []).flatMap(group => group.documents || []) || [];
      const receiving = state.viewData?.receiving?.rows || [];
      return [
        ...projectRows,
        ...buying.slice(0, 6).map(row => ({ title: row.name, detail: `采购 · ${statusLabel(row.status)}`, status: "项目采购", detailDoctype: "Purchase Order", detailName: row.name })),
        ...receiving.slice(0, 6).map(row => ({ title: row.name, detail: `到货 · 剩余 ${row.remaining_receipt_percent ?? "待核验"}%`, status: "项目收货", detailDoctype: "Purchase Order", detailName: row.name })),
      ];
    }
    const approvals = (sections.approvals?.items || []).map(row => ({ title: row.title || row.reference_name, detail: `${row.reference_doctype} · ${row.workflow_state || "待处理"}`, status: "待处理", actions: row.actions || [], document: row, detailDoctype: row.reference_doctype, detailName: row.reference_name, urgency: row.urgency_label, schedule_date: row.schedule_date }));
    const buying = (sections.pending_procurement?.rows || []).map(row => ({ title: row.sku_name || row.item_code, detail: `${row.remaining_qty || 0} ${row.uom || ""} · ${row.schedule_date || "未定日期"}`, status: row.urgency_label || "待采购", warn: row.inventory_coverage === "shortage", detailDoctype: row.reference_doctype || "Material Request", detailName: row.reference_name || row.material_request, urgency: row.urgency_label, schedule_date: row.schedule_date }));
    const receiving = (sections.receiving?.rows || []).map(row => ({ title: row.supplier || row.name, detail: `${row.name} · 剩余 ${row.remaining_receipt_percent ?? "待核验"}%`, status: "待收货", detailDoctype: "Purchase Order", detailName: row.name, schedule_date: row.schedule_date }));
    return [...approvals, ...buying, ...receiving].sort((a, b) => todoRank(a) - todoRank(b) || dueValue(a).localeCompare(dueValue(b))).slice(0, 12);
  }

  function renderContent() {
    const [title, description, section] = sectionForView();
    $("pageTitle").textContent = title; $("pageDescription").textContent = description; $("sectionTitle").textContent = section;
    document.querySelectorAll(".nav-link[data-view]").forEach(link => link.classList.toggle("active", link.dataset.view === state.view));
    const rows = rowsForView();
    $("contentState").hidden = Boolean(rows.length); $("contentStateText").textContent = rows.length ? "" : "当前没有需要处理的业务记录。"; $("retryButton").hidden = true;
    $("contentList").innerHTML = rows.slice(0, 30).map(row => {
      const canOpen = Boolean(row.detailDoctype && row.detailName);
      const detailAttrs = canOpen ? `data-detail-doctype="${esc(row.detailDoctype)}" data-detail-name="${esc(row.detailName)}"` : "";
      const businessActions = row.actions?.length ? `<div class="row-actions">${row.actions.map(action => { const data = typeof action === "string" ? { label: action, kind: "workflow", action } : action; return `<button type="button" class="row-action" data-workflow-action="${data.kind === "workflow" ? esc(data.action) : ""}" data-business-action="${data.kind !== "workflow" ? esc(data.kind) : ""}" data-business-payload="${data.kind !== "workflow" ? esc(JSON.stringify(data.payload || {})) : ""}" data-doctype="${esc(row.document?.reference_doctype)}" data-name="${esc(row.document?.reference_name)}">${esc(data.label)}</button>`; }).join("")}</div>` : "";
      const detailButton = canOpen ? `<button type="button" class="document-card-button" data-open-document data-doctype="${esc(row.detailDoctype)}" data-name="${esc(row.detailName)}">查看单据</button>` : "";
      return `<article ${detailAttrs}><div class="item-copy"><strong>${esc(row.title)}</strong><small>${esc(row.detail)}</small>${businessActions}</div><div class="item-actions"><span class="status-pill ${row.warn ? "warn" : ""}">${esc(row.status)}</span>${detailButton}</div></article>`;
    }).join("");
    document.querySelectorAll("[data-detail-doctype]").forEach(row => row.addEventListener("click", () => openDocumentDetail(row.dataset.detailDoctype, row.dataset.detailName).catch(error => setToast(error.message))));
    document.querySelectorAll("[data-open-document]").forEach(button => button.addEventListener("click", event => { event.stopPropagation(); openDocumentDetail(button.dataset.doctype, button.dataset.name).catch(error => setToast(error.message)); }));
    document.querySelectorAll("[data-workflow-action]").forEach(button => button.addEventListener("click", () => performWorkflow(button).catch(error => setToast(error.message))));
    document.querySelectorAll("[data-workflow-action]").forEach(button => button.addEventListener("click", event => event.stopPropagation()));
    document.querySelectorAll("[data-business-action]").forEach(button => button.addEventListener("click", () => performBusinessAction(button).catch(error => setToast(error.message))));
    document.querySelectorAll("[data-business-action]").forEach(button => button.addEventListener("click", event => event.stopPropagation()));
    const showFilters = state.view === "requests" || state.view === "documents";
    $("inventoryFilters").hidden = state.view !== "inventory";
    $("contentFilters").hidden = !showFilters;
    if (showFilters) {
      $("filterQuery").value = state.filters.query;
      $("filterStatusScope").value = state.filters.status_scope;
      $("filterDateFrom").value = state.filters.date_from;
      $("filterDateTo").value = state.filters.date_to;
    }
    if (state.view === "inventory") {
      $("filterInventoryItem").value = state.filters.inventory_item;
      $("filterInventoryWarehouse").value = state.filters.inventory_warehouse;
    }
  }

  function renderLoadingFrame() {
    const [title, description, section] = sectionForView();
    $("pageTitle").textContent = title;
    $("pageDescription").textContent = description;
    $("sectionTitle").textContent = section;
    document.querySelectorAll(".nav-link[data-view]").forEach(link => link.classList.toggle("active", link.dataset.view === state.view));
    $("contentState").hidden = false;
    $("contentStateText").textContent = "正在读取 ERPNext 业务数据…";
    $("retryButton").hidden = true;
  }

  function formatDetail(payload) {
    const doc = payload.document || {};
    const process = payload.process || {};
    const summary = payload.summary || {};
    const links = payload.source_links || [];
    const ledger = payload.inventory?.ledger || [];
    const project = doc.project || (doc.items || []).find(item => item?.project)?.project || "—";
    const history = process.history || [];
    const comments = process.comments || [];
    const approvalStages = process.approval_stages || [];
    const fields = [["单号", payload.name], ["状态", process.state || doc.status || "—"], ["项目", project], ["申请人", doc.owner || "—"], ["日期", doc.transaction_date || doc.posting_date || "—"], ["用途", doc.title || doc.description || "—"]];
    const quantities = [["行数", summary.line_count], ["订购数量", summary.ordered_qty], ["已收数量", summary.received_qty], ["已退数量", summary.returned_qty], ["剩余数量", summary.remaining_qty], ["单位", (summary.uoms || []).join("、") || "—"]];
    const items = (doc.items || []).filter(item => item && typeof item === "object");
    let operationButtons = "";
    if (payload.doctype === "Purchase Order") operationButtons = `<button type="button" class="row-action" data-business-action="purchase_receipt.create" data-business-payload="${esc(JSON.stringify({ purchase_order: payload.name, selected_items: [] }))}">收货（填写数量）</button>`;
    if (payload.doctype === "Request for Quotation" && Number(doc.docstatus) === 0) operationButtons = `<button type="button" class="row-action" data-business-action="submit" data-business-payload="${esc(JSON.stringify({ doctype: payload.doctype, name: payload.name }))}">提交询价</button>`;
    if (payload.doctype === "Request for Quotation" && Number(doc.docstatus) === 1) operationButtons = `<button type="button" class="row-action" data-business-action="quotation.create" data-business-payload="${esc(JSON.stringify({ request_for_quotation: payload.name }))}">录入供应商报价</button>`;
    if (payload.doctype === "Supplier Quotation" && Number(doc.docstatus) === 0) operationButtons = `<button type="button" class="row-action" data-business-action="submit" data-business-payload="${esc(JSON.stringify({ doctype: payload.doctype, name: payload.name }))}">提交报价</button>`;
    if (payload.doctype === "Supplier Quotation" && Number(doc.docstatus) === 1) operationButtons = `<button type="button" class="row-action" data-business-action="purchase_order.create" data-business-payload="${esc(JSON.stringify({ supplier_quotation: payload.name, selected_items: [] }))}">从报价创建订单</button>`;
    if (payload.doctype === "Purchase Receipt" && !doc.is_return) operationButtons = `<button type="button" class="row-action" data-business-action="purchase_discrepancy.create" data-business-payload="${esc(JSON.stringify({ purchase_receipt: payload.name }))}">登记收货差异</button><button type="button" class="row-action" data-business-action="purchase_return.create" data-business-payload="${esc(JSON.stringify({ purchase_receipt: payload.name, items: [] }))}">创建采购退货</button>`;
    if (payload.doctype === "Stock Entry" && String(doc.stock_entry_type || doc.purpose || "").includes("Issue")) operationButtons = `<button type="button" class="row-action" data-business-action="stock.project_return.create" data-business-payload="${esc(JSON.stringify({ target_warehouse: (items[0] || {}).t_warehouse || (items[0] || {}).s_warehouse || "", items: items.map(item => ({ item_code: item.item_code, qty: item.qty, uom: item.uom || item.stock_uom, t_warehouse: item.t_warehouse || item.s_warehouse, project: item.project })) }))}">项目退料</button>`;
    if (payload.doctype === "Material Request" && Number(doc.docstatus) === 0 && (!doc.workflow_state || doc.workflow_state === "Nexterp材料草稿")) operationButtons = `<button type="button" class="row-action" data-business-action="submit" data-business-payload="${esc(JSON.stringify({ doctype: "Material Request", name: payload.name }))}">提交申请</button><button type="button" class="row-action" data-business-action="material_request.update_draft" data-business-payload="${esc(JSON.stringify({ name: payload.name }))}">编辑草稿</button><button type="button" class="row-action" data-business-action="material_request.copy" data-business-payload="${esc(JSON.stringify({ name: payload.name }))}">复制申请</button>`;
    const workflowEvidence = [...history.map(row => `<div class="detail-link"><span>${esc(row.action || row.workflow_state || row.modified || "工作流")}</span><strong>${esc(row.comment || row.reason || row.owner || "")}</strong></div>`), ...comments.map(row => `<div class="detail-link"><span>${esc(row.creation || row.comment_by || "备注")}</span><strong>${esc(row.content || row.text || "")}</strong></div>`)];
    const approvalFlow = approvalStages.length ? `<ol class="approval-flow">${approvalStages.map(stage => `<li class="approval-stage ${esc(stage.status || "pending")}"><span class="approval-marker" aria-hidden="true"></span><div><strong>${esc(stage.label || stage.state)}</strong><small>${esc(stage.role || "")} · ${esc(stage.status_label || "待处理")}</small></div></li>`).join("")}</ol>` : `<p class="muted">该单据无需多级审批，状态以 ERPNext 回读为准。</p>`;
    return `<section class="detail-section"><h3>单据基本信息</h3><div class="detail-kv">${fields.map(([key, value]) => `<span>${esc(key)}</span><strong>${esc(value)}</strong>`).join("")}</div>${operationButtons ? `<div class="row-actions">${operationButtons}</div>` : ""}</section><section class="detail-section approval-section"><h3>审批流程</h3><div class="detail-kv"><span>ERPNext 当前节点</span><strong>${esc(process.state || "—")}</strong><span>当前账号可执行</span><strong>${esc((process.available_actions || []).join("、") || "无")}</strong></div>${approvalFlow}${workflowEvidence.length ? `<h4>审批记录与意见</h4><div class="detail-links">${workflowEvidence.join("")}</div>` : "<p class='muted'>暂无单独记录的审批意见。</p>"}</section><section class="detail-section"><h3>物料明细</h3><div class="detail-links">${items.length ? items.map(item => `<div class="detail-link"><span>${esc(item.item_name || item.item_code || "物料")}</span><strong>${esc(item.qty ?? "—")} ${esc(item.uom || item.stock_uom || "")}</strong></div>`).join("") : "<span>暂无物料明细</span>"}</div></section><section class="detail-section"><h3>数量与回读</h3><div class="detail-kv">${quantities.map(([key, value]) => `<span>${esc(key)}</span><strong>${esc(value ?? "—")}</strong>`).join("")}<span>ERPNext</span><strong>${payload.readback?.verified ? "已回读" : "待核验"}</strong></div></section><section class="detail-section"><h3>来源链</h3><div class="detail-links">${links.length ? links.map(link => `<div class="detail-link"><span>${esc(link.label)}</span><strong>${esc(link.name)}</strong></div>`).join("") : "<span>暂无显式来源单据</span>"}</div></section>${ledger.length ? `<section class="detail-section"><h3>最近库存流水</h3><div class="detail-links">${ledger.slice(0, 10).map(row => `<div class="detail-link"><span>${esc(row.posting_date || row.posting_datetime || "—")} · ${esc(row.warehouse || "")}</span><strong>${esc(row.actual_qty ?? row.qty ?? "—")}</strong></div>`).join("")}</div></section>` : ""}`;
  }

  async function openDocumentDetail(doctype, name) {
    if (!doctype || !name) return;
    state.lastFocused = document.activeElement;
    document.body.classList.add("modal-open");
    $("detailDrawer").hidden = false; $("detailShade").hidden = false; $("detailState").hidden = false; $("detailBody").innerHTML = ""; $("detailState").textContent = "正在读取 ERPNext 详情…"; $("detailTitle").textContent = name;
    $("detailClose").focus();
    try { const payload = await api(`/api/business/document?doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(name)}`); $("detailState").hidden = true; $("detailBody").innerHTML = formatDetail(payload); bindBusinessActionButtons(); }
    catch (error) { $("detailState").textContent = `详情读取失败：${error.message}`; }
  }

  function closeDocumentDetail() {
    $("detailDrawer").hidden = true;
    $("detailShade").hidden = true;
    document.body.classList.remove("modal-open");
    state.lastFocused?.focus?.();
  }

  function bindBusinessActionButtons() {
    document.querySelectorAll("#detailBody [data-business-action]").forEach(button => button.addEventListener("click", () => performBusinessAction(button).catch(error => setToast(error.message))));
  }

  async function loadViewData() {
    const project = state.bootstrap?.context?.project_code || "";
    const cacheKey = state.view === "inventory"
      ? `inventory|${project}|${state.filters.inventory_item}|${state.filters.inventory_warehouse}`
      : state.view === "project"
        ? `project|${project}`
        : state.view === "documents" || state.view === "requests"
          ? `${state.view}|${state.filters.status_scope}|${state.filters.query}|${state.filters.date_from}|${state.filters.date_to}`
          : "";
    if (cacheKey && state.viewCache.has(cacheKey)) {
      state.viewData = state.viewCache.get(cacheKey);
      if (state.view === "requests") state.dashboard.sections.documents = state.viewData;
      return;
    }
    state.viewData = null;
    if (state.view === "inventory") {
      const params = new URLSearchParams({ item_code: state.filters.inventory_item, warehouse: state.filters.inventory_warehouse, project, limit: "100" });
      state.viewData = await api(`/api/business/inventory?${params}`);
    }
    if (state.view === "project") state.viewData = await api(`/api/business/project-materials?project=${encodeURIComponent(project)}`);
    if (state.view === "documents" || state.view === "requests") {
      const params = new URLSearchParams({ module: "buying", page_size: "50", status_scope: state.filters.status_scope, query: state.filters.query, date_from: state.filters.date_from, date_to: state.filters.date_to });
      if (state.view === "requests") params.set("doctype", "Material Request");
      state.viewData = await api(`/api/business/documents?${params}`);
      if (state.view === "requests") state.dashboard.sections.documents = state.viewData;
    }
    if (cacheKey && state.viewData) state.viewCache.set(cacheKey, state.viewData);
  }

  async function performWorkflow(button) {
    const workflowAction = button.dataset.workflowAction;
    const needsReason = /退回|驳回|拒绝/.test(workflowAction);
    const comment = needsReason ? window.prompt("请填写退回原因（必填）") : "";
    if (needsReason && !String(comment || "").trim()) { setToast("退回必须填写原因，未执行任何写入"); return; }
    const preview = await post("/api/business/commands/preview", { action: "workflow.action", payload: { doctype: button.dataset.doctype, name: button.dataset.name, action: workflowAction, comment: String(comment || "").trim() } });
    if (!window.confirm(`确认执行“${workflowAction}”吗？\n${button.dataset.doctype} · ${button.dataset.name}`)) return;
    await post(`/api/business/commands/${encodeURIComponent(preview.command.command_id)}/confirm`, { request_id: `wf-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}` });
    setToast("审批动作已完成，正在刷新 ERPNext 状态");
    await load();
  }

  async function performBusinessAction(button) {
    const action = button.dataset.businessAction;
    let payload = JSON.parse(button.dataset.businessPayload || "{}");
    if (action === "material_request.update_draft") {
      const source = await api(`/api/business/document?doctype=Material%20Request&name=${encodeURIComponent(payload.name)}`);
      const scheduleDate = window.prompt("新的要求到货日期（YYYY-MM-DD）", source.document?.schedule_date || "");
      if (scheduleDate === null) return;
      const purpose = window.prompt("新的用途说明（可留空）", source.document?.title || "");
      if (purpose === null) return;
      payload.schedule_date = scheduleDate.trim(); payload.purpose = purpose.trim();
    }
    if (action === "material_request.copy") {
      const source = await api(`/api/business/document?doctype=Material%20Request&name=${encodeURIComponent(payload.name)}`);
      payload = { items: (source.document?.items || []).map(item => ({ item_code: item.item_code, qty: item.qty, uom: item.uom, warehouse: item.warehouse, description: item.description })), schedule_date: window.prompt("新申请要求到货日期（YYYY-MM-DD）", source.document?.schedule_date || "") || "", purpose: window.prompt("新申请用途说明", source.document?.title || "") || "" };
      if (!payload.schedule_date) return;
    }
    if (action === "quotation.create") {
      const source = await api(`/api/business/document?doctype=Request%20for%20Quotation&name=${encodeURIComponent(payload.request_for_quotation)}`);
      const suppliers = (source.document?.suppliers || []).map(row => row.supplier || row.supplier_name).filter(Boolean);
      const supplierCode = window.prompt(`供应商名称（可选：${suppliers.join("、")}）`, suppliers[0] || "");
      if (!supplierCode) return;
      payload.supplier_code = supplierCode;
      payload.valid_till = window.prompt("报价有效期（YYYY-MM-DD，可留空）", "") || "";
      payload.offers = (source.document?.items || []).map(item => ({ request_for_quotation_item: item.name, rate: Number(window.prompt(`请输入 ${item.item_name || item.item_code} 的含税单价`, "0")) || 0, schedule_date: item.schedule_date }));
    }
    if (action === "purchase_order.create") {
      const source = await api(`/api/business/document?doctype=Supplier%20Quotation&name=${encodeURIComponent(payload.supplier_quotation)}`);
      payload.selected_items = (source.document?.items || []).map(item => ({ supplier_quotation_item: item.name, item_code: item.item_code, qty: item.qty }));
    }
    if (action === "purchase_receipt.create") {
      const source = await api(`/api/business/document?doctype=Purchase%20Order&name=${encodeURIComponent(payload.purchase_order)}`);
      const selected = [];
      for (const item of source.document?.items || []) {
        const remaining = Math.max(0, Number(item.qty || 0) - Number(item.received_qty || 0) + Number(item.returned_qty || 0));
        if (!remaining) continue;
        const raw = window.prompt(`本次收货数量：${item.item_name || item.item_code}\n剩余 ${remaining} ${item.uom || item.stock_uom || ""}`, String(remaining));
        if (raw === null) return;
        const qty = Number(raw);
        if (!Number.isFinite(qty) || qty <= 0 || qty > remaining) { setToast("收货数量必须大于0且不超过剩余数量"); return; }
        selected.push({ item_code: item.item_code, qty, uom: item.uom || item.stock_uom, purchase_order_item: item.name, warehouse: item.warehouse, project: item.project });
      }
      if (!selected.length) { setToast("没有可收货的剩余数量"); return; }
      payload.selected_items = selected;
    }
    if (action === "purchase_discrepancy.create") {
      const description = window.prompt("请填写收货差异说明（必填）");
      if (!String(description || "").trim()) { setToast("差异说明必填，未执行任何写入"); return; }
      payload.description = String(description).trim();
    }
    if (action === "purchase_return.create") {
      const reason = window.prompt("请填写采购退货原因（必填）");
      if (!String(reason || "").trim()) { setToast("退货原因必填，未执行任何写入"); return; }
      payload.reason = String(reason).trim();
    }
    if (action === "stock.project_issue.create" || action === "stock.project_return.create") {
      const raw = window.prompt(action === "stock.project_issue.create" ? "请输入本次项目领料数量" : "请输入本次项目退料数量", "1");
      if (raw === null) return;
      const qty = Number(raw);
      if (!Number.isFinite(qty) || qty <= 0) { setToast("数量必须大于0，未执行任何写入"); return; }
      payload.items = [{ ...(payload.items?.[0] || {}), item_code: payload.item_code || payload.items?.[0]?.item_code, qty, uom: payload.uom || payload.items?.[0]?.uom }];
      delete payload.item_code;
      delete payload.uom;
    }
    const labels = { "rfq.create": "创建询价草稿", "quotation.create": "录入供应商报价", "purchase_order.create": "创建采购订单草稿", "purchase_receipt.create": "创建收货草稿", "material_request.update_draft": "修改申请草稿", "material_request.copy": "复制材料申请", submit: "提交材料申请" };
    const previewAction = action === "submit" ? "document.submit" : action === "material_request.copy" ? "material_request.create_draft" : action;
    const preview = await post("/api/business/commands/preview", { action: previewAction, payload });
    if (!window.confirm(`确认${labels[action] || "执行该业务动作"}吗？\n${preview.summary?.title || previewAction}`)) return;
    await post(`/api/business/commands/${encodeURIComponent(preview.command.command_id)}/confirm`, { request_id: `biz-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}` });
    setToast(`${labels[action] || "业务动作"}已完成，正在回读 ERPNext`);
    await load();
  }

  async function loadView() {
    const sequence = ++state.loadSequence;
    const startedAt = performance.now();
    state.loading = true;
    renderLoadingFrame();
    try { await loadViewData(); if (sequence !== state.loadSequence) return; renderMetrics(); renderContent(); }
    catch (error) { if (sequence !== state.loadSequence) return; $("contentState").hidden = false; $("contentStateText").textContent = `业务状态暂时无法读取：${error.message}`; $("retryButton").hidden = false; $("footerStatus").textContent = "连接异常"; setToast(error.message); }
    finally {
      state.loading = false;
      const elapsed = Math.round(performance.now() - startedAt);
      window.__nexterpLastViewLoadMs = elapsed;
      document.documentElement.dataset.nexterpLastViewLoadMs = String(elapsed);
    }
  }
  async function load() {
    if (state.loading) return;
    state.loading = true;
    state.viewCache.clear();
    try {
      const [bootstrap, dashboard] = await Promise.all([api("/api/business/bootstrap"), api("/api/business/dashboard")]);
      state.bootstrap = bootstrap;
      applyContext();
      state.dashboard = dashboard;
    }
    catch (error) { $("contentState").hidden = false; $("contentStateText").textContent = `业务状态暂时无法读取：${error.message}`; $("retryButton").hidden = false; $("footerStatus").textContent = "连接异常"; setToast(error.message); state.loading = false; return; }
    state.loading = false;
    await loadView();
  }
  document.querySelectorAll(".nav-link[data-view]").forEach(link => link.addEventListener("click", event => { if (link.hidden) return; state.view = link.dataset.view; state.requestedView = state.view; history.pushState({}, "", `/?view=${encodeURIComponent(state.view)}`); loadView().catch(error => setToast(error.message)); event.preventDefault(); }));
  $("refreshButton").addEventListener("click", load);
  $("retryButton").addEventListener("click", () => load().catch(error => setToast(error.message)));
  $("applyFilters").addEventListener("click", () => {
    state.filters = { ...state.filters, query: $("filterQuery").value.trim(), status_scope: $("filterStatusScope").value, date_from: $("filterDateFrom").value, date_to: $("filterDateTo").value };
    loadView().catch(error => setToast(error.message));
  });
  $("applyInventoryFilters").addEventListener("click", () => {
    state.filters.inventory_item = $("filterInventoryItem").value.trim();
    state.filters.inventory_warehouse = $("filterInventoryWarehouse").value.trim();
    loadView().catch(error => setToast(error.message));
  });
  $("businessUser").addEventListener("change", () => switchBusinessContext().catch(error => setToast(error.message)));
  $("businessProject").addEventListener("change", () => switchBusinessContext().catch(error => setToast(error.message)));
  $("classificationSource").addEventListener("change", () => switchClassificationSource().catch(error => setToast(error.message)));
  $("detailClose").addEventListener("click", closeDocumentDetail);
  $("detailShade").addEventListener("click", closeDocumentDetail);
  document.addEventListener("keydown", event => { if (event.key === "Escape" && !$("detailDrawer").hidden) closeDocumentDetail(); });
  window.addEventListener("popstate", () => { state.view = new URLSearchParams(location.search).get("view") || "home"; state.requestedView = state.view; loadView().catch(error => setToast(error.message)); }); load();
})();
