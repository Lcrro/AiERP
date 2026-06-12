from __future__ import annotations

import csv
from html import escape
from pathlib import Path

import frappe
import frappe.permissions
from frappe.utils import cint, today


PERMISSION_ACTIONS = (
    "select",
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "print",
    "email",
    "report",
    "import",
    "export",
    "share",
)


ITEM_MASTER_CUSTOM_FIELDS = {
    "specification": {"label": "规格型号", "fieldtype": "Data"},
    "material": {"label": "材质", "fieldtype": "Data"},
    "drawing_no": {"label": "图号", "fieldtype": "Data"},
    "standard": {"label": "执行标准", "fieldtype": "Data"},
    "brand": {"label": "品牌", "fieldtype": "Data"},
    "model": {"label": "型号", "fieldtype": "Data"},
    "package_spec": {"label": "包装规格", "fieldtype": "Data"},
    "raw_name": {"label": "原始叫法", "fieldtype": "Data"},
    "alias_names": {"label": "别名", "fieldtype": "Small Text"},
}


ITEM_MASTER_RULES = {
    "raw_metal_sheet": {
        "label": "原材料 / 金属材料 / 板材",
        "erpnext_item_group": "原材料",
        "code_prefix": "RM-MET-SHT",
        "default_uom": "Kg",
        "defaults": {
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "include_item_in_manufacturing": 1,
            "has_batch_no": 1,
            "create_new_batch": 1,
            "has_serial_no": 0,
        },
        "required_specs": ["material", "thickness", "width", "form", "standard"],
        "aliases": ["冷板", "冷轧板", "冷轧钢板", "冷轧钢卷", "钢板", "薄板", "铁板"],
    },
    "raw_plastic_granule": {
        "label": "原材料 / 塑料橡胶 / 颗粒",
        "erpnext_item_group": "原材料",
        "code_prefix": "RM-PLA-GRN",
        "default_uom": "Kg",
        "defaults": {
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "include_item_in_manufacturing": 1,
            "has_batch_no": 1,
            "create_new_batch": 1,
            "has_serial_no": 0,
        },
        "required_specs": ["material", "grade", "color", "melt_index", "package_spec"],
        "aliases": ["胶粒", "塑料粒子", "塑胶粒", "原料粒"],
    },
    "electronic_component": {
        "label": "原材料 / 电子元器件",
        "erpnext_item_group": "原材料",
        "code_prefix": "RM-ELE-CMP",
        "default_uom": "Nos",
        "defaults": {
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "include_item_in_manufacturing": 1,
            "has_batch_no": 0,
            "create_new_batch": 0,
            "has_serial_no": 0,
        },
        "required_specs": ["model", "brand", "package", "key_parameter"],
        "aliases": ["电子料", "元件", "芯片", "电阻", "电容"],
    },
    "packaging_material": {
        "label": "包装材料",
        "erpnext_item_group": "包装材料",
        "code_prefix": "PKG",
        "default_uom": "Nos",
        "defaults": {
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "include_item_in_manufacturing": 1,
            "has_batch_no": 0,
            "create_new_batch": 0,
            "has_serial_no": 0,
        },
        "required_specs": ["material", "size", "package_spec"],
        "aliases": ["包材", "纸箱", "胶袋", "标签"],
    },
    "consumable": {
        "label": "辅料耗材",
        "erpnext_item_group": "耗材",
        "code_prefix": "CNS",
        "default_uom": "Nos",
        "defaults": {
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "include_item_in_manufacturing": 0,
            "has_batch_no": 0,
            "create_new_batch": 0,
            "has_serial_no": 0,
        },
        "required_specs": ["specification", "brand"],
        "aliases": ["耗材", "辅料", "低值易耗"],
    },
    "spare_part": {
        "label": "备品备件",
        "erpnext_item_group": "备品备件",
        "code_prefix": "SP",
        "default_uom": "Nos",
        "defaults": {
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "include_item_in_manufacturing": 0,
            "has_batch_no": 0,
            "create_new_batch": 0,
            "has_serial_no": 0,
        },
        "required_specs": ["model", "brand", "equipment"],
        "aliases": ["备件", "配件", "维修件"],
    },
    "semi_finished_good": {
        "label": "半成品",
        "erpnext_item_group": "半成品",
        "code_prefix": "SF",
        "default_uom": "Nos",
        "defaults": {
            "is_stock_item": 1,
            "is_purchase_item": 0,
            "is_sales_item": 0,
            "include_item_in_manufacturing": 1,
            "has_batch_no": 0,
            "create_new_batch": 0,
            "has_serial_no": 0,
        },
        "required_specs": ["model", "version", "process_stage"],
        "aliases": ["半成品", "中间品", "在制品"],
    },
    "finished_good": {
        "label": "成品",
        "erpnext_item_group": "产品展示",
        "code_prefix": "FG",
        "default_uom": "Nos",
        "defaults": {
            "is_stock_item": 1,
            "is_purchase_item": 0,
            "is_sales_item": 1,
            "include_item_in_manufacturing": 0,
            "has_batch_no": 0,
            "create_new_batch": 0,
            "has_serial_no": 0,
        },
        "required_specs": ["model", "version", "package_spec"],
        "aliases": ["成品", "产品", "整机"],
    },
    "service_item": {
        "label": "服务",
        "erpnext_item_group": "服务",
        "code_prefix": "SV",
        "default_uom": "Nos",
        "defaults": {
            "is_stock_item": 0,
            "is_purchase_item": 1,
            "is_sales_item": 1,
            "include_item_in_manufacturing": 0,
            "has_batch_no": 0,
            "create_new_batch": 0,
            "has_serial_no": 0,
        },
        "required_specs": ["service_scope", "billing_unit"],
        "aliases": ["服务", "维修服务", "安装服务"],
    },
}

ITEM_IMPORT_WHOLE_NUMBER_UOMS = {
    "个",
    "只",
    "件",
    "套",
    "把",
    "根",
    "支",
    "张",
    "包",
    "盒",
    "桶",
    "瓶",
    "块",
    "卷",
    "台",
    "双",
    "付",
    "副",
    "条",
    "本",
    "袋",
    "片",
    "盘",
    "箱",
    "组",
    "节",
    "辆",
    "部",
    "床",
}

ITEM_IMPORT_REQUIRED_COLUMNS = {
    "draft_sku_id",
    "draft_item_code",
    "release_status",
    "放行等级",
    "标准名称",
    "必填规格",
    "辅助规格",
    "标准分组",
    "标准单位",
    "别名/土名",
}


@frappe.whitelist()
def ping() -> dict:
    """Health check used by the external agent adapter."""

    return {
        "ok": True,
        "site": frappe.local.site,
        "user": frappe.session.user,
    }


@frappe.whitelist()
def import_standard_item_master_draft(
    input_path: str,
    limit: int | None = None,
    offset: int = 0,
    update_existing: bool = False,
    commit_every: int = 100,
) -> dict:
    """Import the local SKU draft TSV into ERPNext Item records.

    This is intended for the local sandbox. It still uses normal Frappe document
    creation and validation, but avoids thousands of external HTTP calls.
    """

    frappe.only_for("System Manager")
    setup_item_master()

    path = Path(input_path).expanduser()
    if not path.exists():
        frappe.throw(f"input_path does not exist: {input_path}")

    rows = _read_standard_item_rows(path)
    offset = cint(offset)
    limit_value = cint(limit) if limit not in (None, "") else None
    selected_rows = rows[offset:]
    if limit_value:
        selected_rows = selected_rows[:limit_value]

    item_group_map = _build_import_item_group_map(selected_rows)
    summary = {
        "input_path": str(path),
        "total_input_rows": len(rows),
        "selected_rows": len(selected_rows),
        "offset": offset,
        "limit": limit_value,
        "created_uoms": 0,
        "skipped_existing_uoms": 0,
        "created_item_groups": 0,
        "skipped_existing_item_groups": 0,
        "created_items": 0,
        "updated_items": 0,
        "skipped_existing_items": 0,
        "failed_items": 0,
        "failures": [],
    }

    for uom in sorted({_clean_import_text(row.get("标准单位")) or "个" for row in selected_rows}):
        if frappe.db.exists("UOM", uom):
            summary["skipped_existing_uoms"] += 1
            continue
        doc = frappe.get_doc(
            {
                "doctype": "UOM",
                "uom_name": uom,
                "enabled": 1,
                "must_be_whole_number": 1 if uom in ITEM_IMPORT_WHOLE_NUMBER_UOMS else 0,
            }
        )
        doc.insert(ignore_permissions=True)
        summary["created_uoms"] += 1

    parent_item_group = _choose_import_item_group_root()
    for target_group in sorted(set(item_group_map.values())):
        if frappe.db.exists("Item Group", target_group):
            summary["skipped_existing_item_groups"] += 1
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": target_group,
                "parent_item_group": parent_item_group,
                "is_group": 0,
            }
        )
        doc.insert(ignore_permissions=True)
        summary["created_item_groups"] += 1

    item_meta = frappe.get_meta("Item")
    custom_fields = {
        fieldname
        for fieldname in ("specification", "raw_name", "alias_names")
        if item_meta.has_field(fieldname)
    }

    for index, row in enumerate(selected_rows, start=1):
        item_code = _clean_import_text(row.get("draft_item_code"))
        if not item_code:
            summary["failed_items"] += 1
            summary["failures"].append({"row": offset + index, "error": "draft_item_code is blank"})
            continue

        try:
            item_doc = _build_import_item_doc(row, item_group_map, custom_fields)
            if frappe.db.exists("Item", item_code):
                if update_existing:
                    doc = frappe.get_doc("Item", item_code)
                    doc.update(item_doc)
                    doc.save(ignore_permissions=True)
                    summary["updated_items"] += 1
                else:
                    summary["skipped_existing_items"] += 1
            else:
                frappe.get_doc(item_doc).insert(ignore_permissions=True)
                summary["created_items"] += 1
        except Exception as exc:
            summary["failed_items"] += 1
            summary["failures"].append({"item_code": item_code, "row": offset + index, "error": str(exc)})

        if commit_every and index % cint(commit_every) == 0:
            frappe.db.commit()

    frappe.db.commit()
    return summary


@frappe.whitelist()
def apply_material_catalog_usability_fixes(
    input_path: str,
    limit: int | None = None,
    offset: int = 0,
    commit_every: int = 200,
) -> dict:
    """Make imported materials easier to use in purchase/stock forms."""

    frappe.only_for("System Manager")
    setup_item_master()
    return {
        "material_request_labels": setup_material_request_chinese_labels(),
        "material_request_item_view": setup_material_request_item_user_view(),
        "item_search_fields": setup_item_search_fields(),
        "clean_item_descriptions": clean_imported_item_descriptions(
            input_path=input_path,
            limit=limit,
            offset=offset,
            commit_every=commit_every,
        ),
    }


@frappe.whitelist()
def setup_material_request_chinese_labels() -> dict:
    """Use business-friendly Chinese labels on Material Request forms."""

    frappe.only_for("System Manager")
    created = []
    updated = []
    for doctype, fieldname, label in [
        ("Material Request", "schedule_date", "需求日期"),
        ("Material Request Item", "schedule_date", "需求日期"),
    ]:
        result = _set_property_setter(doctype, fieldname, "label", label, "Data")
        created.extend(result["created"])
        updated.extend(result["updated"])

    frappe.clear_cache(doctype="Material Request")
    frappe.clear_cache(doctype="Material Request Item")
    frappe.db.commit()
    return {"created": created, "updated": updated}


@frappe.whitelist()
def setup_material_request_item_user_view() -> dict:
    """Show item name and specification in Material Request child rows."""

    frappe.only_for("System Manager")
    created = []
    updated = []

    field_result = _upsert_custom_field(
        "Material Request Item",
        "agent_item_specification",
        {
            "label": "规格型号",
            "fieldtype": "Data",
            "insert_after": "item_name",
            "fetch_from": "item_code.specification",
            "fetch_if_empty": 1,
            "read_only": 1,
            "in_list_view": 1,
            "columns": 3,
        },
    )
    created.extend(field_result["created"])
    updated.extend(field_result["updated"])

    for fieldname, property_name, value, property_type in [
        ("item_code", "columns", 2, "Int"),
        ("item_name", "in_list_view", 1, "Check"),
        ("item_name", "columns", 3, "Int"),
        ("description", "in_list_view", 0, "Check"),
        ("schedule_date", "columns", 2, "Int"),
        ("qty", "columns", 1, "Int"),
        ("warehouse", "columns", 2, "Int"),
        ("uom", "columns", 1, "Int"),
    ]:
        result = _set_property_setter(
            "Material Request Item",
            fieldname,
            property_name,
            value,
            property_type,
        )
        created.extend(result["created"])
        updated.extend(result["updated"])

    frappe.clear_cache(doctype="Material Request Item")
    frappe.db.commit()
    return {"created": created, "updated": updated}


@frappe.whitelist()
def setup_item_search_fields() -> dict:
    """Let Item links search by name, group, description, specification and aliases."""

    frappe.only_for("System Manager")
    result = _set_property_setter(
        "Item",
        None,
        "search_fields",
        "item_name,item_group,description,specification,alias_names",
        "Small Text",
        for_doctype=True,
    )
    frappe.clear_cache(doctype="Item")
    frappe.db.commit()
    return result


@frappe.whitelist()
def clean_imported_item_descriptions(
    input_path: str,
    limit: int | None = None,
    offset: int = 0,
    commit_every: int = 200,
) -> dict:
    """Replace noisy import audit descriptions with purchase-friendly text."""

    frappe.only_for("System Manager")
    path = Path(input_path).expanduser()
    if not path.exists():
        frappe.throw(f"input_path does not exist: {input_path}")

    rows = _read_standard_item_rows(path)
    offset = cint(offset)
    limit_value = cint(limit) if limit not in (None, "") else None
    selected_rows = rows[offset:]
    if limit_value:
        selected_rows = selected_rows[:limit_value]

    updated = 0
    skipped_missing_item = 0
    skipped_unchanged = 0
    sample_updates = []
    for index, row in enumerate(selected_rows, start=1):
        item_code = _clean_import_text(row.get("draft_item_code"))
        if not item_code or not frappe.db.exists("Item", item_code):
            skipped_missing_item += 1
            continue

        new_description = _build_clean_item_description(row)
        old_description = frappe.db.get_value("Item", item_code, "description")
        if old_description == new_description:
            skipped_unchanged += 1
            continue

        frappe.db.set_value("Item", item_code, "description", new_description, update_modified=False)
        updated += 1
        if len(sample_updates) < 5:
            sample_updates.append({"item_code": item_code, "description": new_description})

        if commit_every and index % cint(commit_every) == 0:
            frappe.db.commit()

    frappe.db.commit()
    return {
        "input_path": str(path),
        "total_input_rows": len(rows),
        "selected_rows": len(selected_rows),
        "updated_items": updated,
        "skipped_missing_item": skipped_missing_item,
        "skipped_unchanged": skipped_unchanged,
        "sample_updates": sample_updates,
    }


@frappe.whitelist()
def submit_document(doctype: str, name: str) -> dict:
    """Submit a submittable ERPNext document through normal Frappe rules."""

    doc = frappe.get_doc(doctype, name)
    doc.submit()
    return _compact_doc(doc)


@frappe.whitelist()
def cancel_document(doctype: str, name: str) -> dict:
    """Cancel a submitted ERPNext document through normal Frappe rules."""

    doc = frappe.get_doc(doctype, name)
    doc.cancel()
    return _compact_doc(doc)


@frappe.whitelist()
def check_user_permission(
    user: str,
    doctype: str,
    action: str = "read",
    docname: str | None = None,
    debug: bool = False,
) -> dict:
    """Evaluate a user's runtime permission through Frappe's permission engine."""

    frappe.only_for("System Manager")
    if not user:
        frappe.throw("user is required")
    if not doctype:
        frappe.throw("doctype is required")

    action = (action or "read").strip().lower()
    if action not in PERMISSION_ACTIONS:
        frappe.throw(f"Unsupported permission action: {action}")
    if not frappe.db.exists("User", user):
        frappe.throw(f"User does not exist: {user}", frappe.DoesNotExistError)

    current_user = frappe.session.user
    doc = None
    try:
        frappe.set_user(user)
        roles = frappe.get_roles(user)
        include_debug = bool(cint(debug))
        if docname:
            doc = frappe.get_doc(doctype, docname)
            allowed = doc.has_permission(action, user=user, debug=include_debug)
        else:
            frappe.get_meta(doctype)
            allowed = frappe.permissions.has_permission(
                doctype,
                ptype=action,
                user=user,
                raise_exception=False,
                debug=include_debug,
            )

        debug_log = list(getattr(frappe.local, "permission_debug_log", []) or []) if include_debug else []
        if hasattr(frappe.local, "permission_debug_log"):
            delattr(frappe.local, "permission_debug_log")

        return {
            "status": "checked",
            "user": user,
            "doctype": doctype,
            "docname": docname,
            "action": action,
            "allowed": bool(allowed),
            "roles": roles,
            "is_exact_runtime_evaluation": True,
            "evaluation": "frappe.permissions.has_permission",
            "document": _compact_permission_doc(doc) if doc else None,
            "debug_log": debug_log,
        }
    finally:
        frappe.set_user(current_user)


@frappe.whitelist()
def get_low_stock_items(limit: int = 50) -> list[dict]:
    """Return bin rows where projected quantity is below the reorder level."""

    limit = max(1, min(int(limit), 200))
    return frappe.db.sql(
        """
        select
            b.item_code,
            i.item_name,
            b.warehouse,
            b.actual_qty,
            b.projected_qty,
            b.reserved_qty,
            b.ordered_qty,
            b.stock_uom,
            r.warehouse_reorder_level as reorder_level,
            r.warehouse_reorder_qty as reorder_qty,
            r.material_request_type
        from `tabBin` b
        left join `tabItem` i on i.name = b.item_code
        inner join `tabItem Reorder` r
            on r.parent = b.item_code
           and ifnull(r.warehouse, '') = ifnull(b.warehouse, '')
        where ifnull(r.warehouse_reorder_level, 0) > 0
          and ifnull(b.projected_qty, 0) < ifnull(r.warehouse_reorder_level, 0)
        order by (ifnull(r.warehouse_reorder_level, 0) - ifnull(b.projected_qty, 0)) desc
        limit %(limit)s
        """,
        {"limit": limit},
        as_dict=True,
    )


@frappe.whitelist()
def create_todo(description: str, allocated_to: str | None = None, priority: str = "Medium") -> dict:
    """Create a ToDo document for agent-generated follow-up tasks."""

    todo = frappe.get_doc(
        {
            "doctype": "ToDo",
            "description": description,
            "allocated_to": allocated_to or frappe.session.user,
            "priority": priority,
        }
    )
    todo.insert()
    return _compact_doc(todo)


@frappe.whitelist()
def setup_item_master() -> dict:
    """Create custom Item fields used by material master v0.1."""

    meta = frappe.get_meta("Item")
    existing_fields = {field.fieldname for field in meta.fields}
    created = []
    skipped = []
    for fieldname, spec in ITEM_MASTER_CUSTOM_FIELDS.items():
        if fieldname in existing_fields:
            skipped.append(fieldname)
            continue
        custom_field = frappe.get_doc(
            {
                "doctype": "Custom Field",
                "dt": "Item",
                "fieldname": fieldname,
                "label": spec["label"],
                "fieldtype": spec["fieldtype"],
                "insert_after": "description",
            }
        )
        custom_field.insert(ignore_permissions=True)
        created.append(fieldname)
    if created:
        frappe.clear_cache(doctype="Item")
    frappe.db.commit()
    return {"created": created, "skipped": skipped}


@frappe.whitelist()
def prepare_item_from_intent(intent: dict | str) -> dict:
    """Normalize material intent and return either a draft Item or clarification request."""

    intent = frappe.parse_json(intent) if isinstance(intent, str) else (intent or {})
    group_key = _match_item_group(intent)
    if not group_key:
        return {
            "status": "needs_confirmation",
            "matched_group": None,
            "candidate_groups": [],
            "questions": ["请确认物料属于哪个物料组。"],
        }

    group = ITEM_MASTER_RULES[group_key]
    specs = intent.get("specs") or {}
    missing = [spec for spec in group["required_specs"] if not specs.get(spec)]
    if missing:
        return {
            "status": "needs_clarification",
            "matched_group": group_key,
            "missing_specs": missing,
            "questions": [_question_for_spec(intent.get("item_name") or intent.get("raw_name"), spec) for spec in missing],
        }

    similar = _find_similar_items(intent, group)
    if similar:
        return {
            "status": "needs_confirmation",
            "matched_group": group_key,
            "candidate_items": similar,
            "questions": ["系统中已有相似物料，请确认是复用已有物料还是继续新建。"],
        }

    item_code = _next_item_code(group["code_prefix"])
    return {
        "status": "ready",
        "matched_group": group_key,
        "item_code": item_code,
        "item_doc": _build_item_doc(intent, group, item_code),
        "missing_specs": [],
        "questions": [],
    }


@frappe.whitelist()
def create_item_from_intent(intent: dict | str) -> dict:
    """Create an ERPNext Item only when material master rules say the intent is ready."""

    setup_item_master()
    prepared = prepare_item_from_intent(intent)
    if prepared.get("status") != "ready":
        return prepared

    item_doc = prepared["item_doc"]
    _validate_item_dependencies(item_doc)
    doc = frappe.get_doc(item_doc)
    doc.insert()
    frappe.db.commit()
    return {
        "status": "created",
        "item": _compact_doc(doc),
        "item_doc": _compact_item_doc(doc),
    }


@frappe.whitelist()
def generate_purchase_suggestions(limit: int = 50) -> dict:
    """Return low-stock purchase suggestions grouped by material request type."""

    items = get_low_stock_items(limit)
    groups: dict[str, list[dict]] = {}
    for row in items:
        request_type = row.get("material_request_type") or "Purchase"
        groups.setdefault(request_type, []).append(
            {
                "item_code": row.get("item_code"),
                "item_name": row.get("item_name"),
                "warehouse": row.get("warehouse"),
                "projected_qty": row.get("projected_qty"),
                "reorder_level": row.get("reorder_level"),
                "suggested_qty": row.get("reorder_qty") or max(
                    (row.get("reorder_level") or 0) - (row.get("projected_qty") or 0),
                    0,
                ),
                "stock_uom": row.get("stock_uom"),
            }
        )

    return {
        "count": len(items),
        "groups": groups,
    }


@frappe.whitelist()
def preview_stock_valuation(items: list[dict] | str) -> dict:
    """Preview quantity and stock value impact without creating stock documents."""

    items = frappe.parse_json(items) if isinstance(items, str) else (items or [])
    if not items:
        frappe.throw("items is required")

    rows = []
    totals = {
        "current_stock_value": 0,
        "projected_stock_value": 0,
        "stock_value_difference": 0,
    }
    for row in items:
        item_code = row.get("item_code")
        warehouse = row.get("warehouse")
        qty_delta = float(row.get("qty_delta") or row.get("qty") or 0)
        incoming_rate = row.get("incoming_rate", row.get("valuation_rate"))
        current = _get_bin_snapshot(item_code, warehouse)
        current_qty = float(current.get("actual_qty") or 0)
        current_rate = float(current.get("valuation_rate") or 0)
        current_value = float(current.get("stock_value") or (current_qty * current_rate))
        rate = float(incoming_rate if incoming_rate not in (None, "") else current_rate)
        value_difference = qty_delta * rate
        projected_qty = current_qty + qty_delta
        projected_value = current_value + value_difference
        projected_rate = projected_value / projected_qty if projected_qty else 0
        preview = {
            "item_code": item_code,
            "warehouse": warehouse,
            "current_qty": current_qty,
            "current_valuation_rate": current_rate,
            "current_stock_value": current_value,
            "qty_delta": qty_delta,
            "rate_used": rate,
            "stock_value_difference": value_difference,
            "projected_qty": projected_qty,
            "projected_stock_value": projected_value,
            "projected_valuation_rate": projected_rate,
        }
        rows.append(preview)
        totals["current_stock_value"] += current_value
        totals["projected_stock_value"] += projected_value
        totals["stock_value_difference"] += value_difference

    return {
        "status": "preview",
        "rows": rows,
        "totals": totals,
        "notes": [
            "Preview uses current Bin valuation_rate and provided incoming/valuation rate.",
            "ERPNext remains the source of truth when a Stock Entry or Stock Reconciliation is submitted.",
        ],
    }


@frappe.whitelist()
def allocate_stock_shortages(items: list[dict] | str) -> dict:
    """Preview available allocation and shortages for demand rows without writing documents."""

    items = frappe.parse_json(items) if isinstance(items, str) else (items or [])
    if not items:
        frappe.throw("items is required")

    rows = []
    for row in items:
        item_code = row.get("item_code")
        warehouse = row.get("warehouse")
        required_qty = float(row.get("required_qty") or row.get("qty") or 0)
        current = _get_bin_snapshot(item_code, warehouse)
        actual_qty = float(current.get("actual_qty") or 0)
        reserved_qty = float(current.get("reserved_qty") or 0)
        projected_qty = float(current.get("projected_qty") if current.get("projected_qty") is not None else actual_qty)
        available_qty = max(actual_qty - reserved_qty, 0)
        allocated_qty = min(required_qty, available_qty)
        shortage_qty = max(required_qty - allocated_qty, 0)
        rows.append(
            {
                "item_code": item_code,
                "warehouse": warehouse,
                "required_qty": required_qty,
                "actual_qty": actual_qty,
                "reserved_qty": reserved_qty,
                "projected_qty": projected_qty,
                "available_qty": available_qty,
                "allocated_qty": allocated_qty,
                "shortage_qty": shortage_qty,
                "status": "shortage" if shortage_qty else "allocated",
            }
        )

    shortages = [row for row in rows if row["shortage_qty"] > 0]
    return {
        "status": "has_shortages" if shortages else "fully_allocated",
        "rows": rows,
        "shortage_count": len(shortages),
        "next_actions": ["create_pick_list_draft", "create_reservation_draft", "request_purchase_or_transfer"],
    }


@frappe.whitelist()
def reconcile_bank_transaction(
    bank_transaction: str,
    matches: list[dict] | str,
    replace_existing: bool = False,
    remarks: str | None = None,
) -> dict:
    """Match existing payment documents to one Bank Transaction.

    This wrapper intentionally does not create Payment Entry or Journal Entry
    documents. It only records reviewed matches against an existing Bank
    Transaction and lets ERPNext validate the child table fields.
    """

    matches = frappe.parse_json(matches) if isinstance(matches, str) else (matches or [])
    if not bank_transaction:
        frappe.throw("bank_transaction is required")
    if not matches:
        frappe.throw("matches is required")

    doc = frappe.get_doc("Bank Transaction", bank_transaction)
    if replace_existing:
        doc.set("payment_entries", [])

    for row in matches:
        payment_document = row.get("payment_document")
        payment_entry = row.get("payment_entry")
        allocated_amount = row.get("allocated_amount")
        if not payment_document or not payment_entry or allocated_amount in (None, ""):
            frappe.throw("Each match requires payment_document, payment_entry, and allocated_amount")
        doc.append(
            "payment_entries",
            {
                "payment_document": payment_document,
                "payment_entry": payment_entry,
                "allocated_amount": allocated_amount,
            },
        )

    if remarks and doc.meta.has_field("description"):
        doc.description = f"{doc.get('description') or ''}\n{remarks}".strip()

    doc.save()
    frappe.db.commit()

    payment_entries = [
        {
            "payment_document": row.get("payment_document"),
            "payment_entry": row.get("payment_entry"),
            "allocated_amount": row.get("allocated_amount"),
        }
        for row in doc.get("payment_entries", [])
    ]
    allocated_amount = sum(float(row.get("allocated_amount") or 0) for row in payment_entries)
    transaction_amount = float(doc.get("deposit") or 0) or float(doc.get("withdrawal") or 0)
    return {
        "doctype": doc.doctype,
        "name": doc.name,
        "docstatus": doc.docstatus,
        "status": doc.get("status"),
        "matched_count": len(payment_entries),
        "allocated_amount": allocated_amount,
        "transaction_amount": transaction_amount,
        "unallocated_amount": transaction_amount - allocated_amount,
        "payment_entries": payment_entries,
        "modified": doc.modified,
    }


@frappe.whitelist()
def create_material_request_draft(
    material_request_type: str = "Purchase",
    schedule_date: str | None = None,
    items: list[dict] | None = None,
) -> dict:
    """Create a Material Request draft from explicit item rows."""

    items = frappe.parse_json(items) if isinstance(items, str) else (items or [])
    if not items:
        frappe.throw("items is required")

    doc = frappe.get_doc(
        {
            "doctype": "Material Request",
            "material_request_type": material_request_type,
            "schedule_date": schedule_date or today(),
            "items": [
                {
                    "item_code": row.get("item_code"),
                    "qty": row.get("qty") or row.get("suggested_qty") or 1,
                    "schedule_date": row.get("schedule_date") or schedule_date or today(),
                    "warehouse": row.get("warehouse"),
                }
                for row in items
            ],
        }
    )
    doc.insert()
    return _compact_doc(doc)


def _get_bin_snapshot(item_code: str | None, warehouse: str | None) -> dict:
    if not item_code:
        frappe.throw("item_code is required")
    if not warehouse:
        frappe.throw("warehouse is required")
    row = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ["actual_qty", "projected_qty", "reserved_qty", "valuation_rate", "stock_value"],
        as_dict=True,
    )
    return row or {
        "actual_qty": 0,
        "projected_qty": 0,
        "reserved_qty": 0,
        "valuation_rate": 0,
        "stock_value": 0,
    }


@frappe.whitelist()
def create_sales_order_draft(
    customer: str,
    delivery_date: str,
    items: list[dict],
    transaction_date: str | None = None,
) -> dict:
    """Create a Sales Order draft from explicit customer and item rows."""

    items = frappe.parse_json(items) if isinstance(items, str) else items
    if not items:
        frappe.throw("items is required")

    doc = frappe.get_doc(
        {
            "doctype": "Sales Order",
            "customer": customer,
            "transaction_date": transaction_date or today(),
            "delivery_date": delivery_date,
            "items": [
                {
                    "item_code": row.get("item_code"),
                    "qty": row.get("qty") or 1,
                    "delivery_date": row.get("delivery_date") or delivery_date,
                    "warehouse": row.get("warehouse"),
                }
                for row in items
            ],
        }
    )
    doc.insert()
    return _compact_doc(doc)


@frappe.whitelist()
def get_overdue_receivables_by_owner(limit: int = 100) -> dict:
    """Return overdue receivables grouped by sales owner when available."""

    limit = max(1, min(int(limit), 500))
    rows = frappe.db.sql(
        """
        select
            si.name,
            si.customer,
            si.customer_name,
            si.owner,
            si.due_date,
            si.outstanding_amount,
            si.grand_total,
            si.currency
        from `tabSales Invoice` si
        where si.docstatus = 1
          and ifnull(si.outstanding_amount, 0) > 0
          and si.due_date < %(today)s
        order by si.due_date asc
        limit %(limit)s
        """,
        {"today": today(), "limit": limit},
        as_dict=True,
    )

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row.get("owner") or "Unassigned", []).append(row)

    return {"count": len(rows), "groups": groups}


@frappe.whitelist()
def get_project_risks(limit: int = 100) -> dict:
    """Return overdue project tasks and open issues as project risk signals."""

    limit = max(1, min(int(limit), 500))
    overdue_tasks = frappe.db.sql(
        """
        select name, subject, project, status, owner, exp_end_date
        from `tabTask`
        where ifnull(status, '') not in ('Completed', 'Cancelled')
          and exp_end_date is not null
          and exp_end_date < %(today)s
        order by exp_end_date asc
        limit %(limit)s
        """,
        {"today": today(), "limit": limit},
        as_dict=True,
    )
    open_issues = frappe.get_all(
        "Issue",
        filters={"status": ["not in", ["Closed", "Resolved"]]},
        fields=["name", "subject", "status", "priority", "owner", "project"],
        limit_page_length=limit,
        order_by="modified desc",
    )

    return {
        "overdue_tasks_count": len(overdue_tasks),
        "open_issues_count": len(open_issues),
        "overdue_tasks": overdue_tasks,
        "open_issues": open_issues,
    }


@frappe.whitelist()
def get_manager_exceptions(limit: int = 50) -> dict:
    """Return a compact management exception summary."""

    low_stock = get_low_stock_items(limit)
    receivables = get_overdue_receivables_by_owner(limit)
    risks = get_project_risks(limit)
    delayed_sales_orders = frappe.get_all(
        "Sales Order",
        filters={
            "docstatus": 1,
            "delivery_date": ["<", today()],
            "status": ["not in", ["Completed", "Closed"]],
        },
        fields=["name", "customer", "delivery_date", "status", "owner"],
        limit_page_length=limit,
        order_by="delivery_date asc",
    )

    return {
        "low_stock_count": len(low_stock),
        "overdue_receivables_count": receivables.get("count", 0),
        "project_overdue_tasks_count": risks.get("overdue_tasks_count", 0),
        "open_issues_count": risks.get("open_issues_count", 0),
        "delayed_sales_orders_count": len(delayed_sales_orders),
        "low_stock": low_stock,
        "overdue_receivables": receivables,
        "project_risks": risks,
        "delayed_sales_orders": delayed_sales_orders,
    }


def _read_standard_item_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        missing = ITEM_IMPORT_REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            frappe.throw(f"input file is missing columns: {', '.join(sorted(missing))}")
        return [{key: _clean_import_text(value) for key, value in row.items()} for row in reader]


def _build_import_item_group_map(rows: list[dict]) -> dict:
    item_group_map = {}
    for row in rows:
        source_group = _clean_import_text(row.get("标准分组")) or "未分类物料"
        if source_group in item_group_map:
            continue
        if frappe.db.exists("Item Group", source_group):
            item_group_map[source_group] = source_group
        else:
            item_group_map[source_group] = source_group
    return item_group_map


def _choose_import_item_group_root() -> str:
    for item_group in ("所有物料群组", "All Item Groups"):
        if frappe.db.exists("Item Group", item_group):
            return item_group
    roots = frappe.get_all("Item Group", filters={"is_group": 1}, fields=["name"], limit_page_length=1)
    return roots[0].name if roots else "所有物料群组"


def _build_import_item_doc(row: dict, item_group_map: dict, custom_fields: set[str]) -> dict:
    item_code = _clean_import_text(row.get("draft_item_code"))
    standard_name = _clean_import_text(row.get("标准名称")) or item_code
    required_specs = _clean_import_text(row.get("必填规格"))
    optional_specs = _clean_import_text(row.get("辅助规格"))
    aliases = _clean_import_text(row.get("别名/土名"))
    source_group = _clean_import_text(row.get("标准分组")) or "未分类物料"
    item_group = item_group_map.get(source_group, source_group)
    stock_uom = _clean_import_text(row.get("标准单位")) or "个"

    doc = {
        "doctype": "Item",
        "item_code": item_code,
        "item_name": _clamp_import_text(standard_name, 140),
        "item_group": item_group,
        "stock_uom": stock_uom,
        "disabled": 0,
        "is_stock_item": 1,
        "is_purchase_item": 1,
        "is_sales_item": 0,
        "include_item_in_manufacturing": 0,
        "description": _build_import_item_description(row, item_group),
    }
    optional_field_values = {
        "specification": _clamp_import_text(_join_import_parts(required_specs, optional_specs), 140),
        "raw_name": _clamp_import_text(aliases or standard_name, 140),
        "alias_names": aliases,
    }
    for fieldname, value in optional_field_values.items():
        if fieldname in custom_fields and value:
            doc[fieldname] = value
    return {key: value for key, value in doc.items() if value not in (None, "")}


def _build_import_item_description(row: dict, item_group: str) -> str:
    fields = [
        ("SKU 草案编号", row.get("draft_sku_id")),
        ("标准编码", row.get("draft_item_code")),
        ("标准名称", row.get("标准名称")),
        ("必填规格", row.get("必填规格")),
        ("辅助规格", row.get("辅助规格")),
        ("标准分组", item_group),
        ("标准单位", row.get("标准单位")),
        ("别名/土名", row.get("别名/土名")),
        ("放行等级", row.get("放行等级")),
        ("草案状态", row.get("release_status")),
        ("导入决策", row.get("import_decision")),
        ("整理依据", row.get("整理依据")),
        ("来源候选行", row.get("source_candidate_rows")),
        ("来源采购行", row.get("source_file_rows")),
    ]
    list_items = []
    for label, value in fields:
        value = _clean_import_text(value)
        if value:
            list_items.append(f"<li><strong>{escape(label)}：</strong>{escape(value)}</li>")
    return "<p><strong>Agent 物料主数据草案导入</strong></p><ul>" + "".join(list_items) + "</ul>"


def _build_clean_item_description(row: dict) -> str:
    name = _clean_import_text(row.get("标准名称")) or _clean_import_text(row.get("draft_item_code"))
    required_specs = _clean_import_text(row.get("必填规格"))
    optional_specs = _clean_import_text(row.get("辅助规格"))
    aliases = _clean_import_text(row.get("别名/土名"))
    spec = _join_import_parts(required_specs, optional_specs)

    paragraphs = [f"<p>{escape(name)}</p>"]
    if spec:
        paragraphs.append(f"<p>{escape(spec)}</p>")
    if aliases and aliases != name:
        paragraphs.append(f"<p>别名：{escape(aliases)}</p>")
    return "".join(paragraphs)


def _upsert_custom_field(dt: str, fieldname: str, spec: dict) -> dict:
    created = []
    updated = []
    name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname}, "name")
    if name:
        changed = False
        doc = frappe.get_doc("Custom Field", name)
        for key, value in spec.items():
            if doc.get(key) != value:
                doc.set(key, value)
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
            updated.append(f"Custom Field:{dt}.{fieldname}")
        return {"created": created, "updated": updated}

    payload = {"doctype": "Custom Field", "dt": dt, "fieldname": fieldname}
    payload.update(spec)
    frappe.get_doc(payload).insert(ignore_permissions=True)
    created.append(f"Custom Field:{dt}.{fieldname}")
    return {"created": created, "updated": updated}


def _set_property_setter(
    doctype: str,
    fieldname: str | None,
    property_name: str,
    value,
    property_type: str,
    for_doctype: bool = False,
) -> dict:
    created = []
    updated = []
    filters = {
        "doc_type": doctype,
        "property": property_name,
        "doctype_or_field": "DocType" if for_doctype else "DocField",
    }
    if fieldname:
        filters["field_name"] = fieldname

    name = frappe.db.get_value("Property Setter", filters, "name")
    value = str(value)
    if name:
        doc = frappe.get_doc("Property Setter", name)
        changed = False
        if doc.value != value:
            doc.value = value
            changed = True
        if doc.property_type != property_type:
            doc.property_type = property_type
            changed = True
        if changed:
            doc.save(ignore_permissions=True)
            updated.append(_property_setter_label(doctype, fieldname, property_name))
        return {"created": created, "updated": updated}

    frappe.get_doc(
        {
            "doctype": "Property Setter",
            "doctype_or_field": "DocType" if for_doctype else "DocField",
            "doc_type": doctype,
            "field_name": fieldname,
            "property": property_name,
            "value": value,
            "property_type": property_type,
            "is_system_generated": 1,
        }
    ).insert(ignore_permissions=True)
    created.append(_property_setter_label(doctype, fieldname, property_name))
    return {"created": created, "updated": updated}


def _property_setter_label(doctype: str, fieldname: str | None, property_name: str) -> str:
    target = doctype if not fieldname else f"{doctype}.{fieldname}"
    return f"Property Setter:{target}.{property_name}"


def _clean_import_text(value) -> str:
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def _clamp_import_text(value: str, length: int) -> str:
    value = _clean_import_text(value)
    if len(value) <= length:
        return value
    return value[: length - 1] + "…"


def _join_import_parts(*values: str) -> str:
    return "；".join(value for value in (_clean_import_text(value) for value in values) if value)


def _match_item_group(intent: dict) -> str | None:
    explicit = intent.get("item_group_key")
    if explicit in ITEM_MASTER_RULES:
        return explicit
    haystack = " ".join(
        [
            str(intent.get("raw_text") or ""),
            str(intent.get("raw_name") or ""),
            str(intent.get("item_name") or ""),
            str(intent.get("item_group_hint") or ""),
            " ".join(str(value) for value in (intent.get("specs") or {}).values()),
        ]
    )
    scores = []
    for key, group in ITEM_MASTER_RULES.items():
        score = 0
        if group["erpnext_item_group"] in haystack:
            score += 4
        for alias in group["aliases"]:
            if alias in haystack:
                score += 10
        if score:
            scores.append((key, score))
    scores.sort(key=lambda row: row[1], reverse=True)
    return scores[0][0] if scores else None


def _build_item_doc(intent: dict, group: dict, item_code: str) -> dict:
    specs = intent.get("specs") or {}
    item_name = intent.get("item_name") or intent.get("raw_name")
    specification = specs.get("specification") or _compose_specification(specs)
    aliases = sorted(set([intent.get("raw_name") or "", *(group.get("aliases") or [])]))
    doc = {
        "doctype": "Item",
        "item_code": item_code,
        "item_name": item_name,
        "item_group": group["erpnext_item_group"],
        "stock_uom": _normalize_uom(intent.get("stock_uom") or group["default_uom"]),
        "description": f"{item_name} {specification}".strip(),
        "specification": specification,
        "raw_name": intent.get("raw_name"),
        "alias_names": ", ".join(alias for alias in aliases if alias),
    }
    doc.update(group["defaults"])
    for field in ["material", "drawing_no", "standard", "brand", "model", "package_spec"]:
        if specs.get(field):
            doc[field] = specs[field]
    return {key: value for key, value in doc.items() if value not in (None, "")}


def _compose_specification(specs: dict) -> str:
    ordered = [
        "material",
        "grade",
        "model",
        "brand",
        "thickness",
        "width",
        "size",
        "form",
        "color",
        "standard",
        "package_spec",
    ]
    values = [str(specs[key]) for key in ordered if specs.get(key)]
    values.extend(str(value) for key, value in specs.items() if key not in ordered and value)
    return " ".join(values)


def _next_item_code(prefix: str) -> str:
    rows = frappe.get_all("Item", filters={"name": ["like", f"{prefix}-%"]}, fields=["name"], limit_page_length=1000)
    max_number = 0
    for row in rows:
        suffix = str(row.name).replace(f"{prefix}-", "", 1)
        if suffix.isdigit():
            max_number = max(max_number, int(suffix))
    return f"{prefix}-{max_number + 1:06d}"


def _find_similar_items(intent: dict, group: dict) -> list[dict]:
    specs = intent.get("specs") or {}
    item_name = intent.get("item_name") or intent.get("raw_name") or ""
    filters = {"disabled": 0, "item_group": group["erpnext_item_group"]}
    rows = frappe.get_all(
        "Item",
        filters=filters,
        fields=["name", "item_name", "item_group", "stock_uom", "specification", "material", "standard", "brand", "model"],
        limit_page_length=50,
    )
    candidates = []
    for row in rows:
        searchable = " ".join(str(row.get(field) or "") for field in row).lower()
        score = 0
        if item_name and item_name.lower() in searchable:
            score += 30
        for value in specs.values():
            if value and str(value).lower() in searchable:
                score += 10
        if score >= 40:
            candidates.append({"item_code": row.name, "item_name": row.item_name, "score": score, "data": row})
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:5]


def _validate_item_dependencies(item_doc: dict) -> None:
    if not frappe.db.exists("Item Group", item_doc["item_group"]):
        frappe.throw(f"Item Group does not exist: {item_doc['item_group']}")
    if not frappe.db.exists("UOM", item_doc["stock_uom"]):
        frappe.throw(f"UOM does not exist: {item_doc['stock_uom']}")


def _normalize_uom(value: str) -> str:
    return {"公斤": "Kg", "千克": "Kg", "个": "Nos", "件": "Nos"}.get(value, value)


def _question_for_spec(item_name: str | None, spec: str) -> str:
    labels = {
        "material": "材质",
        "thickness": "厚度",
        "width": "宽度",
        "form": "形态",
        "standard": "执行标准",
        "grade": "牌号/等级",
        "color": "颜色",
        "melt_index": "熔指",
        "package_spec": "包装规格",
        "model": "型号",
        "brand": "品牌",
        "package": "封装",
        "key_parameter": "关键参数",
        "size": "尺寸",
        "specification": "规格型号",
        "equipment": "适用设备",
        "version": "版本",
        "process_stage": "工序阶段",
        "service_scope": "服务范围",
        "billing_unit": "计价单位",
    }
    target = f"{item_name}的" if item_name else ""
    return f"请补充{target}{labels.get(spec, spec)}。"


def _compact_item_doc(doc) -> dict:
    fields = [
        "name",
        "item_code",
        "item_name",
        "item_group",
        "stock_uom",
        "specification",
        "material",
        "standard",
        "brand",
        "model",
        "package_spec",
    ]
    return {field: doc.get(field) for field in fields if doc.get(field) is not None}


def _compact_doc(doc) -> dict:
    return {
        "doctype": doc.doctype,
        "name": doc.name,
        "docstatus": doc.docstatus,
        "modified": doc.modified,
    }


def _compact_permission_doc(doc) -> dict | None:
    if not doc:
        return None
    return {
        "doctype": doc.doctype,
        "name": doc.name,
        "owner": doc.get("owner"),
        "docstatus": doc.get("docstatus"),
        "modified": doc.get("modified"),
    }
