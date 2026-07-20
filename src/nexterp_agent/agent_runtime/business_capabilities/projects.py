from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .procurement import (
    CapabilityCompilationError,
    DocumentLoader,
    DocumentReference,
    PreparedBusinessAction,
    canonical_tool_call_hash,
)


PROJECT_GOALS = frozenset({
    "query_project_cost",
    "query_project_exceptions",
    "create_project_task",
    "update_project_task",
})


@dataclass(frozen=True)
class ProjectBusinessIntentDraft:
    goal: str
    source_documents: tuple[DocumentReference, ...] = ()
    project: str | None = None
    company: str | None = None
    subject: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    progress: float | None = None
    from_date: str | None = None
    to_date: str | None = None
    exp_start_date: str | None = None
    exp_end_date: str | None = None
    provenance: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProjectBusinessIntentDraft":
        if not isinstance(payload, dict):
            raise ValueError("business_intent must be an object")
        goal = str(payload.get("goal") or "").strip()
        if goal not in PROJECT_GOALS:
            raise ValueError(f"unsupported project goal: {goal}")
        raw_sources = payload.get("source_documents") or []
        if isinstance(payload.get("source_document"), dict):
            raw_sources = [payload["source_document"], *raw_sources]
        if not isinstance(raw_sources, list):
            raise ValueError("source_documents must be an array")
        progress = payload.get("progress")
        if progress not in (None, ""):
            progress = float(progress)
            if progress < 0 or progress > 100:
                raise ValueError("progress must be between 0 and 100")
        provenance = payload.get("provenance") or {}
        return cls(
            goal=goal,
            source_documents=tuple(DocumentReference.from_dict(row) for row in raw_sources if isinstance(row, dict)),
            project=_text(payload.get("project")),
            company=_text(payload.get("company")),
            subject=_text(payload.get("subject")),
            description=_text(payload.get("description")),
            priority=_text(payload.get("priority")),
            status=_text(payload.get("status")),
            progress=progress,
            from_date=_iso_date(payload.get("from_date"), "from_date"),
            to_date=_iso_date(payload.get("to_date"), "to_date"),
            exp_start_date=_iso_date(payload.get("exp_start_date"), "exp_start_date"),
            exp_end_date=_iso_date(payload.get("exp_end_date"), "exp_end_date"),
            provenance={str(key): str(value) for key, value in provenance.items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectCapabilityGraph:
    _CARDS = {
        "query_project_cost": ("project.cost.query", "erpnext.projects.get_project_cost_context", False),
        "query_project_exceptions": ("project.exceptions.query", "erpnext.projects.get_project_exceptions", False),
        "create_project_task": ("project.task.create", "erpnext.projects.create_task", True),
        "update_project_task": ("project.task.update", "erpnext.projects.update_task", True),
    }

    def for_goal(self, goal: str) -> dict[str, Any]:
        value = self._CARDS.get(goal)
        if value is None:
            raise CapabilityCompilationError(f"没有项目业务能力可以处理目标 {goal}")
        name, tool, write = value
        return {"name": name, "goal": goal, "tool": tool, "write": write}

    def cards(self) -> list[dict[str, Any]]:
        return [self.for_goal(goal) for goal in sorted(self._CARDS)]


class ProjectCapabilityCompiler:
    def __init__(self, document_loader: DocumentLoader, *, graph: ProjectCapabilityGraph | None = None) -> None:
        self.document_loader = document_loader
        self.graph = graph or ProjectCapabilityGraph()

    def compile(self, intent: ProjectBusinessIntentDraft, *, runtime_context: dict[str, Any], today: date) -> PreparedBusinessAction:
        spec = self.graph.for_goal(intent.goal)
        runtime_project = _text(runtime_context.get("project"))
        if intent.project and runtime_project and intent.project != runtime_project:
            raise CapabilityCompilationError("项目与当前已确认项目不一致，请先切换或重新确认项目。")
        project = intent.project or runtime_project
        snapshots = [self.document_loader(ref.doctype, ref.name) for ref in intent.source_documents]
        if intent.goal != "update_project_task":
            if not project:
                raise CapabilityCompilationError("缺少项目。", questions=("请确认要操作哪个项目。",))
            self.document_loader("Project", project)
        if intent.goal == "query_project_cost":
            arguments = {"project": project, "company": intent.company or runtime_context.get("company"), "from_date": intent.from_date, "to_date": intent.to_date, "limit": 100}
            summary = f"查询项目 {project} 的成本上下文"
            checks = ["project_resolved", "read_only"]
        elif intent.goal == "query_project_exceptions":
            arguments = {"project": project, "as_of_date": intent.to_date or today.isoformat(), "limit": 200}
            summary = f"查询项目 {project} 截至 {arguments['as_of_date']} 的异常"
            checks = ["project_resolved", "read_only"]
        elif intent.goal == "create_project_task":
            if not intent.subject:
                raise CapabilityCompilationError("创建任务缺少任务名称。", questions=("这项任务叫什么？",))
            _validate_dates(intent.exp_start_date, intent.exp_end_date)
            arguments = {
                "project": project, "subject": intent.subject, "description": intent.description,
                "priority": intent.priority, "exp_start_date": intent.exp_start_date, "exp_end_date": intent.exp_end_date,
            }
            summary = f"在项目 {project} 创建任务：{intent.subject}"
            checks = ["project_resolved", "subject_from_user", "task_dates_valid"]
        else:
            source = _single_task_source(intent, snapshots)
            _validate_dates(intent.exp_start_date, intent.exp_end_date)
            changes = {
                "status": intent.status, "progress": intent.progress, "priority": intent.priority,
                "exp_start_date": intent.exp_start_date, "exp_end_date": intent.exp_end_date,
                "description": intent.description,
            }
            if not any(value is not None for value in changes.values()):
                raise CapabilityCompilationError("没有需要修改的任务字段。", questions=("请说明任务状态、进度、优先级、日期或描述要如何修改。",))
            arguments = {"task": source["name"], **changes}
            summary = f"更新项目任务 {source['name']}"
            checks = ["task_resolved", "task_live_snapshot_loaded", "controlled_fields_only"]
        tool_call = {"tool": spec["tool"], "arguments": _without_empty(arguments)}
        return PreparedBusinessAction(
            capability=spec["name"], goal=intent.goal, tool_call=tool_call, summary=summary,
            field_sources={key: intent.provenance.get(key, "user_or_runtime") for key in tool_call["arguments"]},
            preflight_checks=tuple(checks), confirmation_hash=canonical_tool_call_hash(tool_call), write=bool(spec["write"]),
        )


def verify_project_result(prepared: PreparedBusinessAction, tool_result: dict[str, Any], document_loader: DocumentLoader) -> dict[str, Any]:
    if not tool_result.get("ok"):
        return {"ok": False, "reason": "tool_result_failed", "checks": []}
    if not prepared.write:
        return {"ok": True, "reason": "read_only_action", "checks": ["tool_result_ok"]}
    data = tool_result.get("data") if isinstance(tool_result.get("data"), dict) else {}
    name = str(data.get("name") or prepared.tool_call["arguments"].get("task") or "")
    if not name:
        return {"ok": False, "reason": "missing_task_identity", "checks": ["tool_result_ok"]}
    task = document_loader("Task", name)
    checks = ["tool_result_ok", "task_read_back"]
    if prepared.goal == "create_project_task" and task.get("project") != prepared.tool_call["arguments"]["project"]:
        return {"ok": False, "reason": "task_project_mismatch", "checks": checks, "document": task}
    for field in ("status", "progress", "priority", "exp_start_date", "exp_end_date"):
        if field in prepared.tool_call["arguments"] and task.get(field) != prepared.tool_call["arguments"][field]:
            return {"ok": False, "reason": f"task_{field}_mismatch", "checks": checks, "document": task}
    checks.append("task_fields_verified")
    return {"ok": True, "reason": "verified", "checks": checks, "document": task}


def _single_task_source(intent, snapshots) -> dict[str, Any]:
    if len(intent.source_documents) != 1 or len(snapshots) != 1 or intent.source_documents[0].doctype != "Task":
        raise CapabilityCompilationError("更新任务需要唯一任务单据。", questions=("请选择一项要更新的任务。",))
    source = dict(snapshots[0])
    source.setdefault("name", intent.source_documents[0].name)
    return source


def _validate_dates(start: str | None, end: str | None) -> None:
    if start and end and start > end:
        raise CapabilityCompilationError("任务开始日期不能晚于结束日期。")


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
