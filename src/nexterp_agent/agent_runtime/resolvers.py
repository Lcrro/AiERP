from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re
from typing import Any, Callable

from nexterp_agent.master_data import MasterDataRelease


@dataclass(frozen=True)
class ResolutionResult:
    status: str
    value: str | None = None
    label: str | None = None
    confidence: float = 0.0
    candidates: tuple[dict[str, Any], ...] = ()
    question: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "value": self.value,
            "label": self.label,
            "confidence": self.confidence,
            "candidates": list(self.candidates),
            "question": self.question,
            "reason": self.reason,
        }


class EntityResolverRegistry:
    def __init__(self, release: MasterDataRelease | None = None) -> None:
        self.release = release or MasterDataRelease()
        self._resolvers: dict[str, Callable[..., ResolutionResult]] = {
            "company": self.resolve_company,
            "project": self.resolve_project,
            "warehouse": self.resolve_warehouse,
            "supplier": self.resolve_supplier,
            "date": self.resolve_date,
            "uom": self.resolve_uom,
        }

    def resolve(self, kind: str, query: str | None, **kwargs: Any) -> ResolutionResult:
        if kind not in self._resolvers:
            raise KeyError(f"Unknown resolver: {kind}")
        return self._resolvers[kind](query, **kwargs)

    def resolve_company(self, query: str | None = None, **_: Any) -> ResolutionResult:
        companies = list(self.release.companies.values())
        if len(companies) == 1:
            row = companies[0]
            return ResolutionResult("resolved", row["erpnext_company_name"], row["company_name"], 1.0, reason="唯一公司")
        return self._match_rows(
            query,
            companies,
            value_key="erpnext_company_name",
            label_key="company_name",
            search_keys=("company_code", "company_name", "erpnext_company_name"),
            question="请选择公司。",
        )

    def resolve_project(self, query: str | None, **_: Any) -> ResolutionResult:
        return self._match_rows(
            query,
            list(self.release.projects.values()),
            value_key="project_code",
            label_key="project_short_name",
            search_keys=("project_code", "project_short_name", "project_name"),
            question="请说明是哪个项目。",
        )

    def resolve_warehouse(self, query: str | None, **_: Any) -> ResolutionResult:
        return self._match_rows(
            query,
            list(self.release.warehouses.values()),
            value_key="erpnext_warehouse_name",
            label_key="warehouse_name",
            search_keys=("warehouse_code", "warehouse_name", "erpnext_warehouse_name", "project_code"),
            question="请说明物料要送到哪个仓库。",
        )

    def resolve_supplier(self, query: str | None, **_: Any) -> ResolutionResult:
        return self._match_rows(
            query,
            self.release.table("suppliers.tsv"),
            value_key="supplier_name",
            label_key="supplier_name",
            search_keys=("supplier_code", "supplier_name", "primary_category"),
            question="请选择供应商。",
        )

    def resolve_uom(self, query: str | None, **_: Any) -> ResolutionResult:
        value = str(query or "").strip()
        if not value:
            return ResolutionResult("needs_clarification", question="请说明数量单位。")
        known = {row["stock_uom"] for row in self.release.materials} | {row["purchase_uom"] for row in self.release.materials}
        if value in known:
            return ResolutionResult("resolved", value, value, 1.0, reason="单位精确匹配")
        return ResolutionResult("not_found", question=f"单位“{value}”不在物料主数据中，请确认。")

    def resolve_date(self, query: str | None, *, current_date: date | None = None, **_: Any) -> ResolutionResult:
        today = current_date or date.today()
        value = str(query or "").strip()
        if not value:
            return ResolutionResult("needs_clarification", question="你希望什么时候需要这些物料？")
        relative = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2}
        if value in relative:
            resolved = today + timedelta(days=relative[value])
            return ResolutionResult("resolved", resolved.isoformat(), value, 1.0, reason="相对日期解析")
        match = re.search(r"\d{4}-\d{2}-\d{2}", value)
        if match:
            try:
                resolved = date.fromisoformat(match.group(0))
            except ValueError:
                return ResolutionResult("needs_clarification", question="日期格式不正确，请使用 YYYY-MM-DD。")
            return ResolutionResult("resolved", resolved.isoformat(), resolved.isoformat(), 1.0, reason="ISO日期")
        return ResolutionResult("needs_clarification", question=f"暂时无法确定“{value}”对应哪一天，请给出具体日期。")

    def _match_rows(
        self,
        query: str | None,
        rows: list[dict[str, str]],
        *,
        value_key: str,
        label_key: str,
        search_keys: tuple[str, ...],
        question: str,
    ) -> ResolutionResult:
        query_norm = _normalize(query)
        if not query_norm:
            return ResolutionResult("needs_clarification", question=question)
        scored: list[tuple[int, dict[str, str], str]] = []
        for row in rows:
            best = 0
            reason = ""
            for key in search_keys:
                candidate = _normalize(row.get(key))
                if not candidate:
                    continue
                if candidate == query_norm:
                    best, reason = max((best, reason), (100, f"{key}精确匹配"))
                elif query_norm in candidate or candidate in query_norm:
                    best, reason = max((best, reason), (70, f"{key}包含匹配"))
            if best:
                scored.append((best, row, reason))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            return ResolutionResult("not_found", question=question, reason="无候选")
        top_score = scored[0][0]
        top = [item for item in scored if item[0] == top_score]
        candidates = tuple(
            {"value": row[value_key], "label": row[label_key], "score": score / 100, "reason": reason, "row": row}
            for score, row, reason in scored[:10]
        )
        if len(top) == 1:
            score, row, reason = top[0]
            return ResolutionResult("resolved", row[value_key], row[label_key], score / 100, candidates, reason=reason)
        return ResolutionResult(
            "needs_selection",
            candidates=candidates,
            question=question,
            reason="多个同分候选",
        )


def _normalize(value: Any) -> str:
    return re.sub(r"[\s（）()\-_/]+", "", str(value or "")).lower()
