from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from nexterp_agent.erpnext.risk_policy import infer_risk_level_for_call
from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS

from .tool_access import ToolExposure, infer_tool_exposure, make_tool_access_policy


CONFIRM_LEVELS = {
    "none",
    "user_confirm",
    "submit_confirm",
    "supervisor_confirm",
    "financial_confirm",
    "admin_confirm",
}

REPAIR_POLICIES = {
    "resolve_entity",
    "ask_clarification",
    "present_candidates",
    "inject_context",
    "validate_before_execute",
    "permission_denied",
    "erpnext_validation_error",
}

ROLE_PROFILES: tuple[tuple[str, str], ...] = (
    ("仓管", "仓库主管"),
    ("采购", "采购员"),
    ("项目经理", "项目经理"),
    ("班组长", "班组长"),
    ("财务", "财务主管"),
    ("资产管理员", "资产管理员"),
    ("管理层", "管理层"),
    ("系统管理员", "系统管理员"),
    ("developer", "developer"),
)


@dataclass(frozen=True)
class BackendMapping:
    doctypes: tuple[str, ...] = ()
    reports: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    notes: str | None = None


@dataclass(frozen=True)
class ParameterContract:
    name: str
    json_type: str
    required: str = "no"
    source: str | None = None
    resolver: str | None = None
    enum_values: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    repair: tuple[str, ...] = ()
    description: str | None = None


@dataclass(frozen=True)
class ToolContract:
    name: str
    purpose: str
    risk_level: str
    expose: ToolExposure
    allowed_roles: tuple[str, ...]
    confirm: str
    parameters: tuple[ParameterContract, ...] = ()
    backend_mapping: BackendMapping = field(default_factory=BackendMapping)
    repair: tuple[str, ...] = ()
    audit_fields: tuple[str, ...] = ()
    business_contract: tuple[str, ...] = ()


def default_tool_contract_overrides_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "tool_contracts"


def load_tool_contract_overrides(path: str | Path | None = None) -> dict[str, Any]:
    override_path = Path(path) if path else default_tool_contract_overrides_path()
    if not override_path.exists():
        return {}
    if override_path.is_dir():
        return _load_tool_contract_override_dir(override_path)
    return _load_tool_contract_override_file(override_path)


def _load_tool_contract_override_dir(path: Path) -> dict[str, Any]:
    merged: dict[str, Any] = {"tools": {}}
    for override_file in sorted(path.glob("*.yaml")):
        payload = _load_tool_contract_override_file(override_file)
        tools = payload.get("tools") or {}
        duplicate_tools = sorted(set(merged["tools"]) & set(tools))
        if duplicate_tools:
            joined = ", ".join(duplicate_tools)
            raise ValueError(f"Duplicate ToolCall overrides in {override_file}: {joined}")
        merged["tools"].update(tools)
    return merged


def _load_tool_contract_override_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Tool contract override file must be a mapping: {path}")
    return payload


def build_tool_contracts(overrides: dict[str, Any] | None = None) -> list[ToolContract]:
    payload = overrides if overrides is not None else load_tool_contract_overrides()
    tool_overrides = payload.get("tools", {}) if isinstance(payload, dict) else {}
    if not isinstance(tool_overrides, dict):
        raise ValueError("tools override must be a mapping keyed by ToolCall name")

    schemas = {schema["name"]: schema for schema in ERPNext_TOOL_SCHEMAS}
    unknown_tools = sorted(set(tool_overrides) - set(schemas))
    if unknown_tools:
        raise ValueError(f"Unknown ToolCall overrides: {', '.join(unknown_tools)}")

    contracts = [
        _build_contract_from_schema(schema, tool_overrides.get(schema["name"]) or {})
        for schema in ERPNext_TOOL_SCHEMAS
    ]
    return contracts


def get_tool_contract(name: str, overrides: dict[str, Any] | None = None) -> ToolContract:
    for contract in build_tool_contracts(overrides):
        if contract.name == name:
            return contract
    raise KeyError(name)


def _build_contract_from_schema(schema: dict[str, Any], override: dict[str, Any]) -> ToolContract:
    if not isinstance(override, dict):
        raise ValueError(f"Override for {schema['name']} must be a mapping")

    name = schema["name"]
    risk_level = infer_risk_level_for_call({"tool": name})
    expose = _coerce_exposure(override.get("expose")) if override.get("expose") else infer_tool_exposure(name)
    confirm = override.get("confirm") or _default_confirm_for_risk(risk_level)
    _validate_confirm(confirm, name)

    parameters = _build_parameter_contracts(schema, override.get("parameters") or {})
    repairs = tuple(override.get("repair") or _default_repair_for_exposure(expose))
    _validate_repair(repairs, name)

    backend = _build_backend_mapping(override.get("backend_mapping") or {})

    return ToolContract(
        name=name,
        purpose=override.get("purpose") or schema.get("description") or "",
        risk_level=risk_level,
        expose=expose,
        allowed_roles=tuple(override.get("allowed_roles") or _infer_allowed_roles(name, expose)),
        confirm=confirm,
        parameters=parameters,
        backend_mapping=backend,
        repair=repairs,
        audit_fields=tuple(override.get("audit_fields") or _default_audit_fields(parameters)),
        business_contract=tuple(override.get("business_contract") or ()),
    )


def _build_parameter_contracts(schema: dict[str, Any], overrides: dict[str, Any]) -> tuple[ParameterContract, ...]:
    if not isinstance(overrides, dict):
        raise ValueError(f"Parameter overrides for {schema['name']} must be a mapping")

    params = schema.get("parameters") or {}
    properties = params.get("properties") or {}
    required = set(params.get("required") or [])
    unknown_parameters = sorted(set(overrides) - set(properties))
    invalid_unknown_parameters = [
        name for name in unknown_parameters if "." not in name and "[]" not in name
    ]
    if invalid_unknown_parameters:
        raise ValueError(
            f"Unknown parameter overrides for {schema['name']}: {', '.join(invalid_unknown_parameters)}"
        )

    contracts = []
    for param_name, param_schema in properties.items():
        override = overrides.get(param_name) or {}
        constraints = _schema_constraints(param_schema)
        constraints.extend(override.get("constraints") or [])
        repairs = tuple(override.get("repair") or ())
        _validate_repair(repairs, f"{schema['name']}.{param_name}")

        contracts.append(
            ParameterContract(
                name=param_name,
                json_type=_schema_type(param_schema),
                required=override.get("required") or ("yes" if param_name in required else "no"),
                source=override.get("source"),
                resolver=override.get("resolver"),
                enum_values=tuple(str(value) for value in param_schema.get("enum") or override.get("enum_values") or ()),
                constraints=tuple(constraints),
                repair=repairs,
                description=override.get("description") or param_schema.get("description"),
            )
        )
    for param_name in unknown_parameters:
        override = overrides.get(param_name) or {}
        repairs = tuple(override.get("repair") or ())
        _validate_repair(repairs, f"{schema['name']}.{param_name}")
        contracts.append(
            ParameterContract(
                name=param_name,
                json_type=override.get("type") or "nested",
                required=override.get("required") or "no",
                source=override.get("source"),
                resolver=override.get("resolver"),
                enum_values=tuple(str(value) for value in override.get("enum_values") or ()),
                constraints=tuple(override.get("constraints") or ()),
                repair=repairs,
                description=override.get("description"),
            )
        )
    return tuple(contracts)


def _schema_constraints(param_schema: dict[str, Any]) -> list[str]:
    constraints = []
    if "minimum" in param_schema:
        constraints.append(f"minimum={param_schema['minimum']}")
    if "exclusiveMinimum" in param_schema:
        constraints.append(f"exclusiveMinimum={param_schema['exclusiveMinimum']}")
    if "maximum" in param_schema:
        constraints.append(f"maximum={param_schema['maximum']}")
    if "maxLength" in param_schema:
        constraints.append(f"maxLength={param_schema['maxLength']}")
    if "pattern" in param_schema:
        constraints.append(f"pattern={param_schema['pattern']}")
    if param_schema.get("items"):
        constraints.append("array_items_schema=true")
    return constraints


def _schema_type(param_schema: dict[str, Any]) -> str:
    if param_schema.get("enum"):
        return "enum"
    value = param_schema.get("type")
    if isinstance(value, list):
        return "|".join(value)
    return str(value or "any")


def _coerce_exposure(value: str) -> ToolExposure:
    try:
        return ToolExposure(value)
    except ValueError as exc:
        valid = ", ".join(item.value for item in ToolExposure)
        raise ValueError(f"Invalid expose value {value!r}; expected one of {valid}") from exc


def _default_confirm_for_risk(risk_level: str) -> str:
    if risk_level in {"L0", "L1"}:
        return "none"
    if risk_level in {"L2", "L3"}:
        return "user_confirm"
    if risk_level == "L5_ADMIN":
        return "admin_confirm"
    if risk_level == "L5_FINANCIAL":
        return "financial_confirm"
    return "submit_confirm"


def _default_repair_for_exposure(exposure: ToolExposure) -> tuple[str, ...]:
    if exposure is ToolExposure.AGENT_VISIBLE:
        return ("ask_clarification", "permission_denied", "erpnext_validation_error")
    if exposure is ToolExposure.RUNTIME_INTERNAL:
        return ("validate_before_execute", "erpnext_validation_error")
    return ("permission_denied",)


def _validate_confirm(confirm: str, name: str) -> None:
    if confirm not in CONFIRM_LEVELS:
        raise ValueError(f"Invalid confirm level for {name}: {confirm}")


def _validate_repair(repairs: tuple[str, ...], name: str) -> None:
    invalid = sorted(set(repairs) - REPAIR_POLICIES)
    if invalid:
        raise ValueError(f"Invalid repair policies for {name}: {', '.join(invalid)}")


def _build_backend_mapping(payload: dict[str, Any]) -> BackendMapping:
    if not isinstance(payload, dict):
        raise ValueError("backend_mapping must be a mapping")
    return BackendMapping(
        doctypes=tuple(payload.get("doctypes") or ()),
        reports=tuple(payload.get("reports") or ()),
        methods=tuple(payload.get("methods") or ()),
        notes=payload.get("notes"),
    )


def _infer_allowed_roles(name: str, exposure: ToolExposure) -> list[str]:
    if exposure is ToolExposure.RUNTIME_INTERNAL:
        return ["Runtime"]
    if exposure is ToolExposure.DEVELOPER_ONLY:
        return ["developer"]

    roles = []
    for label, profile in ROLE_PROFILES:
        if profile == "developer":
            continue
        policy = make_tool_access_policy(profile)
        if policy.decide(name, origin="agent").allowed:
            roles.append(label)
    return roles


def _default_audit_fields(parameters: tuple[ParameterContract, ...]) -> tuple[str, ...]:
    names = [param.name for param in parameters if param.required in {"yes", "conditional"}]
    return tuple(names[:8])
