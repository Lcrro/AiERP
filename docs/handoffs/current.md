# 当前开发交接

新任务先运行 `python scripts/dev/project_context.py resume`，再按本次请求选择模块。

- 分支：`codex/material-intake-publish-v0.8`
- HEAD：`5a07a151e5ea570c0211e63de90c06232ebb20e5`
- 工作区业务变化：`1` 个；运行时文件不纳入上下文。
- 当前里程碑：`procurement-frequency-discovery-v0.6`

## 入口

- workbench: `http://127.0.0.1:8788/`
- material_intake_lab: `http://127.0.0.1:8788/material-intake-lab`
- material_item_lab: `http://127.0.0.1:8788/material-item-lab`
- tariff_extraction_lab: `http://127.0.0.1:8788/tariff-extraction-lab`
- tariff_declaration_lab: `http://127.0.0.1:8788/tariff-declaration-lab`
- tariff_family_review: `http://127.0.0.1:8788/tariff-family-review`
- tariff_taxonomy_browser: `http://127.0.0.1:8788/tariff-taxonomy-browser`
- procurement_batch_pilot: `http://127.0.0.1:8788/procurement-batch-pilot`
- capability_api: `http://127.0.0.1:8790`
- erpnext_civil: `http://localhost:8002`
- erpnext_material_test: `http://localhost:8003`

## 需要知道的事实

- GPC 物料目录统一六层结构 v0.5 已完成：标准类型统一采用 Segment→Family→Class→Brick→物料族→标准类型；63 个原五层类型迁至第六层，新增 43 个业务物料族和 1 个灭火器附属设备本地 Brick 等价层。当前 49 个物料族、85 个标准类型节点中分别有 48/83 个挂载 259 项实际物料；重复 ID、错误父级、遗留 NXT 引用均为 0，重复干跑新增/重编号/重挂载均为 0。SQLite r10，215 个物料模块测试和 60 个工作台测试通过；ERPNext 写入 0。
- 物料采购目录离线降级已完成：目录接口不再沿用 90 秒业务写入超时，ERPNext 不可用时回退到最近同步的 259 项目录并缓存结果；页面明确显示离线状态、禁用加入申请和创建草稿，另有 12 秒浏览器超时兜底。88 个聚焦测试和浏览器回读通过；未写入 ERPNext。
- 螺栓标准类型与规格聚合 v0.1 已完成：逐条复核 27 个原分类边界项，以头型、结构和用途证据重分为六角、双头、头型待识别、绞制孔、预埋、环向/纵向连接、带孔和全螺纹杆；104 个 SKU 在采购页聚合为 8 张类型卡片，并用规格、材质/表面处理、性能等级和供货范围唯一解析现有 SKU。SQLite r9，33 个聚焦测试、浏览器唯一匹配和项目检查通过；未重编号 ERPNext Item，ERPNext 写入 0。
- GPC 到无头 ERPNext 物料测试账套同步 v0.1 已完成：独立 Docker Site `material-test.localhost` 运行 ERPNext v15.118.2，零物料基线保存在 Git 忽略的 `.secrets`；GPC 2026-05 SQLite r7 冻结为 SHA-256 `b2cc2b6a6d18408486e52a248b52d6db50a572dc7be93eca521feaaad6c9f4fe`，通过标准 Frappe REST 创建 14 个在用 Segment 经营组、16 个 UOM 和 259 个实际 SKU。逐项全字段回读为 259 unchanged、冲突/额外/不一致均 0；同 request_id 重放未重复创建；采购、收货、库存流水、总账等 9 类交易记录均为 0。
- GPC 扩展层级统一编号 v0.4 已完成：官方 8 位编码保持不变，每新增一层在父编码后追加两位 `01–99`；89 个自建节点全部由 `NXT-*` 迁移为 10/12 位编号，83 个标准类型、6 个物料族、259 项实际物料和 81 个类型档案引用同步更新。当前活动目录、物料、类型档案、发布规则和历史规格发布器中的 `NXT-*` 引用为 0；示例为 `1000836401 排水泵用耐磨排水软管`、`1000318501 螺栓`、`100031850101 六角螺栓`。SQLite r7，ERPNext 写入 0。
- GPC 物料层级与命名规范化 v0.3 已完成：259 项实际物料全部统一挂在“标准类型”层，直接挂官方 Brick 的 74 项降为 0；新增 66 个确定性标准类型后共 83 个，“外六角螺栓”档案并入“六角螺栓”，类型档案 82→81，170 个标准名称按“类型→规格→材质/表面→性能等级→结构/供货”统一重排。普通页面不再显示 `NXT-*` 技术键、“非 GPC”徽标或特殊样式，但 259 项均保留数据库/API 隐性来源属性；SQLite r6，ERPNext 写入 0。
- GPC 内部稀疏物料层级 v0.2 已完成：保持 GS1 GPC 6463 个官方节点不变，在宽口径 Brick 下新增 6 个明确标注非 GPC 的内部物料族和 17 个内部标准类型；从“土木行业参考物料表”清洗发布 180 个真实规格组合（紧固件 115、钢筋 65），12 个重复规格合并、41 个不完整或错类行不发布。现有 4 个外六角螺栓同步迁入“螺栓→六角螺栓”，工作台现为 259 项物料、82 个类型档案；SQLite r5、API、网页空目录过滤和 258 项聚焦测试通过，ERPNext 写入 0。
- 参考目录工作台已迁移到本机 SQLite 运行库 v0.1：官方 GPC 6463 节点、1 个明确标注非 GPC 的内部末级、2085 个属性、13733 个属性值、79 项实际物料和 68 个采购类型档案完成事务导入与回读；目录业务表触发器自动推进 revision，页面每 2.5 秒局部刷新。真实 SQL 改名/恢复验证 r1→r2→r3，页面均自动同步且控制台错误 0；JSON/JSONL 保留为导入与兼容备份，ERPNext 写入 0。
- 灭火器箱已从错误的 GPC 10008382 消防设备迁出：在官方 Class 91030300 家庭/企业灭火器下声明 Nexterp 内部末级 NXT-91030300-FIRE-EXT-CABINET（非 GPC），唯一分类属性为“适配灭火器配置”；第 43 行标准化为“双具灭火器箱｜适配2×2 kg手提式灭火器｜不含灭火器”，原错误 Brick 回读物料数 0，官方 GPC 6463 节点保持不变，ERPNext 写入 0。
- 首批 100 行已稀疏发布到本机 GPC 工作台：保留原 8 项并新增 71 项，共 79 项实际物料、68 个类型档案、45 个有物料的官方 Brick 和 1 个有物料的内部末级。经用户确认，第 36/37/45 行工地抽排水软管已从草坪浇水软管 10003254 修正为工业泵配件 10008364；吸水端/出水端分别标明，且保留 GPC 宽口径映射提示。修正记录在发布整理层，冻结审阅文件未覆盖；ERPNext 写入 0。
- 龙华实际采购清单首批 34 个边界聚类已在网页逐项审阅并冻结：确认 14、修订 17、暂缓 2、排除 1；22 个单一 SKU 候选、4 个聚类拆成 8 个实际 SKU 候选、7 个保持 hold；19 条可复用规则已接入 GPC 候选置顶和错误编码拦截。冻结文件绑定源候选与规则目录 SHA-256，范围严格为源表第 2–101 行，第 101–300 条未处理，ERPNext 写入 0。
- 龙华实际采购清单前 100 行批处理试验 v0.1 已完成：100 行/94 个精确不同项压缩为 82 个分析簇，4 次 DeepSeek 调用共 122737 Token，估算 ¥0.142088，形成 8 个既有候选簇、38 个新增类型候选、34 个复核项和 2 个服务项；模型错误 0，历史参考表未使用，ERPNext 写入 0；8788 页面与筛选已回读验证。
- 施工采购模板与稀疏 SKU 框架 v0.1 已建立：固定 10 份主模板和 5 份叠加约束，不按 GPC Brick 人工穷举；当前 8 项黄金样本形成 8 个轻量类型档案，程序校验为 7 个真实组合 SKU 候选和 1 个卷帘项目配置，禁止属性笛卡尔积且未写入 ERPNext。
- GPC 实际物料采用施工采购精简字段门禁：每项只保留采购必选（最多 4 条）、显著价格/适配因素（最多 3 条）和 GPC 分类提示（最多 3 条）；规格依据继续留作运行期审计但不在采购卡重复展示，当前 8 项已按此规则精简，未写入 ERPNext。
- GPC 实际物料挂载保留完整记录门禁：只接受标准类型、完整标准名、库存单位、三组精简字段和规格依据齐全且无待确认问题的物料；原始缺失规格经用户授权按现场最常用可采购规格补齐，不同规格以后新增独立物料。当前 8 项运行期物料均为“已完整录入”，未写入 ERPNext。
- GPC 工作台已支持运行期实际物料候选挂载和空目录过滤：物料只挂到有效 Brick，Brick 详情显示候选卡，祖先节点汇总数量；“隐藏无实际物料目录”保留完整父链并将当前样本收敛为 5 Segment、5 Family、7 Class、8 Brick。候选数据留在 Git 忽略的 `.runtime/material-master/`，未写入 ERPNext。
- 税则浏览器已接入八位税号申报属性详情面板：点击八位税号按需读取申报要素、分类属性、来源页和原文；四位/六位节点保持结构视图，属性接口只读且未写入 ERPNext。
- 涉税规范申报目录 v0.1 已完成：642 页 PDF 解析生成 8,650 条唯一八位申报记录，重复/父级校验 0；局部 25/73/84/85 章任务生成 1,851 条，网页演示与状态 API 已回读验证，未写入 ERPNext。与税则 8,972 个八位叶子匹配 8,649 条（96.3999%），未匹配项保留审计清单，不自动补写属性。
- 税则唯一 xx00 子目与无编码分组提取 v0.5 已完成：271 个唯一六位子目继承完整四位名称，1010 个八位税号补齐分组上下文；编码增删 0、父级变化 0、重复分组 0，250100 盐/纯氯化钠/海水结构已按 PDF 回读；物料族审阅候选因语义补齐由 142 增至 147，新增 5 项均为可解释的橡胶、阀门、电缆候选，仍需人工审核且未写入 ERPNext。
- 税则完整结构浏览器加载遮罩已修复：`.loading-state[hidden]` 强制隐藏，页面回读为 hidden=true、display=none、21 个根节点正常显示；未写入 ERPNext。
- 税则六位层级提取 v0.4 已修复同级兄弟串联、跨页父标题丢失和税率脚注污染：全量仍为 15929 节点、8972 个八位税号、父级变化 0；修正 1761 个六位名称，清理 14 个税率污染名称，400 个跨页风险边界审计失败 0；物料族审阅包及 8788 浏览器已切换到新候选包，未写入 ERPNext。
- 2026 税则完整结构浏览器已接入 8788 工作台：以懒加载树展示 21 类、96 章、1228 个四位品目、5612 个六位子目和 8972 个八位税号，支持逐层展开/折叠、展开到章、全库检索、层级筛选与命中路径定位；只读且不写 ERPNext。
- GPC 2026-05 参考目录已整合到同一工作台：45 Segment、162 Family、938 Class、5318 Brick、2085 个唯一属性和 13733 个唯一属性值；目录名称工作译名完成 6463/6463，Brick 属性与属性值工作译名完成 15818/15818，均保留官方英文且不写 ERPNext。
- GPC 属性术语反向搜索已接入：可按 Attribute/Attribute Value 编码及中英文名称检索，聚合显示 Brick 与属性引用数，并可展开引用位置、跳转到 Brick 后高亮术语；30002654 已回读为“是 / YES”、1062 个 Brick、1963 个属性引用。
- GPC 2026-05 Brick 详情正文已完成全量中文工作译文：Definition/Includes/Excludes 共 15829 个字段实例，按原文 SHA-256 去重为 10004 段并减少 5825 次重复翻译；DeepSeek V4-Flash 37 个请求失败 0、缺失 0、质量检查异常 0。工作台默认显示中文并保留可折叠官方英文，不写 ERPNext。
- 修复 Windows 隐藏/分离启动工作台时 stderr 不可用导致 HTTP 空响应的问题；8788 健康检查、税则审阅页、汇总接口与 73181510 查询均已回读验证，未写入 ERPNext。
- 税则完整层级提取 v0.3 已完成：官方 2026 PDF 1492 页生成 15929 个节点，包含 21 类、96 章、1228 个四位品目、5612 个六位子目和 8972 个八位税号；父级缺失 0、校验问题 0，且八位税号名称与旧基线完全一致，未写入 ERPNext。
- 税则物料族审阅包已基于完整层级重建：八位税号直接父级升级为六位子目，仍为 142 个确定性候选、3 个歧义项、8827 个未映射项；现有人工决定均为空，未覆盖业务审核结果。
- Hash-bound tariff attribute decision template, review-only attribute freeze validator, and family-plus-attribute standard type/SKU candidate compiler added; no ERPNext writes.
- Tariff family review browser now supports local attribute approve/reject/revise decisions and exports a separate tariff_attribute_decisions.tsv; no browser decision is persisted or written to ERPNext.
- Tariff family review browser now merges source-backed attribute evidence, supports attribute-status filtering, and exports the evidence columns with local decisions; server remains read-only.
- {'Fastener tariff attribute review v0.1 generated from the HS 7317/7318/7415 slice': '20 evidence-only rows; all remain review_required, including 73181510 tensile strength >=800 MPa and mixed screw/bolt evidence; no ERPNext writes.'}
- {'Tariff family review v0.1 rules tightened and regenerated': '8,972 rows, 142 deterministic candidates, 3 ambiguous rows, 8,827 unmapped rows, no ERPNext writes.'}
- {'Fastener review slice v0.2 expanded to HS 7317/7318/7415': '20 rows, 16 deterministic candidates and 4 intentionally unmapped rows; mixed 7616-style taxonomy remains review-required.'}
- {'Fastener review slice v0.1 generated for HS 7317/7318': '14 rows, 13 deterministic candidates and 1 intentionally unmapped row, with its own hash-bound decision template.'}
- Tariff family review browser now supports local approve/reject/revise decisions and TSV export; it never persists review state or writes ERPNext.
- {'Tariff family decision workflow v0.1 added': 'generated a 8,972-row blank decision template with candidate SHA-256 binding; explicit approve/reject/revise is required before a review-only frozen release, with no ERPNext writes.'}
- {'Tariff family review v0.1 generated 8,972 review rows from the coordinate-extracted package': '143 deterministic candidates, 1 ambiguous row, 8,828 unmapped rows, and no ERPNext writes.'}
- 税则坐标列提取 v0.2 已完成：复用官方 2026 PDF，1492 页生成 10200 个节点、8972 个 8 位税号，重复编码 0、父级引用缺失 0，未写入 ERPNext。
- Material master v1.1 full rebuild candidate generated from 1979 published SKUs; 1979 rows preserved, 785 types mapped, and audit flags emitted.
- 物料准入闭环 v0.8 已完成：聚焦测试 63 passed，物料模块 127 passed，排除 2 个已知历史断言后快速回归 525 passed。
- 物料批量高召回检索 v0.6 已提交， focused tests 9 passed。
- 物料录入草稿 v0.7 已提交，分析阶段不写 ERPNext。
- OpenClaw 工作台主链已接入材料申请、采购闭环和身份情境层。
- 项目维护 CLI、文档审计、状态快照和交接文档已完成并通过 `check`。
- 历史计划、旧 Runtime 对照实验和旧机器说明已归档；项目 Skill 已安装并通过校验。

## 下一步

- 在物料分类工作台增加“同步 ERPNext 测试账套”按钮：先只读生成 release diff，再由用户确认 release_hash 和 request_id；复用现有 CLI，不开放任意 Site URL 或低层 ToolCall 参数。
- 第 101–300 条保持未处理；只有用户明确开始下一批后，才新建独立任务并应用已冻结的 19 条规则，不能追加或覆盖首批冻结审阅。
- Business reviewer should review the full declaration evidence package and coverage-audit.json; missing tax codes must be checked against the official customs query before any material rule is derived.
- Business reviewer must fill the 20-row tariff_attribute_decisions.tsv and the matching tariff_family_decisions.tsv before compiling any standard type/SKU candidates.
- Business reviewer should use the attribute-status filter to review source evidence, then explicitly confirm the target standard type/SKU attributes before any publish operation.
- Business reviewer should review fastener family and source-backed attribute candidates together before freezing any taxonomy or creating standard types/SKUs.
- Business reviewer should review the expanded fastener slice before adding rules for other material chapters.
- Business reviewer should first review data/material_master/tariff_family_review_v0_1/fastener_review_v0_2 before expanding mappings to other chapters.
- Business reviewer should use the review page or TSV template to approve the first fastener subset, then run the hash-bound freeze command.
- Fill and review tariff_family_decisions.tsv for the business-approved subset; freeze only after reviewer, target family, and source hash checks pass.
- Business-review the tariff family candidate package; only approved rows may enter a frozen Nexterp taxonomy release.
- Review the complete section/chapter/heading/subheading tariff candidate package and map only business-approved nodes to Nexterp internal material families before any publication.
- Review v1.1 audit flags, resolve missing attributes and ambiguous aliases, then explicitly promote the candidate release if business-approved.
- 新 Codex 任务先运行 `resume`，再只读取本次涉及模块的代码、测试和文档。
- 物料准入下一轮真实写入验收必须在员工明确确认测试 Item 后执行，并验证 ERPNext 与运行期目录回读一致。
- 下一业务里程碑优先推进材料申请完整闭环，不横向扩展无关 ToolCall。
- 只有在里程碑边界显式运行长时 LLM/ERPNext 验收，不把外部测试放进日常循环。

## 开发规约

- 先核对 Git 工作区，保留用户未提交改动。
- 只读取本次相关模块的代码、测试和文档；不要遍历全部文档。
- 优先使用 CodeGraph，不可用时使用 `rg` 和 `.runtime/context/repo-map.json`。
- 写操作必须使用员工本人身份、明确确认、幂等 request_id 和执行后回读。
- 不读取或打包 `.env`、`.secrets`、凭据和运行日志。
