from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .procurement import (
    CapabilityCompilationError,
    DocumentLoader,
    DocumentReference,
    IntentItem,
    PreparedBusinessAction,
    canonical_tool_call_hash,
)


FINANCE_GOALS = frozenset({
    "query_accounts_payable",
    "create_purchase_invoice_from_receipt",
    "create_supplier_payment_from_invoice",
    "cancel_financial_document",
})

FINANCIAL_DOCTYPES = frozenset({
    "Journal Entry",
    "Payment Entry",
    "Sales Invoice",
    "Purchase Invoice",
    "Period Closing Voucher",
})


@dataclass(frozen=True)
class FinanceBusinessIntentDraft:
    goal: str
    source_documents: tuple[DocumentReference, ...] = ()
    items: tuple[IntentItem, ...] = ()
    company: str | None = None
    supplier: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    posting_date: str | None = None
    bill_no: str | None = None
    bill_date: str | None = None
    paid_amount: float | None = None
    reference_no: str | None = None
    reference_date: str | None = None
    reason: str | None = None
    remarks: str | None = None
    provenance: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FinanceBusinessIntentDraft":
        if not isinstance(payload, dict):
            raise ValueError("business_intent must be an object")
        goal = str(payload.get("goal") or "").strip()
        if goal not in FINANCE_GOALS:
            raise ValueError(f"unsupported finance goal: {goal}")
        raw_sources = payload.get("source_documents") or []
        if isinstance(payload.get("source_document"), dict):
            raw_sources = [payload["source_document"], *raw_sources]
        if not isinstance(raw_sources, list):
            raise ValueError("source_documents must be an array")
        raw_items = payload.get("items") or []
        if not isinstance(raw_items, list):
            raise ValueError("items must be an array")
        provenance = payload.get("provenance") or {}
        if not isinstance(provenance, dict):
            raise ValueError("provenance must be an object")
        return cls(
            goal=goal,
            source_documents=tuple(DocumentReference.from_dict(row) for row in raw_sources if isinstance(row, dict)),
            items=tuple(IntentItem.from_dict(row) for row in raw_items if isinstance(row, dict)),
            company=_text(payload.get("company")),
            supplier=_text(payload.get("supplier")),
            from_date=_iso_date(payload.get("from_date"), "from_date"),
            to_date=_iso_date(payload.get("to_date"), "to_date"),
            posting_date=_iso_date(payload.get("posting_date"), "posting_date"),
            bill_no=_text(payload.get("bill_no")),
            bill_date=_iso_date(payload.get("bill_date"), "bill_date"),
            paid_amount=_optional_positive_number(payload.get("paid_amount"), "paid_amount"),
            reference_no=_text(payload.get("reference_no")),
            reference_date=_iso_date(payload.get("reference_date"), "reference_date"),
            reason=_text(payload.get("reason")),
            remarks=_text(payload.get("remarks")),
            provenance={str(key): str(value) for key, value in provenance.items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FinanceCapabilityGraph:
    _CARDS = {
        "query_accounts_payable": ("finance.accounts_payable.query", "erpnext.accounting.accounts_payable", False),
        "create_purchase_invoice_from_receipt": ("finance.purchase_invoice.from_receipt", "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft", True),
        "create_supplier_payment_from_invoice": ("finance.supplier_payment.from_invoice", "erpnext.accounting.create_supplier_payment_from_purchase_invoice_draft", True),
        "cancel_financial_document": ("finance.document.cancel", "erpnext.accounting.cancel_financial_document", True),
    }

    def for_goal(self, goal: str) -> dict[str, Any]:
        value = self._CARDS.get(goal)
        if value is None:
            raise CapabilityCompilationError(f"没有财务业务能力可以处理目标 {goal}")
        name, tool, write = value
        return {"name": name, "goal": goal, "tool": tool, "write": write}

    def cards(self) -> list[dict[str, Any]]:
        return [self.for_goal(goal) for goal in sorted(self._CARDS)]


class FinanceCapabilityCompiler:
    def __init__(self, document_loader: DocumentLoader, *, graph: FinanceCapabilityGraph | None = None) -> None:
        self.document_loader = document_loader
        self.graph = graph or FinanceCapabilityGraph()

    def compile(self, intent: FinanceBusinessIntentDraft, *, runtime_context: dict[str, Any], today: date) -> PreparedBusinessAction:
        spec = self.graph.for_goal(intent.goal)
        snapshots = [self.document_loader(ref.doctype, ref.name) for ref in intent.source_documents]
        builders = {
            "query_accounts_payable": self._accounts_payable,
            "create_purchase_invoice_from_receipt": self._purchase_invoice,
            "create_supplier_payment_from_invoice": self._supplier_payment,
            "cancel_financial_document": self._cancel_document,
        }
        arguments, sources, checks, summary = builders[intent.goal](intent, runtime_context, today, snapshots)
        tool_call = {"tool": spec["tool"], "arguments": _without_empty(arguments)}
        return PreparedBusinessAction(
            capability=spec["name"],
            goal=intent.goal,
            tool_call=tool_call,
            summary=summary,
            field_sources=sources,
            preflight_checks=tuple(checks),
            confirmation_hash=canonical_tool_call_hash(tool_call),
            write=bool(spec["write"]),
        )

    def _accounts_payable(self, intent, runtime, today, _snapshots):
        company = intent.company or runtime.get("company")
        if not company:
            raise CapabilityCompilationError("应付查询缺少公司。", questions=("请确认要查询哪家公司。",))
        from_date = intent.from_date
        to_date = intent.to_date or today.isoformat()
        if from_date and from_date > to_date:
            raise CapabilityCompilationError("应付查询开始日期不能晚于结束日期。")
        return (
            {"company": company, "from_date": from_date, "to_date": to_date, "party": intent.supplier},
            _sources(intent, "company", "from_date", "to_date", "supplier"),
            ["company_resolved", "supplier_resolved_if_present", "read_only_report"],
            f"查询截至 {to_date} 的应付账款",
        )

    def _purchase_invoice(self, intent, runtime, today, snapshots):
        source = _single_source(intent, snapshots, "Purchase Receipt", submitted=True)
        if not intent.bill_no:
            raise CapabilityCompilationError("采购发票缺少供应商发票号。", questions=("请提供供应商发票号。",))
        if not intent.bill_date:
            raise CapabilityCompilationError("采购发票缺少供应商发票日期。", questions=("请提供供应商发票日期。",))
        selected = []
        for item in intent.items:
            selected.append(_without_empty({
                "purchase_receipt_item": item.source_row,
                "item_code": item.item_code,
                "qty": item.qty,
                "rate": item.rate,
            }))
        return (
            {
                "purchase_receipt": source["name"],
                "posting_date": intent.posting_date or today.isoformat(),
                "bill_no": intent.bill_no,
                "bill_date": intent.bill_date,
                "company": intent.company or source.get("company") or runtime.get("company"),
                "selected_items": selected or None,
            },
            _sources(intent, "posting_date", "bill_no", "bill_date", "company", source_documents="resolver+erpnext"),
            ["receipt_is_submitted", "receipt_is_not_return", "supplier_invoice_number_from_user", "billable_quantity_checked_by_adapter", "draft_only"],
            f"从采购收货单 {source['name']} 创建采购发票草稿，供应商发票号 {intent.bill_no}",
        )

    def _supplier_payment(self, intent, _runtime, today, snapshots):
        source = _single_source(intent, snapshots, "Purchase Invoice", submitted=True)
        outstanding = _number(source.get("outstanding_amount"))
        if outstanding <= 0:
            raise CapabilityCompilationError("该采购发票没有未付金额。")
        if intent.paid_amount is not None and intent.paid_amount > outstanding:
            raise CapabilityCompilationError(f"付款金额不能超过发票未付金额 {outstanding:g}。")
        return (
            {
                "purchase_invoice": source["name"],
                "posting_date": intent.posting_date or today.isoformat(),
                "paid_amount": intent.paid_amount,
                "reference_no": intent.reference_no,
                "reference_date": intent.reference_date,
                "remarks": intent.remarks,
            },
            _sources(intent, "posting_date", "paid_amount", "reference_no", "reference_date", source_documents="resolver+erpnext"),
            ["invoice_is_submitted", "outstanding_amount_positive", "payment_not_above_outstanding", "accounts_generated_by_erpnext", "draft_only"],
            f"从采购发票 {source['name']} 创建供应商付款草稿，金额 {intent.paid_amount or outstanding:g}",
        )

    def _cancel_document(self, intent, _runtime, _today, snapshots):
        if not intent.reason:
            raise CapabilityCompilationError("财务冲销缺少业务原因。", questions=("请说明为什么需要取消冲销这张财务单据。",))
        if len(intent.source_documents) != 1 or len(snapshots) != 1:
            raise CapabilityCompilationError("财务冲销需要唯一来源单据。", questions=("请选择一张要取消冲销的财务单据。",))
        ref, source = intent.source_documents[0], snapshots[0]
        if ref.doctype not in FINANCIAL_DOCTYPES:
            raise CapabilityCompilationError(f"不支持取消冲销 {ref.doctype}。")
        if int(source.get("docstatus") or 0) != 1:
            raise CapabilityCompilationError("只有已提交的财务单据才能取消冲销。")
        return (
            {"doctype": ref.doctype, "name": ref.name, "reason": intent.reason},
            _sources(intent, "reason", source_documents="resolver+erpnext"),
            ["financial_document_resolved", "document_is_submitted", "reason_from_user", "erpnext_period_and_link_validation", "financial_confirmation_required"],
            f"取消冲销 {ref.doctype} {ref.name}，原因：{intent.reason}",
        )


def verify_finance_result(prepared: PreparedBusinessAction, tool_result: dict[str, Any], document_loader: DocumentLoader) -> dict[str, Any]:
    if not tool_result.get("ok"):
        return {"ok": False, "reason": "tool_result_failed", "checks": []}
    if not prepared.write:
        return {"ok": True, "reason": "read_only_action", "checks": ["tool_result_ok"]}
    data = tool_result.get("data") if isinstance(tool_result.get("data"), dict) else {}
    expected = {
        "create_purchase_invoice_from_receipt": "Purchase Invoice",
        "create_supplier_payment_from_invoice": "Payment Entry",
        "cancel_financial_document": prepared.tool_call["arguments"].get("doctype"),
    }.get(prepared.goal)
    name = str(data.get("name") or prepared.tool_call["arguments"].get("name") or "")
    if not expected or not name:
        return {"ok": False, "reason": "missing_document_identity", "checks": ["tool_result_ok"]}
    snapshot = document_loader(str(expected), name)
    checks = ["tool_result_ok", "document_read_back"]
    if prepared.goal == "cancel_financial_document":
        if int(snapshot.get("docstatus") or 0) != 2:
            return {"ok": False, "reason": "financial_document_not_cancelled", "checks": checks, "document": snapshot}
        checks.append("cancelled_state_verified")
    elif prepared.goal == "create_purchase_invoice_from_receipt":
        receipt = prepared.tool_call["arguments"]["purchase_receipt"]
        if not any(str(row.get("purchase_receipt") or "") == receipt for row in snapshot.get("items") or []):
            return {"ok": False, "reason": "purchase_receipt_lineage_missing", "checks": checks, "document": snapshot}
        checks.append("purchase_receipt_lineage_preserved")
    elif prepared.goal == "create_supplier_payment_from_invoice":
        invoice = prepared.tool_call["arguments"]["purchase_invoice"]
        if not any(str(row.get("reference_name") or "") == invoice for row in snapshot.get("references") or []):
            return {"ok": False, "reason": "purchase_invoice_allocation_missing", "checks": checks, "document": snapshot}
        checks.append("purchase_invoice_allocation_preserved")
    return {"ok": True, "reason": "verified", "checks": checks, "document": snapshot}


def _single_source(intent, snapshots, doctype: str, *, submitted: bool) -> dict[str, Any]:
    if len(intent.source_documents) != 1 or len(snapshots) != 1:
        raise CapabilityCompilationError(f"该操作需要唯一 {doctype} 来源单据。", questions=(f"请选择一张 {doctype}。",))
    ref, source = intent.source_documents[0], snapshots[0]
    if ref.doctype != doctype:
        raise CapabilityCompilationError(f"该操作不能使用 {ref.doctype} 作为来源。")
    if submitted and int(source.get("docstatus") or 0) != 1:
        raise CapabilityCompilationError(f"{doctype} {ref.name} 尚未提交。")
    source = dict(source)
    source.setdefault("name", ref.name)
    return source


def _sources(intent: FinanceBusinessIntentDraft, *fields: str, source_documents: str | None = None) -> dict[str, str]:
    result = {field: intent.provenance.get(field, "user_or_runtime") for field in fields}
    if source_documents:
        result["source_documents"] = source_documents
    return result


def _without_empty(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None and value != ""}


def _text(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def _iso_date(value: Any, field_name: str) -> str | None:
    value = _text(value)
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO YYYY-MM-DD") from exc


def _optional_positive_number(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return number


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
