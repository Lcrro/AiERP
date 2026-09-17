# 涉税规范申报目录证据源 v0.1

## 目的

Nexterp 现在把《中华人民共和国海关进出口商品涉税规范申报目录（2026年版）》作为税则结构之外的第二个、只读证据源。税则 PDF 负责 21 类 → 96 章 → 四位品目 → 六位子目 → 八位税号的法定父子关系；本目录负责在八位税号上补充归类要素、申报要素和来源页码。

这两个来源不互相改写。目录中的“其他”保持原文值，不根据名称猜测具体商品，也不把商业网站的改写名称覆盖官方文本。

## 生成方式

```powershell
python scripts/material_master/extract_tariff_declaration_catalog.py `
  --input .runtime/tariff-declaration/source/customs-declaration-catalog-2026.pdf `
  --output .runtime/tariff-declaration/<job-id>/tariff-declaration-profiles.jsonl

python scripts/material_master/audit_tariff_declaration_coverage.py `
  --profiles .runtime/tariff-declaration/<job-id>/tariff-declaration-profiles.jsonl `
  --tariff-nodes .runtime/tariff-extraction/<release>/tariff-nodes.jsonl `
  --output .runtime/tariff-declaration/<job-id>/coverage-audit.json
```

工作台入口是 `/tariff-declaration-lab`，支持演示、局部章节（例如 `25,73,84,85`）和全量模式。局部模式仍完整读取 PDF，再按章节过滤，因此不会破坏跨页父级上下文。

税则完整结构浏览器 `/tariff-taxonomy-browser` 已接入详情面板：点击八位税号才按需请求 `/api/tariff-declaration/profile?code=...`，显示分类属性、完整申报要素、来源页和原文。四位/六位节点不会加载大字段；没有目录记录的税号显示“未覆盖”，不会被自动补齐。

## JSONL 字段

| 字段 | 含义 |
| --- | --- |
| `code` | 八位税号，去掉点号后的稳定键 |
| `name` | 目录中该八位税号的原文名称；例如 `25059000` 仍为“其他” |
| `heading_code` / `subheading_code` | 从八位税号前缀推导的四位/六位代码 |
| `heading_name` | 四位品目原文标题 |
| `hierarchy_path` | 目录中位于该税号前的带短横线分组标题 |
| `declaration_attributes` | 原始申报要素，包含品牌、型号等完整字段 |
| `classification_attributes` | 去除品牌/型号等价格或识别字段后的保守分类字段；不是法律结论 |
| `page` | PDF 页码（从 1 开始） |
| `source_text` | 该行的原始文本证据 |

解析器保留跨页状态，并会修复 PDF 的中文断行，例如把“抗拉强度在800兆帕及以 / 上”还原为“抗拉强度在800兆帕及以上”。每个输出包的 `manifest.json` 记录 SHA-256、页数、模式、过滤章节、问题数及 `erpnext_written: false`。

## 覆盖解释

2026 目录全量解析得到 8,650 条唯一八位申报记录；与当前税则结构的 8,972 个八位叶子对照，匹配 8,649 条，覆盖率 96.3999%。这不是解析器把剩余税号“漏掉”的结论：规范申报目录本身只对需要规范申报要素的范围提供记录，未匹配税号必须回到税则原文或海关官方查询逐项确认，禁止自动补写属性。

## 安全边界

- 该流程只写入 `.runtime/tariff-declaration/<job-id>/`，不写 ERPNext、不创建物料、不冻结分类。
- 任何标准类型/SKU 仍须经过物料准入草稿、人工确认、幂等请求和 ERPNext 回读验证。
- 商业查询站点可用于人工交叉检查，但其名称、税率和 CIQ 信息不作为 Nexterp 的权威写入源。
