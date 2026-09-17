(() => {
  const state = {
    projects: [],
    project: null,
    employee: null,
    rows: [],
    facets: { segments: [], standardTypes: [], uoms: [] },
    categoryTree: [],
    filters: { q: "", segment: "", category: "", standardType: "", stockUom: "", sort: "name", page: 1 },
    pageSize: 24,
    total: 0,
    skuTotal: 0,
    cart: new Map(),
    requestToken: 0,
    businessContext: null,
    businessModules: [],
    businessEmployees: [],
    classificationSources: [],
    classificationSource: "original",
    developerIdentitySwitcher: false,
    variantProfile: null,
    variantSelections: {},
    variantQuantity: 1,
    erpnextVerified: false,
    catalogReadOnly: false,
  };

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
  const formatNumber = value => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 3 });
  // material_id is the internal publication/source key. Keep it for lookup,
  // but show the ERPNext item code in procurement-facing UI.
  const displayItemCode = row => row?.item_code ? String(row.item_code) : "待同步";
  const palette = ["#c9d9d3", "#d9cfbf", "#c8c9bf", "#d9c2a7", "#b9ced1", "#d8d4c5", "#c5d1bc", "#d8c6c0"];
  const todayPlus = days => {
    const date = new Date();
    date.setDate(date.getDate() + days);
    return date.toISOString().slice(0, 10);
  };

  async function api(path) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, signal: controller.signal });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`);
      return payload;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("目录服务响应超时，请稍后重试");
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function restoreCart() {
    try {
      const rows = JSON.parse(localStorage.getItem("nexterp.material-marketplace.cart") || "[]");
      state.cart = new Map(rows.map(row => [row.material_id, row]));
    } catch (_error) {
      state.cart = new Map();
    }
  }

  async function hydrateCartRows() {
    // A cart may survive a local catalog revision. Always resolve its source
    // IDs against the current ungrouped release so renamed types, normalized
    // attributes and ERPNext item metadata cannot remain stale in the drawer.
    const savedRows = [...state.cart.values()].filter(row => row?.material_id);
    if (!savedRows.length) return;
    const resolved = await Promise.all(savedRows.map(async row => {
      try {
        const payload = await api(`/api/material-marketplace/catalog?classification_source=${encodeURIComponent(state.classificationSource)}&q=${encodeURIComponent(row.material_id)}&page=1&page_size=60&group_variants=0`);
        return payload.rows?.find(candidate => candidate.material_id === row.material_id) || null;
      } catch (_error) {
        return null;
      }
    }));
    let changed = false;
    savedRows.forEach((savedRow, index) => {
      const currentRow = resolved[index];
      if (!currentRow?.item_code) {
        state.cart.delete(savedRow.material_id);
        changed = true;
        return;
      }
      state.cart.set(savedRow.material_id, { ...currentRow, qty: savedRow.qty });
      changed = true;
    });
    if (changed) persistCart();
  }

  function persistCart() {
    localStorage.setItem("nexterp.material-marketplace.cart", JSON.stringify([...state.cart.values()]));
  }

  async function boot() {
    restoreCart();
    $("scheduleDate").min = new Date().toISOString().slice(0, 10);
    $("scheduleDate").value = todayPlus(7);
    bindEvents();
    if (window.matchMedia("(max-width: 680px)").matches) {
      document.querySelectorAll("#filterPanel details").forEach(details => details.removeAttribute("open"));
    }
    try {
      // Use the same session-bound identity and project as the business portal.
      // The legacy workbench bootstrap exposed arbitrary employee selectors,
      // which could make a request appear to belong to somebody else.
      const bootstrap = await api("/api/business/bootstrap");
      state.businessContext = bootstrap.context || null;
      state.businessModules = bootstrap.modules || [];
      state.businessEmployees = bootstrap.employees || [];
      state.classificationSources = bootstrap.classification_sources || [];
      const requestedSource = new URLSearchParams(location.search).get("classification_source");
      state.classificationSource = requestedSource || state.businessContext?.classification_source || "original";
      renderClassificationOptions();
      // A deep link must establish the paired account before the first catalog
      // read; otherwise a ChatGPT URL could display V4 rows while a later
      // preview still used the previous GPC Site cookie.
      if (requestedSource && requestedSource !== bootstrap.context?.classification_source) {
        const switchResponse = await fetch("/api/business/classification", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ classification_source: state.classificationSource }),
        });
        const switchPayload = await switchResponse.json();
        if (!switchResponse.ok || switchPayload.ok === false) throw new Error(switchPayload.error || "无法切换分类测试账套");
        state.businessContext = switchPayload.context || state.businessContext;
        renderClassificationOptions();
      }
      state.developerIdentitySwitcher = Boolean(bootstrap.features?.developer_identity_switcher);
      renderFunctionNav();
      state.projects = bootstrap.projects || [];
      renderProjectOptions();
      await loadCatalog();
      await hydrateCartRows();
    } catch (error) {
      $("loadingState").textContent = `目录读取失败：${error.message}`;
      $("catalogStatus").textContent = "目录暂不可用";
    }
    renderCart();
  }

  function renderProjectOptions() {
    const contextProject = state.businessContext?.project_code || "";
    const storedProject = state.developerIdentitySwitcher ? localStorage.getItem("nexterp.material-marketplace.project") : "";
    state.project = state.projects.find(row => row.project_code === (storedProject || contextProject))
      || state.projects.find(row => row.project_code === contextProject)
      || state.projects[0]
      || null;
    const visibleProjects = state.developerIdentitySwitcher ? state.projects : state.projects.filter(row => row.project_code === contextProject);
    $("projectSelect").innerHTML = visibleProjects.map(project => (
      `<option value="${esc(project.project_code)}">${esc(project.project_short_name)} · ${esc(project.operating_status)}</option>`
    )).join("");
    if (state.project) $("projectSelect").value = state.project.project_code;
    $("projectSelect").disabled = !state.developerIdentitySwitcher;
    renderEmployeeOptions();
  }

  function renderEmployeeOptions() {
    const employees = state.businessEmployees.length ? state.businessEmployees : (state.project?.employees || []);
    const contextUser = state.businessContext?.user || "";
    const storedEmployee = state.developerIdentitySwitcher ? localStorage.getItem("nexterp.material-marketplace.employee") : "";
    state.employee = employees.find(row => row.user_email === (storedEmployee || contextUser))
      || employees.find(row => row.user_email === contextUser)
      || employees[0]
      || null;
    const visibleEmployees = state.developerIdentitySwitcher ? employees : employees.filter(row => row.user_email === contextUser);
    $("employeeSelect").innerHTML = visibleEmployees.map(employee => (
      `<option value="${esc(employee.user_email)}">${esc(employee.employee_name)} · ${esc(employee.project_position || employee.position || "")}</option>`
    )).join("");
    if (state.employee) $("employeeSelect").value = state.employee.user_email;
    $("employeeSelect").disabled = !state.developerIdentitySwitcher;
    $("employeeSelect").setAttribute("aria-label", state.developerIdentitySwitcher ? "测试环境申请人" : "当前登录员工");
  }

  function renderClassificationOptions() {
    const select = $("classificationSource");
    if (!select) return;
    const sources = state.classificationSources.length
      ? state.classificationSources
      : [{ code: "original", label: "原分类（GPC）" }, { code: "chatgpt_v4", label: "ChatGPT 分类（龙华 V4）" }];
    select.innerHTML = sources.map(source => `<option value="${esc(source.code)}" ${source.available === false ? "disabled" : ""}>${esc(source.label)}</option>`).join("");
    const selected = sources.find(source => source.code === state.classificationSource);
    if (!selected || selected.available === false || ![...select.options].some(option => option.value === state.classificationSource)) state.classificationSource = "original";
    select.value = state.classificationSource;
    const activeSource = sources.find(source => source.code === state.classificationSource) || sources[0];
    select.title = activeSource?.note || "切换物料分类版本";
    const workbenchLink = $("classificationWorkbenchLink");
    if (workbenchLink) workbenchLink.href = `/tariff-taxonomy-browser?catalog=gpc&classification_source=${encodeURIComponent(state.classificationSource)}`;
    const description = $("catalogDescription");
    const account = state.businessContext?.account || {};
    const boundForWrites = account.classification_source === state.classificationSource && account.write_enabled;
    if (description) description.textContent = activeSource?.read_only && !boundForWrites
      ? `${activeSource.note || "当前为分类预览"} 该版本暂不能生成采购申请。`
      : `${boundForWrites ? `${account.label || "当前测试账套"}已绑定。` : (activeSource?.note || "原分类（GPC）为当前物料采购目录，可用于申请。")} 没有维护的价格和库存不会用估算值代替。`;
    const accountLabel = $("accountLabel");
    if (accountLabel) accountLabel.textContent = account.label ? `账套：${account.label}` : "账套：未连接";
  }

  async function switchClassificationSource() {
    const source = $("classificationSource")?.value || "original";
    const previousSource = state.classificationSource;
    if (source === previousSource) return;
    try {
      const payload = await fetch("/api/business/classification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ classification_source: source }),
      }).then(async response => {
        const result = await response.json();
        if (!response.ok || result.ok === false) throw new Error(result.error || `HTTP ${response.status}`);
        return result;
      });
      state.classificationSource = payload.classification_source || source;
      if (payload.context) state.businessContext = payload.context;
      history.replaceState({}, "", `/material-marketplace?classification_source=${encodeURIComponent(state.classificationSource)}`);
      state.filters.page = 1;
      state.cart = new Map([...state.cart.values()].filter(row => row.classification_source === state.classificationSource || (!row.classification_source && state.classificationSource === "original")));
      persistCart();
      renderClassificationOptions();
      await loadCatalog();
      await hydrateCartRows();
      renderCart();
    } catch (error) {
      state.classificationSource = previousSource;
      renderClassificationOptions();
      showToast(`切换分类失败：${error.message}`);
    }
  }

  function renderFunctionNav() {
    const roles = new Set(["all", state.businessContext?.employee?.position || ""]);
    const modules = state.businessModules || [];
    document.querySelectorAll(".function-nav a[data-module]").forEach(link => {
      const module = modules.find(row => row.code === link.dataset.module);
      link.hidden = Boolean(module) && !(module.roles || []).some(role => roles.has(role));
    });
  }

  async function loadCatalog() {
    const token = ++state.requestToken;
    $("loadingState").hidden = false;
    $("loadingState").textContent = "正在整理目录…";
    $("emptyState").hidden = true;
    const params = new URLSearchParams({
      q: state.filters.q,
      segment: state.filters.segment,
      category: state.filters.category,
      standard_type: state.filters.standardType,
      stock_uom: state.filters.stockUom,
      sort: state.filters.sort,
      page: String(state.filters.page),
      page_size: String(state.pageSize),
      group_variants: "1",
      classification_source: state.classificationSource,
    });
    try {
      const payload = await api(`/api/material-marketplace/catalog?${params}`);
      if (token !== state.requestToken) return;
      state.rows = payload.rows || [];
      state.total = Number(payload.total || 0);
      state.skuTotal = Number(payload.sku_total || payload.total || 0);
      state.facets = {
        segments: payload.segments || [],
        standardTypes: payload.standard_types || [],
        uoms: payload.stock_uoms || [],
      };
      state.categoryTree = payload.category_tree || [];
      state.erpnextVerified = payload.erpnext_sync_status === "erpnext_verified";
      state.catalogReadOnly = payload.erpnext_sync_status === "classification_only";
      const skuContext = state.skuTotal > state.total ? `，对应 ${formatNumber(state.skuTotal)} 个具体 SKU` : "";
      $("catalogStatus").textContent = `${formatNumber(state.total)} 项匹配${skuContext} · ${payload.erpnext_sync_message || payload.source_version || ""}`;
      renderCatalog();
    } catch (error) {
      if (token !== state.requestToken) return;
      $("loadingState").textContent = `目录读取失败：${error.message}`;
    }
  }

  function renderCatalog() {
    $("loadingState").hidden = true;
    $("resultCount").textContent = state.skuTotal > state.total
      ? `${formatNumber(state.total)} 个标准类型/物料 · ${formatNumber(state.skuTotal)} 个具体 SKU`
      : `${formatNumber(state.total)} 项物料`;
    renderCategoryNav();
    renderFilters();
    renderActiveFilters();
    $("emptyState").hidden = state.rows.length > 0;
    $("productGrid").innerHTML = state.rows.map((row, index) => productCard(row, index)).join("");
    bindProductEvents();
    renderPagination();
  }

  function renderCategoryNav() {
    $("categoryNav").innerHTML = state.facets.segments.slice(0, 6).map(segment => (
      `<button type="button" data-nav-segment="${esc(segment.code)}" class="${state.filters.segment === segment.code ? "active" : ""}">${esc(segment.name)}</button>`
    )).join("");
    document.querySelectorAll("[data-nav-segment]").forEach(button => {
      button.onclick = () => {
        state.filters.category = "";
        setFilter("segment", button.dataset.navSegment || "");
      };
    });
  }

  function categoryTreeNode(node) {
    const children = node.children || [];
    const selected = state.filters.category === node.code;
    const hasChildren = children.length > 0;
    const toggle = hasChildren
      ? '<button class="category-toggle" type="button" data-toggle-category="' + esc(node.code) + '" aria-expanded="false" aria-label="展开 ' + esc(node.name) + '">+</button>'
      : '<span class="category-toggle-spacer" aria-hidden="true"></span>';
    const childList = hasChildren
      ? '<ul class="category-children" data-children-for="' + esc(node.code) + '" hidden>' + children.map(categoryTreeNode).join("") + "</ul>"
      : "";
    return '<li class="category-node"><div class="category-node-row">'
      + toggle
      + '<button class="category-select ' + (selected ? "active" : "") + '" type="button" data-category="' + esc(node.code) + '"><span>'
      + esc(node.name) + "</span><em>" + formatNumber(node.count) + " SKU</em></button></div>" + childList + "</li>";
  }

  function filterOption(kind, value, label, count, selected) {
    return `<label class="filter-option"><input type="radio" name="${kind}" value="${esc(value)}" ${selected ? "checked" : ""}><span>${esc(label)}</span><em>${formatNumber(count)}</em></label>`;
  }

  function renderFilters() {
    const total = state.facets.segments.reduce((sum, row) => sum + Number(row.count || 0), 0);
    $("segmentFilters").innerHTML = '<button class="category-all ' + (!state.filters.category && !state.filters.segment ? "active" : "") + '" type="button" data-category=""><span>全部分类</span><em>'
      + formatNumber(total) + " SKU</em></button><ul class=\"category-tree\">" + state.categoryTree.map(categoryTreeNode).join("") + "</ul>";
    $("typeFilters").innerHTML = filterOption("standardType", "", "全部类型", state.total, !state.filters.standardType)
      + state.facets.standardTypes.map(row => filterOption("standardType", row.name, row.name, row.count, state.filters.standardType === row.name)).join("");
    $("uomFilters").innerHTML = filterOption("stockUom", "", "全部单位", state.total, !state.filters.stockUom)
      + state.facets.uoms.map(row => filterOption("stockUom", row.name, row.name, row.count, state.filters.stockUom === row.name)).join("");
    document.querySelectorAll(".filter-options input").forEach(input => {
      input.onchange = () => setFilter(input.name, input.value);
    });
    document.querySelectorAll("[data-category]").forEach(button => {
      button.onclick = () => {
        state.filters.segment = "";
        setFilter("category", button.dataset.category || "");
      };
    });
    document.querySelectorAll("[data-toggle-category]").forEach(button => {
      button.onclick = () => {
        const code = button.dataset.toggleCategory;
        const children = document.querySelector("[data-children-for=\"" + CSS.escape(code) + "\"]");
        if (!children) return;
        const willOpen = children.hidden;
        children.hidden = !willOpen;
        button.textContent = willOpen ? "−" : "+";
        button.setAttribute("aria-expanded", String(willOpen));
        button.setAttribute("aria-label", (willOpen ? "收起 " : "展开 ") + (button.nextElementSibling?.querySelector("span")?.textContent || "分类"));
      };
    });
  }

  function renderActiveFilters() {
    const segment = state.facets.segments.find(row => row.code === state.filters.segment)?.name;
    const category = findCategory(state.categoryTree, state.filters.category);
    const filters = [
      ["q", state.filters.q ? `搜索：${state.filters.q}` : ""],
      ["segment", segment || ""],
      ["category", category?.path || category?.name || ""],
      ["standardType", state.filters.standardType],
      ["stockUom", state.filters.stockUom ? `单位：${state.filters.stockUom}` : ""],
    ].filter(([, label]) => label);
    $("activeFilters").innerHTML = filters.map(([key, label]) => `<button type="button" data-clear-filter="${key}">${esc(label)} ×</button>`).join("");
    document.querySelectorAll("[data-clear-filter]").forEach(button => {
      button.onclick = () => {
        const key = button.dataset.clearFilter;
        if (key === "q") $("searchInput").value = "";
        setFilter(key, "");
      };
    });
  }

  function findCategory(nodes, code, parents = []) {
    if (!code) return null;
    for (const node of nodes || []) {
      const path = [...parents, node.name].join(" / ");
      if (node.code === code) return { ...node, path };
      const found = findCategory(node.children, code, [...parents, node.name]);
      if (found) return found;
    }
    return null;
  }

  function productCard(row, index) {
    if (row.record_kind === "standard_type_group") return variantGroupCard(row, index);
    const attributes = Object.entries(row.procurement_attributes || {}).slice(0, 3);
    const colorIndex = Math.abs([...String(row.segment_code || row.material_id)].reduce((sum, char) => sum + char.charCodeAt(0), 0)) % palette.length;
    const itemIndex = String((state.filters.page - 1) * state.pageSize + index + 1).padStart(2, "0");
    return `<article class="product-card" data-material-card="${esc(row.material_id)}">
      <button class="product-title" type="button" data-open-material="${esc(row.material_id)}">
        <div class="product-plate" style="--card-color:${palette[colorIndex]}">
          <span class="plate-index">${itemIndex}</span>
          <span class="plate-classification"><span>${esc(row.segment_name || "标准物料")}</span><code>${esc(displayItemCode(row))}</code></span>
        </div>
        <div class="product-kicker"><span>${esc(row.standard_type)}</span><span>${esc(row.stock_uom)}</span></div>
        <h3>${esc(row.material_name)}</h3>
      </button>
      <div class="product-attributes">${attributes.map(([key, value]) => `<span>${esc(key)} · ${esc(value)}</span>`).join("")}</div>
      <div class="availability">
        <span>参考价格<strong>尚未维护</strong></span>
        <span>项目库存<strong>申请时查询</strong></span>
      </div>
      <div class="add-row">
        <div class="quantity-control">
          <button type="button" data-step="-1" data-material="${esc(row.material_id)}" aria-label="减少数量">−</button>
          <input type="number" min="0.001" step="1" value="1" data-qty="${esc(row.material_id)}" aria-label="申请数量">
          <button type="button" data-step="1" data-material="${esc(row.material_id)}" aria-label="增加数量">+</button>
        </div>
        <button class="add-button" type="button" data-add="${esc(row.material_id)}" ${state.erpnextVerified ? "" : "disabled"}>${state.catalogReadOnly ? "仅供浏览" : state.erpnextVerified ? "加入申请" : "ERPNext 离线"}</button>
      </div>
    </article>`;
  }

  function variantGroupCard(row, index) {
    const attributes = Object.entries(row.variant_attributes || {})
      .sort(([left], [right]) => variantAttributeRank(left) - variantAttributeRank(right) || left.localeCompare(right, "zh-CN"))
      .slice(0, 4);
    const colorIndex = Math.abs([...String(row.segment_code || row.variant_type_code)].reduce((sum, char) => sum + char.charCodeAt(0), 0)) % palette.length;
    const itemIndex = String((state.filters.page - 1) * state.pageSize + index + 1).padStart(2, "0");
    return `<article class="product-card variant-group-card" data-material-card="${esc(row.material_id)}">
      <button class="product-title" type="button" data-open-material="${esc(row.material_id)}" aria-label="选择 ${esc(row.standard_type)} 的规格">
        <div class="product-plate" style="--card-color:${palette[colorIndex]}">
          <span class="plate-index">${itemIndex}</span>
          <span class="plate-classification"><span>${esc(row.segment_name || "标准物料")}</span><code>${esc(row.variant_type_code)}</code></span>
        </div>
        <div class="product-kicker"><span>${esc(row.standard_type)}</span><span>${formatNumber(row.variant_count)} 种规格</span></div>
        <h3>${esc(row.standard_type)}</h3>
      </button>
      <p class="product-description">同一标准类型集中选择规格，完整选择后对应到唯一物料编码。</p>
      <div class="product-attributes">${attributes.map(([key, value]) => `<span>${esc(key)} · ${esc(value)}</span>`).join("")}</div>
      <div class="availability">
        <span>具体价格<strong>选定规格后查询</strong></span>
        <span>项目库存<strong>按具体 SKU 查询</strong></span>
      </div>
      <button class="add-button choose-variant-button" type="button" data-open-material="${esc(row.material_id)}">选择规格</button>
    </article>`;
  }

  function bindProductEvents() {
    document.querySelectorAll("[data-step]").forEach(button => {
      button.onclick = () => {
        const input = document.querySelector(`[data-qty="${CSS.escape(button.dataset.material)}"]`);
        input.value = String(Math.max(1, Number(input.value || 1) + Number(button.dataset.step)));
      };
    });
    document.querySelectorAll("[data-add]").forEach(button => {
      button.onclick = () => addToCart(button.dataset.add);
    });
    document.querySelectorAll("[data-open-material]").forEach(button => {
      button.onclick = () => openMaterial(button.dataset.openMaterial);
    });
  }

  function addToCart(materialId) {
    const row = state.rows.find(item => item.material_id === materialId);
    if (!row) return;
    const input = document.querySelector(`[data-qty="${CSS.escape(materialId)}"]`);
    const qty = Math.max(0.001, Number(input?.value || 1));
    addRowToCart(row, qty);
  }

  function addRowToCart(row, qty) {
    const wasEmpty = state.cart.size === 0;
    const current = state.cart.get(row.material_id);
    state.cart.set(row.material_id, { ...row, qty: Number(current?.qty || 0) + qty });
    persistCart();
    renderCart();
    showToast(`已加入：${row.standard_type}`);
    if (wasEmpty) openCart();
  }

  function renderCart() {
    const rows = [...state.cart.values()];
    $("cartCount").textContent = String(rows.length);
    $("cartLineCount").textContent = String(rows.length);
    $("cartEmpty").hidden = rows.length > 0;
    $("requestForm").hidden = rows.length === 0;
    $("cartItems").innerHTML = rows.map(row => `<article class="cart-item">
      <div class="cart-item-head"><strong>${esc(row.material_name)}</strong><button type="button" data-remove="${esc(row.material_id)}">移除</button></div>
      <small>${esc(displayItemCode(row))} · ${esc(row.standard_type)}</small>
      <div class="cart-item-controls">
        <div class="quantity-control">
          <button type="button" data-cart-step="-1" data-cart-material="${esc(row.material_id)}">−</button>
          <input type="number" min="0.001" step="1" value="${esc(row.qty)}" data-cart-qty="${esc(row.material_id)}">
          <button type="button" data-cart-step="1" data-cart-material="${esc(row.material_id)}">+</button>
        </div>
        <span>${esc(row.stock_uom)} · 数量需复核</span>
      </div>
    </article>`).join("");
    document.querySelectorAll("[data-remove]").forEach(button => {
      button.onclick = () => { state.cart.delete(button.dataset.remove); persistCart(); renderCart(); };
    });
    document.querySelectorAll("[data-cart-step]").forEach(button => {
      button.onclick = () => updateCartQty(button.dataset.cartMaterial, Number(button.dataset.cartStep));
    });
    document.querySelectorAll("[data-cart-qty]").forEach(input => {
      input.onchange = () => setCartQty(input.dataset.cartQty, Number(input.value));
    });
  }

  function updateCartQty(materialId, delta) {
    const row = state.cart.get(materialId);
    if (!row) return;
    setCartQty(materialId, Math.max(1, Number(row.qty || 1) + delta));
  }

  function setCartQty(materialId, qty) {
    const row = state.cart.get(materialId);
    if (!row) return;
    row.qty = Math.max(0.001, Number(qty || 1));
    state.cart.set(materialId, row);
    persistCart();
    renderCart();
  }

  function renderPagination() {
    const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (pages <= 1) { $("pagination").innerHTML = ""; return; }
    const current = state.filters.page;
    const start = Math.max(1, Math.min(current - 2, pages - 4));
    const end = Math.min(pages, start + 4);
    const buttons = [];
    buttons.push(`<button type="button" data-page="${current - 1}" ${current === 1 ? "disabled" : ""}>上一页</button>`);
    for (let page = start; page <= end; page += 1) buttons.push(`<button type="button" class="${page === current ? "active" : ""}" data-page="${page}">${page}</button>`);
    buttons.push(`<button type="button" data-page="${current + 1}" ${current === pages ? "disabled" : ""}>下一页</button>`);
    $("pagination").innerHTML = buttons.join("");
    document.querySelectorAll("[data-page]").forEach(button => {
      button.onclick = () => { state.filters.page = Number(button.dataset.page); loadCatalog(); window.scrollTo({ top: $("productGrid").offsetTop - 220, behavior: "smooth" }); };
    });
  }

  function openMaterial(materialId) {
    const row = state.rows.find(item => item.material_id === materialId) || state.cart.get(materialId);
    if (!row) return;
    if (row.record_kind === "standard_type_group") {
      openVariantSelector(row);
      return;
    }
    const attributes = Object.entries(row.procurement_attributes || {});
    const priceDrivers = Object.entries(row.price_drivers || {});
    $("dialogBody").innerHTML = `<div class="dialog-content">
      <p class="eyebrow">${esc(row.standard_type)}</p>
      <h2>${esc(row.material_name)}</h2>
      <div class="dialog-meta"><span>${esc(displayItemCode(row))}</span><span>库存单位：${esc(row.stock_uom)}</span><span>${state.catalogReadOnly ? "分类预览" : "已完成准入"}</span></div>
      <section class="dialog-section"><h3>采购必选规格</h3><div class="dialog-specs">${attributes.map(([key, value]) => `<div><span>${esc(key)}</span><strong>${esc(value)}</strong></div>`).join("")}</div></section>
      <section class="dialog-section"><h3>价格与适配关键</h3><div class="dialog-specs">${priceDrivers.map(([key, value]) => `<div><span>${esc(key)}</span><strong>${esc(value)}</strong></div>`).join("")}</div></section>
      <section class="dialog-section"><h3>分类路径</h3><p class="dialog-path">${(row.classification_path || []).map(node => `${esc(node.name)} (${esc(node.code)})`).join(" / ")}</p></section>
      <button class="primary-action" type="button" data-dialog-add="${esc(row.material_id)}" ${state.catalogReadOnly || !state.erpnextVerified ? "disabled" : ""}>${state.catalogReadOnly ? "分类预览（不可申请）" : state.erpnextVerified ? "加入采购申请" : "ERPNext 离线"}</button>
    </div>`;
    $("materialDialog").showModal();
    $("dialogBody").querySelector("[data-dialog-add]").onclick = () => { addToCart(materialId); $("materialDialog").close(); };
  }

  function variantAttributes(row) {
    return {
      ...(row.procurement_attributes || {}),
      ...(row.price_drivers || {}),
    };
  }

  function variantAttributeRank(key) {
    const preferred = ["类别", "类型", "接头类型", "头型", "头型/驱动", "牌号", "材质", "材质/表面处理", "表面处理", "性能/质量等级", "强度等级", "公称直径", "主管直径", "支管直径", "规格", "长度", "角度", "交货形态", "供货范围", "包装", "包装规格"];
    const index = preferred.indexOf(key);
    return index === -1 ? preferred.length : index;
  }

  async function openVariantSelector(groupRow) {
    $("dialogBody").innerHTML = `<div class="dialog-content variant-loading"><p class="eyebrow">${esc(groupRow.standard_type)}</p><h2>正在读取可选规格…</h2></div>`;
    $("materialDialog").showModal();
    try {
      const params = new URLSearchParams({ classification_source: state.classificationSource, standard_type: groupRow.standard_type, page: "1", page_size: "60", sort: "code", group_variants: "0" });
      const payload = await api(`/api/material-marketplace/catalog?${params}`);
      const variants = (payload.rows || []).filter(row => row.gpc_brick_code === groupRow.variant_type_code && row.item_code);
      if (!variants.length) throw new Error("没有找到已同步的具体规格");
      const valueSets = new Map();
      variants.forEach(variant => Object.entries(variantAttributes(variant)).forEach(([key, value]) => {
        if (!valueSets.has(key)) valueSets.set(key, new Set());
        valueSets.get(key).add(String(value));
      }));
      const attributes = [...valueSets.entries()].map(([key, values]) => ({
        key,
        values: [...values].sort((left, right) => left.localeCompare(right, "zh-CN", { numeric: true })),
      })).sort((left, right) => variantAttributeRank(left.key) - variantAttributeRank(right.key) || (left.values.length === 1) - (right.values.length === 1) || left.values.length - right.values.length || left.key.localeCompare(right.key, "zh-CN"));
      state.variantProfile = { groupRow, variants, attributes };
      state.variantSelections = Object.fromEntries(attributes.filter(attribute => attribute.values.length === 1).map(attribute => [attribute.key, attribute.values[0]]));
      state.variantQuantity = 1;
      renderVariantSelector();
    } catch (error) {
      $("dialogBody").innerHTML = `<div class="dialog-content"><p class="eyebrow">${esc(groupRow.standard_type)}</p><h2>规格暂时无法读取</h2><p class="muted">${esc(error.message)}</p></div>`;
    }
  }

  function matchingVariants(ignoreKey = "", candidateValue = "") {
    const profile = state.variantProfile;
    if (!profile) return [];
    return profile.variants.filter(variant => {
      const attributes = variantAttributes(variant);
      if (ignoreKey && String(attributes[ignoreKey] ?? "") !== String(candidateValue)) return false;
      return Object.entries(state.variantSelections).every(([key, value]) => key === ignoreKey || String(attributes[key] ?? "") === String(value));
    });
  }

  function renderVariantSelector() {
    const profile = state.variantProfile;
    if (!profile) return;
    const currentMatches = matchingVariants();
    const selectedKeys = new Set(Object.keys(state.variantSelections));
    const unresolvedAttributes = profile.attributes.filter(attribute => {
      if (selectedKeys.has(attribute.key)) return false;
      const values = new Set(currentMatches.map(row => variantAttributes(row)[attribute.key]).filter(value => value !== undefined && value !== ""));
      return values.size > 1;
    });
    const nextAttributeKey = unresolvedAttributes[0]?.key || "";
    const variableAttributes = profile.attributes.filter(attribute => (
      attribute.values.length > 1
      && (selectedKeys.has(attribute.key) || attribute.key === nextAttributeKey)
    ));
    const fixedAttributes = profile.attributes.filter(attribute => (
      attribute.values.length === 1
      && profile.variants.every(row => String(variantAttributes(row)[attribute.key] ?? "") === String(attribute.values[0]))
    ));
    const resolved = currentMatches.length === 1 && selectedKeys.size > 0 ? currentMatches[0] : null;
    const groupUoms = [...new Set(profile.variants.map(row => row.stock_uom).filter(Boolean))];
    const selectedUom = resolved?.stock_uom || (groupUoms.length === 1 ? groupUoms[0] : "选定规格后确定");
    const selectorHtml = variableAttributes.map(attribute => `<fieldset class="variant-attribute"><legend>${esc(attribute.key)}</legend><div class="variant-options">${attribute.values.map(value => {
      const selected = state.variantSelections[attribute.key] === value;
      const enabled = matchingVariants(attribute.key, value).length > 0;
      return `<button type="button" data-variant-key="${esc(attribute.key)}" data-variant-value="${esc(value)}" aria-pressed="${selected}" ${enabled ? "" : "disabled"}>${esc(value)}</button>`;
    }).join("")}</div></fieldset>`).join("");
    const fixedHtml = fixedAttributes.length ? `<div class="fixed-variant-summary">${fixedAttributes.map(attribute => `<span>${esc(attribute.key)}<strong>${esc(attribute.values[0])}</strong></span>`).join("")}</div>` : "";
    const resolution = resolved
      ? `<div class="variant-resolution resolved"><span>已匹配具体物料</span><strong>${esc(resolved.material_name)}</strong><code>${esc(displayItemCode(resolved))}</code></div>`
      : `<div class="variant-resolution"><span>继续选择规格</span><strong>完整选择后显示具体物料编码</strong></div>`;
    $("dialogBody").innerHTML = `<div class="dialog-content variant-selector">
      <p class="eyebrow">标准类型 · ${formatNumber(profile.variants.length)} 种有效规格</p>
      <h2>${esc(profile.groupRow.standard_type)}</h2>
      <div class="dialog-meta"><span>${esc(profile.groupRow.variant_type_code)}</span><span>库存单位：${esc(selectedUom)}</span><span>只展示已存在 SKU</span></div>
      <section class="dialog-section"><h3>请选择采购规格</h3>${selectorHtml}${fixedHtml}</section>
      ${resolution}
      <div class="variant-submit-row">
        <label><span>申请数量（${esc(selectedUom)}）</span><input data-variant-qty type="number" min="0.001" step="1" value="${esc(state.variantQuantity)}" ${resolved ? "" : "disabled"}></label>
        <button class="primary-action" type="button" data-add-resolved ${resolved && state.erpnextVerified ? "" : "disabled"}>${state.catalogReadOnly ? "分类预览（不可申请）" : state.erpnextVerified ? "加入采购申请" : "ERPNext 离线"}</button>
      </div>
    </div>`;
    $("dialogBody").querySelectorAll("[data-variant-key]").forEach(button => {
      button.onclick = () => {
        state.variantQuantity = Math.max(0.001, Number($("dialogBody").querySelector("[data-variant-qty]")?.value || state.variantQuantity || 1));
        state.variantSelections[button.dataset.variantKey] = button.dataset.variantValue;
        renderVariantSelector();
      };
    });
    const addButton = $("dialogBody").querySelector("[data-add-resolved]");
    if (resolved && state.erpnextVerified) addButton.onclick = () => {
      const qty = Math.max(0.001, Number($("dialogBody").querySelector("[data-variant-qty]")?.value || state.variantQuantity || 1));
      addRowToCart(resolved, qty);
      $("materialDialog").close();
    };
  }

  function setFilter(key, value) {
    state.filters[key] = value;
    state.filters.page = 1;
    loadCatalog();
  }

  function resetFilters() {
    state.filters = { ...state.filters, q: "", segment: "", category: "", standardType: "", stockUom: "", page: 1 };
    $("searchInput").value = "";
    loadCatalog();
  }

  async function createDraftHandoff() {
    const rows = [...state.cart.values()];
    if (!rows.length || !state.project) return;
    if (!state.erpnextVerified) { showToast(state.catalogReadOnly ? "当前为 ChatGPT 分类只读预览，请切换到原分类后再申请" : "ERPNext 当前离线，恢复连接后才能创建申请"); return; }
    const scheduleDate = $("scheduleDate").value;
    const purpose = $("requestPurpose").value.trim();
    const requestId = `mr-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}`;
    const errorMessage = payload => {
      const path = payload?.field_path ? `（字段：${payload.field_path}）` : "";
      return `${payload?.error || "请求失败"}${path}`;
    };
    try {
      if (state.developerIdentitySwitcher && state.project?.project_code && state.employee?.user_email) {
        const contextResponse = await fetch("/api/business/context", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user: state.employee.user_email, project_code: state.project.project_code }),
        });
        const contextPayload = await contextResponse.json();
        if (!contextResponse.ok || contextPayload.ok === false) throw new Error(errorMessage(contextPayload) || "无法确认项目上下文");
      }
      const previewResponse = await fetch("/api/business/commands/preview", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "material_request.create_draft", payload: {
          schedule_date: scheduleDate,
          purpose: purpose || "现场施工使用",
          items: rows.map(row => ({ item_code: row.item_code || row.material_id, qty: row.qty, uom: row.stock_uom })),
        }}),
      });
      const preview = await previewResponse.json();
      if (!previewResponse.ok || preview.ok === false) throw new Error(errorMessage(preview) || "无法生成业务预览");
      const summary = preview.command?.summary || {};
      if (!window.confirm(`将创建材料申请草稿\n项目：${state.project.project_short_name}\n物料行：${summary.line_count || rows.length}\n总数量：${summary.quantity || "—"}\n\n不要自动提交；确认后才会写入 ERPNext。`)) return;
      const confirmResponse = await fetch(`/api/business/commands/${encodeURIComponent(preview.command.command_id)}/confirm`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: requestId }),
      });
      const result = await confirmResponse.json();
      if (!confirmResponse.ok || result.ok === false) throw new Error(errorMessage(result) || "创建材料申请失败");
      // Keep a semantic event for legacy extensions while the new portal owns the write.
      window.dispatchEvent(new CustomEvent("nexterp.material-marketplace.handoff", { detail: result.result || result }));
      state.cart.clear(); persistCart(); renderCart();
      showToast(`已创建材料申请草稿：${result.result?.name || "ERPNext 已回读"}`);
    } catch (error) { showToast(error.message); }
  }

  function openCart() { document.body.classList.add("cart-open"); $("requestPanel").classList.add("open"); }
  function closeCart() { document.body.classList.remove("cart-open"); $("requestPanel").classList.remove("open"); }
  let searchTimer = null;
  function bindEvents() {
    $("searchInput").oninput = event => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => setFilter("q", event.target.value.trim()), 260);
    };
    $("sortSelect").onchange = event => setFilter("sort", event.target.value);
    $("projectSelect").onchange = event => {
      if (!state.developerIdentitySwitcher) return;
      state.project = state.projects.find(row => row.project_code === event.target.value) || null;
      localStorage.setItem("nexterp.material-marketplace.project", event.target.value);
      renderEmployeeOptions();
    };
    $("employeeSelect").onchange = event => {
      if (!state.developerIdentitySwitcher) return;
      state.employee = (state.project?.employees || []).find(row => row.user_email === event.target.value) || null;
      localStorage.setItem("nexterp.material-marketplace.employee", event.target.value);
    };
    $("classificationSource").onchange = () => switchClassificationSource();
    $("resetFilters").onclick = resetFilters;
    $("cartToggle").onclick = openCart;
    $("cartClose").onclick = closeCart;
    $("drawerShade").onclick = closeCart;
    $("dialogClose").onclick = () => $("materialDialog").close();
    $("createDraft").onclick = createDraftHandoff;
  }

  function showToast(message) {
    $("toast").textContent = message;
    $("toast").classList.add("visible");
    window.setTimeout(() => $("toast").classList.remove("visible"), 1800);
  }

  boot();
})();
