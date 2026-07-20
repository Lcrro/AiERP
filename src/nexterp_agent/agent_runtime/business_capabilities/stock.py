from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .procurement import CapabilityCompilationError, DocumentLoader, PreparedBusinessAction, canonical_tool_call_hash


STOCK_GOALS = frozenset(
    {
        "query_stock_balance",
        "create_stock_transfer",
        "create_project_material_issue",
        "create_stock_reconciliation",
    }
)


@dataclass(frozen=True)
class StockIntentItem:
    item_code: str | None = None
    qty: float | None = None
    uom: str | None = None
    valuation_rate: float | None = None
    batch_no: str | None = None
    serial_no: str | None = None
    description: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StockIntentItem":
        qty = _optional_non_negative_number(payload.get("qty"), "items[].qty")
        valuation_rate = _optional_non_negative_number(payload.get("valuation_rate"), "items[].valuation_rate")
        return cls(
            item_code=_text(payload.get("item_code")),
            qty=qty,
            uom=_text(payload.get("uom")),
            valuation_rate=valuation_rate,
            batch_no=_text(payload.get("batch_no")),
            serial_no=_text(payload.get("serial_no")),
            description=_text(payload.get("description")),
        )


@dataclass(frozen=True)
class StockBusinessIntentDraft:
    goal: str
    items: tuple[StockIntentItem, ...] = ()
    company: str | None = None
    project: str | None = None
    source_warehouse: str | None = None
    target_warehouse: str | None = None
    warehouse: str | None = None
    posting_date: str | None = None
    cost_center: str | None = None
    expense_account: str | None = None
    remarks: str | None = None
    include_zero: bool = False
    require_available_stock: bool = True
    provenance: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StockBusinessIntentDraft":
        if not isinstance(payload, dict):
            raise ValueError("business_intent must be an object")
        goal = str(payload.get("goal") or "").strip()
        if goal not in STOCK_GOALS:
            raise ValueError(f"unsupported stock goal: {goal}")
        raw_items = payload.get("items") or []
        if not isinstance(raw_items, list):
            raise ValueError("items must be an array")
        provenance = payload.get("provenance") or {}
        if not isinstance(provenance, dict):
            raise ValueError("provenance must be an object")
        return cls(
            goal=goal,
            items=tuple(StockIntentItem.from_dict(row) for row in raw_items if isinstance(row, dict)),
            company=_text(payload.get("company")),
            project=_text(payload.get("project")),
            source_warehouse=_text(payload.get("source_warehouse")),
            target_warehouse=_text(payload.get("target_warehouse")),
            warehouse=_text(payload.get("warehouse")),
            posting_date=_iso_date(payload.get("posting_date"), "posting_date"),
            cost_center=_text(payload.get("cost_center")),
            expense_account=_text(payload.get("expense_account")),
            remarks=_text(payload.get("remarks")),
            include_zero=bool(payload.get("include_zero")),
            require_available_stock=bool(payload.get("require_available_stock", True)),
            provenance={str(key): str(value) for key, value in provenance.items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StockCapabilityGraph:
    _CARDS = {
        "query_stock_balance": ("stock.balance.query", "erpnext.stock.get_item_locations", False),
        "create_stock_transfer": ("stock.transfer.create", "erpnext.stock.create_transfer_draft", True),
        "create_project_material_issue": ("stock.project_issue.create", "erpnext.projects.create_material_issue_draft", True),
        "create_stock_reconciliation": ("stock.reconciliation.create", "erpnext.stock.create_reconciliation_draft", True),
    }

    def for_goal(self, goal: str) -> dict[str, Any]:
        value = self._CARDS.get(goal)
        if value is None:
            raise CapabilityCompilationError(f"没有库存业务能力可以处理目标 {goal}")
        name, tool, write = value
        return {"name": name, "goal": goal, "tool": tool, "write": write}

    def cards(self) -> list[dict[str, Any]]:
        return [self.for_goal(goal) for goal in sorted(self._CARDS)]


class StockCapabilityCompiler:
    def __init__(self, document_loader: DocumentLoader, *, graph: StockCapabilityGraph | None = None) -> None:
        self.document_loader = document_loader
        self.graph = graph or StockCapabilityGraph()

    def compile(
        self,
        intent: StockBusinessIntentDraft,
        *,
        runtime_context: dict[str, Any],
        today: date,
    ) -> PreparedBusinessAction:
        spec = self.graph.for_goal(intent.goal)
        builders = {
            "query_stock_balance": self._query_balance,
            "create_stock_transfer": self._transfer,
            "create_project_material_issue": self._project_issue,
            "create_stock_reconciliation": self._reconciliation,
        }
        arguments, sources, checks, summary = builders[intent.goal](intent, runtime_context, today)
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

    def _query_balance(self, intent: StockBusinessIntentDraft, runtime: dict[str, Any], _: date):
        item = _single_item(intent)
        if not item.item_code:
            raise CapabilityCompilationError("库存查询缺少已解析物料。", questions=("请选择要查询的标准物料。",))
        return (
            {"item_code": item.item_code, "include_zero": intent.include_zero, "limit": 200},
            {"item_code": "resolver", "include_zero": "user_or_default"},
            ["item_code_resolved", "erpnext_bin_is_source_of_truth"],
            f"查询 {item.item_code} 在各仓库的实时库存",
        )

    def _transfer(self, intent: StockBusinessIntentDraft, runtime: dict[str, Any], today: date):
        source = intent.source_warehouse
        target = intent.target_warehouse
        if not source or not target:
            raise CapabilityCompilationError("仓库调拨缺少源仓或目标仓。", questions=("请确认从哪个仓库调到哪个仓库。",))
        if source == target:
            raise CapabilityCompilationError("源仓和目标仓不能相同。")
        items = _movement_items(intent.items)
        posting_date = intent.posting_date or today.isoformat()
        return (
            {
                "source_warehouse": source,
                "target_warehouse": target,
                "company": intent.company or runtime.get("company"),
                "project": intent.project or runtime.get("project"),
                "posting_date": posting_date,
                "remarks": intent.remarks,
                "require_available_stock": intent.require_available_stock,
                "items": items,
            },
            _sources(intent, "source_warehouse", "target_warehouse", "company", "project", "posting_date"),
            ["item_codes_resolved", "warehouses_resolved", "source_and_target_differ", "positive_quantities", "live_source_stock_precheck", "draft_only"],
            f"创建库存调拨草稿：{source} → {target}，共 {len(items)} 行",
        )

    def _project_issue(self, intent: StockBusinessIntentDraft, runtime: dict[str, Any], today: date):
        project = intent.project or runtime.get("project")
        source = intent.source_warehouse or intent.warehouse or runtime.get("warehouse")
        if not project:
            raise CapabilityCompilationError("项目领料缺少项目。", questions=("请确认领料所属项目。",))
        if not source:
            raise CapabilityCompilationError("项目领料缺少出库仓库。", questions=("请确认从哪个仓库领料。",))
        items = _movement_items(intent.items)
        return (
            {
                "project": project,
                "source_warehouse": source,
                "company": intent.company or runtime.get("company"),
                "posting_date": intent.posting_date or today.isoformat(),
                "cost_center": intent.cost_center,
                "expense_account": intent.expense_account,
                "remarks": intent.remarks,
                "require_available_stock": intent.require_available_stock,
                "items": items,
            },
            _sources(intent, "project", "source_warehouse", "company", "posting_date", "cost_center", "expense_account"),
            ["item_codes_resolved", "project_resolved", "source_warehouse_resolved", "positive_quantities", "live_source_stock_precheck", "draft_only"],
            f"创建项目领料草稿：{project}，从 {source} 领用 {len(items)} 行物料",
        )

    def _reconciliation(self, intent: StockBusinessIntentDraft, runtime: dict[str, Any], today: date):
        warehouse = intent.warehouse or runtime.get("warehouse")
        if not warehouse:
            raise CapabilityCompilationError("库存盘点缺少仓库。", questions=("请确认盘点的是哪个仓库。",))
        if not intent.items:
            raise CapabilityCompilationError("库存盘点缺少实盘物料。", questions=("请提供物料和实盘数量。",))
        rows = []
        for item in intent.items:
            if not item.item_code:
                raise CapabilityCompilationError("盘点明细存在未解析物料。", questions=("请选择明确的标准物料。",))
            if item.qty is None:
                raise CapabilityCompilationError(f"{item.item_code} 缺少实盘数量。", questions=(f"请说明 {item.item_code} 的实盘数量。",))
            rows.append(_without_empty({
                "item_code": item.item_code,
                "warehouse": warehouse,
                "qty": item.qty,
                "valuation_rate": item.valuation_rate,
                "batch_no": item.batch_no,
                "serial_no": item.serial_no,
            }))
        return (
            {
                "company": intent.company or runtime.get("company"),
                "posting_date": intent.posting_date or today.isoformat(),
                "purpose": "Stock Reconciliation",
                "expense_account": intent.expense_account,
                "cost_center": intent.cost_center,
                "remarks": intent.remarks,
                "items": rows,
            },
            _sources(intent, "warehouse", "company", "posting_date", "cost_center", "expense_account"),
            ["item_codes_resolved", "warehouse_resolved", "non_negative_physical_quantities", "draft_only", "submission_requires_separate_confirmation"],
            f"创建 {warehouse} 库存盘点草稿，共 {len(rows)} 行",
        )


def verify_stock_result(
    prepared: PreparedBusinessAction,
    tool_result: dict[str, Any],
    document_loader: DocumentLoader,
) -> dict[str, Any]:
    if not tool_result.get("ok"):
        return {"ok": False, "reason": "tool_result_failed", "checks": []}
    if not prepared.write:
        return {"ok": True, "reason": "read_only_action", "checks": ["tool_result_ok"]}
    data = tool_result.get("data") if isinstance(tool_result.get("data"), dict) else {}
    name = str(data.get("name") or "")
    expected = "Stock Reconciliation" if prepared.goal == "create_stock_reconciliation" else "Stock Entry"
    doctype = str(data.get("doctype") or expected)
    if not name:
        return {"ok": False, "reason": "missing_created_document_identity", "checks": ["tool_result_ok"]}
    snapshot = document_loader(doctype, name)
    checks = ["tool_result_ok", "document_read_back"]
    if str(snapshot.get("name") or "") != name:
        return {"ok": False, "reason": "read_back_name_mismatch", "checks": checks, "document": snapshot}
    checks.append("document_identity_matches")
    if prepared.goal == "create_stock_transfer":
        rows = snapshot.get("items") or []
        args = prepared.tool_call["arguments"]
        if not rows or not all(row.get("s_warehouse") == args["source_warehouse"] and row.get("t_warehouse") == args["target_warehouse"] for row in rows):
            return {"ok": False, "reason": "transfer_warehouse_mismatch", "checks": checks, "document": snapshot}
        checks.append("transfer_warehouses_match")
    if prepared.goal == "create_project_material_issue":
        rows = snapshot.get("items") or []
        project = prepared.tool_call["arguments"]["project"]
        if not rows or not all(str(row.get("project") or "") == project for row in rows):
            return {"ok": False, "reason": "project_lineage_missing", "checks": checks, "document": snapshot}
        checks.append("project_lineage_preserved")
    return {"ok": True, "reason": "verified", "checks": checks, "document": snapshot}


def _single_item(intent: StockBusinessIntentDraft) -> StockIntentItem:
    if len(intent.items) != 1:
        raise CapabilityCompilationError("该库存查询需要唯一物料。", questions=("请选择一个要查询的标准物料。",))
    return intent.items[0]


def _movement_items(items: tuple[StockIntentItem, ...]) -> list[dict[str, Any]]:
    if not items:
        raise CapabilityCompilationError("库存动作缺少物料明细。", questions=("请说明物料和数量。",))
    rows = []
    for item in items:
        if not item.item_code:
            raise CapabilityCompilationError("库存明细存在未解析物料。", questions=("请选择明确的标准物料。",))
        if item.qty is None:
            raise CapabilityCompilationError(f"{item.item_code} 缺少数量。", questions=(f"请说明 {item.item_code} 的数量。",))
        if item.qty <= 0:
            raise CapabilityCompilationError(f"{item.item_code} 的移动数量必须大于 0。")
        rows.append(_without_empty({
            "item_code": item.item_code,
            "qty": item.qty,
            "uom": item.uom,
            "batch_no": item.batch_no,
            "serial_no": item.serial_no,
            "description": item.description,
        }))
    return rows


def _sources(intent: StockBusinessIntentDraft, *fields: str) -> dict[str, str]:
    result = {field: intent.provenance.get(field, "user_or_runtime") for field in fields}
    result["items"] = "resolver+user"
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


def _optional_non_negative_number(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number < 0:
        raise ValueError(f"{field_name} must be at least 0")
    return number
