from __future__ import annotations

from datetime import date
import os
from collections.abc import Callable
from typing import Any

from ..schemas import ToolResult

ACCOUNTING_SUBMITTABLE_DOCTYPES = {
    "Journal Entry",
    "Payment Entry",
    "Sales Invoice",
    "Purchase Invoice",
    "Period Closing Voucher",
}

ACCOUNTING_STRUCTURE_DOCTYPES = {
    "Account",
    "Cost Center",
    "Bank Account",
    "Mode of Payment",
    "Fiscal Year",
    "Accounting Period",
    "Payment Term",
    "Payment Terms Template",
    "Sales Taxes and Charges Template",
    "Purchase Taxes and Charges Template",
    "Tax Category",
    "Tax Rule",
    "Finance Book",
    "Budget",
}

ACCOUNTING_WRITE_GUARDED_DOCTYPES = ACCOUNTING_SUBMITTABLE_DOCTYPES | ACCOUNTING_STRUCTURE_DOCTYPES

ACCOUNTING_MUTATING_METHODS = {
    "frappe.client.insert",
    "frappe.client.save",
    "frappe.client.set_value",
    "frappe.client.delete",
    "frappe.client.submit",
    "frappe.client.cancel",
}

STOCK_SUBMITTABLE_DOCTYPES = {
    "Stock Entry",
    "Stock Reconciliation",
    "Delivery Note",
    "Purchase Receipt",
    "Purchase Invoice",
    "Sales Invoice",
    "Pick List",
    "Stock Reservation Entry",
}

ASSET_SUBMITTABLE_DOCTYPES = {
    "Asset",
    "Asset Movement",
    "Asset Maintenance",
    "Asset Maintenance Log",
    "Asset Repair",
    "Asset Value Adjustment",
}

ASSET_FINANCIAL_DOCTYPES = {
    "Asset",
    "Asset Value Adjustment",
}

BUYING_SUBMITTABLE_DOCTYPES = {
    "Material Request",
    "Request for Quotation",
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
}

USER_PERMISSION_ACTIONS = (
    "select",
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "import",
    "share",
    "print",
    "email",
)

def _report_filters(args: dict[str, Any]) -> dict[str, Any]:
    filters = dict(args.get("filters") or {})
    for key in ("company", "from_date", "to_date", "fiscal_year", "account", "party_type", "party"):
        if args.get(key) is not None:
            filters[key] = args[key]
    return filters

def _supplier_quotation_comparison_result(
    quotations: list[dict[str, Any]],
    requested_names: list[str],
    *,
    include_drafts: bool,
) -> ToolResult:
    summaries: list[dict[str, Any]] = []
    comparable: list[tuple[dict[str, Any], dict[str, Any]]] = []
    excluded: list[dict[str, Any]] = []
    for doc in quotations:
        summary = _supplier_quotation_summary(doc)
        summaries.append(summary)
        docstatus = summary.get("docstatus")
        if docstatus == 2:
            excluded.append({**summary, "reason": "cancelled"})
            continue
        if docstatus == 0 and not include_drafts:
            excluded.append({**summary, "reason": "draft_not_included"})
            continue
        if docstatus not in (0, 1):
            excluded.append({**summary, "reason": "unsupported_docstatus"})
            continue
        comparable.append((doc, summary))

    if not comparable:
        return ToolResult(
            ok=False,
            error="No comparable Supplier Quotation documents were available.",
            error_type="no_comparable_quotations",
            user_message="没有可比较的供应商报价单。默认只比较已提交报价；如需草稿预览，请设置 include_drafts=true。",
            data={
                "doctype": "Supplier Quotation",
                "status": "no_comparable_quotations",
                "summary": "No submitted Supplier Quotations were available for comparison.",
                "requested_supplier_quotations": requested_names,
                "quotations": summaries,
                "excluded_quotations": excluded,
                "next_actions": ["submit_supplier_quotations", "retry_comparison"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )

    currencies = sorted({summary["currency"] for _, summary in comparable if summary.get("currency")})
    warnings = []
    if len(currencies) > 1:
        warnings.append("Multiple currencies are present; nominal totals are not directly comparable without FX normalization.")
    if include_drafts:
        warnings.append("Draft Supplier Quotations are included for preview only and must be reviewed before award.")

    total_ranking = sorted(
        (_supplier_quotation_ranking_row(summary) for _, summary in comparable),
        key=lambda row: _sort_number(row.get("total_amount")),
    )
    item_comparisons = _supplier_quotation_item_comparisons(comparable)
    lowest = total_ranking[0]
    recommendation_status = "review_required" if len(currencies) > 1 else "lowest_total"
    recommendation = {
        "status": recommendation_status,
        "supplier_quotation": lowest.get("name"),
        "supplier": lowest.get("supplier"),
        "total_amount": lowest.get("total_amount"),
        "currency": lowest.get("currency"),
        "requires_human_review": True,
        "award_tool": None,
        "draft_po_tool": "erpnext.buying.create_purchase_order_draft",
    }
    return ToolResult(
        ok=True,
        data={
            "doctype": "Supplier Quotation",
            "status": "Comparison Ready",
            "summary": f"Compared {len(comparable)} Supplier Quotations; lowest comparable total is {lowest.get('name')}.",
            "requested_supplier_quotations": requested_names,
            "include_drafts": include_drafts,
            "quotations": summaries,
            "excluded_quotations": excluded,
            "total_ranking": total_ranking,
            "item_comparisons": item_comparisons,
            "recommendation": recommendation,
            "warnings": warnings,
            "next_actions": ["review_price_quality_terms", "create_purchase_order_draft"],
            "risk": {"level": "L1", "requires_confirmation_for_submit": False, "does_not_award": True},
        },
        debug={"raw_supplier_quotation_names": [doc.get("name") for doc in quotations]},
    )

def _supplier_quotation_summary(doc: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in doc.get("items") or [] if isinstance(item, dict)]
    total_amount = _first_float(doc, ("grand_total", "rounded_total", "net_total", "total"))
    if total_amount is None:
        total_amount = sum(_supplier_quotation_item_amount(item) for item in items)
    return {
        "name": doc.get("name"),
        "supplier": doc.get("supplier"),
        "supplier_name": doc.get("supplier_name"),
        "transaction_date": doc.get("transaction_date"),
        "valid_till": doc.get("valid_till"),
        "currency": doc.get("currency"),
        "docstatus": doc.get("docstatus"),
        "status": doc.get("status"),
        "request_for_quotation": doc.get("request_for_quotation"),
        "item_count": len(items),
        "total_amount": round(float(total_amount or 0), 2),
    }

def _supplier_quotation_ranking_row(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": summary.get("name"),
        "supplier": summary.get("supplier"),
        "supplier_name": summary.get("supplier_name"),
        "docstatus": summary.get("docstatus"),
        "currency": summary.get("currency"),
        "total_amount": summary.get("total_amount"),
        "item_count": summary.get("item_count"),
    }

def _supplier_quotation_item_comparisons(comparable: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for doc, summary in comparable:
        for index, item in enumerate(doc.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            item_key = str(item.get("item_code") or item.get("item_name") or f"{summary.get('name')}:line-{index}")
            bucket = buckets.setdefault(
                item_key,
                {
                    "item_code": item.get("item_code"),
                    "item_name": item.get("item_name"),
                    "uom": item.get("uom"),
                    "offers": [],
                },
            )
            bucket["offers"].append(_supplier_quotation_item_offer(item, summary))

    comparisons: list[dict[str, Any]] = []
    for item_key, bucket in buckets.items():
        offers = sorted(bucket["offers"], key=lambda offer: (_sort_number(offer.get("rate")), _sort_number(offer.get("amount"))))
        if not offers:
            continue
        best = offers[0]
        comparisons.append(
            {
                "item_code": bucket.get("item_code") or item_key,
                "item_name": bucket.get("item_name"),
                "uom": bucket.get("uom"),
                "offer_count": len(offers),
                "best_supplier_quotation": best.get("supplier_quotation"),
                "best_supplier": best.get("supplier"),
                "best_rate": best.get("rate"),
                "best_amount": best.get("amount"),
                "offers": offers,
            }
        )
    return sorted(comparisons, key=lambda row: str(row.get("item_code") or ""))

def _supplier_quotation_item_offer(item: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    qty = _float_or_none(item.get("qty"))
    rate = _supplier_quotation_item_rate(item)
    amount = _supplier_quotation_item_amount(item)
    return {
        "supplier_quotation": summary.get("name"),
        "supplier": summary.get("supplier"),
        "supplier_name": summary.get("supplier_name"),
        "docstatus": summary.get("docstatus"),
        "currency": summary.get("currency"),
        "qty": qty,
        "rate": round(rate, 6) if rate is not None else None,
        "amount": round(amount, 2),
    }

def _supplier_quotation_item_rate(item: dict[str, Any]) -> float | None:
    return _first_float(item, ("rate", "net_rate", "base_rate", "price_list_rate"))

def _supplier_quotation_item_amount(item: dict[str, Any]) -> float:
    amount = _first_float(item, ("amount", "net_amount", "base_net_amount", "base_amount"))
    if amount is not None:
        return amount
    qty = _float_or_none(item.get("qty")) or 0.0
    rate = _supplier_quotation_item_rate(item) or 0.0
    return qty * rate

def _first_float(data: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _float_or_none(data.get(key))
        if value is not None:
            return value
    return None

def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _sort_number(value: Any) -> float:
    numeric = _float_or_none(value)
    if numeric is None:
        return float("inf")
    return numeric

def _validate_accounting_report_filters(report_name: str, filters: dict[str, Any]) -> ToolResult | None:
    spec = _accounting_report_filter_spec(report_name)
    required = spec["required_filters"] if spec else []
    missing = [field for field in required if not filters.get(field)]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Missing required report filters for {report_name}: {', '.join(missing)}",
            error_type="missing_report_filter",
            user_message=f"{report_name} 报表缺少必要过滤条件：{', '.join(missing)}。",
            data={
                "report_name": report_name,
                "status": "Missing Required Filters",
                "missing_filters": missing,
                "summary": f"{report_name} requires {', '.join(required)} before running.",
                "next_actions": ["provide_required_filters", "retry_report"],
                "risk": {"level": "L0"},
            },
        )

    date_guard = _validate_report_date_range(report_name, filters)
    if date_guard:
        return date_guard
    return None

def _accounting_report_filter_spec(report_name: str) -> dict[str, Any] | None:
    specs: dict[str, dict[str, Any]] = {
        "General Ledger": {
            "required_filters": ["company"],
            "optional_filters": ["from_date", "to_date", "account", "party_type", "party", "voucher_no", "cost_center", "project"],
            "defaults": {"group_by": "Group by Voucher (Consolidated)"},
            "known_date_filters": ["from_date", "to_date"],
        },
        "Accounts Receivable": {
            "required_filters": ["company"],
            "optional_filters": ["report_date", "customer", "customer_group", "payment_terms_template", "sales_partner", "based_on_payment_terms"],
            "defaults": {},
            "known_date_filters": ["report_date"],
        },
        "Accounts Payable": {
            "required_filters": ["company"],
            "optional_filters": ["report_date", "supplier", "supplier_group", "payment_terms_template", "based_on_payment_terms"],
            "defaults": {},
            "known_date_filters": ["report_date"],
        },
        "Trial Balance": {
            "required_filters": ["company"],
            "optional_filters": ["from_date", "to_date", "fiscal_year", "finance_book", "cost_center", "project"],
            "defaults": {},
            "known_date_filters": ["from_date", "to_date"],
        },
        "Balance Sheet": {
            "required_filters": ["company"],
            "optional_filters": ["period_start_date", "period_end_date", "from_fiscal_year", "to_fiscal_year", "periodicity", "finance_book"],
            "defaults": {"periodicity": "Yearly"},
            "known_date_filters": ["period_start_date", "period_end_date"],
        },
        "Profit and Loss Statement": {
            "required_filters": ["company"],
            "optional_filters": ["period_start_date", "period_end_date", "from_fiscal_year", "to_fiscal_year", "periodicity", "finance_book", "cost_center", "project"],
            "defaults": {"periodicity": "Yearly"},
            "known_date_filters": ["period_start_date", "period_end_date"],
        },
        "Cash Flow": {
            "required_filters": ["company"],
            "optional_filters": ["period_start_date", "period_end_date", "from_fiscal_year", "to_fiscal_year", "periodicity", "finance_book"],
            "defaults": {"periodicity": "Yearly"},
            "known_date_filters": ["period_start_date", "period_end_date"],
        },
    }
    return specs.get(report_name)

def _validate_report_date_range(report_name: str, filters: dict[str, Any]) -> ToolResult | None:
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not from_date and not to_date:
        return None
    parsed: dict[str, date] = {}
    for key, value in {"from_date": from_date, "to_date": to_date}.items():
        if not value:
            continue
        try:
            parsed[key] = date.fromisoformat(str(value))
        except ValueError:
            return ToolResult(
                ok=False,
                error=f"Invalid date filter for {report_name}: {key}={value}",
                error_type="validation_error",
                user_message=f"{report_name} 报表的 {key} 必须使用 YYYY-MM-DD 日期格式。",
                data={
                    "report_name": report_name,
                    "status": "Invalid Date Filter",
                    "invalid_filter": key,
                    "summary": f"{key} must be an ISO date in YYYY-MM-DD format.",
                    "next_actions": ["fix_date_filter", "retry_report"],
                    "risk": {"level": "L0"},
                },
            )
    if parsed.get("from_date") and parsed.get("to_date") and parsed["from_date"] > parsed["to_date"]:
        return ToolResult(
            ok=False,
            error=f"Invalid date range for {report_name}: from_date is after to_date.",
            error_type="validation_error",
            user_message=f"{report_name} 报表的 from_date 不能晚于 to_date。",
            data={
                "report_name": report_name,
                "status": "Invalid Date Range",
                "summary": "from_date must be earlier than or equal to to_date.",
                "next_actions": ["fix_date_range", "retry_report"],
                "risk": {"level": "L0"},
            },
        )
    return None

def _draft_doc(doctype: str, data: dict[str, Any]) -> dict[str, Any]:
    draft = dict(data)
    draft["doctype"] = doctype
    draft["docstatus"] = 0
    return draft

def _asset_financial_snapshot(
    asset: dict[str, Any],
    schedule_docs: list[dict[str, Any]],
    *,
    finance_book: str | None,
    include_schedule_rows: bool,
) -> dict[str, Any]:
    finance_books = [
        row
        for row in asset.get("finance_books") or []
        if isinstance(row, dict) and (not finance_book or row.get("finance_book") == finance_book)
    ]
    schedules = []
    for schedule in schedule_docs:
        rows = [
            _clean_mapping(
                {
                    "schedule_date": row.get("schedule_date"),
                    "depreciation_amount": row.get("depreciation_amount"),
                    "accumulated_depreciation_amount": row.get("accumulated_depreciation_amount"),
                    "journal_entry": row.get("journal_entry"),
                    "depreciation_status": row.get("depreciation_status"),
                }
            )
            for row in schedule.get("depreciation_schedule") or []
            if isinstance(row, dict)
        ]
        schedules.append(
            _clean_mapping(
                {
                    "name": schedule.get("name"),
                    "asset": schedule.get("asset"),
                    "finance_book": schedule.get("finance_book"),
                    "status": schedule.get("status"),
                    "docstatus": schedule.get("docstatus"),
                    "value_after_depreciation": schedule.get("value_after_depreciation"),
                    "schedule_row_count": len(rows),
                    "schedule_rows": rows if include_schedule_rows else None,
                }
            )
        )

    return {
        "doctype": "Asset",
        "name": asset.get("name"),
        "docstatus": asset.get("docstatus"),
        "status": "Financial Snapshot",
        "summary": f"Prepared read-only financial snapshot for Asset {asset.get('name')}.",
        "asset": _clean_mapping(
            {
                "asset_name": asset.get("asset_name"),
                "company": asset.get("company"),
                "item_code": asset.get("item_code"),
                "asset_category": asset.get("asset_category"),
                "location": asset.get("location"),
                "custodian": asset.get("custodian"),
                "asset_status": asset.get("status"),
                "available_for_use_date": asset.get("available_for_use_date"),
                "gross_purchase_amount": asset.get("gross_purchase_amount"),
                "purchase_amount": asset.get("purchase_amount"),
                "opening_accumulated_depreciation": asset.get("opening_accumulated_depreciation"),
                "value_after_depreciation": asset.get("value_after_depreciation"),
                "total_number_of_depreciations": asset.get("total_number_of_depreciations"),
                "frequency_of_depreciation": asset.get("frequency_of_depreciation"),
                "depreciation_method": asset.get("depreciation_method"),
            }
        ),
        "finance_book_filter": finance_book,
        "finance_books": finance_books,
        "depreciation_schedules": schedules,
        "next_actions": ["review_financial_snapshot", "prepare_disposal_or_sale", "create_value_adjustment_draft"],
        "risk": {
            "level": "L0",
            "creates_financial_posting": False,
            "does_not_process_depreciation": True,
            "does_not_create_disposal_or_sale": True,
        },
    }

def _asset_depreciation_schedule_preview(schedule: dict[str, Any], only_due_before: str | None) -> dict[str, Any]:
    rows = []
    for row in schedule.get("depreciation_schedule") or []:
        if not isinstance(row, dict):
            continue
        schedule_date = row.get("schedule_date")
        if only_due_before and schedule_date and not _iso_date_on_or_before(str(schedule_date), only_due_before):
            continue
        rows.append(
            _clean_mapping(
                {
                    "schedule_date": schedule_date,
                    "depreciation_amount": row.get("depreciation_amount"),
                    "accumulated_depreciation_amount": row.get("accumulated_depreciation_amount"),
                    "journal_entry": row.get("journal_entry"),
                    "depreciation_status": row.get("depreciation_status"),
                }
            )
        )
    return _clean_mapping(
        {
            "name": schedule.get("name"),
            "asset": schedule.get("asset"),
            "finance_book": schedule.get("finance_book"),
            "status": schedule.get("status"),
            "docstatus": schedule.get("docstatus"),
            "value_after_depreciation": schedule.get("value_after_depreciation"),
            "schedule_row_count": len(rows),
            "schedule_rows": rows,
        }
    )

def _supplier_procurement_eligibility(supplier: dict[str, Any], scorecards: list[Any]) -> dict[str, Any]:
    scorecard_rows = [row for row in scorecards if isinstance(row, dict)]
    rfq_blockers = _supplier_blockers(supplier, scorecard_rows, "rfq")
    po_blockers = _supplier_blockers(supplier, scorecard_rows, "po")
    rfq_warnings = _supplier_warnings(supplier, scorecard_rows, "rfq")
    po_warnings = _supplier_warnings(supplier, scorecard_rows, "po")
    return {
        "eligible_for_rfq": _procurement_eligibility_status(rfq_blockers, rfq_warnings, scorecard_rows),
        "eligible_for_po": _procurement_eligibility_status(po_blockers, po_warnings, scorecard_rows),
        "rfq_blockers": rfq_blockers,
        "po_blockers": po_blockers,
        "rfq_warnings": rfq_warnings,
        "po_warnings": po_warnings,
        "scorecard_status": "available" if scorecard_rows else "unknown",
    }

def _supplier_blockers(supplier: dict[str, Any], scorecards: list[dict[str, Any]], mode: str) -> list[str]:
    blockers = []
    for field in ("disabled", "is_frozen", "on_hold"):
        if _truthy(supplier.get(field)):
            blockers.append(field)
    flag = "prevent_rfqs" if mode == "rfq" else "prevent_pos"
    if _truthy(supplier.get(flag)):
        blockers.append(flag)
    if any(_truthy(row.get(flag)) for row in scorecards):
        blockers.append(f"scorecard_{flag}")
    return blockers

def _supplier_warnings(supplier: dict[str, Any], scorecards: list[dict[str, Any]], mode: str) -> list[str]:
    flag = "warn_rfqs" if mode == "rfq" else "warn_pos"
    warnings = []
    if _truthy(supplier.get(flag)):
        warnings.append(flag)
    if any(_truthy(row.get(flag)) for row in scorecards):
        warnings.append(f"scorecard_{flag}")
    return warnings

def _procurement_eligibility_status(blockers: list[str], warnings: list[str], scorecards: list[dict[str, Any]]) -> str:
    if blockers:
        return "blocked"
    if warnings:
        return "warning"
    if not scorecards:
        return "unknown"
    return "allowed"

def _stock_batch_balance_rows(
    item_code: str,
    batch_meta: dict[str, dict[str, Any]],
    ledger_rows: list[Any],
    *,
    include_expired: bool,
    include_zero: bool,
    as_of_date: str | None,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in ledger_rows:
        if not isinstance(row, dict):
            continue
        batch_no = row.get("batch_no")
        if not batch_no:
            continue
        batch_key = str(batch_no)
        meta = batch_meta.get(batch_key, {})
        if not include_expired and _batch_is_expired(meta, as_of_date):
            continue
        key = (batch_key, row.get("warehouse"))
        existing = grouped.setdefault(
            key,
            {
                "item_code": item_code,
                "batch_no": batch_key,
                "warehouse": row.get("warehouse"),
                "actual_qty": 0.0,
                "latest_posting_date": row.get("posting_date"),
                "latest_posting_time": row.get("posting_time"),
                "latest_qty_after_transaction": row.get("qty_after_transaction"),
                "valuation_rate": row.get("valuation_rate"),
                "stock_value": row.get("stock_value"),
                "expiry_date": meta.get("expiry_date"),
                "disabled": _truthy(meta.get("disabled")),
            },
        )
        existing["actual_qty"] += _float_or_none(row.get("actual_qty")) or 0.0

    records = []
    for record in grouped.values():
        record["actual_qty"] = round(record["actual_qty"], 6)
        if not include_zero and record["actual_qty"] == 0:
            continue
        records.append(record)
    return sorted(records, key=lambda row: (str(row.get("expiry_date") or "9999-12-31"), str(row.get("batch_no") or ""), str(row.get("warehouse") or "")))

def _batch_is_expired(batch: dict[str, Any], as_of_date: str | None) -> bool:
    expiry = batch.get("expiry_date")
    if not expiry:
        return False
    comparison = as_of_date or date.today().isoformat()
    return _iso_date_on_or_before(str(expiry), comparison) and str(expiry) < comparison

def _iso_date_on_or_before(candidate: str, boundary: str) -> bool:
    try:
        return date.fromisoformat(candidate) <= date.fromisoformat(boundary)
    except ValueError:
        return candidate <= boundary

def _invoice_doctype_for_payment(party_type: str, payment_type: str) -> str:
    if party_type == "Customer" or payment_type == "Receive":
        return "Sales Invoice"
    if party_type == "Supplier" or payment_type == "Pay":
        return "Purchase Invoice"
    return ""

def _payment_references(
    invoices: list[dict[str, Any]],
    paid_amount: float | int | None,
    allocations: dict[str, Any],
    invoice_doctype: str,
) -> tuple[list[dict[str, Any]], float | None]:
    remaining = float(paid_amount) if paid_amount is not None else None
    references = []
    for invoice in invoices:
        name = invoice.get("name")
        outstanding = float(invoice.get("outstanding_amount") or 0)
        explicit = allocations.get(name) if name else None
        if explicit is not None:
            allocated = min(float(explicit), outstanding)
        elif remaining is None:
            allocated = outstanding
        else:
            allocated = min(max(remaining, 0), outstanding)
        if remaining is not None:
            remaining -= allocated
        references.append(
            {
                "reference_doctype": invoice_doctype,
                "reference_name": name,
                "total_amount": invoice.get("grand_total"),
                "outstanding_amount": outstanding,
                "allocated_amount": allocated,
                "due_date": invoice.get("due_date"),
                "currency": invoice.get("currency"),
            }
        )
    return references, remaining

def _tax_template_doctype(invoice_type: str) -> str | None:
    normalized = invoice_type.lower()
    if normalized in {"sales", "sales_invoice", "sales invoice"}:
        return "Sales Taxes and Charges Template"
    if normalized in {"purchase", "purchase_invoice", "purchase invoice"}:
        return "Purchase Taxes and Charges Template"
    return None

def _prepared_tax_rows(source_taxes: list[dict[str, Any]], net_total: float) -> tuple[list[dict[str, Any]], float]:
    rows = []
    total_tax = 0.0
    for row in source_taxes:
        rate = float(row.get("rate") or 0)
        explicit_amount = row.get("tax_amount") if row.get("tax_amount") is not None else row.get("amount")
        estimated_amount = float(explicit_amount) if explicit_amount is not None else round(net_total * rate / 100, 2)
        total_tax += estimated_amount
        rows.append(
            {
                "charge_type": row.get("charge_type"),
                "account_head": row.get("account_head"),
                "description": row.get("description"),
                "rate": rate,
                "estimated_tax_amount": estimated_amount,
                "cost_center": row.get("cost_center"),
                "included_in_print_rate": row.get("included_in_print_rate"),
            }
        )
    return rows, round(total_tax, 2)

def _users_filters(args: dict[str, Any], keys: tuple[str, ...]) -> list[list[Any]]:
    filters = []
    for key in keys:
        if key in args and args[key] is not None:
            value = args[key]
            if isinstance(value, bool):
                value = 1 if value else 0
            filters.append([key, "=", value])
    return filters

def _extract_permission_rows(schema_data: dict[str, Any]) -> list[dict[str, Any]]:
    containers = [schema_data]
    data = schema_data.get("data")
    if isinstance(data, dict):
        containers.append(data)
    docs = schema_data.get("docs")
    if isinstance(docs, list):
        containers.extend(doc for doc in docs if isinstance(doc, dict))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for container in containers:
        raw_permissions = container.get("permissions")
        if not isinstance(raw_permissions, list):
            continue
        for row in raw_permissions:
            if not isinstance(row, dict):
                continue
            fingerprint = tuple(sorted((str(key), str(value)) for key, value in row.items()))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append(dict(row))
    return rows

def _metadata_effective_permissions(
    role_names: set[str],
    permission_rows: list[dict[str, Any]],
) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    effective = {action: False for action in USER_PERMISSION_ACTIONS}
    matched_rows: list[dict[str, Any]] = []
    roles_to_match = set(role_names) | {"All"}

    for row in permission_rows:
        role = row.get("role")
        if role not in roles_to_match:
            continue
        matched_row = _permission_row_preview(row)
        matched_rows.append(matched_row)
        for action in USER_PERMISSION_ACTIONS:
            if _truthy(row.get(action)):
                effective[action] = True
    return effective, matched_rows

def _permission_difference_reasons(docname: str | None, metadata_allowed: bool, server_allowed: bool) -> list[str]:
    if metadata_allowed == server_allowed:
        return []
    if metadata_allowed and not server_allowed:
        reasons = ["user_permission", "controller_hook", "workflow_state"]
        if docname:
            reasons.insert(0, "owner_rule")
            reasons.insert(1, "docshare")
        return reasons
    return ["docshare", "owner_rule", "controller_hook"]

def _permission_row_preview(row: dict[str, Any]) -> dict[str, Any]:
    preview = {
        "role": row.get("role"),
        "permlevel": row.get("permlevel", 0),
        "if_owner": _truthy(row.get("if_owner")),
        "apply_user_permissions": _truthy(row.get("apply_user_permissions")),
    }
    for action in USER_PERMISSION_ACTIONS:
        preview[action] = _truthy(row.get(action))
    if row.get("name"):
        preview["name"] = row.get("name")
    return preview

PERMISSION_POLICY_FIELDS = set(USER_PERMISSION_ACTIONS) | {"if_owner", "apply_user_permissions"}

PERMISSION_POLICY_MATCH_FIELDS = PERMISSION_POLICY_FIELDS | {"name", "role", "permlevel"}

def _simulate_permission_policy_changes(
    before_rows: list[dict[str, Any]],
    changes: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]] | ToolResult:
    after_rows = [dict(row) for row in before_rows]
    diff: dict[str, list[dict[str, Any]]] = {"added": [], "updated": [], "removed": []}
    normalized_changes: list[dict[str, Any]] = []

    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            return _permission_policy_validation_error(index, "Each change must be an object.")
        operation = str(change.get("operation") or "").strip().lower()
        if operation not in {"add", "update", "remove"}:
            return _permission_policy_validation_error(index, "operation must be add, update, or remove.")

        permissions_result = _normalize_permission_policy_permissions(change.get("permissions") or {}, index)
        if isinstance(permissions_result, ToolResult):
            return permissions_result
        permissions = permissions_result

        if operation == "add":
            role = change.get("role")
            if not role:
                return _permission_policy_validation_error(index, "add requires role.")
            permlevel_result = _normalize_permlevel(change.get("permlevel", 0), index)
            if isinstance(permlevel_result, ToolResult):
                return permlevel_result
            row = _blank_permission_policy_row(str(role), permlevel_result)
            row.update(permissions)
            after_rows.append(row)
            diff["added"].append(dict(row))
            normalized_changes.append({"operation": operation, "role": row["role"], "permlevel": row["permlevel"], "permissions": permissions})
            continue

        match_result = _normalize_permission_policy_match(change.get("match") or change, index)
        if isinstance(match_result, ToolResult):
            return match_result
        match = match_result
        target_indexes = [row_index for row_index, row in enumerate(after_rows) if _permission_policy_row_matches(row, match)]
        if not target_indexes:
            return _permission_policy_validation_error(index, "No permission row matched the change.", {"match": match})
        if len(target_indexes) > 1:
            return _permission_policy_validation_error(index, "Permission row match is ambiguous.", {"match": match, "matched_rows": [after_rows[i] for i in target_indexes]})

        target_index = target_indexes[0]
        before = dict(after_rows[target_index])
        if operation == "remove":
            removed = after_rows.pop(target_index)
            diff["removed"].append(dict(removed))
            normalized_changes.append({"operation": operation, "match": match})
            continue

        if not permissions:
            return _permission_policy_validation_error(index, "update requires at least one permission field.")
        updated = dict(before)
        updated.update(permissions)
        after_rows[target_index] = updated
        changed_fields = {
            key: {"before": before.get(key), "after": updated.get(key)}
            for key in permissions
            if before.get(key) != updated.get(key)
        }
        diff["updated"].append({"match": match, "before": before, "after": dict(updated), "changed_fields": changed_fields})
        normalized_changes.append({"operation": operation, "match": match, "permissions": permissions})

    return after_rows, diff, normalized_changes

def _blank_permission_policy_row(role: str, permlevel: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "role": role,
        "permlevel": permlevel,
        "if_owner": False,
        "apply_user_permissions": False,
    }
    for action in USER_PERMISSION_ACTIONS:
        row[action] = False
    return row

def _normalize_permission_policy_permissions(value: dict[str, Any], index: int) -> dict[str, bool] | ToolResult:
    if not isinstance(value, dict):
        return _permission_policy_validation_error(index, "permissions must be an object.")
    invalid = sorted(set(value) - PERMISSION_POLICY_FIELDS)
    if invalid:
        return _permission_policy_validation_error(index, "Unsupported permission fields.", {"unsupported_fields": invalid, "supported_fields": sorted(PERMISSION_POLICY_FIELDS)})
    return {key: _truthy(field_value) for key, field_value in value.items()}

def _normalize_permission_policy_match(value: dict[str, Any], index: int) -> dict[str, Any] | ToolResult:
    if not isinstance(value, dict):
        return _permission_policy_validation_error(index, "match must be an object.")
    match = {key: value[key] for key in value if key in PERMISSION_POLICY_MATCH_FIELDS and key not in {"operation", "permissions"}}
    invalid = sorted(set(value) - PERMISSION_POLICY_MATCH_FIELDS - {"operation", "permissions"})
    if invalid:
        return _permission_policy_validation_error(index, "Unsupported match fields.", {"unsupported_fields": invalid, "supported_fields": sorted(PERMISSION_POLICY_MATCH_FIELDS)})
    if not match:
        return _permission_policy_validation_error(index, "update/remove requires match, role, permlevel, or name.")
    if "permlevel" in match:
        permlevel_result = _normalize_permlevel(match["permlevel"], index)
        if isinstance(permlevel_result, ToolResult):
            return permlevel_result
        match["permlevel"] = permlevel_result
    for key in PERMISSION_POLICY_FIELDS:
        if key in match:
            match[key] = _truthy(match[key])
    if "role" in match:
        match["role"] = str(match["role"])
    if "name" in match:
        match["name"] = str(match["name"])
    return match

def _permission_policy_row_matches(row: dict[str, Any], match: dict[str, Any]) -> bool:
    return all(row.get(key) == value for key, value in match.items())

def _normalize_permlevel(value: Any, index: int) -> int | ToolResult:
    try:
        permlevel = int(value)
    except (TypeError, ValueError):
        return _permission_policy_validation_error(index, "permlevel must be an integer.")
    if permlevel < 0:
        return _permission_policy_validation_error(index, "permlevel must be zero or greater.")
    return permlevel

def _permission_policy_validation_error(index: int, message: str, data: dict[str, Any] | None = None) -> ToolResult:
    payload = {"change_index": index, "message": message}
    if data:
        payload.update(data)
    return ToolResult(
        ok=False,
        error=message,
        error_type="validation_error",
        user_message="权限策略预览参数不正确，请检查变更类型、匹配条件和权限字段。",
        data=payload,
    )

def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    return bool(value)

def _users_read_result(result: ToolResult, doctype: str, summary: str) -> ToolResult:
    if not result.ok:
        return result
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "doctype": doctype,
            "status": "Read Only",
            "summary": summary,
            "records": result.data or [],
            "next_actions": ["review_results", "use_L5_ADMIN_tool_for_changes"],
            "risk": {"level": "L0", "admin_write_tools_require_confirmation": True},
        },
    )

def _users_write_result(result: ToolResult, doctype: str, name: str | None, summary: str) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "doctype": doctype,
            "name": raw.get("name") or name,
            "docstatus": raw.get("docstatus"),
            "status": "Admin Change Applied",
            "summary": summary,
            "next_actions": ["audit_change", "review_effective_access"],
            "risk": {"level": "L5_ADMIN", "confirmation_required": True, "confirmation_checked": True},
        },
        debug={"raw_document": raw or result.data},
    )

def _buying_quotation_comparison_result(
    quotations: list[dict[str, Any]],
    *,
    prefer: str,
    include_unsubmitted: bool,
) -> ToolResult:
    warnings: list[str] = []
    rows_by_item: dict[str, list[dict[str, Any]]] = {}
    skipped: list[dict[str, Any]] = []

    for quotation in quotations:
        name = quotation.get("name")
        docstatus = int(quotation.get("docstatus") or 0)
        if docstatus == 0 and not include_unsubmitted:
            skipped.append({"supplier_quotation": name, "reason": "draft_excluded"})
            continue
        supplier = quotation.get("supplier")
        currency = quotation.get("currency")
        transaction_date = quotation.get("transaction_date")
        valid_till = quotation.get("valid_till")
        for item in quotation.get("items") or []:
            if not isinstance(item, dict):
                continue
            item_code = item.get("item_code")
            if not item_code:
                warnings.append(f"Supplier Quotation {name} has an item row without item_code.")
                continue
            qty = _number_or_none(item.get("qty"))
            rate = _number_or_none(item.get("rate") if item.get("rate") is not None else item.get("base_rate"))
            amount = _number_or_none(item.get("amount") if item.get("amount") is not None else item.get("base_amount"))
            row = {
                "supplier_quotation": name,
                "supplier": supplier,
                "docstatus": docstatus,
                "currency": currency,
                "transaction_date": transaction_date,
                "valid_till": valid_till,
                "item_code": item_code,
                "item_name": item.get("item_name"),
                "qty": qty,
                "uom": item.get("uom") or item.get("stock_uom"),
                "rate": rate,
                "amount": amount,
                "schedule_date": item.get("schedule_date") or item.get("expected_delivery_date"),
                "lead_time_days": _number_or_none(item.get("lead_time_days")),
            }
            rows_by_item.setdefault(str(item_code), []).append(row)

    comparisons = []
    recommendations = []
    for item_code in sorted(rows_by_item):
        candidates = rows_by_item[item_code]
        currencies = {row.get("currency") for row in candidates if row.get("currency")}
        if len(currencies) > 1:
            warnings.append(f"Item {item_code} has multiple currencies; rates were not FX-normalized.")
        ranked = sorted(candidates, key=_quotation_candidate_sort_key(prefer))
        best = ranked[0] if ranked else None
        comparisons.append(
            {
                "item_code": item_code,
                "candidate_count": len(candidates),
                "candidates": ranked,
                "best_supplier": best.get("supplier") if best else None,
                "best_supplier_quotation": best.get("supplier_quotation") if best else None,
                "best_rate": best.get("rate") if best else None,
                "currency": best.get("currency") if best else None,
            }
        )
        if best:
            recommendations.append(
                {
                    "item_code": item_code,
                    "supplier": best.get("supplier"),
                    "supplier_quotation": best.get("supplier_quotation"),
                    "rate": best.get("rate"),
                    "currency": best.get("currency"),
                    "reason": _quotation_recommendation_reason(best, prefer),
                }
            )

    return ToolResult(
        ok=True,
        data={
            "doctype": "Supplier Quotation",
            "name": None,
            "docstatus": None,
            "status": "Comparison Preview",
            "summary": f"Compared {len(quotations)} supplier quotation(s) across {len(comparisons)} item(s).",
            "next_actions": ["review_recommendations", "confirm_supplier_selection", "create_purchase_order_draft"],
            "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            "prefer": prefer,
            "comparisons": comparisons,
            "recommendations": recommendations,
            "warnings": warnings,
            "skipped": skipped,
        },
        debug={"raw_documents": quotations},
    )

def _quotation_candidate_sort_key(prefer: str) -> Callable[[dict[str, Any]], tuple[Any, ...]]:
    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        rate = row.get("rate")
        amount = row.get("amount")
        schedule_date = row.get("schedule_date") or "9999-12-31"
        lead_time = row.get("lead_time_days")
        rate_key = rate if rate is not None else float("inf")
        amount_key = amount if amount is not None else float("inf")
        lead_time_key = lead_time if lead_time is not None else float("inf")
        if prefer == "earliest_delivery":
            return (schedule_date, lead_time_key, rate_key, amount_key, str(row.get("supplier") or ""))
        if prefer == "lowest_amount":
            return (amount_key, rate_key, schedule_date, str(row.get("supplier") or ""))
        return (rate_key, amount_key, schedule_date, str(row.get("supplier") or ""))

    return key

def _quotation_recommendation_reason(row: dict[str, Any], prefer: str) -> str:
    if prefer == "earliest_delivery":
        return "Earliest schedule date, then lead time and rate."
    if prefer == "lowest_amount":
        return "Lowest line amount, then rate and delivery date."
    return "Lowest quoted rate, then amount and delivery date."

def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _require_admin_confirmation(
    action: str,
    doctype: str,
    name: str | None,
    confirmation: dict[str, Any] | None,
    preview: dict[str, Any],
) -> ToolResult | None:
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed", "confirmed_by", "confirmed_at", "reason")
        if not confirmation.get(field)
    ]
    if confirmation.get("confirmed") is not True or missing:
        return ToolResult(
            ok=False,
            data={
                "doctype": doctype,
                "name": name,
                "status": "Confirmation Required",
                "summary": f"Admin confirmation required before {action} can be executed.",
                "preview": preview,
                "next_actions": ["obtain_explicit_admin_confirmation", "retry_with_confirmation_metadata"],
                "risk": {
                    "level": "L5_ADMIN",
                    "confirmation_required": True,
                    "required_confirmation_fields": ["confirmed", "confirmed_by", "confirmed_at", "reason"],
                },
            },
            error=f"Admin confirmation required for {action}.",
            error_type="admin_confirmation_required",
            user_message="用户、角色、权限变更属于 L5_ADMIN 高风险操作，需要明确确认后才能执行。",
            meta={
                "risk_level": "L5_ADMIN",
                "required_confirmation_fields": ["confirmed", "confirmed_by", "confirmed_at", "reason"],
                "action": action,
                "doctype": doctype,
                "name": name,
            },
        )
    return None

def _clean_mapping(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}

def _module_search_result(result: ToolResult, doctype: str, filters: dict[str, Any], risk_level: str) -> ToolResult:
    if not result.ok:
        return result
    records = result.data if isinstance(result.data, list) else []
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "doctype": doctype,
            "records": records,
            "count": len(records),
            "filters": filters,
            "summary": f"Fetched {len(records)} {doctype} records.",
            "next_actions": [],
            "risk": {"level": risk_level},
        },
        debug={"raw_data": result.data},
    )

def _module_report_result(result: ToolResult, report_name: str, filters: dict[str, Any]) -> ToolResult:
    if not result.ok:
        return result
    data = result.data if isinstance(result.data, dict) else {}
    rows = data.get("rows") or []
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "report_name": report_name,
            "filters": filters,
            "columns": data.get("columns") or [],
            "rows": rows,
            "summary": f"Fetched {len(rows)} rows from {report_name}.",
            "report_summary": data.get("summary"),
            "next_actions": [],
            "risk": {"level": "L0"},
        },
        debug={"raw_report": data.get("raw") or data},
    )

def _module_doc_result(
    result: ToolResult,
    doctype: str,
    risk_level: str,
    summary: str,
    next_actions: list[str],
    *,
    requires_confirmation_for_submit: bool,
) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    docstatus = raw.get("docstatus")
    status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(docstatus, raw.get("status"))
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "doctype": raw.get("doctype") or doctype,
            "name": raw.get("name"),
            "docstatus": docstatus,
            "status": status,
            "summary": summary,
            "next_actions": next_actions,
            "risk": {
                "level": risk_level,
                "requires_confirmation_for_submit": requires_confirmation_for_submit,
            },
        },
        debug={"raw_document": result.data},
    )

def _module_draft_result(
    result: ToolResult,
    *,
    doctype: str,
    summary: str,
    risk_level: str = "L3",
    submit_tool: str | None = None,
) -> ToolResult:
    wrapped = _module_doc_result(
        result,
        doctype,
        risk_level,
        summary,
        ["review_draft", "confirm_submit"] if submit_tool else ["review_master_data"],
        requires_confirmation_for_submit=bool(submit_tool),
    )
    if wrapped.ok and submit_tool and isinstance(wrapped.data, dict):
        wrapped.data["risk"]["submit_tool"] = submit_tool
    return wrapped

def _without_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in (None, "")}

def _select_ready_item(search_result: dict[str, Any]) -> str | None:
    candidates = search_result.get("candidates") or []
    if search_result.get("status") != "ready" or not candidates:
        return None
    candidate = candidates[0]
    if not candidate.get("enabled", True):
        return None
    return candidate.get("item_code")

def _item_resolution_error(message: str = "无法解析到唯一可用的 ERPNext Item，请先调用 erpnext.stock.resolve_item 并让用户确认。") -> ToolResult:
    return ToolResult(
        ok=False,
        error=message,
        error_type="item_resolution_required",
        user_message="无法确认唯一物料编码，请先检索并确认 Item。",
        data={
            "status": "needs_item_resolution",
            "summary": message,
            "next_actions": ["search_items", "confirm_item_selection", "retry_draft_creation"],
            "risk": {"level": "L1", "requires_confirmation_for_submit": False},
        },
        meta={"next_tool": "erpnext.search_items"},
    )

def _stock_draft_result(result: ToolResult, *, doctype: str, summary: str) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    name = raw.get("name")
    data = {
        "doctype": doctype,
        "name": name,
        "docstatus": raw.get("docstatus", 0),
        "status": "Draft",
        "summary": summary,
        "next_actions": ["review_draft", "confirm_submit"],
        "risk": {
            "level": "L3",
            "requires_confirmation_for_submit": True,
            "submit_tool": "erpnext.stock.submit_document",
        },
    }
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data=data,
        debug={"raw_document": raw} if raw else result.debug,
    )

def _stock_master_result(result: ToolResult, *, doctype: str, action: str) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    data = {
        "doctype": doctype,
        "name": raw.get("name"),
        "docstatus": raw.get("docstatus"),
        "status": raw.get("disabled", 0) and "Disabled" or "Active",
        "summary": action,
        "next_actions": ["review_master_data"],
        "risk": {
            "level": "L3",
            "requires_confirmation_for_submit": False,
        },
    }
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data=data,
        debug={"raw_document": raw} if raw else result.debug,
    )

def _stock_traceability_result(result: ToolResult, *, doctype: str, action: str) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    data = {
        "doctype": doctype,
        "name": raw.get("name"),
        "docstatus": raw.get("docstatus"),
        "status": raw.get("status") or (raw.get("disabled", 0) and "Disabled") or "Updated",
        "summary": action,
        "next_actions": ["audit_traceability_record"],
        "risk": {
            "level": "L4",
            "requires_confirmation_for_submit": False,
        },
    }
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data=data,
        debug={"raw_document": raw} if raw else result.debug,
    )

def _stock_preview_result(result: ToolResult, *, summary: str, next_actions: list[str]) -> ToolResult:
    if not result.ok:
        return result
    payload = result.data if isinstance(result.data, dict) else {"raw": result.data}
    data = {
        "doctype": None,
        "name": None,
        "docstatus": None,
        "status": payload.get("status", "preview"),
        "summary": summary,
        "next_actions": next_actions,
        "risk": {
            "level": "L1",
            "requires_confirmation_for_submit": False,
        },
        "preview": payload,
    }
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data=data,
        debug=result.debug,
    )

def _stock_document_impact_result(doctype: str, name: str, document: Any, ledger_entries: Any) -> ToolResult:
    doc = document if isinstance(document, dict) else {}
    ledger_rows = ledger_entries if isinstance(ledger_entries, list) else []
    total_qty = sum(float(row.get("actual_qty") or 0) for row in ledger_rows if isinstance(row, dict))
    total_value_difference = sum(float(row.get("stock_value_difference") or 0) for row in ledger_rows if isinstance(row, dict))
    owner_module = "Sales" if doctype == "Delivery Note" else "Buying"
    return ToolResult(
        ok=True,
        data={
            "doctype": doctype,
            "name": name,
            "docstatus": doc.get("docstatus"),
            "status": doc.get("status"),
            "summary": f"Read stock impact for {doctype} {name}: {len(ledger_rows)} stock ledger rows.",
            "next_actions": ["review_stock_ledger_entries", f"use_{owner_module.lower()}_module_for_draft_changes"],
            "risk": {
                "level": "L0",
                "requires_confirmation_for_submit": False,
            },
            "boundary": {
                "owner_module": owner_module,
                "stock_module_role": "read_stock_impact_only",
                "draft_creation_tool": "erpnext.buying.create_purchase_receipt_draft" if doctype == "Purchase Receipt" else None,
            },
            "impact": {
                "ledger_entry_count": len(ledger_rows),
                "total_actual_qty": total_qty,
                "total_stock_value_difference": total_value_difference,
                "ledger_entries": ledger_rows,
            },
            "document": {
                "customer": doc.get("customer"),
                "supplier": doc.get("supplier"),
                "posting_date": doc.get("posting_date"),
                "modified": doc.get("modified"),
            },
        },
        debug={"raw_document": doc},
    )

def _require_stock_confirmation(doctype: str | None, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    if doctype not in STOCK_SUBMITTABLE_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Stock confirmation required for {doctype}.",
            error_type="stock_confirmation_required",
            user_message="库存提交/取消会影响库存数量或成本，需要 confirmation 的 confirmed_by、confirmed_at、confirmation_text 和 reason。",
            meta={
                "risk_level": "L4",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
                "name": name,
            },
        )
    return None

def _require_traceability_confirmation(doctype: str, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Traceability confirmation required for {doctype}.",
            error_type="traceability_confirmation_required",
            user_message="批次/序列号更新会影响库存追溯，需要 confirmation 的 confirmed_by、confirmed_at、confirmation_text 和 reason。",
            data={
                "doctype": doctype,
                "name": name,
                "status": "confirmation_required",
                "summary": f"{doctype} traceability update requires explicit confirmation.",
                "next_actions": ["collect_confirmation", "retry_update"],
                "risk": {"level": "L4", "requires_confirmation_for_submit": False},
            },
            meta={
                "risk_level": "L4",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
                "name": name,
            },
        )
    return None

def _require_buying_confirmation(doctype: str | None, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    if doctype not in BUYING_SUBMITTABLE_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Buying confirmation required for {doctype}.",
            error_type="buying_confirmation_required",
            user_message="采购提交会形成业务承诺或库存影响，需要 confirmation 的 confirmed_by、confirmed_at、confirmation_text 和 reason。",
            meta={
                "risk_level": "L4",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
                "name": name,
            },
        )
    return None

def _require_accounting_write_confirmation(
    action: str,
    doctype: str | None,
    name: str | None,
    confirmation: dict[str, Any] | None,
) -> ToolResult | None:
    if doctype not in ACCOUNTING_WRITE_GUARDED_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Accounting write confirmation required for {doctype}.",
            error_type="financial_confirmation_required",
            user_message="财务凭证或财务主数据写入属于高风险操作，需要 confirmation.confirmed_by、confirmed_at、confirmation_text 和 reason。",
            data={
                "doctype": doctype,
                "name": name,
                "status": "Confirmation Required",
                "summary": f"L5_FINANCIAL confirmation required before {action} can be executed.",
                "next_actions": ["obtain_explicit_finance_confirmation", "use_accounting_module_tool_when_available", "retry_with_confirmation_metadata"],
                "risk": {
                    "level": "L5_FINANCIAL",
                    "confirmation_required": True,
                    "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                },
            },
            meta={
                "risk_level": "L5_FINANCIAL",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "action": action,
                "doctype": doctype,
                "name": name,
            },
        )
    return None

def _call_method_doctype(method: str, args: dict[str, Any]) -> str | None:
    if method in {"agent_bridge.api.submit_document", "agent_bridge.api.cancel_document"}:
        return args.get("doctype")
    if method in {"frappe.client.insert", "frappe.client.save"}:
        doc = args.get("doc") or args.get("docs")
        if isinstance(doc, dict):
            return doc.get("doctype")
        return args.get("doctype")
    return args.get("doctype") or args.get("dt")

def _call_method_name(args: dict[str, Any]) -> str | None:
    doc = args.get("doc") or args.get("docs")
    if isinstance(doc, dict) and doc.get("name"):
        return doc.get("name")
    return args.get("name") or args.get("dn")

def _require_asset_confirmation(doctype: str | None, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    if doctype not in ASSET_SUBMITTABLE_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Asset confirmation required for {doctype}.",
            error_type="asset_confirmation_required",
            user_message="资产提交、资本化、价值调整、报废或出售属于高风险操作，需要 confirmation.confirmed_by、confirmed_at、confirmation_text 和 reason。",
            meta={
                "risk_level": "L5_FINANCIAL" if doctype in ASSET_FINANCIAL_DOCTYPES else "L4",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
                "name": name,
            },
        )
    return None

def _require_l5_financial_confirmation(action: str, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"L5 financial confirmation required for {action}.",
            error_type="financial_confirmation_required",
            user_message="此财务操作属于 L5_FINANCIAL 高风险操作，需要 confirmation.confirmed_by、confirmed_at、confirmation_text 和 reason。",
            data={
                "doctype": None,
                "name": name,
                "status": "Confirmation Required",
                "summary": f"L5_FINANCIAL confirmation required before {action} can be executed.",
                "next_actions": ["obtain_explicit_finance_confirmation", "retry_with_confirmation_metadata"],
                "risk": {
                    "level": "L5_FINANCIAL",
                    "confirmation_required": True,
                    "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                },
            },
            meta={
                "risk_level": "L5_FINANCIAL",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "action": action,
                "name": name,
            },
        )
    return None

def _require_financial_confirmation(doctype: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    if doctype not in ACCOUNTING_SUBMITTABLE_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Financial confirmation required for {doctype}.",
            error_type="financial_confirmation_required",
            user_message="财务提交/取消属于 L5_FINANCIAL 高风险操作，需要 confirmation.confirmed_by、confirmed_at、confirmation_text 和 reason。",
            meta={
                "risk_level": "L5_FINANCIAL",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
            },
        )
    return None


__all__ = [name for name in globals() if not name.startswith("__")]
