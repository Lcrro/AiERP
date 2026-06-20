# 小型土木公司一日运转模拟：执行记录

本文用于按时间顺序记录“一天事件流”的实际执行情况。

关联文档：

- [时间顺序事件流](civil-company-day-events.md)
- [一天事件流准备度](civil-company-day-readiness.md)
- [ToolCall 覆盖矩阵](civil-company-day-toolcall-coverage.md)
- [Sandbox 初始化](civil-company-day-seed.md)

## 记录规则

- `未开始`：还没跑。
- `进行中`：正在执行或刚创建了中间单据，后续链路还没结束。
- `已完成`：本时间点目标已经跑通，并记录了关键结果。
- `阻塞`：因为工具缺口、数据缺失、权限、流程策略或业务歧义暂时停住。

每条记录尽量写清楚：

- 使用了哪些 ToolCall
- 产生了哪些单据 / ToDo / Comment
- 遇到了什么校验或阻塞
- 下一步依赖什么

## 执行总览

| 时间 | 事件 | 状态 | 结果摘要 | 关键产物 / 依赖 |
|---|---|---|---|---|
| 08:00 | 管理层查看今日异常 | 已完成 | 汇总出 5 项开工前风险；应付报表为空；当天 MR/PO 尚未开始 | 5 条背景异常 ToDo；项目仓电气缺口；后续等待 08:20 起现场造单 |
| 08:20 | 城东项目提报劳保用品需求 | 已完成 | 成功创建 3 行劳保用品 MR 草稿；自然语言组合检索未命中 | `MAT-MR-2026-00001`；下一步由项目经理审核 |
| 08:35 | 南区项目提报管材管件需求 | 已完成 | 系统正确进入追问/确认模式，没有贸然创建错误 MR | 产出规格追问；暴露 `PVC管 -> PVC排水管` 别名召回缺口 |
| 08:50 | 西站项目提报电气耗材需求 | 已完成 | 成功创建 4 行电气 MR 草稿；多物料组合检索未命中，单项检索部分可用 | `MAT-MR-2026-00002`；暴露 `漏电断路器 -> 漏电保护器` 别名缺口 |
| 09:10 | 项目经理审核材料需求 | 已完成 | 两张 MR 已提交并进入 Pending；确认对象字段要求已验证 | `MAT-MR-2026-00001`、`MAT-MR-2026-00002` 已提交 |
| 09:30 | 采购汇总待处理材料申请 | 已完成 | 成功汇总 2 张 Pending MR，并区分出劳保常用品与电气高紧急缺料 | 待采购清单；暴露 Item Price 结果里供应商映射不足 |
| 10:00 | 常用品直接转采购订单 | 已完成 | 已从劳保 MR 成功生成 1 张 PO 草稿 | `PUR-ORD-2026-00001`；保留 MR 行级引用 |
| 10:30 | 管材类材料发起询价 | 阻塞 | 供应商画像可读，但南区需求仍缺关键规格，未创建 RFQ | 供应商候选已确认；需先补口径/材质/压力等级 |
| 11:20 | 中心仓检查可用库存 | 已完成 | 中心仓手套库存充足；电气需求行在项目仓 100% 缺料 | `SAFE-000005` 库存 300；后续走补采/调拨 |
| 13:30 | 供应商送来劳保用品 | 已完成 | 已提交 PO 并成功生成/提交劳保采购收货 | `PUR-ORD-2026-00001`、`MAT-PRE-2026-00001` |
| 14:00 | 到货规格不符 | 已完成 | 已记录差异、创建跟进 ToDo，并生成退货草稿 | Comment + ToDo；`MAT-PR-RET-2026-00001` |
| 14:30 | 项目仓领料 | 已完成 | 已创建并提交项目领料，库存与价值影响已校验 | `MAT-STE-2026-00005` |
| 15:10 | 缺料触发补采 | 已完成 | 电气 3 行缺料预览成功；项目仓对明日施工确有短缺 | shortage preview；采购建议 business method 仍未命中 |
| 16:00 | 财务处理采购发票 | 已完成 | 已从 PR 生成并提交 PI，应付与总账已出现真实记录 | `ACC-PINV-2026-00001`；AP 710 CNY |
| 16:40 | 采购跟进未到货订单 | 已完成 | 当前无逾期 PO；唯一已下单劳保 PO 已收货待开票 | `PUR-ORD-2026-00001` 状态 `To Bill` |
| 17:20 | 项目经理查看项目成本 | 已完成 | 通过领料校验和总账可看到成本影响；项目成本上下文聚合仍偏弱 | `MAT-STE-2026-00005`、GL、PI/PR 记录 |
| 18:00 | 总经理看当天收尾摘要 | 已完成 | 已形成当天业务闭环摘要，并识别出剩余风险与工具缺口 | MR/PO/PR/PI/Return/Issue 全链路记录 |

## 逐条记录

### 08:00 管理层查看今日异常

- 状态：`已完成`
- 目标：汇总缺料、延期、待审批、逾期付款、退货风险。
- 预期 ToolCall：
  - `erpnext.search_documents`
  - `erpnext.stock.get_balance`
  - `erpnext.accounting.accounts_payable`
  - `erpnext.buying.run_purchase_analysis`
- 预置输入：
  - `SCEN-CIVIL-PREP-MANAGER-LOW-STOCK`
  - `SCEN-CIVIL-PREP-PO-DELAY-RISK`
  - `SCEN-CIVIL-PREP-AP-DUE-RISK`
  - `SCEN-CIVIL-PREP-RETURN-RISK`
  - `SCEN-CIVIL-PREP-APPROVAL-QUEUE`
- 实际执行 ToolCall：
  - `erpnext.search_documents`：查询 `SCEN-CIVIL-PREP-*` 开放 ToDo
  - `erpnext.search_documents`：查询中心仓 / 项目仓 `Bin`
  - `erpnext.accounting.accounts_payable`：查看 `STEC (Demo)` 2026-06-01 到 2026-06-13 的应付报表
  - `erpnext.search_documents`：查询已提交 `Purchase Order`
  - `erpnext.search_documents`：查询草稿 `Material Request`
- 实际结果：
  - 共汇总到 5 条开工前风险输入，已经覆盖今日重点关注项：
    - `高`：项目仓 LED 灯管、漏电保护器库存偏低，影响西站项目明天施工
    - `高`：通达管材存在到货延期风险，下午需要采购跟进
    - `中`：强盛建材有历史应付款今日到期，需要财务核对
    - `中`：安科劳保用品存在历史规格不符风险，今日收货需重点核对
    - `中`：项目经理 09:10 前有材料需求审批堆积
  - 项目仓当前只有 `ELEC-000005`、`SAFE-000006`、`MAT-CEM-000004`、`SAFE-000007`、`SAFE-000005`、`PIPE-000415` 有库存；`ELEC-000001` 漏电保护器和 `ELEC-000007` LED 灯管未见项目仓现货，可视为今日开场的真实缺口。
  - 中心仓有可调剂库存，但漏电保护器仅 4 个、井盖仅 6 套、脚手架仅 6 套，属于后续需要持续盯住的低量物资。
  - `Accounts Payable` 报表返回 0 行，说明“今日到期应付款”目前是沙盘背景异常，不是已经落到账内的真实应付单据。
  - 已提交 `Purchase Order = 0`，草稿 `Material Request = 0`，符合“当天业务尚未开始”的预期。
- 管理层视角摘要：
  - 今天开场前最优先关注的是三件事：西站项目电气缺料、通达管材延期风险、09:10 前的审批堆积。
  - 财务到期风险和劳保收货质量风险已经被标记，但要等今天后续采购/收货动作落地后才会转成真实 ERP 单据链。
- 产生的产物：
  - 无新增单据
  - 无新增 ToDo / Comment
- 下一步依赖：
  - 进入 `08:20`，由马超为城东项目创建劳保用品 `Material Request` 草稿

### 08:20 城东项目提报劳保用品需求

- 状态：`已完成`
- 目标：为帆布手套、安全帽、反光背心生成 MR 草稿。
- 预期 ToolCall：
  - `erpnext.search_items`
  - `erpnext.buying.create_material_request_draft`
- 实际执行 ToolCall：
  - `erpnext.search_items`：查询“帆布手套 安全帽 反光背心”
  - `erpnext.buying.create_material_request_draft`：为城东项目创建 3 行采购型 `Material Request`
- 实际结果：
  - `search_items` 对这句组合式自然语言返回 `not_found`，没有直接召回候选物料，并要求补充标准名称、规格型号、材质、品牌或物料编码。
  - 使用结构化 `item_code` 直接创建草稿成功，生成：
    - `MAT-MR-2026-00001`
    - 标题：`采购申请帆布手套, 安全帽, 反光背心`
    - `docstatus = 0`
    - `status = Draft`
  - 草稿内 3 行物料都自动带出了项目、仓库、单位和当前库存快照：
    - `SAFE-000005` 帆布手套 `20 双`，项目仓现货 `50`
    - `SAFE-000006` 安全帽 `10 个`，项目仓现货 `12`
    - `SAFE-000007` 反光背心 `15 件`，项目仓现货 `20`
  - 这说明当前 ERP Tool 层能够稳定创建劳保用品 MR 草稿，但“把一句多人话拆成多个物料查询”还不够强，属于 Agent Runtime / 检索编排层的待补项。
- 产生的产物：
  - 新增 `Material Request` 草稿：`MAT-MR-2026-00001`
  - 未新增 ToDo / Comment
- 当前判断：
  - 从库存角度看，这三项在项目仓其实都有现货；如果走更聪明的 Agent 逻辑，后续可能会建议“先领料 / 再补库”，而不是默认全量采购。
  - 但从本条事件定义来看，它的目标是“班组先提报需求并生成申请草稿”，这一点已经完成。
- 下一步依赖：
  - 进入 `08:35`，为南区项目提报管材管件需求；这一条更适合顺手检验“规格不清时追问”的行为。

### 08:35 南区项目提报管材管件需求

- 状态：`已完成`
- 目标：为 PVC 管、弯头、三通、井盖等生成 MR，规格不清时记录追问。
- 预期 ToolCall：
  - `erpnext.search_items`
  - `erpnext.buying.create_material_request_draft`
- 实际执行 ToolCall：
  - `erpnext.search_items`：查询组合表达 `PVC管 弯头 三通 井盖`
  - `erpnext.search_items`：分别查询 `PVC管`、`弯头`、`三通`、`井盖`
- 实际结果：
  - 组合查询 `PVC管 弯头 三通 井盖` 返回 `not_found`，没有直接召回任何可信候选。
  - `PVC管` 单独查询同样返回 `not_found`，说明当前检索还不能把用户土名稳定映射到 `PVC排水管`。
  - `弯头` 成功召回 `PIPE-000021 / PVC弯头`，但状态是 `needs_clarification`，要求补充规格、材质、型号、口径、长度或适用设备。
  - `三通` 成功召回 `PIPE-000416 / PVC三通`，但同样是 `needs_clarification`。
  - `井盖` 召回 `MAT-CAST-000001 / 球墨铸铁井盖`，状态为 `needs_confirmation`，要求补充规格、品牌、型号或物料组。
  - 系统没有在规格不清时直接创建 `Material Request`，这一点符合场景要求。
- 产生的产物：
  - 未新增 `Material Request`
  - 未新增 ToDo / Comment
- 当前判断：
  - 这条事件的主目标不是“必须建单”，而是“规格不清时要追问”，这一点已经跑通。
  - 当前最明显的检索缺口是：
    - `PVC管` 没法稳定映射到 `PVC排水管`
    - 管材管件还缺少口径、压力等级、材质等结构化规格字段来支撑更细的追问
- 推荐追问示例：
  - `PVC 管`：请补充管径、壁厚/压力等级、用途，是排水管还是给水管？
  - `弯头 / 三通`：请补充口径、材质、承压等级或适配管型。
  - `井盖`：请补充材质、承载等级、尺寸和安装位置。
- 下一步依赖：
  - 进入 `08:50`，测试西站项目的电气耗材需求；这一条适合看电气物料在当前检索下是否更容易落到正确 SKU。

### 08:50 西站项目提报电气耗材需求

- 状态：`已完成`
- 目标：为电工胶布、热缩管、漏电断路器、灯管生成 MR 草稿。
- 预期 ToolCall：
  - `erpnext.search_items`
  - `erpnext.buying.create_material_request_draft`
- 实际执行 ToolCall：
  - `erpnext.search_items`：查询组合表达 `电工胶布 热缩管 漏电断路器 灯管`
  - `erpnext.search_items`：分别查询 `电工胶布`、`热缩管`、`漏电断路器`、`灯管`
  - `erpnext.buying.create_material_request_draft`：为西站项目创建 4 行采购型 `Material Request`
- 实际结果：
  - 组合查询再次返回 `not_found`，说明当前检索还不支持一句话里并列多个物料。
  - 单项查询表现分化：
    - `电工胶布` -> `ELEC-000005 / PVC电工胶布`，`needs_confirmation`
    - `热缩管` -> `ELEC-000002 / 热缩管`，`needs_confirmation`
    - `灯管` -> `ELEC-000007 / LED灯管`，`needs_confirmation`
    - `漏电断路器` -> `not_found`
  - 使用结构化 `item_code` 创建草稿成功，生成：
    - `MAT-MR-2026-00002`
    - `docstatus = 0`
    - `status = Draft`
  - 草稿包含 4 行物料：
    - `ELEC-000005` PVC电工胶布 `8 卷`，项目仓现货 `12`
    - `ELEC-000002` 热缩管 `30 米`，项目仓现货 `0`
    - `ELEC-000001` 漏电保护器 `2 个`，项目仓现货 `0`
    - `ELEC-000007` LED灯管 `6 根`，项目仓现货 `0`
  - 通过直接按名称查询，可以确认 `MAT-MR-2026-00002` 已存在；列表查询在刚创建后出现了短暂不一致，这更像本地 sandbox 检索延迟，而不是建单失败。
- 产生的产物：
  - 新增 `Material Request` 草稿：`MAT-MR-2026-00002`
  - 未新增 ToDo / Comment
- 当前判断：
  - 电气类比管材类更容易召回正确候选，但仍然达不到“自动放心选择”的程度。
  - 最明显的别名缺口是：`漏电断路器` 没法稳定映射到 `漏电保护器`。
  - 从库存角度看，这张 MR 更像真实缺料：热缩管、漏电保护器、LED灯管在项目仓都为 `0`，比 `08:20` 的劳保 MR 更有采购动机。
- 下一步依赖：
  - 进入 `09:10`，由项目经理审核并提交已经生成的材料申请；当前应至少处理 `MAT-MR-2026-00001` 和 `MAT-MR-2026-00002`。

### 09:10 项目经理审核材料需求

- 状态：`已完成`
- 目标：检查 MR 必填项并提交，必要时记录确认或阻塞原因。
- 预期 ToolCall：
  - `erpnext.get_document`
  - `erpnext.buying.submit_document`
  - `erpnext.get_workflow_actions`
  - `erpnext.apply_workflow`
- 实际执行 ToolCall：
  - `erpnext.get_document`：读取 `MAT-MR-2026-00001`、`MAT-MR-2026-00002`
  - `erpnext.get_workflow_actions`：检查是否存在显式 workflow 动作
  - `erpnext.buying.submit_document`：按采购提交确认对象提交两张 MR
  - `erpnext.search_documents`：回查 `docstatus = 1` 的 `Material Request`
- 实际结果：
  - 第一次尝试提交时，`confirmation` 误用了字符串，触发了 adapter 里的结构约束；修正后改为对象并成功提交。
  - 采购提交确认对象需要这 4 个字段：
    - `confirmed_by`
    - `confirmed_at`
    - `confirmation_text`
    - `reason`
  - `MAT-MR-2026-00001` 提交成功：
    - `docstatus = 1`
    - 单据状态变为 `Pending`
  - `MAT-MR-2026-00002` 提交成功：
    - `docstatus = 1`
    - 单据状态变为 `Pending`
  - 回查已提交 `Material Request` 列表时，两张单据都能稳定看到。
- 产生的产物：
  - 无新增新单据类型
  - 现有单据状态变化：
    - `MAT-MR-2026-00001`：`Draft -> Submitted/Pending`
    - `MAT-MR-2026-00002`：`Draft -> Submitted/Pending`
- 当前判断：
  - 这一条验证了“高风险提交必须带结构化确认元数据”的机制是生效的。
  - 也说明当前流程不依赖额外 workflow，就可以先用 `submit_document` 把 MR 推到采购可处理状态。
- 下一步依赖：
  - 进入 `09:30`，采购应能基于这两张 `Pending` 材料申请做汇总和分流。

### 09:30 采购汇总待处理材料申请

- 状态：`已完成`
- 目标：按项目、物料类别、供应商和紧急程度生成采购处理清单。
- 预期 ToolCall：
  - `erpnext.search_documents`
  - `erpnext.buying.search_suppliers`
  - `erpnext.buying.search_item_prices`
- 实际执行 ToolCall：
  - `erpnext.search_documents`：查询 `docstatus = 1`、`material_request_type = Purchase` 的 `Material Request`
  - `erpnext.buying.search_suppliers`：查询场景供应商
  - `erpnext.buying.search_item_prices`：查询 `Standard Buying` 价格
- 实际结果：
  - 当前待采购的 `Pending Material Request` 共 2 张：
    - `MAT-MR-2026-00001`：`采购申请帆布手套, 安全帽, 反光背心`
    - `MAT-MR-2026-00002`：`采购申请PVC电工胶布, 热缩管, 漏电保护器`
  - 当前可用场景供应商共 4 家：
    - `SCEN-CIVIL 恒信电气`
    - `SCEN-CIVIL 强盛建材`
    - `SCEN-CIVIL 通达管材`
    - `SCEN-CIVIL 安科劳保用品`
  - `Standard Buying` 价格表能够返回本场景物料的标准采购价，可用于快速生成采购处理清单。
  - 基于 MR 明细和当前库存快照整理后的采购判断如下：
    - `MAT-MR-2026-00001 / 城东项目 / 劳保用品`
      - `SAFE-000005` 帆布手套：项目仓现货 `50`，本次申请 `20`，紧急度 `normal`
      - `SAFE-000006` 安全帽：项目仓现货 `12`，本次申请 `10`，紧急度 `normal`
      - `SAFE-000007` 反光背心：项目仓现货 `20`，本次申请 `15`，紧急度 `normal`
      - 这张更适合作为“常用品直接下单”样本
    - `MAT-MR-2026-00002 / 西站项目 / 电气耗材`
      - `ELEC-000005` PVC电工胶布：项目仓现货 `12`，紧急度 `normal`
      - `ELEC-000002` 热缩管：项目仓现货 `0`，紧急度 `high`
      - `ELEC-000001` 漏电保护器：项目仓现货 `0`，紧急度 `high`
      - `ELEC-000007` LED灯管：项目仓现货 `0`，紧急度 `high`
      - 这张应优先进入缺料处理/加急采购
- 产生的产物：
  - 无新增 ERP 单据
  - 形成了采购处理视角的待办分流：
    - 常用品直接转单：`MAT-MR-2026-00001`
    - 高紧急缺料优先处理：`MAT-MR-2026-00002`
- 当前判断：
  - 采购汇总这一条已经能跑通，工具层足够把“待采购 MR + 供应商 + 价格”拉出来做分流。
  - 目前还有一个很实际的小缺口：`search_item_prices` 的当前结果里没有直接把供应商映射得很友好，所以做“自动推荐供应商”时，还需要额外补一层价格记录解释或主数据绑定。
- 下一步依赖：
  - 进入 `10:00`，先把劳保这类低风险常用品从 `MAT-MR-2026-00001` 直接转成采购订单草稿。

### 10:00 常用品直接转采购订单

- 状态：`已完成`
- 目标：把低风险常用品转成 PO 草稿。
- 预期 ToolCall：
  - `erpnext.buying.create_purchase_order_from_material_request_draft`
  - `erpnext.buying.create_purchase_order_draft`
- 实际执行 ToolCall：
  - `erpnext.buying.create_purchase_order_from_material_request_draft`
  - `erpnext.get_document`：通过创建返回值核验 PO 草稿内容
- 实际结果：
  - 以 `MAT-MR-2026-00001` 为来源，指定供应商 `SCEN-CIVIL 安科劳保用品`，成功创建采购订单草稿：
    - `PUR-ORD-2026-00001`
    - `docstatus = 0`
    - `status = Draft`
  - 新建 PO 保留了来源 MR 的行级引用关系，3 行物料都能追溯回原始申请行：
    - `SAFE-000005` 帆布手套 `20 双`，单价 `8`，金额 `160`
    - `SAFE-000006` 安全帽 `10 个`，单价 `28`，金额 `280`
    - `SAFE-000007` 反光背心 `15 件`，单价 `18`，金额 `270`
  - PO 草稿同时带出了项目、仓库、需求日期等关键信息，总金额为 `710 CNY`。
  - 创建后立刻用通用列表查询回查时，出现了和前面 MR 类似的短暂列表不一致；但创建返回值里已经带有完整原始 PO 文档，因此本次创建本身视为成功。
- 产生的产物：
  - 新增 `Purchase Order` 草稿：`PUR-ORD-2026-00001`
- 当前判断：
  - “从已提交 MR 直接生成 PO 草稿”这条采购主干链路已经跑通。
  - 当前 sandbox 更适合把“创建返回结果 + 直接按单号读取”作为权威确认方式，不能过度依赖刚创建后立即列表查询的可见性。
- 下一步依赖：
  - 进入 `10:30`，处理管材类询价；但南区项目上一条还停留在“规格待澄清”，因此这里大概率会以“待补规格后再发 RFQ”的形式推进。

### 10:30 管材类材料发起询价

- 状态：`阻塞`
- 目标：生成 RFQ 和 Supplier Quotation 草稿。
- 预期 ToolCall：
  - `erpnext.buying.create_request_for_quotation_draft`
  - `erpnext.buying.create_supplier_quotation_draft`
  - `erpnext.buying.compare_supplier_quotations`
- 实际执行 ToolCall：
  - `erpnext.buying.search_suppliers`：确认场景供应商候选仍可用
  - `erpnext.buying.get_supplier_procurement_profile`：读取 `SCEN-CIVIL 通达管材`、`SCEN-CIVIL 强盛建材`
- 实际结果：
  - 两家候选供应商画像都能正常读取，没有 `warn/prevent RFQ` 阻断。
  - 但南区项目在 `08:35` 的核心结论没有改变：用户只说了 `PVC 管、弯头、三通、井盖`，还没有补齐口径、材质、压力等级、型号等关键规格。
  - 在这种前提下，当前最合理的行为不是硬建 RFQ，而是把这条明确记为“等待规格澄清后再发询价”。
- 产生的产物：
  - 无新增 RFQ / Supplier Quotation
- 当前判断：
  - 这不是 ToolCall 本身缺失，而是业务前置条件没满足。
  - 这条事件反而说明现在的工具边界是对的：供应商信息能查，但在物料规格不完整时不应该自动发出去。
- 下一步依赖：
  - 先补充：PVC 管径、壁厚/压力等级；弯头/三通口径；井盖尺寸、材质、承载等级。

### 11:20 中心仓检查可用库存

- 状态：`已完成`
- 目标：判断可直接发料、需调拨还是需采购。
- 预期 ToolCall：
  - `erpnext.stock.get_balance`
  - `erpnext.stock.get_item_locations`
  - `erpnext.stock.allocate_shortages`
- 实际执行 ToolCall：
  - `erpnext.stock.get_balance`：查询 `SAFE-000005 / SCEN-CIVIL 中心仓 - SD`
  - `erpnext.stock.allocate_shortages`：按西站项目的电气缺料行预览
- 实际结果：
  - 中心仓 `SAFE-000005` 帆布手套现货 `300 双`，估值单价 `8`，证明劳保常用品有稳定中心仓储备。
  - 对西站项目电气需求做缺料预览时，项目仓 3 行全部短缺：
    - `ELEC-000002` 热缩管：需求 `30`，缺口 `30`
    - `ELEC-000001` 漏电保护器：需求 `2`，缺口 `2`
    - `ELEC-000007` LED灯管：需求 `6`，缺口 `6`
  - 这说明上午的电气 MR 并不是“多提了一张单”，而是真实反映了明日施工缺料。
- 产生的产物：
  - 无新增单据
  - 形成可操作判断：
    - 劳保常用品：中心仓/常规采购都可覆盖
    - 电气材料：项目仓当前缺口明确，需要调拨或补采
- 下一步依赖：
  - 进入 `13:30`，让劳保 PO 真正生成采购收货。

### 13:30 供应商送来劳保用品

- 状态：`已完成`
- 目标：从采购订单生成采购收货草稿。
- 预期 ToolCall：
  - `erpnext.buying.create_purchase_receipt_from_purchase_order_draft`
  - `erpnext.buying.create_purchase_receipt_draft`
- 实际执行 ToolCall：
  - `erpnext.buying.submit_document`：提交 `PUR-ORD-2026-00001`
  - `erpnext.buying.create_purchase_receipt_from_purchase_order_draft`：从已提交 PO 创建 PR 草稿
  - `erpnext.buying.submit_document`：提交 `MAT-PRE-2026-00001`
- 实际结果：
  - `PUR-ORD-2026-00001` 已提交，状态转为 `Submitted`。
  - 成功从 PO 生成采购收货草稿：
    - `MAT-PRE-2026-00001`
    - 保留 3 行 `purchase_order / purchase_order_item` 来源引用
    - 自动带出项目、仓库、单价、金额
  - 随后采购收货也已提交：
    - `docstatus = 1`
    - 状态变为 `To Bill`
  - 这一条验证了 `PO -> PR` 的正式 wrapper 已经能在真实沙盘里跑通。
- 产生的产物：
  - 已提交 `Purchase Order`：`PUR-ORD-2026-00001`
  - 已提交 `Purchase Receipt`：`MAT-PRE-2026-00001`
- 下一步依赖：
  - 进入 `14:00`，在已提交 PR 上记录到货规格不符并生成退货跟进。

### 14:00 到货规格不符

- 状态：`已完成`
- 目标：记录差异、创建 ToDo，必要时生成退货上下文或退货草稿。
- 预期 ToolCall：
  - `erpnext.buying.record_purchase_receipt_discrepancy`
  - `erpnext.buying.get_purchase_receipt_return_context`
  - `erpnext.buying.create_purchase_receipt_return_draft`
- 实际执行 ToolCall：
  - `erpnext.buying.record_purchase_receipt_discrepancy`
  - `erpnext.buying.create_purchase_receipt_return_draft`
  - `erpnext.search_documents`：回查 ToDo / Comment
- 实际结果：
  - 以 `SAFE-000005 / 帆布手套` 为例，记录了“应为加厚款，实到普通薄款”的规格不符。
  - 差异记录成功写入 `Purchase Receipt MAT-PRE-2026-00001`，并自动创建：
    - Comment：`Agent 到货差异记录`
    - ToDo：分配给 `zhao.qiang@scen-civil.local`
  - 同时成功生成退货草稿：
    - `MAT-PR-RET-2026-00001`
    - `is_return = 1`
    - `return_against = MAT-PRE-2026-00001`
    - 退货行为 1 行，负数量 `-20 双`
- 产生的产物：
  - Comment：记录到货差异
  - ToDo：跟进供应商退换货
  - 采购退货草稿：`MAT-PR-RET-2026-00001`
- 当前判断：
  - “收货异常 -> 评论/待办 -> 退货草稿”这条后半段采购链也已经能跑通。
- 下一步依赖：
  - 进入 `14:30`，做项目仓真实领料并验证成本影响。

### 14:30 项目仓领料

- 状态：`已完成`
- 目标：创建项目领料草稿并检查成本影响。
- 预期 ToolCall：
  - `erpnext.projects.get_material_issue_context`
  - `erpnext.projects.create_material_issue_draft`
  - `erpnext.projects.verify_material_issue_cost_impact`
- 实际执行 ToolCall：
  - `erpnext.projects.get_material_issue_context`
  - `erpnext.projects.create_material_issue_draft`
  - `erpnext.stock.submit_document`
  - `erpnext.projects.verify_material_issue_cost_impact`
- 实际结果：
  - 以 `SAFE-000006 / 安全帽` 为例，为城东项目创建了项目领料草稿：
    - 草稿单号：`MAT-STE-2026-00005`
    - 来源仓库：`SCEN-CIVIL 项目仓 - SD`
    - 数量：`6 个`
  - 草稿提交成功后，成本影响验证通过：
    - `item_issue_qty = 6`
    - `item_issue_amount = 168`
    - `ledger_out_qty = 6`
    - `ledger_value_difference = -168`
  - 这说明项目领料已经不只是“能建草稿”，而是能够真正落到库存账和项目成本痕迹里。
- 产生的产物：
  - 已提交 `Stock Entry / Material Issue`：`MAT-STE-2026-00005`
- 当前判断：
  - 这里还暴露了一个很重要的 Agent Runtime 需求：提交后必须把新单号写回上下文，否则很容易误拿旧单号继续操作。
- 下一步依赖：
  - 进入 `15:10`，根据项目仓短缺情况触发补采判断。

### 15:10 缺料触发补采

- 状态：`已完成`
- 目标：生成缺料建议和补采动作。
- 预期 ToolCall：
  - `erpnext.stock.get_balance`
  - `erpnext.buying.generate_purchase_suggestions`
  - `erpnext.buying.create_material_request_draft`
  - `erpnext.create_todo`
- 实际执行 ToolCall：
  - `erpnext.stock.allocate_shortages`
  - `erpnext.buying.generate_purchase_suggestions`
- 实际结果：
  - `allocate_shortages` 已经把西站项目的 3 行电气缺料全部明确出来，缺口分别为 `30 / 2 / 6`。
  - `generate_purchase_suggestions` 当前返回 `0` 行，说明 `agent_bridge` 里的这条业务建议方法还没有和这套 clean site 的实际缺料状态形成联动。
- 产生的产物：
  - 无新增 MR / ToDo
  - 形成明确结论：底层缺料预览已可用，自动采购建议 business method 仍需补实战联动
- 当前判断：
  - 这条事件“业务上已识别缺料”是成立的，但“自动补采建议”还不够成熟。
- 下一步依赖：
  - 进入 `16:00`，对已收货的劳保用品生成采购发票。

### 16:00 财务处理采购发票

- 状态：`已完成`
- 目标：从 PR 生成 PI 草稿并检查应付影响。
- 预期 ToolCall：
  - `erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft`
  - `erpnext.accounting.accounts_payable`
- 实际执行 ToolCall：
  - `erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft`
  - `erpnext.accounting.submit_financial_document`
  - `erpnext.accounting.accounts_payable`
  - `erpnext.accounting.general_ledger`
- 实际结果：
  - 成功从 `MAT-PRE-2026-00001` 生成采购发票草稿：
    - `ACC-PINV-2026-00001`
    - 保留 `purchase_receipt/pr_detail` 和 `purchase_order/po_detail` 引用
  - 财务确认后已提交：
    - `docstatus = 1`
    - `status = Submitted`
    - 风险级别为 `L5_FINANCIAL`
  - `Accounts Payable` 报表已出现真实应付：
    - 供应商：`SCEN-CIVIL 安科劳保用品`
    - 发票：`ACC-PINV-2026-00001`
    - 金额 / 未付：`710 CNY`
  - `General Ledger` 也已出现对应分录：
    - `Creditors - SD` 贷方 `710`
    - `Stock Received But Not Billed - SD` 借方 `710`
- 产生的产物：
  - 已提交 `Purchase Invoice`：`ACC-PINV-2026-00001`
  - 真实应付账款记录：`710 CNY`
- 下一步依赖：
  - 进入 `16:40`，检查今天是否存在真实逾期采购订单。

### 16:40 采购跟进未到货订单

- 状态：`已完成`
- 目标：查询逾期 PO 并生成跟进动作。
- 预期 ToolCall：
  - `erpnext.search_documents`
  - `erpnext.create_todo`
  - `erpnext.add_comment`
- 实际执行 ToolCall：
  - `erpnext.search_documents`：查询已提交 `Purchase Order`
- 实际结果：
  - 当前只有 1 张真实已提交采购订单：
    - `PUR-ORD-2026-00001`
    - 供应商：`SCEN-CIVIL 安科劳保用品`
    - 状态：`To Bill`
    - `per_received = 100`
    - `schedule_date = 2026-06-14`
  - 由于已经全收货且计划日期还没过，所以今天没有真实“逾期未到货 PO”，不需要新增跟进 ToDo。
- 产生的产物：
  - 无新增 ToDo / Comment
- 当前判断：
  - 这条不是没能力，而是今天这套沙盘数据下确实没有逾期 PO。
- 下一步依赖：
  - 进入 `17:20`，从项目成本视角复盘今天的采购、收货、领料和发票。

### 17:20 项目经理查看项目成本

- 状态：`已完成`
- 目标：查看当日采购、领料、退货对项目成本的影响。
- 预期 ToolCall：
  - `erpnext.projects.get_project_cost_context`
  - `erpnext.stock.get_ledger_entries`
  - `erpnext.accounting.general_ledger`
- 实际执行 ToolCall：
  - `erpnext.projects.get_project_cost_context`
  - `erpnext.projects.verify_material_issue_cost_impact`
  - `erpnext.accounting.general_ledger`
- 实际结果：
  - `verify_material_issue_cost_impact` 已明确验证：
    - `MAT-STE-2026-00005` 为城东项目领料 `6 个安全帽`
    - 对项目相关库存价值影响为 `-168`
  - `General Ledger` 已看到与今天业务相关的 3 类关键分录：
    - `Purchase Receipt MAT-PRE-2026-00001`：库存与暂估应付 `710`
    - `Purchase Invoice ACC-PINV-2026-00001`：暂估应付转正式应付 `710`
    - `Stock Entry MAT-STE-2026-00005`：项目领料成本 `168`
  - `get_project_cost_context` 当前返回值仍偏弱，没有把今天刚生成的 `Stock Entry / Purchase Receipt` 自动汇总出来，说明这个项目成本聚合工具还需要补查询逻辑。
- 产生的产物：
  - 无新增单据
  - 形成了项目成本复盘依据：`领料验证 + 总账 + 单据链`
- 当前判断：
  - 项目成本已经“可验证”，但还没做到“一条 ToolCall 就给经理看懂的项目成本摘要”。
- 下一步依赖：
  - 进入 `18:00`，汇总当天闭环摘要。

### 18:00 总经理看当天收尾摘要

- 状态：`已完成`
- 目标：汇总采购、库存、项目、财务和异常闭环情况。
- 预期 ToolCall：
  - `erpnext.search_documents`
  - `erpnext.run_report`
  - `erpnext.accounting.accounts_payable`
  - `erpnext.buying.run_purchase_analysis`
- 实际结果：
  - 今天已经形成完整真实单据链：
    - `Material Request`：`MAT-MR-2026-00001`、`MAT-MR-2026-00002`
    - `Purchase Order`：`PUR-ORD-2026-00001`
    - `Purchase Receipt`：`MAT-PRE-2026-00001`
    - `Purchase Receipt Return Draft`：`MAT-PR-RET-2026-00001`
    - `Purchase Invoice`：`ACC-PINV-2026-00001`
    - `Stock Entry / Material Issue`：`MAT-STE-2026-00005`
  - 当天已落地的管理事实：
    - 劳保用品采购、收货、发票和项目领料主线已闭环
    - 西站项目电气缺料已被真实识别，仍待补采/调拨
    - 南区项目管材需求仍因规格不清被挡在询价前
    - 收货规格不符已形成 Comment、ToDo 和退货草稿
    - 财务应付已真实入账 `710 CNY`
  - 当天暴露出的工具/编排缺口：
    - 多物料自然语言检索还不稳
    - `generate_purchase_suggestions` 对 clean site 缺料状态没有产出建议
    - `get_project_cost_context` 聚合还不够完整
    - `search_documents` 对某些非法字段的错误分类不够准确
    - 运行时必须可靠记住新生成单号，否则很容易串单
