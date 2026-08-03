from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from nexterp_agent.master_data.release import MasterDataRelease

from .catalog import ExternalIdentity
from .context_models import (
    AgentContextEnvelope,
    AgentIdentityContext,
    AgentTaskContext,
    AgentWorkplaceContext,
    ContextFact,
)


ROOT = Path(__file__).resolve().parents[3]
ALL_CONTEXT_TOPICS = [
    "responsibilities", "collaboration", "project",
    "recent_documents", "inbox", "process_position",
]


class AgentContextBuilder:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.release = MasterDataRelease(root / "data/master_data/release_v0_1")

    def build(
        self,
        identity: ExternalIdentity,
        session: dict[str, Any],
    ) -> AgentContextEnvelope:
        employee = next(
            (row for row in self.release.employees.values() if row.get("user_email") == identity.employee_user),
            None,
        )
        if not employee:
            raise PermissionError("员工账号未出现在可信基础主数据中")
        project_code = str(session.get("project_code") or identity.default_project or "")
        if identity.allowed_projects and project_code not in identity.allowed_projects:
            raise PermissionError("当前工作情境项目不在员工允许范围内")
        project = self.release.projects.get(project_code)
        if not project:
            raise KeyError(f"Unknown project: {project_code}")
        departments = {row["department_code"]: row for row in self.release.table("departments.tsv")}
        department = departments.get(employee.get("department_code", ""), {})
        assignments = [
            row for row in self.release.table("employee_assignments.tsv")
            if row.get("employee_code") == employee.get("employee_code") and row.get("is_active") == "1"
        ]
        project_assignment = next(
            (row for row in assignments if row.get("scope_type") in {"project", "base"} and row.get("scope_code") == project_code),
            None,
        )
        warehouse_code = project.get("default_warehouse_code", "")
        warehouse = self.release.warehouses.get(warehouse_code, {})
        identity_context = AgentIdentityContext(
            employee_code=employee["employee_code"],
            employee_name=employee["employee_name"],
            employee_user=employee["user_email"],
            role_code=(project_assignment or employee).get("role_code", employee.get("role_code", "")),
            position=employee.get("position", ""),
            project_position=(project_assignment or {}).get("position", employee.get("position", "")),
            department_code=employee.get("department_code", ""),
            department_name=department.get("department_name", employee.get("department_code", "")),
            profile_name=identity.profile_name,
        )
        workplace = AgentWorkplaceContext(
            project_code=project_code,
            project_name=project.get("project_name", project_code),
            project_short_name=project.get("project_short_name", project_code),
            project_status=project.get("project_operating_status", project.get("status", "")),
            warehouse_code=warehouse_code,
            warehouse_name=warehouse.get("warehouse_name", warehouse_code),
            allowed_projects=list(identity.allowed_projects),
        )
        task = AgentTaskContext.model_validate({
            "current_goal": session.get("current_goal", ""),
            "intent_mode": session.get("intent_mode", "read"),
            "confirmed_entities": session.get("confirmed_entities") or {},
            "unresolved_fields": session.get("unresolved_fields") or [],
            "active_capability": session.get("active_capability"),
            "loaded_context": session.get("loaded_context") or [],
            "recent_documents": session.get("recent_documents") or [],
            "pending_operation": session.get("pending_operation"),
            "last_successful_progress": session.get("last_successful_progress"),
        })
        return AgentContextEnvelope(
            identity=identity_context,
            workplace=workplace,
            task=task,
            current_date=date.today(),
            available_context_topics=ALL_CONTEXT_TOPICS,
            provenance={
                "identity": ContextFact(value=employee["employee_code"], source="master_data/employees.tsv", trust="trusted_master_data"),
                "assignment": ContextFact(value=project_code, source="master_data/employee_assignments.tsv", trust="trusted_master_data"),
                "project": ContextFact(value=project_code, source="master_data/projects.tsv", trust="trusted_master_data"),
                "task": ContextFact(value=session.get("current_goal", ""), source="agent_session_context", trust="session"),
                "permissions": ContextFact(value="ERPNext + ToolAccessPolicy", source="runtime enforcement", trust="authoritative"),
            },
        )
