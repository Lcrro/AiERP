from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from nexterp_agent.erpnext.risk_policy import infer_risk_level
from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS

COMPANY = "STEC (Demo)"
PROJECT_CHENGDONG = "PROJ-0001"
CENTER_WAREHOUSE = "SCEN-CIVIL 中心仓 - SD"
PROJECT_WAREHOUSE = "SCEN-CIVIL 项目仓 - SD"
SUPPLIER_LABOR = "SCEN-CIVIL 安科劳保用品"


@dataclass(frozen=True)
class WizardTool:
    id: str
    group: str
    label: str
    actor: str
    tool: str
    arguments: dict[str, Any]
    writes: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_level"] = infer_risk_level(self.tool)
        return payload


def build_wizard_tools(today: date | None = None) -> list[WizardTool]:
    """Return the curated ToolCall buttons for Wizard of Oz testing."""

    current_day = today or date.today()
    required_by = current_day + timedelta(days=1)
    month_start = current_day.replace(day=1)

    return [
        WizardTool(
            id="auth-current-user",
            group="00 连接检查",
            label="检查当前 ERPNext 用户",
            actor="许峰，系统管理员",
            tool="erpnext.get_logged_user",
            arguments={},
            writes=False,
            description="确认本地 API 凭据可用。",
        ),
        WizardTool(
            id="setup-list-users",
            group="01 基座数据检查",
            label="查看沙盘员工账号",
            actor="许峰，系统管理员",
            tool="erpnext.search_documents",
            arguments={
                "doctype": "User",
                "filters": {"email": ["like", "%scen-civil.local%"]},
                "fields": ["name", "email", "full_name", "enabled", "user_type", "modified"],
                "limit": 30,
                "order_by": "modified desc",
            },
            writes=False,
            description="检查沙盘员工账号是否存在。",
        ),
        WizardTool(
            id="setup-list-projects",
            group="01 基座数据检查",
            label="查看三个项目",
            actor="李志远，项目经理",
            tool="erpnext.search_documents",
            arguments={
                "doctype": "Project",
                "filters": {"project_name": ["like", "%SCEN-CIVIL%"]},
                "fields": ["name", "project_name", "status", "company"],
                "limit": 10,
            },
            writes=False,
            description="检查城东、南区、西站三个项目。",
        ),
        WizardTool(
            id="setup-list-warehouses",
            group="01 基座数据检查",
            label="查看中心仓和项目仓",
            actor="王海，仓库主管",
            tool="erpnext.stock.list_warehouses",
            arguments={"company": COMPANY, "query": "SCEN-CIVIL", "limit": 20},
            writes=False,
            description="检查沙盘仓库是否存在。",
        ),
        WizardTool(
            id="setup-list-suppliers",
            group="01 基座数据检查",
            label="查看沙盘供应商",
            actor="赵强，采购主管",
            tool="erpnext.buying.search_suppliers",
            arguments={"query": "SCEN-CIVIL", "limit": 20},
            writes=False,
            description="检查劳保、管材、建材、电气供应商。",
        ),
        WizardTool(
            id="setup-search-gloves",
            group="01 基座数据检查",
            label="搜索劳保用品物料",
            actor="马超，施工班组长",
            tool="erpnext.search_items",
            arguments={"query": "帆布手套 安全帽 反光背心", "limit": 10},
            writes=False,
            description="检查城东劳保需求中的基础物料是否能被检索到。",
        ),
        WizardTool(
            id="setup-list-item-prices",
            group="01 基座数据检查",
            label="查看采购价格",
            actor="赵强，采购主管",
            tool="erpnext.buying.search_item_prices",
            arguments={"price_list": "Standard Buying", "limit": 20},
            writes=False,
            description="检查沙盘物料是否已有采购价格和默认供应商线索。",
        ),
        WizardTool(
            id="setup-list-background-todos",
            group="01 基座数据检查",
            label="查看背景异常待办",
            actor="陈建国，总经理",
            tool="erpnext.search_documents",
            arguments={
                "doctype": "ToDo",
                "filters": {"description": ["like", "%SCEN-CIVIL-PREP%"], "status": ["!=", "Closed"]},
                "fields": ["name", "description", "allocated_to", "priority", "reference_type", "reference_name", "status"],
                "limit": 10,
            },
            writes=False,
            description="检查 08:00 管理层摘要的背景异常输入。",
        ),
        WizardTool(
            id="stock-project-gloves",
            group="02 库存检查",
            label="查项目仓帆布手套库存",
            actor="周鹏，项目仓管员",
            tool="erpnext.stock.get_balance",
            arguments={"item_code": "SAFE-000005", "warehouse": PROJECT_WAREHOUSE},
            writes=False,
            description="查看项目仓当前帆布手套库存。",
        ),
        WizardTool(
            id="stock-center-gloves",
            group="02 库存检查",
            label="查中心仓帆布手套库存",
            actor="王海，仓库主管",
            tool="erpnext.stock.get_balance",
            arguments={"item_code": "SAFE-000005", "warehouse": CENTER_WAREHOUSE},
            writes=False,
            description="查看中心仓当前帆布手套库存。",
        ),
        WizardTool(
            id="mr-create-gloves",
            group="03 项目提料",
            label="创建城东劳保材料申请草稿",
            actor="马超，施工班组长",
            tool="erpnext.buying.create_material_request_draft",
            arguments={
                "material_request_type": "Purchase",
                "company": COMPANY,
                "schedule_date": required_by.isoformat(),
                "items": [
                    {
                        "item_code": "SAFE-000005",
                        "qty": 20,
                        "uom": "双",
                        "schedule_date": required_by.isoformat(),
                        "warehouse": PROJECT_WAREHOUSE,
                        "project": PROJECT_CHENGDONG,
                        "description": "Wizard 测试：城东道路改造项目申请 20 双帆布手套。",
                    },
                    {
                        "item_code": "SAFE-000006",
                        "qty": 10,
                        "uom": "个",
                        "schedule_date": required_by.isoformat(),
                        "warehouse": PROJECT_WAREHOUSE,
                        "project": PROJECT_CHENGDONG,
                        "description": "Wizard 测试：城东道路改造项目申请 10 个安全帽。",
                    },
                    {
                        "item_code": "SAFE-000007",
                        "qty": 15,
                        "uom": "件",
                        "schedule_date": required_by.isoformat(),
                        "warehouse": PROJECT_WAREHOUSE,
                        "project": PROJECT_CHENGDONG,
                        "description": "Wizard 测试：城东道路改造项目申请 15 件反光背心。",
                    }
                ],
            },
            writes=True,
            description="模拟班组长说人话后，Wizard 手动触发材料申请 ToolCall。",
        ),
        WizardTool(
            id="mr-list-pending",
            group="03 项目提料",
            label="查询待处理材料申请",
            actor="赵强，采购主管",
            tool="erpnext.search_documents",
            arguments={
                "doctype": "Material Request",
                "filters": {"material_request_type": "Purchase", "docstatus": 0},
                "fields": ["name", "title", "status", "transaction_date", "schedule_date", "company"],
                "limit": 10,
                "order_by": "modified desc",
            },
            writes=False,
            description="采购主管查看待处理材料申请。",
        ),
        WizardTool(
            id="po-create-gloves",
            group="04 采购",
            label="创建劳保采购订单草稿",
            actor="孙丽，行政采购员",
            tool="erpnext.buying.create_purchase_order_draft",
            arguments={
                "supplier": SUPPLIER_LABOR,
                "company": COMPANY,
                "transaction_date": current_day.isoformat(),
                "schedule_date": required_by.isoformat(),
                "items": [
                    {"item_code": "SAFE-000005", "qty": 20, "uom": "双", "warehouse": CENTER_WAREHOUSE, "rate": 8},
                    {"item_code": "SAFE-000006", "qty": 10, "uom": "个", "warehouse": CENTER_WAREHOUSE, "rate": 28},
                    {"item_code": "SAFE-000007", "qty": 15, "uom": "件", "warehouse": CENTER_WAREHOUSE, "rate": 18},
                ],
            },
            writes=True,
            description="先用直接 PO 草稿测试采购 ToolCall。",
        ),
        WizardTool(
            id="pr-create-gloves",
            group="05 收货",
            label="创建采购收货草稿",
            actor="王海，仓库主管",
            tool="erpnext.buying.create_purchase_receipt_draft",
            arguments={
                "supplier": SUPPLIER_LABOR,
                "company": COMPANY,
                "posting_date": current_day.isoformat(),
                "items": [
                    {"item_code": "SAFE-000005", "qty": 20, "uom": "双", "warehouse": CENTER_WAREHOUSE, "rate": 8},
                    {"item_code": "SAFE-000006", "qty": 10, "uom": "个", "warehouse": CENTER_WAREHOUSE, "rate": 28},
                    {"item_code": "SAFE-000007", "qty": 15, "uom": "件", "warehouse": CENTER_WAREHOUSE, "rate": 18},
                ],
            },
            writes=True,
            description="模拟供应商送货后，仓库创建收货草稿。",
        ),
        WizardTool(
            id="issue-preview-gloves",
            group="06 项目领料",
            label="预览项目领料是否足够",
            actor="周鹏，项目仓管员",
            tool="erpnext.projects.get_material_issue_context",
            arguments={
                "project": PROJECT_CHENGDONG,
                "source_warehouse": PROJECT_WAREHOUSE,
                "items": [{"item_code": "SAFE-000005", "qty": 10, "uom": "双", "description": "Wizard 测试：班组领用帆布手套。"}],
            },
            writes=False,
            description="先检查项目仓库存，再决定是否创建领料草稿。",
        ),
        WizardTool(
            id="issue-create-gloves",
            group="06 项目领料",
            label="创建项目领料草稿",
            actor="周鹏，项目仓管员",
            tool="erpnext.projects.create_material_issue_draft",
            arguments={
                "project": PROJECT_CHENGDONG,
                "source_warehouse": PROJECT_WAREHOUSE,
                "company": COMPANY,
                "posting_date": current_day.isoformat(),
                "remarks": "Wizard 测试：城东项目帆布手套领料草稿",
                "items": [{"item_code": "SAFE-000005", "qty": 10, "uom": "双", "description": "Wizard 测试：班组领用帆布手套。"}],
            },
            writes=True,
            description="只创建库存出库草稿，不提交库存移动。",
        ),
        WizardTool(
            id="finance-ap",
            group="07 财务查看",
            label="查看应付账款报表",
            actor="刘敏，财务主管",
            tool="erpnext.accounting.accounts_payable",
            arguments={"company": COMPANY, "from_date": month_start.isoformat(), "to_date": current_day.isoformat()},
            writes=False,
            description="财务查看应付报表，作为后续采购发票流程的观察点。",
        ),
    ]


def grouped_wizard_catalog(today: date | None = None) -> dict[str, Any]:
    tools = [tool.to_dict() for tool in build_wizard_tools(today)]
    groups: dict[str, list[dict[str, Any]]] = {}
    for tool in tools:
        groups.setdefault(tool["group"], []).append(tool)
    return {
        "company": COMPANY,
        "default_profile": "civil",
        "setup": {
            "script": "scripts/seed_civil_company_scenario.py",
            "dry_run_command": "python scripts/seed_civil_company_scenario.py --profile civil",
            "apply_command": "python scripts/seed_civil_company_scenario.py --profile civil --apply",
        },
        "groups": [{"name": name, "tools": entries} for name, entries in groups.items()],
        "all_tools": list_tool_schema_summaries(),
    }


def list_tool_schema_summaries() -> list[dict[str, Any]]:
    summaries = []
    for schema in ERPNext_TOOL_SCHEMAS:
        name = schema["name"]
        parameters = schema.get("parameters") or {}
        summaries.append(
            {
                "name": name,
                "risk_level": infer_risk_level(name),
                "description": schema.get("description", ""),
                "required": parameters.get("required") or [],
            }
        )
    return summaries
