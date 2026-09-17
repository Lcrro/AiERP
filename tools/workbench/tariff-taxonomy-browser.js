(() => {
  "use strict";

  // Compatibility: the original GPC revision endpoint remains
  // /api/reference-catalog/revision?catalog=gpc; source-aware requests below
  // add classification_source without changing the old contract.

  const get = id => document.getElementById(id);
  const numberText = value => Number(value || 0).toLocaleString("zh-CN");
  const LEGACY_HS_ENDPOINTS = {
    summary: "/api/tariff-taxonomy/summary",
    children: "/api/tariff-taxonomy/children",
    search: "/api/tariff-taxonomy/search",
    declarationProfile: "/api/tariff-declaration/profile?code=",
  };
  const pageParams = new URLSearchParams(window.location.search);
  const allowedClassificationSources = new Set(["original", "chatgpt_v4"]);
  const requestedClassificationSource = pageParams.get("classification_source") || pageParams.get("source");
  const state = {
    catalog: pageParams.get("catalog") === "gpc" ? "gpc" : "hs",
    classificationSource: allowedClassificationSources.has(requestedClassificationSource)
      ? requestedClassificationSource
      : "original",
    query: "",
    searchTimer: null,
    searchToken: 0,
    revisionTimer: null,
    refreshingRevision: false,
    sourceSwitchQueue: Promise.resolve(),
    revisions: {hs: null, gpc: null},
    materialVariantProfile: null,
    materialVariantSelections: {},
    catalogs: {
      hs: makeCatalogState(),
      gpc: makeCatalogState(),
    },
  };

  function makeCatalogState() {
    return {
      summary: null,
      roots: [],
      nodes: new Map(),
      children: new Map(),
      elements: new Map(),
      expanded: new Set(),
      selectedCode: "",
      scrollTop: 0,
      attributeToken: 0,
      materializedOnly: false,
    };
  }

  function current() {
    return state.catalogs[state.catalog];
  }

  function isChatgptClassification() {
    return state.catalog === "gpc" && state.classificationSource === "chatgpt_v4";
  }

  function visibleCode(node) {
    return isChatgptClassification() && node.display_code ? node.display_code : node.code;
  }

  function referenceUrl(path, params = new URLSearchParams()) {
    params.set("catalog", state.catalog);
    if (state.catalog === "gpc") params.set("classification_source", state.classificationSource);
    return `${path}?${params}`;
  }

  function pageUrl(code = "") {
    const params = new URLSearchParams({catalog: state.catalog});
    if (state.catalog === "gpc" && state.classificationSource !== "original") {
      params.set("classification_source", state.classificationSource);
    }
    const node = code ? current().nodes.get(code) : null;
    const hashCode = node ? visibleCode(node) : code;
    return `?${params}${hashCode ? `#code=${encodeURIComponent(hashCode)}` : ""}`;
  }

  function materialVariantAttributes(material) {
    const attributes = {
      ...(material.procurement_attributes || {}),
      ...(material.price_drivers || {}),
    };
    if (/螺栓/.test(String(material.standard_type || "")) && attributes["规格"]) {
      const normalized = String(attributes["规格"]).trim().replace(/\*/g, "×");
      const match = normalized.match(/^M\s*(\d+(?:\.\d+)?)\s*×\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*(.*)$/i);
      if (match) {
        const suffix = match[3].trim();
        delete attributes["规格"];
        return {
          "公称直径": `M${match[1]}`,
          "长度/牙型": `${match[2]} mm${suffix ? suffix : ""}`,
          ...attributes,
        };
      }
    }
    return attributes;
  }

  function materialVariantAttributeRank(key) {
    const preferred = ["牌号", "公称直径", "长度/牙型", "交货形态", "规格", "性能/质量等级", "材质/表面处理", "供货范围"];
    const index = preferred.indexOf(key);
    return index === -1 ? preferred.length : index;
  }

  function materialVariantDimensions(materials) {
    const valueSets = new Map();
    materials.forEach(material => Object.entries(materialVariantAttributes(material)).forEach(([key, value]) => {
      if (!valueSets.has(key)) valueSets.set(key, new Set());
      valueSets.get(key).add(String(value));
    }));
    return [...valueSets.entries()].map(([key, values]) => ({
      key,
      values: [...values].sort((left, right) => left.localeCompare(right, "zh-CN", {numeric: true})),
    })).sort((left, right) => materialVariantAttributeRank(left.key) - materialVariantAttributeRank(right.key)
      || (left.values.length === 1) - (right.values.length === 1)
      || left.values.length - right.values.length
      || left.key.localeCompare(right.key, "zh-CN"));
  }

  function matchingMaterialVariants(limitIndex = null, candidateKey = "", candidateValue = "") {
    const profile = state.materialVariantProfile;
    if (!profile) return [];
    const variable = profile.dimensions.filter(dimension => dimension.values.length > 1);
    return profile.materials.filter(material => {
      const attributes = materialVariantAttributes(material);
      if (candidateKey && String(attributes[candidateKey] ?? "") !== String(candidateValue)) return false;
      return variable.every((dimension, index) => {
        if (limitIndex !== null && index >= limitIndex) return true;
        const selected = state.materialVariantSelections[dimension.key];
        return !selected || String(attributes[dimension.key] ?? "") === String(selected);
      });
    });
  }

  function renderMaterialVariantSelector() {
    const profile = state.materialVariantProfile;
    if (!profile) return;
    const body = get("material-variant-body");
    body.replaceChildren();
    const eyebrow = document.createElement("p");
    eyebrow.className = "material-variant-eyebrow";
    eyebrow.textContent = `标准类型 · ${numberText(profile.materials.length)} 种已录入规格`;
    const title = document.createElement("h2");
    title.id = "material-variant-title";
    title.textContent = profile.standardType;
    const note = document.createElement("p");
    note.className = "material-variant-note";
    note.textContent = "只显示已经存在的真实组合；选择前一项后，不可能组成现有物料的选项会自动禁用。";
    body.append(eyebrow, title, note);

    const variable = profile.dimensions.filter(dimension => dimension.values.length > 1);
    const fixed = profile.dimensions.filter(dimension => dimension.values.length === 1);
    variable.forEach((dimension, dimensionIndex) => {
      const fieldset = document.createElement("fieldset");
      fieldset.className = "material-variant-field";
      const legend = document.createElement("legend");
      legend.textContent = dimension.key;
      const options = document.createElement("div");
      options.className = "material-variant-options";
      dimension.values.forEach(value => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = value;
        button.setAttribute("aria-pressed", String(state.materialVariantSelections[dimension.key] === value));
        button.disabled = matchingMaterialVariants(dimensionIndex, dimension.key, value).length === 0;
        button.addEventListener("click", () => {
          state.materialVariantSelections[dimension.key] = value;
          variable.slice(dimensionIndex + 1).forEach(later => delete state.materialVariantSelections[later.key]);
          renderMaterialVariantSelector();
        });
        options.append(button);
      });
      fieldset.append(legend, options);
      body.append(fieldset);
    });

    if (fixed.length) {
      const fixedSummary = document.createElement("div");
      fixedSummary.className = "material-variant-fixed";
      fixed.forEach(dimension => {
        const item = document.createElement("span");
        item.append(document.createTextNode(dimension.key));
        const value = document.createElement("strong");
        value.textContent = dimension.values[0];
        item.append(value);
        fixedSummary.append(item);
      });
      body.append(fixedSummary);
    }

    const allSelected = variable.every(dimension => state.materialVariantSelections[dimension.key]);
    const matches = allSelected ? matchingMaterialVariants() : [];
    const resolution = document.createElement("section");
    resolution.className = `material-variant-resolution ${matches.length === 1 ? "resolved" : ""}`;
    const label = document.createElement("span");
    if (matches.length === 1) {
      const material = matches[0];
      label.textContent = "已定位具体物料";
      const name = document.createElement("strong");
      name.textContent = material.material_name;
      const code = document.createElement("code");
      code.textContent = material.item_code || material.material_id;
      const meta = document.createElement("small");
      meta.textContent = `库存单位：${material.stock_uom || "—"} · 状态：${material.review_status || "已整理"}`;
      resolution.append(label, name, code, meta);
    } else if (allSelected && matches.length > 1) {
      label.textContent = "该组合对应多条记录";
      const name = document.createElement("strong");
      name.textContent = "这些记录的规格字段仍不足以区分唯一物料";
      resolution.append(label, name);
      matches.slice(0, 8).forEach(material => {
        const record = document.createElement("small");
        record.textContent = `${material.material_name} · ${material.item_code || material.material_id}`;
        resolution.append(record);
      });
    } else {
      label.textContent = "继续选择规格";
      const name = document.createElement("strong");
      name.textContent = `${variable.filter(dimension => !state.materialVariantSelections[dimension.key]).length} 项属性尚未选择`;
      resolution.append(label, name);
    }
    body.append(resolution);
  }

  function openMaterialVariantSelector(materials, standardType) {
    const dimensions = materialVariantDimensions(materials);
    state.materialVariantProfile = {materials, standardType, dimensions};
    state.materialVariantSelections = Object.fromEntries(
      dimensions.filter(dimension => dimension.values.length === 1).map(dimension => [dimension.key, dimension.values[0]])
    );
    renderMaterialVariantSelector();
    get("material-variant-dialog").showModal();
  }

  async function requestJson(url) {
    const response = await fetch(url, {cache: "no-store"});
    const body = await response.json();
    if (!response.ok || !body.ok) throw new Error(body.error || `请求失败 (${response.status})`);
    return body;
  }

  function levelMeta(kind) {
    const summary = current().summary || {};
    const level = (summary.levels || []).find(row => row.kind === kind);
    return level || {kind, label: kind, label_zh: kind, count: 0, level: 0};
  }

  function displayName(node) {
    return node.working_name || node.name || node.official_name || node.code;
  }

  function registerNodes(nodes) {
    nodes.forEach(node => current().nodes.set(node.code, node));
    updateVisibleCount();
  }

  function updateVisibleCount() {
    get("visible-count").textContent = numberText(current().elements.size);
  }

  function childText(node) {
    if (!node.has_children) return node.page ? `第 ${node.page} 页` : "末级";
    if (state.catalog === "gpc" && Number(node.internal_child_count || 0) > 0) return `${numberText(node.child_count)} 个子级`;
    const meta = levelMeta(node.kind);
    const child = (current().summary.levels || []).find(row => Number(row.level) === Number(node.level) + 1);
    return `${numberText(node.child_count)} ${child ? (child.label_zh || child.label) : meta.label_zh}`;
  }

  function createTreeNode(node) {
    const item = document.createElement("li");
    item.className = `tree-node kind-${node.kind}`;
    item.dataset.code = node.code;
    item.setAttribute("role", "treeitem");
    item.setAttribute("aria-level", String(Number(node.level) + 1));
    if (node.has_children) item.setAttribute("aria-expanded", "false");

    const row = document.createElement("div");
    row.className = "node-row";
    const toggle = document.createElement(node.has_children ? "button" : "span");
    toggle.className = node.has_children ? "node-toggle" : "node-spacer";
    if (node.has_children) {
      toggle.type = "button";
      toggle.setAttribute("aria-label", `展开 ${displayName(node)}`);
      toggle.addEventListener("click", () => toggleNode(node.code));
    }
    const code = document.createElement("code");
    code.className = "node-code";
    code.textContent = visibleCode(node);
    code.title = visibleCode(node);
    const name = document.createElement("button");
    name.type = "button";
    name.className = "node-name";
    name.textContent = displayName(node);
    name.title = node.official_name && node.official_name !== displayName(node) ? node.official_name : displayName(node);
    name.addEventListener("click", () => selectNode(node.code));
    if (state.catalog === "gpc" && node.translation_status === "missing") {
      const badge = document.createElement("small");
      badge.className = "translation-badge missing";
      badge.textContent = "中文待补";
      name.append(" ", badge);
    }
    const meta = document.createElement("span");
    meta.className = "node-meta";
    const hierarchyMeta = document.createElement("span");
    hierarchyMeta.textContent = childText(node);
    meta.append(hierarchyMeta);
    if (state.catalog === "gpc" && Number(node.actual_material_count || 0) > 0) {
      const materialBadge = document.createElement("strong");
      materialBadge.className = "material-count-badge";
      materialBadge.textContent = `${numberText(node.actual_material_count)} 项物料`;
      meta.append(materialBadge);
    }
    row.append(toggle, code, name, meta);
    item.append(row);
    if (node.has_children) {
      const children = document.createElement("ul");
      children.className = "node-children";
      children.setAttribute("role", "group");
      children.hidden = true;
      item.append(children);
    }
    current().elements.set(node.code, item);
    return item;
  }

  function renderTreeRows(container, rows) {
    const fragment = document.createDocumentFragment();
    rows.forEach(node => fragment.append(createTreeNode(node)));
    container.append(fragment);
    updateVisibleCount();
  }

  // Kept as a named helper for the HS compatibility tests and old bookmarks.
  async function loadChildren(parentCode) {
    const catalogState = current();
    const materializedOnly = state.catalog === "gpc" && catalogState.materializedOnly;
    const cacheKey = `${materializedOnly ? "materialized" : "all"}:${parentCode}`;
    if (catalogState.children.has(cacheKey)) return catalogState.children.get(cacheKey);
    const params = new URLSearchParams({catalog: state.catalog});
    if (parentCode) params.set("parent_code", parentCode);
    if (materializedOnly) params.set("materialized_only", "true");
    const body = await requestJson(referenceUrl("/api/reference-catalog/children", params));
    catalogState.children.set(cacheKey, body.rows);
    registerNodes(body.rows);
    return body.rows;
  }

  async function expandNode(code) {
    const item = current().elements.get(code);
    const node = current().nodes.get(code);
    if (!item || !node || !node.has_children) return;
    const childList = item.querySelector(":scope > .node-children");
    if (!childList.dataset.loaded) {
      const rows = await loadChildren(code);
      renderTreeRows(childList, rows);
      childList.dataset.loaded = "true";
    }
    item.classList.add("expanded");
    item.setAttribute("aria-expanded", "true");
    item.querySelector(":scope > .node-row .node-toggle").setAttribute("aria-label", `折叠 ${displayName(node)}`);
    childList.hidden = false;
    current().expanded.add(code);
  }

  function collapseNode(code) {
    const item = current().elements.get(code);
    const node = current().nodes.get(code);
    if (!item || !node || !node.has_children) return;
    item.classList.remove("expanded");
    item.setAttribute("aria-expanded", "false");
    item.querySelector(":scope > .node-row .node-toggle").setAttribute("aria-label", `展开 ${displayName(node)}`);
    const childList = item.querySelector(":scope > .node-children");
    if (childList) childList.hidden = true;
    current().expanded.delete(code);
  }

  async function toggleNode(code) {
    if (current().expanded.has(code)) collapseNode(code);
    else await expandNode(code);
  }

  function pathFromLoadedNode(code) {
    const path = [];
    let node = current().nodes.get(code);
    const seen = new Set();
    while (node && !seen.has(node.code)) {
      seen.add(node.code);
      path.push(node);
      node = node.parent_code ? current().nodes.get(node.parent_code) : null;
    }
    return path.reverse();
  }

  function renderBreadcrumb(path) {
    const breadcrumb = get("tree-breadcrumb");
    breadcrumb.replaceChildren();
    const root = document.createElement("span");
    root.textContent = "完整目录";
    breadcrumb.append(root);
    path.forEach(node => {
      const step = document.createElement("span");
      step.textContent = `${visibleCode(node)} ${displayName(node)}`;
      step.title = node.official_name || step.textContent;
      breadcrumb.append(step);
    });
  }

  function renderAttributeList(id, values, emptyText) {
    const target = get(id);
    target.replaceChildren();
    if (!values || !values.length) {
      const empty = document.createElement("span");
      empty.className = "attribute-empty";
      empty.textContent = emptyText;
      target.append(empty);
      return;
    }
    values.forEach(value => {
      const chip = document.createElement("span");
      chip.className = "attribute-chip";
      chip.textContent = typeof value === "string" ? value : `${value.name || value.title || value.code}${value.code ? ` (${value.code})` : ""}`;
      chip.title = typeof value === "string" ? value : (value.definition || "");
      if (typeof value !== "string" && value.code) chip.dataset.code = value.code;
      if (typeof value !== "string" && value.attribute_code) chip.dataset.attributeCode = value.attribute_code;
      if (typeof value !== "string" && value.term_kind) chip.dataset.termKind = value.term_kind;
      target.append(chip);
    });
  }

  function renderActualMaterials(node, materials = null) {
    const section = get("actual-materials-section");
    const count = Number(node.actual_material_count || node.direct_material_count || 0);
    section.hidden = state.catalog !== "gpc" || count <= 0;
    get("actual-materials-count").textContent = `${numberText(count)} 项`;
    const list = get("actual-materials-list");
    list.replaceChildren();
    if (section.hidden) return;
    if (!(["brick", "internal_type"].includes(node.kind))) {
      get("actual-materials-message").textContent = `该目录及其下级共挂载 ${numberText(count)} 项已整理候选物料；展开到末级可查看明细。`;
      return;
    }
    if (materials === null) {
      get("actual-materials-message").textContent = `正在读取该${node.kind === "internal_type" ? "标准类型" : " Brick"}下的候选物料…`;
      return;
    }
    get("actual-materials-message").textContent = materials.length
      ? `${isChatgptClassification() ? "ChatGPT 分类已整理物料" : "多规格类型已合并展示"}；选择属性只会命中已经存在的真实物料组合。`
      : `该${node.kind === "internal_type" ? "标准类型" : " Brick"}暂无已整理候选物料。`;
    const materialGroups = new Map();
    materials.forEach(material => {
      const key = material.standard_type || material.gpc_brick_code || "未命名类型";
      if (!materialGroups.has(key)) materialGroups.set(key, []);
      materialGroups.get(key).push(material);
    });
    const singleMaterials = [];
    materialGroups.forEach((groupMaterials, standardType) => {
      if (groupMaterials.length === 1) {
        singleMaterials.push(groupMaterials[0]);
        return;
      }
      const dimensions = materialVariantDimensions(groupMaterials);
      const card = document.createElement("article");
      card.className = "actual-material-card actual-material-variant-group";
      const heading = document.createElement("div");
      heading.className = "actual-material-card-heading";
      const title = document.createElement("strong");
      title.textContent = standardType;
      const countBadge = document.createElement("span");
      countBadge.className = "material-variant-count";
      countBadge.textContent = `${numberText(groupMaterials.length)} 种规格`;
      heading.append(title, countBadge);
      const description = document.createElement("p");
      description.textContent = "同一标准类型集中选择属性，完整选择后定位到唯一具体物料。";
      const axes = document.createElement("div");
      axes.className = "material-variant-axes";
      dimensions.slice(0, 5).forEach(dimension => {
        const chip = document.createElement("span");
        chip.textContent = dimension.values.length === 1
          ? `${dimension.key}：${dimension.values[0]}`
          : `${dimension.key}：${numberText(dimension.values.length)} 种可选`;
        axes.append(chip);
      });
      const action = document.createElement("button");
      action.type = "button";
      action.className = "material-variant-open";
      action.textContent = "选择规格";
      action.addEventListener("click", () => openMaterialVariantSelector(groupMaterials, standardType));
      card.append(heading, description, axes, action);
      list.append(card);
    });
    singleMaterials.forEach(material => {
      const card = document.createElement("article");
      card.className = "actual-material-card";
      const heading = document.createElement("div");
      heading.className = "actual-material-card-heading";
      const title = document.createElement("strong");
      title.textContent = material.material_name || material.standard_type || material.material_id;
      const status = document.createElement("span");
      status.className = `material-review-status ${material.completeness_status === "完整" ? "complete" : (material.review_status === "待补信息" ? "needs-info" : "pending")}`;
      status.textContent = material.review_status || "待业务确认";
      heading.append(title, status);
      const meta = document.createElement("p");
      const metaParts = [material.item_code || material.material_id];
      if (material.standard_type) metaParts.push(`标准类型：${material.standard_type}`);
      if (material.stock_uom) metaParts.push(`库存单位：${material.stock_uom}`);
      if (material.source_rows && material.source_rows.length) metaParts.push(`来源行：${material.source_rows.join("、")}`);
      meta.textContent = metaParts.filter(Boolean).join(" · ");
      card.append(heading, meta);
      if (material.procurement_profile) {
        const policy = document.createElement("section");
        policy.className = "material-procurement-policy";
        const template = document.createElement("strong");
        template.textContent = `主模板：${material.procurement_profile.main_template_name}`;
        const constraintText = (material.procurement_profile.constraint_names || []).length
          ? ` · 叠加：${material.procurement_profile.constraint_names.join("、")}`
          : " · 无叠加约束";
        const rule = document.createElement("p");
        rule.textContent = `${material.procurement_profile.record_policy_label}${constraintText}`;
        policy.append(template, rule);
        card.append(policy);
        const roleDetails = document.createElement("details");
        roleDetails.className = "material-role-details";
        const summary = document.createElement("summary");
        summary.textContent = "查看属性角色";
        roleDetails.append(summary);
        const roleLabels = {
          sku_identity: "SKU身份",
          transaction: "项目/交易",
          supplier_offer: "供应报价",
        };
        Object.entries(material.attribute_roles || {}).forEach(([role, values]) => {
          const rows = Object.entries(values || {});
          if (!rows.length) return;
          const line = document.createElement("p");
          line.innerHTML = `<strong>${roleLabels[role] || role}：</strong>`;
          line.append(document.createTextNode(rows.map(([key]) => key.split(".").slice(1).join(".")).join("、")));
          roleDetails.append(line);
        });
        card.append(roleDetails);
      }
      const appendAttributeGroup = (label, values, className) => {
        const attributes = Object.entries(values || {});
        if (!attributes.length) return;
        const group = document.createElement("section");
        group.className = `material-field-group ${className}`;
        const groupLabel = document.createElement("strong");
        groupLabel.textContent = label;
        const chips = document.createElement("div");
        chips.className = "actual-material-attributes";
        attributes.forEach(([key, value]) => {
          const chip = document.createElement("span");
          chip.textContent = `${key}：${value}`;
          chips.append(chip);
        });
        group.append(groupLabel, chips);
        card.append(group);
      };
      appendAttributeGroup("采购必选", material.procurement_attributes, "procurement-fields");
      appendAttributeGroup("价格 / 适配关键", material.price_drivers, "price-fields");
      if ((material.gpc_notes || []).length) {
        const group = document.createElement("section");
        group.className = "material-field-group gpc-notes";
        const groupLabel = document.createElement("strong");
        groupLabel.textContent = "分类依据";
        const notes = document.createElement("ul");
        material.gpc_notes.forEach(value => {
          const note = document.createElement("li");
          note.textContent = value;
          notes.append(note);
        });
        group.append(groupLabel, notes);
        card.append(group);
      }
      (material.questions || []).forEach(question => {
        const warning = document.createElement("p");
        warning.className = "material-question";
        warning.textContent = `待确认：${question}`;
        card.append(warning);
      });
      list.append(card);
    });
  }

  function highlightProfileTerm(termCode, attributeCode = "") {
    const chips = Array.from(get("detail-gpc-attributes").querySelectorAll(".attribute-chip"));
    chips.forEach(chip => chip.classList.remove("profile-term-highlight"));
    const target = chips.find(chip => chip.dataset.code === termCode && (!attributeCode || chip.dataset.attributeCode === attributeCode));
    if (!target) return;
    target.classList.add("profile-term-highlight");
    target.scrollIntoView({behavior: "smooth", block: "center"});
  }

  function resetDetailEvidence(node) {
    const status = get("detail-attribute-status");
    const message = get("detail-attribute-message");
    get("detail-evidence-label").textContent = isChatgptClassification() ? "分类属性详情" : (state.catalog === "gpc" ? "目录属性详情" : "申报属性证据");
    get("detail-attribute-body").hidden = true;
    get("detail-gpc-definition").hidden = true;
    status.className = "attribute-status pending";
    status.textContent = ["brick", "internal_type", "sku"].includes(node.kind) ? "正在读取" : "结构节点";
    message.textContent = "选择末级节点后读取该参考目录的详情。";
    renderAttributeList("detail-classification-attributes", [], "等待末级详情");
    renderAttributeList("detail-declaration-attributes", [], "等待末级详情");
    get("detail-source-page").textContent = "—";
    get("detail-source-text").textContent = "";
  }

  async function loadAttributeEvidence(node) {
    const catalogState = current();
    const token = ++catalogState.attributeToken;
    if (state.catalog === "hs" && node.kind !== "sku") return;
    if (state.catalog === "gpc" && !(["brick", "internal_type"].includes(node.kind))) return;
    try {
      // HS keeps its established declaration evidence endpoint.
      const url = state.catalog === "hs"
        ? `${LEGACY_HS_ENDPOINTS.declarationProfile}${encodeURIComponent(node.code)}`
        : referenceUrl("/api/reference-catalog/profile", new URLSearchParams({code: node.code}));
      const body = await requestJson(url);
      if (token !== catalogState.attributeToken || catalogState.selectedCode !== node.code) return;
      const status = get("detail-attribute-status");
      const message = get("detail-attribute-message");
      if (state.catalog === "gpc") {
        const profile = body;
        const isBusinessType = profile.is_gpc === false;
        renderActualMaterials(node, profile.actual_materials || []);
        status.className = "attribute-status available";
        status.textContent = profile.attributes && profile.attributes.length ? "已读取" : "无属性";
        message.textContent = isBusinessType
          ? (isChatgptClassification() ? "ChatGPT 分类详情：属性和值仅用于分类预览，正式物料仍以 ERPNext 为准。" : "标准类型详情：属性和值仅展示在详情面板。")
          : "GPC 砖块详情：属性和值仅展示在详情面板，不作为第五层节点。";
        get("detail-attribute-body").hidden = false;
        get("detail-gpc-definition").hidden = isBusinessType && !isChatgptClassification();
        const includesOfficial = profile.includes_official || profile.definition_official || profile.includes || profile.definition || "";
        const includesWorking = profile.includes_working || profile.definition_working || includesOfficial;
        const excludesOfficial = profile.excludes_official || profile.excludes || "";
        const excludesWorking = profile.excludes_working || excludesOfficial;
        get("detail-gpc-includes").textContent = includesWorking || "—";
        get("detail-gpc-excludes").textContent = excludesWorking || "—";
        const includesOfficialBox = get("detail-gpc-includes-official");
        includesOfficialBox.hidden = !includesOfficial || includesOfficial === includesWorking;
        includesOfficialBox.open = false;
        includesOfficialBox.querySelector("p").textContent = includesOfficial;
        const excludesOfficialBox = get("detail-gpc-excludes-official");
        excludesOfficialBox.hidden = !excludesOfficial || excludesOfficial === excludesWorking;
        excludesOfficialBox.open = false;
        excludesOfficialBox.querySelector("p").textContent = excludesOfficial;
        const attrValues = [];
        (profile.attributes || []).forEach(attribute => {
          const attributeName = attribute.working_name || attribute.name;
          const attributeOfficial = attribute.official_name || attribute.name;
          attrValues.push({
            name: attributeOfficial && attributeOfficial !== attributeName ? `${attributeName} / ${attributeOfficial}` : attributeName,
            code: attribute.code,
            definition: attribute.definition,
            attribute_code: attribute.code,
            term_kind: "attribute",
          });
          (attribute.values || []).forEach(value => {
            const valueName = value.working_name || value.name;
            const valueOfficial = value.official_name || value.name;
            attrValues.push({
              name: `↳ ${valueOfficial && valueOfficial !== valueName ? `${valueName} / ${valueOfficial}` : valueName}`,
              code: value.code,
              definition: value.definition,
              attribute_code: attribute.code,
              term_kind: "attribute_value",
            });
          });
        });
        get("detail-gpc-attributes-label").textContent = isBusinessType ? "类型属性与可选值" : "GPC 分类属性与可选值";
        renderAttributeList("detail-gpc-attributes", attrValues, isBusinessType ? "该标准类型暂无属性" : "该 Brick 暂无属性");
        renderAttributeList("detail-classification-attributes", [], isBusinessType ? "类型属性见上方" : "GPC 属性见上方");
        renderAttributeList("detail-declaration-attributes", [], isBusinessType ? "该标准类型不提供 HS 申报要素" : "GPC 不提供 HS 申报要素");
        get("detail-source-page").textContent = isChatgptClassification()
          ? "ChatGPT 分类（龙华 V4）"
          : (isBusinessType ? "物料分类工作台" : "GS1 GPC 2026-05 XML");
        get("detail-source-text").textContent = isChatgptClassification()
          ? "来源于龙华项目公司标准物料示范清单第四轮附件治理工作簿；仅用于分类预览。"
          : (isBusinessType ? "用于组织实际采购物料。" : (profile.official_name || ""));
        return;
      }
      const profile = body.profile;
      if (body.status === "available" && profile) {
        status.className = "attribute-status available";
        status.textContent = "已读取";
        message.textContent = body.message;
        get("detail-attribute-body").hidden = false;
        renderAttributeList("detail-classification-attributes", profile.classification_attributes, "未派生分类属性");
        renderAttributeList("detail-declaration-attributes", profile.declaration_attributes, "目录未列出申报要素");
        get("detail-source-page").textContent = profile.page ? `PDF 第 ${profile.page} 页` : "页码未知";
        get("detail-source-text").textContent = profile.source_text || "未保留原文行";
      } else {
        status.className = `attribute-status ${body.status === "no_attributes" ? "empty" : "missing"}`;
        status.textContent = body.status === "no_attributes" ? "无属性" : "未覆盖";
        message.textContent = body.message || "未找到属性证据";
      }
    } catch (error) {
      if (token !== catalogState.attributeToken || catalogState.selectedCode !== node.code) return;
      get("detail-attribute-status").className = "attribute-status missing";
      get("detail-attribute-status").textContent = "读取失败";
      get("detail-attribute-message").textContent = error.message || "详情接口读取失败";
    }
  }

  function renderDetails(node, path) {
    get("inspector-empty").hidden = true;
    get("search-panel").hidden = true;
    get("detail-panel").hidden = false;
    const meta = levelMeta(node.kind);
    get("detail-kind").textContent = `${node.kind_label_zh || meta.label_zh || meta.label} · 第 ${Number(node.level) + 1} 层`;
    get("detail-code").textContent = visibleCode(node);
    get("detail-code").hidden = false;
    get("detail-name").textContent = displayName(node);
    get("detail-official-name").textContent = state.catalog === "gpc" && node.official_name && node.official_name !== displayName(node)
      ? `官方英文：${node.official_name}` : "";
    get("detail-children").textContent = node.has_children ? `${numberText(node.child_count)} 个` : "无";
    get("detail-page").textContent = node.page
      ? `PDF 第 ${node.page} 页`
      : (state.catalog === "gpc"
          ? (isChatgptClassification() ? "ChatGPT 分类（龙华 V4）" : (node.is_gpc === false ? "物料分类工作台" : "GS1 GPC 2026-05"))
        : "目录范围节点");
    const pathBox = get("detail-path");
    pathBox.replaceChildren();
    path.forEach(step => {
      const row = document.createElement("div");
      row.className = "path-step";
      const code = document.createElement("code");
      code.textContent = visibleCode(step);
      const name = document.createElement("span");
      name.textContent = displayName(step);
      row.append(code, name);
      pathBox.append(row);
    });
    renderActualMaterials(node);
    resetDetailEvidence(node);
  }

  async function selectNode(code, suppliedPath = null) {
    const catalogState = current();
    if (catalogState.selectedCode && catalogState.elements.has(catalogState.selectedCode)) catalogState.elements.get(catalogState.selectedCode).classList.remove("selected");
    catalogState.selectedCode = code;
    const item = catalogState.elements.get(code);
    if (item) item.classList.add("selected");
    const node = catalogState.nodes.get(code) || (suppliedPath && suppliedPath[suppliedPath.length - 1]);
    const path = suppliedPath || pathFromLoadedNode(code);
    if (node) {
      renderDetails(node, path);
      await loadAttributeEvidence(node);
    }
    renderBreadcrumb(path);
    document.querySelectorAll(".section-jump").forEach(button => button.classList.toggle("active", path[0] && button.dataset.code === path[0].code));
  }

  async function revealPath(path) {
    registerNodes(path);
    for (let index = 0; index < path.length - 1; index += 1) await expandNode(path[index].code);
    const target = path[path.length - 1];
    await selectNode(target.code, path);
    const item = current().elements.get(target.code);
    if (item) {
      item.classList.remove("reveal-target");
      void item.offsetWidth;
      item.classList.add("reveal-target");
      item.scrollIntoView({behavior: "smooth", block: "center"});
    }
    history.replaceState(null, "", pageUrl(target.code));
  }

  function renderSectionRail(rows) {
    const list = get("section-list");
    list.replaceChildren();
    const rootMeta = levelMeta(rows[0] ? rows[0].kind : "segment");
    const childMeta = (current().summary.levels || []).find(level => Number(level.level) === Number(rootMeta.level) + 1) || rootMeta;
    rows.forEach(node => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "section-jump";
      button.dataset.code = node.code;
      const code = document.createElement("code");
      code.textContent = visibleCode(node);
      const name = document.createElement("span");
      name.textContent = displayName(node);
      name.title = node.official_name || displayName(node);
      const count = document.createElement("small");
      count.textContent = state.catalog === "gpc" && Number(node.actual_material_count || 0) > 0
        ? `${numberText(node.actual_material_count)} 项物料`
        : `${node.child_count || 0} ${childMeta.label_zh || childMeta.label}`;
      button.append(code, name, count);
      button.addEventListener("click", async () => {
        await expandNode(node.code);
        selectNode(node.code);
        current().elements.get(node.code)?.scrollIntoView({behavior: "smooth", block: "start"});
      });
      list.append(button);
    });
    get("section-loaded").textContent = `${rows.length} / ${rows.length}`;
  }

  function renderProfileTermResult(row) {
    const card = document.createElement("article");
    card.className = "search-result profile-term-result";
    const top = document.createElement("span");
    top.className = "result-top";
    const code = document.createElement("code");
    code.textContent = visibleCode(row);
    const kind = document.createElement("small");
    kind.textContent = row.kind_label_zh || row.kind_label || row.kind;
    top.append(code, kind);
    const name = document.createElement("strong");
    const workingName = row.working_name || row.official_name || row.code;
    name.textContent = row.official_name && row.official_name !== workingName ? `${workingName} / ${row.official_name}` : workingName;
    const usage = document.createElement("span");
    usage.className = "term-usage";
    usage.textContent = `${numberText(row.brick_count)} 个 Brick · ${numberText(row.usage_count)} 个属性引用`;
    card.append(top, name, usage);

    const references = row.references || [];
    if (!references.length) return card;
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "term-reference-toggle";
    toggle.textContent = `查看引用位置（${references.length}${row.references_truncated ? "+" : ""}）`;
    const list = document.createElement("div");
    list.className = "term-references";
    list.hidden = true;
    references.forEach(reference => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "term-reference";
      const brickName = reference.brick_working_name || reference.brick_official_name || reference.brick_code;
      const attributeName = reference.attribute_working_name || reference.attribute_official_name || reference.attribute_code;
      const label = document.createElement("strong");
      label.textContent = `${reference.brick_code} ${brickName}`;
      const meta = document.createElement("span");
      meta.textContent = `${reference.attribute_code} ${attributeName}`;
      button.append(label, meta);
      button.addEventListener("click", async () => {
        await revealPath(reference.path || []);
        highlightProfileTerm(row.code, reference.attribute_code || "");
      });
      list.append(button);
    });
    if (row.references_truncated) {
      const note = document.createElement("small");
      note.className = "term-reference-note";
      note.textContent = `该术语共有 ${numberText(row.usage_count)} 个属性引用；当前按编码展示前 ${references.length} 个。`;
      list.append(note);
    }
    toggle.addEventListener("click", () => {
      list.hidden = !list.hidden;
      toggle.textContent = list.hidden ? `查看引用位置（${references.length}${row.references_truncated ? "+" : ""}）` : "收起引用位置";
    });
    card.append(toggle, list);
    return card;
  }

  function renderSearchResults(payload, query) {
    get("inspector-empty").hidden = true;
    get("detail-panel").hidden = true;
    get("search-panel").hidden = false;
    get("search-total").textContent = numberText(payload.total);
    get("search-note").textContent = payload.truncated ? `“${query}” 命中 ${numberText(payload.total)} 项，先显示前 ${payload.rows.length} 项` : `“${query}” 命中 ${numberText(payload.total)} 项`;
    const results = get("search-results");
    results.replaceChildren();
    if (!payload.rows.length) {
      const empty = document.createElement("div");
      empty.className = "no-results";
      empty.textContent = "没有找到匹配的编码、名称或定义";
      results.append(empty);
      return;
    }
    payload.rows.forEach(row => {
      if (row.result_type === "profile_term") {
        results.append(renderProfileTermResult(row));
        return;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "search-result";
      const top = document.createElement("span");
      top.className = "result-top";
      const code = document.createElement("code");
      code.textContent = visibleCode(row);
      const kind = document.createElement("small");
      kind.textContent = row.kind_label_zh || row.kind_label || row.kind;
      top.append(code, kind);
      const name = document.createElement("strong");
      name.textContent = displayName(row);
      const path = document.createElement("span");
      path.className = "result-path";
      path.textContent = (row.path || []).map(step => visibleCode(step)).join(" → ");
      button.append(top, name, path);
      button.addEventListener("click", () => revealPath(row.path));
      results.append(button);
    });
  }

  async function runSearch() {
    const query = get("taxonomy-search").value.trim();
    state.query = query;
    get("clear-search").hidden = !query;
    if (!query) {
      get("search-panel").hidden = true;
      if (current().selectedCode) selectNode(current().selectedCode);
      else get("inspector-empty").hidden = false;
      return;
    }
    const token = ++state.searchToken;
    const params = new URLSearchParams({q: query, kind: get("kind-filter").value, limit: "200"});
    if (state.catalog === "gpc" && current().materializedOnly) params.set("materialized_only", "true");
    try {
      const payload = await requestJson(referenceUrl("/api/reference-catalog/search", params));
      if (token !== state.searchToken) return;
      registerNodes(payload.rows.filter(row => row.result_type !== "profile_term"));
      renderSearchResults(payload, query);
    } catch (error) {
      if (token !== state.searchToken) return;
      get("search-note").textContent = error.message;
    }
  }

  async function expandToChapters() {
    get("expand-chapters").disabled = true;
    get("expand-chapters").textContent = "正在展开…";
    try {
      for (const root of current().roots) await expandNode(root.code);
    } finally {
      get("expand-chapters").disabled = false;
      get("expand-chapters").textContent = state.catalog === "hs" ? "展开到章" : "展开下一层";
    }
  }

  function collapseAll() {
    Array.from(current().expanded).forEach(collapseNode);
    current().selectedCode = "";
    get("detail-panel").hidden = true;
    get("search-panel").hidden = true;
    get("inspector-empty").hidden = false;
    renderBreadcrumb([]);
    get("tree-scroll").scrollTo({top: 0, behavior: "smooth"});
  }

  async function locateHashCode() {
    const match = window.location.hash.match(/(?:^#|&)code=([^&]+)/);
    if (!match) return;
    const code = decodeURIComponent(match[1]);
    const params = new URLSearchParams({q: code, limit: "10"});
    if (state.catalog === "gpc" && current().materializedOnly) params.set("materialized_only", "true");
    const payload = await requestJson(referenceUrl("/api/reference-catalog/search", params));
    const exact = payload.rows.find(row => row.code === code || row.display_code === code);
    if (exact) await revealPath(exact.path);
  }

  function renderStructure() {
    const strip = get("structure-strip");
    strip.replaceChildren();
    (current().summary.levels || []).forEach((level, index, levels) => {
      const card = document.createElement("article");
      card.className = `structure-card level-${level.kind}`;
      const hsOrdinals = {section: "01", chapter: "02", heading: "04", subheading: "06", sku: "08"};
      const ordinal = state.catalog === "hs" && hsOrdinals[level.kind] ? hsOrdinals[level.kind] : String((Number(level.level) || 0) + 1).padStart(2, "0");
      const visibleLevelCount = state.catalog === "gpc" && current().materializedOnly
        ? Number((current().summary.materialized_counts || {})[level.kind] || 0)
          + (level.kind === "brick" ? Number((current().summary.materialized_counts || {}).internal_brick || 0) : 0)
        : level.count;
      card.innerHTML = `<span>${ordinal}</span><div><strong id="count-${level.kind}">${numberText(visibleLevelCount)}</strong><small>${level.label_zh || level.label} · ${level.label}</small></div>`;
      strip.append(card);
      if (index < levels.length - 1) {
        const arrow = document.createElement("span");
        arrow.className = "flow-arrow";
        arrow.textContent = "→";
        strip.append(arrow);
      }
    });
  }

  function renderFilters() {
    const filter = get("kind-filter");
    const selected = filter.value;
    filter.replaceChildren(new Option("全部层级", ""));
    (current().summary.levels || []).forEach(level => filter.append(new Option(level.label_zh || level.label, level.kind)));
    filter.value = (current().summary.levels || []).some(level => level.kind === selected) ? selected : "";
  }

  function updateCatalogCopy() {
    const summary = current().summary;
    const isGpc = state.catalog === "gpc";
    const chatgpt = isChatgptClassification();
    get("catalog-title").textContent = chatgpt ? "从 ChatGPT 分类看到物料族" : (isGpc ? "从 Segment 一路看到标准类型" : "从“类”一路看到八位税号");
    get("catalog-description").textContent = chatgpt
      ? "ChatGPT 分类 V4 的龙华项目物料目录。原 GPC 可随时切换；此版本仅作分类预览，正式采购和 ERPNext 编码仍以已发布主数据为准。"
      : (isGpc
        ? "以 GS1 GPC 2026-05 为参考骨架，并在末级统一按物料族、标准类型和实际规格整理。"
        : "内部只读参考目录。保留《中华人民共和国进出口税则（2026）》的完整五层结构，逐层展开、折叠或搜索。");
    get("source-status").querySelector("strong").textContent = `${chatgpt ? "ChatGPT 分类 V4" : (summary.source_version || "参考目录")} · ${numberText(summary.total_nodes)} 节点`;
    get("source-status").querySelector("small").textContent = summary.hierarchy_complete
      ? `${isGpc ? `${numberText(summary.actual_material_count)} 项物料 · ` : ""}父级完整 · ${chatgpt ? "仅供分类预览" : "内部只读参考目录"}`
      : "层级需要复核";
    get("footer-meta").textContent = `${summary.source || "参考目录"} · ${summary.source_version || ""} · ${numberText(summary.total_nodes)} 节点`;
    get("rail-eyebrow").textContent = isGpc ? "SEGMENT INDEX" : "SECTION INDEX";
    const visibleRootCount = isGpc && current().materializedOnly ? current().roots.length : (summary.root_count || current().roots.length);
    get("rail-title").textContent = `${visibleRootCount} ${isGpc ? "Segments" : "类"}`;
    get("expand-chapters").textContent = isGpc ? "展开下一层" : "展开到章";
    get("material-filter-control").hidden = !isGpc || chatgpt;
    get("materialized-only").checked = isGpc && !chatgpt && current().materializedOnly;
    get("material-count-summary").textContent = isGpc && !chatgpt
      ? `${numberText(summary.actual_material_count)} 项实际物料 · ${numberText(summary.materialized_brick_count)} 个末级分类`
      : "";
    const sourceSelect = get("classification-source");
    if (sourceSelect) {
      sourceSelect.value = state.classificationSource;
      sourceSelect.disabled = !isGpc;
    }
    document.querySelectorAll(".catalog-button").forEach(button => {
      button.classList.toggle("active", button.dataset.catalog === state.catalog);
      button.setAttribute("aria-selected", button.dataset.catalog === state.catalog ? "true" : "false");
    });
  }

  function saveCatalogView() {
    const catalogState = current();
    catalogState.scrollTop = get("tree-scroll").scrollTop;
  }

  async function initializeCatalog(catalog) {
    state.catalog = catalog;
    const catalogState = current();
    if (!catalogState.summary) {
      const body = await requestJson(referenceUrl("/api/reference-catalog/summary"));
      if (!body.summary.available) throw new Error(body.summary.message || "GPC 尚未导入");
      catalogState.summary = body.summary;
      catalogState.roots = await loadChildren("");
    }
    updateCatalogCopy();
    renderStructure();
    renderFilters();
    get("tree-loading").hidden = true;
    get("taxonomy-tree").replaceChildren();
    catalogState.elements.clear();
    registerNodes(catalogState.roots);
    renderTreeRows(get("taxonomy-tree"), catalogState.roots);
    renderSectionRail(catalogState.roots);
    // Expansion order is naturally parent-first. Keeping insertion order also
    // lets a database revision rebuild the tree before descendants are loaded.
    const expandedCodes = [...catalogState.expanded];
    for (const code of expandedCodes) {
      if (catalogState.elements.has(code)) await expandNode(code);
    }
    get("tree-scroll").scrollTop = catalogState.scrollTop || 0;
    if (catalogState.selectedCode && catalogState.nodes.has(catalogState.selectedCode)) {
      await selectNode(catalogState.selectedCode);
    }
    if (state.query) {
      get("taxonomy-search").value = state.query;
      await runSearch();
    }
  }

  async function reloadMaterializedTree() {
    if (state.catalog !== "gpc") return;
    const catalogState = current();
    get("tree-loading").hidden = false;
    get("tree-loading").replaceChildren(document.createElement("span"), document.createTextNode(
      catalogState.materializedOnly ? "正在筛选有实际物料的目录…" : "正在恢复完整 GPC 目录…"
    ));
    get("tree-loading").firstChild.className = "spinner";
    catalogState.children.clear();
    catalogState.nodes.clear();
    catalogState.elements.clear();
    catalogState.expanded.clear();
    catalogState.selectedCode = "";
    catalogState.roots = await loadChildren("");
    get("taxonomy-tree").replaceChildren();
    registerNodes(catalogState.roots);
    renderTreeRows(get("taxonomy-tree"), catalogState.roots);
    renderSectionRail(catalogState.roots);
    renderStructure();
    updateCatalogCopy();
    renderBreadcrumb([]);
    get("detail-panel").hidden = true;
    get("search-panel").hidden = true;
    get("inspector-empty").hidden = false;
    get("tree-loading").hidden = true;
    if (state.query) await runSearch();
  }

  async function switchCatalog(catalog) {
    if (catalog === state.catalog) return;
    saveCatalogView();
    get("tree-loading").hidden = false;
    get("tree-loading").replaceChildren(document.createElement("span"), document.createTextNode(`正在读取 ${catalog === "gpc" ? "GPC 2026-05" : "HS 2026"}…`));
    get("tree-loading").firstChild.className = "spinner";
    try {
      await initializeCatalog(catalog);
      history.replaceState(null, "", pageUrl(current().selectedCode));
      get("catalog-availability").textContent = "";
    } catch (error) {
      get("tree-loading").hidden = false;
      get("tree-loading").textContent = error.message || "参考目录不可用";
      get("catalog-availability").textContent = "GPC 未导入：运行 python scripts/material_master/import_gpc_reference.py --version 2026-05";
    }
  }

  function switchClassificationSource(source) {
    const next = allowedClassificationSources.has(source) ? source : "original";
    state.sourceSwitchQueue = state.sourceSwitchQueue.then(async () => {
      if (state.catalog !== "gpc" || next === state.classificationSource) return;
      saveCatalogView();
      state.classificationSource = next;
      state.revisions.gpc = null;
      const catalogState = current();
      catalogState.summary = null;
      catalogState.roots = [];
      catalogState.nodes.clear();
      catalogState.children.clear();
      catalogState.elements.clear();
      catalogState.expanded.clear();
      catalogState.selectedCode = "";
      catalogState.materializedOnly = false;
      get("tree-loading").hidden = false;
      get("tree-loading").replaceChildren(document.createElement("span"), document.createTextNode(
        next === "chatgpt_v4" ? "正在读取 ChatGPT 分类 V4…" : "正在恢复原 GPC 分类…"
      ));
      get("tree-loading").firstChild.className = "spinner";
      try {
        await initializeCatalog("gpc");
        history.replaceState(null, "", pageUrl());
        get("catalog-availability").textContent = "";
      } catch (error) {
        get("tree-loading").hidden = false;
        get("tree-loading").textContent = error.message || "分类来源不可用";
        get("catalog-availability").textContent = "ChatGPT 分类包不可用，请检查发布包";
      }
    });
    return state.sourceSwitchQueue;
  }

  async function refreshCatalogRevision(catalog, revision) {
    const catalogState = state.catalogs[catalog];
    const selectedCode = catalogState.selectedCode;
    const scrollTop = catalogState.scrollTop || get("tree-scroll").scrollTop;
    catalogState.summary = null;
    catalogState.roots = [];
    catalogState.nodes.clear();
    catalogState.children.clear();
    catalogState.elements.clear();
    catalogState.scrollTop = scrollTop;
    if (state.catalog !== catalog) return;
    state.refreshingRevision = true;
    try {
      get("catalog-availability").textContent = `目录数据库 r${revision} 已更新，正在同步页面…`;
      await initializeCatalog(catalog);
      if (selectedCode && !catalogState.nodes.has(selectedCode)) {
        const params = new URLSearchParams({catalog, q: selectedCode, limit: "10"});
        if (catalogState.materializedOnly) params.set("materialized_only", "true");
        const payload = await requestJson(referenceUrl("/api/reference-catalog/search", params));
        const exact = payload.rows.find(row => row.code === selectedCode);
        if (exact) await revealPath(exact.path);
      }
      get("catalog-availability").textContent = `SQLite r${revision} · 已自动同步`;
    } finally {
      state.refreshingRevision = false;
    }
  }

  async function pollCatalogRevision() {
    if (state.refreshingRevision || document.hidden) return;
    try {
      const payload = await requestJson(referenceUrl("/api/reference-catalog/revision"));
      if (!payload.available) return;
      const nextRevision = String(payload.revision);
      const previousRevision = state.revisions.gpc;
      state.revisions.gpc = nextRevision;
      if (previousRevision !== null && previousRevision !== nextRevision) {
        await refreshCatalogRevision("gpc", nextRevision);
      }
    } catch (_error) {
      // Revision polling is an enhancement; a transient request failure must
      // not hide an otherwise usable read-only catalog.
    }
  }

  async function initialize() {
    document.querySelectorAll(".catalog-button").forEach(button => button.addEventListener("click", () => switchCatalog(button.dataset.catalog)));
    const sourceSelect = get("classification-source");
    if (sourceSelect) sourceSelect.addEventListener("change", event => switchClassificationSource(event.target.value));
    try {
      await initializeCatalog(state.catalog);
      // Probe GPC availability without replacing the HS default view.
      if (state.catalog === "hs") {
        const gpcSummary = await requestJson(referenceUrl("/api/reference-catalog/summary", new URLSearchParams({catalog: "gpc"})));
        const gpcButton = document.querySelector('[data-catalog="gpc"]');
        if (!gpcSummary.summary.available) {
          gpcButton.disabled = true;
          get("catalog-availability").textContent = "GPC 尚未导入";
        }
      }
      await locateHashCode();
      await pollCatalogRevision();
      state.revisionTimer = window.setInterval(pollCatalogRevision, 2500);
    } catch (error) {
      const loading = get("tree-loading");
      const title = document.createElement("strong");
      title.textContent = "无法读取参考目录：";
      loading.replaceChildren(title, document.createTextNode(String(error.message || error)));
      if (state.catalog === "gpc") {
        const gpcButton = document.querySelector('[data-catalog="gpc"]');
        if (gpcButton) gpcButton.disabled = true;
        get("catalog-availability").textContent = "GPC 未导入：运行 python scripts/material_master/import_gpc_reference.py --version 2026-05";
      }
      get("source-status").classList.add("error");
      get("source-status").querySelector("strong").textContent = "参考目录不可用";
      get("source-status").querySelector("small").textContent = String(error.message || error);
    }
  }

  get("taxonomy-search").addEventListener("input", () => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(runSearch, 260);
  });
  get("taxonomy-search").addEventListener("keydown", event => {
    if (event.key === "Enter") {
      clearTimeout(state.searchTimer);
      runSearch();
    }
  });
  get("kind-filter").addEventListener("change", () => { if (get("taxonomy-search").value.trim()) runSearch(); });
  get("clear-search").addEventListener("click", () => {
    get("taxonomy-search").value = "";
    get("kind-filter").value = "";
    runSearch();
    get("taxonomy-search").focus();
  });
  get("expand-chapters").addEventListener("click", expandToChapters);
  get("collapse-all").addEventListener("click", collapseAll);
  get("material-variant-close").addEventListener("click", () => get("material-variant-dialog").close());
  get("material-variant-dialog").addEventListener("click", event => {
    if (event.target === get("material-variant-dialog")) get("material-variant-dialog").close();
  });
  get("materialized-only").addEventListener("change", async event => {
    current().materializedOnly = Boolean(event.target.checked);
    try {
      await reloadMaterializedTree();
    } catch (error) {
      get("tree-loading").hidden = false;
      get("tree-loading").textContent = error.message || "实际物料目录筛选失败";
    }
  });
  initialize();
})();
