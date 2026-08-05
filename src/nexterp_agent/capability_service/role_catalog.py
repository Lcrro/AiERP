from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResponsibilitySeed:
    key: str
    label: str
    summary: str
    kind: str = "own"
    priority: int = 100


@dataclass(frozen=True)
class RoleProfileSeed:
    role_code: str
    role_name: str
    mission: str
    boundaries: str
    escalation: str
    responsibilities: tuple[ResponsibilitySeed, ...]


ROLE_PROFILES: tuple[RoleProfileSeed, ...] = (
    RoleProfileSeed("ROLE-GM", "总经理", "掌握公司和项目整体状态，处理跨部门重大异常和关键决策。", "不代替经办人员编制日常单据；不绕过专业审批。", "专业或金额细节交由对应主管核实后决策。", (
        ResponsibilitySeed("management_overview", "管理摘要", "关注项目进度、采购、库存、资金和重大异常。"),
        ResponsibilitySeed("cross_team_decision", "跨部门决策", "协调项目、材料设备、经营和财务负责人。", "collaborate"),
    )),
    RoleProfileSeed("ROLE-MAT-EQP-MGR", "材料设备主管", "统筹物料、仓库、采购和设备资源，并承担材料申请第二级审批。", "不得替供应商虚构报价；重大采购和项目需求仍按工作流审批。", "规格争议找技术负责人，项目优先级找项目经理，资金事项找财务。", (
        ResponsibilitySeed("material_governance", "材料设备统筹", "维护物料口径并协调采购、库存和项目需求。"),
        ResponsibilitySeed("material_request_review", "材料申请审核", "审核材料申请的合理性、库存替代和采购路径。"),
    )),
    RoleProfileSeed("ROLE-MATERIAL-CLERK", "材料员", "准确提出项目材料需求，核对到货、库存和材料台账。", "不自行批准自己的申请；规格不清时不得猜测关键技术参数。", "规格问题找技术负责人，审批找材料设备主管，项目优先级找项目经理。", (
        ResponsibilitySeed("material_request", "材料需求", "查询标准物料和库存，发起并跟进材料申请。"),
        ResponsibilitySeed("receipt_check", "到货核对", "按订单和实物核对数量、规格及异常。"),
    )),
    RoleProfileSeed("ROLE-PROJ-MGR", "项目经理", "对项目进度、资源、材料需求和成本结果负责，并承担项目材料申请最终审批。", "不替代材料、技术和财务岗位的专业核验。", "跨项目资源协调上报材料设备主管或总经理。", (
        ResponsibilitySeed("project_delivery", "项目履约", "关注施工计划、缺料风险、项目成本和待审批事项。"),
        ResponsibilitySeed("project_approval", "项目审批", "审批本项目材料需求并确认工期优先级。"),
    )),
    RoleProfileSeed("ROLE-TECH-LEAD", "技术负责人", "确认材料技术规格、适用标准和现场技术方案。", "不决定采购价格、供应商选择或付款。", "采购可得性找材料设备主管，重大技术风险找项目经理。", (
        ResponsibilitySeed("specification", "规格确认", "澄清型号、材质、标准和适用条件。"),
        ResponsibilitySeed("technical_risk", "技术风险", "识别替代材料和现场使用风险。"),
    )),
    RoleProfileSeed("ROLE-OPS-MGR", "经营主管", "关注合同经营、采购成本、项目经营数据和偏差。", "不替代财务记账，不直接修改库存。", "财务口径找财务人员，现场数据找项目经理。", (
        ResponsibilitySeed("cost_analysis", "经营分析", "查看采购成本、项目经营指标和异常偏差。"),
        ResponsibilitySeed("commercial_coordination", "经营协同", "协调项目和财务核实经营数据。", "collaborate"),
    )),
    RoleProfileSeed("ROLE-FINANCE", "财务人员", "核对采购发票、应付和付款，确保财务记录可追溯。", "不创建采购订单，不替代仓库确认实收。", "数量差异找仓库或材料员，合同价格问题找采购负责人。", (
        ResponsibilitySeed("invoice_match", "发票核对", "核对订单、收货和发票的数量金额。"),
        ResponsibilitySeed("payables", "应付管理", "跟踪应付到期、付款状态和异常。"),
    )),
    RoleProfileSeed("ROLE-SYSADMIN", "系统管理员", "维护测试账套、用户权限、集成配置和系统可用性。", "不代表业务岗位作采购、库存或财务决策。", "业务规则由业务负责人确认，系统异常由管理员处理。", (
        ResponsibilitySeed("system_configuration", "系统配置", "维护用户、权限、集成和测试环境。"),
        ResponsibilitySeed("audit_support", "审计支持", "协助排查权限、接口和执行轨迹。"),
    )),
)


CONTEXT_GUIDES = {
    "responsibilities": ("岗位职责", "了解当前岗位应主动处理、协作和避免的事项。"),
    "collaboration": ("组织协作", "了解当前岗位的上下游协作对象和上报路径。"),
    "project": ("当前项目情境", "了解当前项目状态、仓库和工作范围。"),
    "recent_documents": ("最近单据", "读取与当前员工和项目相关的近期真实单据。"),
    "inbox": ("当前待办", "读取当前员工在 ERPNext 中可处理的待办。"),
    "process_position": ("流程位置", "了解当前岗位在采购及项目流程中的职责位置。"),
}


# Knowledge relevance only. ToolAccessPolicy and ERPNext remain the authority
# for whether an employee may load or execute an operation.
ROLE_CAPABILITY_LINKS: dict[str, tuple[str, ...]] = {
    "ROLE-GM": ("cap.document_lookup",),
    "ROLE-MAT-EQP-MGR": (
        "cap.material_lookup", "cap.material_classification", "cap.document_lookup", "cap.material_request",
        "cap.request_for_quotation", "cap.supplier_quotation", "cap.purchase_order",
        "cap.purchase_receipt", "cap.purchase_return",
    ),
    "ROLE-MATERIAL-CLERK": (
        "cap.material_lookup", "cap.material_classification", "cap.document_lookup", "cap.material_request",
        "cap.purchase_receipt", "cap.purchase_return",
    ),
    "ROLE-PROJ-MGR": ("cap.material_lookup", "cap.document_lookup", "cap.material_request"),
    "ROLE-TECH-LEAD": ("cap.material_lookup", "cap.material_classification", "cap.document_lookup"),
    "ROLE-OPS-MGR": (
        "cap.document_lookup", "cap.request_for_quotation", "cap.supplier_quotation", "cap.purchase_order",
    ),
    "ROLE-FINANCE": ("cap.document_lookup",),
    "ROLE-SYSADMIN": ("cap.material_lookup", "cap.material_classification", "cap.document_lookup"),
}
