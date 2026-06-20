from __future__ import annotations

from collections import Counter
from pathlib import Path

from nexterp_agent.agent_runtime.tool_contracts import (
    ToolContract,
    build_tool_contracts,
)
from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "docs" / "reference" / "toolcall-data-dictionary.md"


def main() -> None:
    contracts = build_tool_contracts()
    OUTPUT_PATH.write_text(render_dictionary(contracts), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(contracts)} ToolCalls)")


def render_dictionary(contracts: list[ToolContract]) -> str:
    counts_by_expose = Counter(contract.expose.value for contract in contracts)
    counts_by_confirm = Counter(contract.confirm for contract in contracts)
    counts_by_risk = Counter(contract.risk_level for contract in contracts)
    schema_count = len(ERPNext_TOOL_SCHEMAS)

    lines: list[str] = [
        "# ToolCall Data Dictionary",
        "",
        "本文由结构化契约自动生成，源数据来自：",
        "",
        "- `ERPNext_TOOL_SCHEMAS`：代码里的 ToolCall JSON Schema。",
        "- `ToolAccessPolicy`：岗位工具门禁。",
        "- `config/tool_contracts/*.yaml`：按模块维护的业务约束、Resolver、Repair 和底层映射。",
        "",
        "本文不是权限系统本身。真正执行时仍由 `ToolGateway` 做工具门禁，由 ERPNext 后端做最终权限裁决。",
        "",
        "## 总览",
        "",
        f"- Tool schema 数：{schema_count}",
        f"- Tool contract 数：{len(contracts)}",
        f"- 覆盖状态：{'完整' if len(contracts) == schema_count else '不完整'}",
        "",
        "### 按 Expose 统计",
        "",
        "| Expose | 数量 |",
        "|---|---:|",
    ]
    for key in sorted(counts_by_expose):
        lines.append(f"| `{key}` | {counts_by_expose[key]} |")

    lines.extend(["", "### 按 Confirm 统计", "", "| Confirm | 数量 |", "|---|---:|"])
    for key in sorted(counts_by_confirm):
        lines.append(f"| `{key}` | {counts_by_confirm[key]} |")

    lines.extend(["", "### 按风险等级统计", "", "| 风险等级 | 数量 |", "|---|---:|"])
    for key in sorted(counts_by_risk):
        lines.append(f"| `{key}` | {counts_by_risk[key]} |")

    lines.extend(
        [
            "",
            "## 字段口径",
            "",
            "| 字段 | 说明 |",
            "|---|---|",
            "| ToolCall | 完整工具名。 |",
            "| 用途 | 业务用途和风险等级。 |",
            "| Allowed Roles | 哪些岗位 profile 可以直接使用。 |",
            "| Expose | `agent_visible`、`runtime_internal`、`developer_only`。 |",
            "| 核心入参 | 参数名、类型、必填、来源、Resolver、约束。 |",
            "| Confirm | 是否需要强确认。 |",
            "| Repair | 失败或不确定时的修复策略。 |",
            "| Backend Mapping | 对应 ERPNext DocType、Report、Frappe Method 或 agent_bridge 方法。 |",
            "| 权限裁决 | ToolGateway 先判断工具可用性，ERPNext 后端做最终业务权限裁决。 |",
            "",
            "## 全量总表",
            "",
            "| ToolCall | 风险 | Expose | Allowed Roles | Confirm | Backend Mapping |",
            "|---|---|---|---|---|---|",
        ]
    )
    for contract in contracts:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{contract.name}`",
                    f"`{contract.risk_level}`",
                    f"`{contract.expose.value}`",
                    _join(contract.allowed_roles),
                    f"`{contract.confirm}`",
                    _backend_summary(contract),
                ]
            )
            + " |"
        )

    detailed = [contract for contract in contracts if contract.business_contract or contract.backend_mapping.doctypes or contract.backend_mapping.methods or contract.backend_mapping.reports]
    lines.extend(
        [
            "",
            "## 人工补充详情",
            "",
            "本节展示已经人工补充业务约束的 ToolCall。未在本节展开的工具仍有基础契约，见后面的参数索引；后续可逐步补齐业务约束。",
            "",
        ]
    )
    for contract in detailed:
        lines.extend(_render_detail(contract))

    lines.extend(
        [
            "",
            "## 全量参数索引",
            "",
            "说明：这里先列代码 schema 中的基础参数。更严格的业务约束以人工补充详情和 `config/tool_contracts/*.yaml` 为准。",
            "",
            "| ToolCall | 参数索引 |",
            "|---|---|",
        ]
    )
    for contract in contracts:
        params = ", ".join(_param_inline(param) for param in contract.parameters) or "-"
        lines.append(f"| `{contract.name}` | {params} |")

    lines.extend(
        [
            "",
            "## 维护方式",
            "",
            "更新流程：",
            "",
            "1. 修改 `config/tool_contracts/*.yaml` 中对应模块文件。",
            "2. 运行 `python scripts/docs/generate_toolcall_data_dictionary.py`。",
            "3. 运行 `python -m pytest tests/unit/agent_runtime/test_tool_contracts.py -q`。",
            "",
            "验收规则：",
            "",
            "- 150 个 Tool schema 必须都有 Tool contract。",
            "- `developer_only` 不得出现在员工 profile 的 schema 列表。",
            "- `runtime_internal` 只能由 Runtime origin 调用。",
            "- 高风险工具必须有 Confirm。",
            "- 涉及主数据外键的参数必须逐步补 Resolver 和 Repair。"
        ]
    )

    return "\n".join(lines) + "\n"


def _render_detail(contract: ToolContract) -> list[str]:
    lines = [
        f"### `{contract.name}`",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 用途 | {_escape(contract.purpose)} |",
        f"| Allowed Roles | {_join(contract.allowed_roles)} |",
        f"| Expose | `{contract.expose.value}` |",
        f"| Confirm | `{contract.confirm}` |",
        f"| Backend Mapping | {_backend_summary(contract)} |",
        f"| Repair | {_join_code(contract.repair)} |",
        f"| 审计重点 | {_join_code(contract.audit_fields)} |",
        "",
    ]

    if contract.business_contract:
        lines.extend(["Business Contract：", ""])
        for item in contract.business_contract:
            lines.append(f"- {_escape(item)}")
        lines.append("")

    lines.extend(["核心入参：", "", "| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |", "|---|---|---|---|---|---|---|"])
    if contract.parameters:
        for param in contract.parameters:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{param.name}`",
                        f"`{param.json_type}`",
                        f"`{param.required}`",
                        _escape(param.source or "-"),
                        f"`{param.resolver}`" if param.resolver else "-",
                        _join(param.constraints) or "-",
                        _join_code(param.repair),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - |")
    lines.append("")
    return lines


def _param_inline(param) -> str:
    required = "必填" if param.required == "yes" else ("条件必填" if param.required == "conditional" else "可选")
    return f"`{param.name}:{param.json_type}/{required}`"


def _backend_summary(contract: ToolContract) -> str:
    parts = []
    if contract.backend_mapping.doctypes:
        parts.append("DocType: " + ", ".join(f"`{value}`" for value in contract.backend_mapping.doctypes))
    if contract.backend_mapping.reports:
        parts.append("Report: " + ", ".join(f"`{value}`" for value in contract.backend_mapping.reports))
    if contract.backend_mapping.methods:
        parts.append("Method: " + ", ".join(f"`{value}`" for value in contract.backend_mapping.methods))
    if contract.backend_mapping.notes:
        parts.append(_escape(contract.backend_mapping.notes))
    return "<br>".join(parts) if parts else "-"


def _join(values: tuple[str, ...] | list[str]) -> str:
    return "、".join(_escape(str(value)) for value in values) if values else "-"


def _join_code(values: tuple[str, ...] | list[str]) -> str:
    return "、".join(f"`{value}`" for value in values) if values else "-"


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


if __name__ == "__main__":
    main()
