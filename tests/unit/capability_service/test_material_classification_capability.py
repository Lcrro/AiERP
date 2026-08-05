from __future__ import annotations

from nexterp_agent.capability_service.catalog import ExternalIdentity
from nexterp_agent.capability_service.models import PrepareOperationRequest, RequestIdentity
from nexterp_agent.capability_service.service import CapabilityManualService


class ClassificationRepository:
    def resolve_identity(self, external_subject: str, agent_id: str = "") -> ExternalIdentity:
        return ExternalIdentity(
            external_subject=external_subject,
            agent_id=agent_id,
            employee_user="material@example.com",
            profile_name="material_clerk_agent",
            default_project="PRJ-HL-13",
            allowed_projects=("PRJ-HL-13",),
        )

    def current_revision(self) -> str:
        return "classification-test"


def test_classification_operation_is_analyze_only_and_returns_dictionary_result() -> None:
    service = CapabilityManualService(ClassificationRepository())  # type: ignore[arg-type]
    result = service.prepare(
        PrepareOperationRequest(
            operation_id="op.material.classify",
            request_id="classify-1",
            query="内六角螺丝 M9*47",
            attributes={"spec": "M9*47"},
            material_family_hint="螺丝/螺栓",
        ),
        RequestIdentity(external_subject="owner", agent_id="main", session_key="session-1"),
    )

    assert result["status"] == "needs_input"
    assert result["operation_mode"] == "analyze"
    assert result["writes_erpnext"] is False
    assert result["selected_type"]["standard_name"] == "内六角螺丝"
    assert result["missing_attributes"][0]["attribute_key"] == "material"
    assert result["catalog_revision"] == "classification-test"
