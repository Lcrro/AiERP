"""Normalize workbench material types, hierarchy targets, and display names.

The public workbench treats every actual material as a child of a standard
material type.  Each Nexterp-added hierarchy level appends a two-digit sibling
number to its parent code, while provenance remains an independent attribute.
"""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Iterable, Mapping


STANDARD_TYPE_ALIASES = {
    "外六角螺栓": "六角螺栓",
    "内六角圆柱头螺钉": "内六角螺钉",
    # The historical list did not contain enough evidence to infer a head
    # shape.  Keep the material usable without presenting an unfinished
    # review label to employees; provenance remains in confidence/basis.
    "头型待识别螺栓": "通用螺栓",
    "PPR弯头": "PPR接头",
    "PPR异径三通": "PPR接头",
    "PPR等径三通": "PPR接头",
    "PPR直接接头": "PPR接头",
    "PPR活接头": "PPR接头",
}

PPR_FITTING_KIND_BY_TYPE = {
    "PPR弯头": "弯头",
    "PPR异径三通": "异径三通",
    "PPR等径三通": "等径三通",
    "PPR直接接头": "直接接头",
    "PPR活接头": "活接头",
}

# Every standard type has one business-facing material-family parent.  The
# explicit names keep the hierarchy useful instead of inserting a generic or
# repeated label merely to satisfy a fixed depth.
FAMILY_NAME_BY_BRICK = {
    "10000397": "清扫工具",
    "10000552": "光源",
    "10001102": "雨具",
    "10001394": "施工防护服",
    "10001395": "手部防护用品",
    "10001761": "垃圾收集袋",
    "10002168": "厨房刀具",
    "10002193": "椅凳",
    "10002525": "砌筑块材",
    "10002526": "水泥材料",
    "10003165": "拉紧件",
    "10003167": "绳索",
    "10003179": "锚固件",
    "10003180": "垫圈组件",
    "10003181": "螺钉",
    "10003185": "螺栓",
    "10003455": "测量与找平尺",
    "10003508": "专用扳手",
    "10003547": "泥工抹平工具",
    "10003573": "抹灰承托工具",
    "10003594": "砌筑抹刀",
    "10003644": "角向磨光工具",
    "10003897": "建筑用砂",
    "10003904": "混凝土试验模具",
    "10004024": "截止阀",
    "10004054": "给排水及金属管材",
    "10004057": "管道固定与连接件",
    "10005408": "手提式灭火器",
    "10005541": "低压电线电缆",
    "10005559": "移动式供电插座",
    "10005567": "墙壁插座",
    "10005571": "穿线工具",
    "10005573": "电气接线端子",
    "10005583": "插座安装盒",
    "10005637": "荧光灯配套件",
    "10005651": "电缆束扎件",
    "10006783": "气割工具",
    "10007009": "人造草坪",
    "10007937": "焊接耗材",
    "10008009": "管道连接件",
    "10008013": "遮阳窗帘",
    "10008122": "清扫工具",
    "10008126": "拖地工具",
    "10008163": "建筑用钢材及制品",
    "10008364": "排水泵管路配件",
    "10008424": "切割耗材",
}

# The extinguisher cabinet is intentionally not forced into an inaccurate
# official Brick. It extends the official class with a local Brick-equivalent
# before following the same Brick -> material family -> standard type shape.
INTERNAL_BRICK_NAME_BY_CLASS = {
    "91030300": "灭火器附属设备",
}

FAMILY_NAME_BY_INTERNAL_BRICK = {
    "91030300": "灭火器箱体",
}

FASTENER_TYPE_TERMS = (
    "螺栓",
    "螺钉",
    "锚栓",
    "螺纹杆",
)

_FASTENER_FIELD_ORDER = (
    "procurement_attributes.规格",
    "price_drivers.材质/表面处理",
    "price_drivers.材质/表面",
    "price_drivers.表面处理",
    "procurement_attributes.材质",
    "procurement_attributes.表面处理",
    "procurement_attributes.性能等级",
    "price_drivers.性能/质量等级",
    "price_drivers.性能等级",
    "procurement_attributes.螺纹形式",
    "procurement_attributes.头型/驱动",
    "procurement_attributes.头型",
    "procurement_attributes.供货范围",
    "procurement_attributes.包装",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", _text(value)).casefold()


def canonical_standard_type(value: Any) -> str:
    """Return the user-facing canonical name for a standard material type."""

    name = _text(value)
    return STANDARD_TYPE_ALIASES.get(name, name)


def hierarchical_child_code(parent_code: str, ordinal: int) -> str:
    """Append one two-digit business hierarchy segment to a numeric parent."""

    parent = _text(parent_code)
    if not parent.isdigit() or len(parent) < 8 or len(parent) % 2:
        raise ValueError(f"父级编码必须是至少 8 位的偶数长度数字：{parent}")
    if ordinal < 1 or ordinal > 99:
        raise ValueError(f"同一父级最多允许 99 个直接子级：{parent}")
    return f"{parent}{ordinal:02d}"


def renumber_internal_hierarchy(
    materials: Iterable[Mapping[str, Any]],
    profiles: Iterable[Mapping[str, Any]],
    extensions: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Replace legacy internal keys with parent-plus-two-digit hierarchy codes."""

    material_rows = [deepcopy(dict(row)) for row in materials]
    profile_rows = [deepcopy(dict(row)) for row in profiles]
    extension_rows = [deepcopy(dict(row)) for row in extensions]
    old_codes = [_text(row.get("code")) for row in extension_rows]
    if any(not code for code in old_codes) or len(old_codes) != len(set(old_codes)):
        raise ValueError("内部目录存在空编码或重复编码")
    internal_codes = set(old_codes)
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in extension_rows:
        children_by_parent.setdefault(_text(row.get("parent_code")), []).append(row)

    code_map: dict[str, str] = {}
    pending_parents = [
        parent for parent in children_by_parent
        if parent not in internal_codes
    ]
    visited_parents: set[str] = set()
    while pending_parents:
        old_parent = pending_parents.pop(0)
        if old_parent in visited_parents:
            continue
        visited_parents.add(old_parent)
        new_parent = code_map.get(old_parent, old_parent)
        if not new_parent.isdigit():
            raise ValueError(f"内部目录父级无法转换为数字层级编码：{old_parent}")
        siblings = children_by_parent.get(old_parent, [])
        used: set[int] = set()
        for row in siblings:
            current = _text(row.get("code"))
            if current.startswith(new_parent) and len(current) == len(new_parent) + 2:
                suffix = current[-2:]
                if suffix.isdigit() and 1 <= int(suffix) <= 99 and int(suffix) not in used:
                    code_map[current] = current
                    used.add(int(suffix))
        next_ordinal = 1
        for row in siblings:
            old_code = _text(row.get("code"))
            if old_code not in code_map:
                while next_ordinal in used:
                    next_ordinal += 1
                code_map[old_code] = hierarchical_child_code(new_parent, next_ordinal)
                used.add(next_ordinal)
            if old_code in children_by_parent:
                pending_parents.append(old_code)
    if len(code_map) != len(extension_rows):
        unresolved = sorted(internal_codes - set(code_map))
        raise ValueError(f"内部目录存在缺失父级或循环：{unresolved[:3]}")

    for row in extension_rows:
        old_code = _text(row.get("code"))
        old_parent = _text(row.get("parent_code"))
        row["code"] = code_map[old_code]
        row["parent_code"] = code_map.get(old_parent, old_parent)
        for attribute_index, attribute in enumerate(list(row.get("attributes") or []), start=1):
            attribute["code"] = hierarchical_child_code(row["code"], attribute_index)
            for value_index, value in enumerate(list(attribute.get("values") or []), start=1):
                value["code"] = hierarchical_child_code(attribute["code"], value_index)

    for material in material_rows:
        source = _text(material.get("gpc_brick_code"))
        target = code_map.get(source, source)
        material["gpc_brick_code"] = target
        if _text(material.get("internal_category_code")):
            material["internal_category_code"] = code_map.get(
                _text(material.get("internal_category_code")), target
            )
    for profile in profile_rows:
        source = _text(profile.get("gpc_brick_code"))
        profile["gpc_brick_code"] = code_map.get(source, source)

    encoded = json.dumps(
        {"materials": material_rows, "profiles": profile_rows, "extensions": extension_rows},
        ensure_ascii=False,
    )
    report = {
        "renumbered_internal_node_count": sum(old != new for old, new in code_map.items()),
        "legacy_nxt_reference_count": encoded.count("NXT-"),
        "code_map": code_map,
    }
    return material_rows, profile_rows, extension_rows, report


def prepare_uniform_six_level_hierarchy(
    materials: Iterable[Mapping[str, Any]],
    profiles: Iterable[Mapping[str, Any]],
    extensions: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Insert missing Brick/family parents before deterministic renumbering.

    Official GPC branches already supply the Brick. A standard type directly
    beneath one of those Bricks receives a material-family parent. The one
    approved class-level extension first receives a local Brick-equivalent and
    then a material family, so every standard type ends at semantic level 6.
    """

    material_rows = [deepcopy(dict(row)) for row in materials]
    profile_rows = [deepcopy(dict(row)) for row in profiles]
    extension_rows = [deepcopy(dict(row)) for row in extensions]
    by_code = {_text(row.get("code")): row for row in extension_rows}
    created_bricks = 0
    created_families = 0
    reparented_types = 0

    def add_extension(code: str, parent: str, kind: str, level: int, name: str) -> dict[str, Any]:
        nonlocal created_bricks, created_families
        existing = by_code.get(code)
        if existing is not None:
            return existing
        row = {
            "code": code,
            "parent_code": parent,
            "kind": kind,
            "level": level,
            "working_name": name,
            "definition_working": f"用于归集“{name}”下的标准物料类型。",
            "catalog_origin": "nexterp",
        }
        extension_rows.append(row)
        by_code[code] = row
        if kind == "internal_brick":
            created_bricks += 1
        else:
            created_families += 1
        return row

    direct_types_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in extension_rows:
        if _text(row.get("kind")) != "internal_type":
            continue
        parent = _text(row.get("parent_code"))
        parent_node = by_code.get(parent)
        if parent_node is None or _text(parent_node.get("kind")) != "internal_family":
            direct_types_by_parent.setdefault(parent, []).append(row)

    # Materials that still point at an official node also need the missing
    # hierarchy even when no internal type row has been created yet.
    source_types: dict[str, list[str]] = {}
    for row in (*material_rows, *profile_rows):
        source = _text(row.get("gpc_brick_code"))
        if source and source not in by_code:
            value = canonical_standard_type(row.get("standard_type"))
            if value:
                source_types.setdefault(source, []).append(value)
    for source in source_types:
        direct_types_by_parent.setdefault(source, [])

    for parent_code, type_rows in sorted(direct_types_by_parent.items()):
        family_parent = parent_code
        if parent_code in INTERNAL_BRICK_NAME_BY_CLASS:
            brick_code = f"NXT-AUTO-BRICK-{parent_code}"
            brick = add_extension(
                brick_code,
                parent_code,
                "internal_brick",
                3,
                INTERNAL_BRICK_NAME_BY_CLASS[parent_code],
            )
            family_parent = _text(brick.get("code"))
            family_name = FAMILY_NAME_BY_INTERNAL_BRICK[parent_code]
        else:
            family_name = FAMILY_NAME_BY_BRICK.get(parent_code)
            if not family_name:
                candidate_names = [
                    canonical_standard_type(row.get("working_name")) for row in type_rows
                ] + source_types.get(parent_code, [])
                candidate_names = [value for value in candidate_names if value]
                family_name = f"{candidate_names[0]}类" if candidate_names else "采购物料"
        family_code = f"NXT-AUTO-FAMILY-{parent_code}"
        family_level = int(by_code.get(family_parent, {}).get("level", 3)) + 1
        family = add_extension(
            family_code,
            family_parent,
            "internal_family",
            family_level,
            family_name,
        )
        for row in type_rows:
            if _text(row.get("parent_code")) == _text(family.get("code")):
                continue
            row["parent_code"] = _text(family.get("code"))
            row["level"] = int(family.get("level", 4)) + 1
            reparented_types += 1

    return material_rows, profile_rows, extension_rows, {
        "created_internal_brick_count": created_bricks,
        "created_material_family_count": created_families,
        "reparented_standard_type_count": reparented_types,
    }


def _field_value(material: Mapping[str, Any], field: str) -> str:
    group, _, key = _text(field).partition(".")
    if not group or not key:
        return ""
    return _text(dict(material.get(group) or {}).get(key))


def _clean_fastener_spec(value: str) -> str:
    value = _text(value).replace("*", "×").replace("X", "×")
    if re.match(r"^M\d", value, re.IGNORECASE):
        value = re.sub(r"\s*mm$", "", value, flags=re.IGNORECASE)
    return value


def canonical_fastener_value(value: Any) -> str:
    """Remove review provenance from a fastener's business-facing value.

    Parenthetical phrases such as ``（常用默认）`` describe how the value was
    obtained, not a selectable SKU property.  Keeping them in the selector
    creates false options (for example both ``4.8级`` and
    ``4.8级（常用默认）``).  The source basis and confidence fields continue to
    retain that provenance.
    """

    text = _text(value)
    text = re.sub(
        r"[（(](?:同系列)?常用默认[）)]",
        "",
        text,
    ).strip()
    if text == "按原表成套供货":
        return "成套供货"
    return text


def _canonicalize_fastener_fields(material: dict[str, Any]) -> int:
    changed = 0
    for group in ("procurement_attributes", "price_drivers"):
        values = dict(material.get(group) or {})
        for key, value in list(values.items()):
            canonical = canonical_fastener_value(value)
            if canonical != _text(value):
                values[key] = canonical
                changed += 1
        material[group] = values
    attributes = dict(material.get("procurement_attributes") or {})
    basis = _text(material.get("specification_basis"))
    supply_scope = _text(attributes.get("供货范围"))
    if supply_scope == "成套供货" and any(term in basis for term in ("螺母", "螺帽", "平垫", "弹垫")):
        explicit_scope = "成套供货（含螺母及垫圈）"
        if explicit_scope != supply_scope:
            attributes["供货范围"] = explicit_scope
            material["procurement_attributes"] = attributes
            changed += 1
    return changed


def _append_unique(parts: list[str], value: Any) -> None:
    text = _text(value)
    if not text:
        return
    normalized = _normalized(text)
    if not normalized or any(_normalized(part) == normalized for part in parts):
        return
    parts.append(text)


def _display_identity_value(field: str, value: str) -> str:
    if field.endswith(".公称直径"):
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*mm", _text(value), re.IGNORECASE)
        if match:
            return f"Φ{match.group(1)}"
    return _text(value)


def _covered_by_parts(value: str, parts: Iterable[str]) -> bool:
    normalized = _normalized(value)
    if not normalized:
        return True
    candidates = [_normalized(part) for part in parts if _normalized(part)]
    if any(normalized in candidate or candidate in normalized for candidate in candidates):
        return True
    if len(normalized) >= 4 and any(
        len(candidate) >= 4 and normalized[:2] == candidate[:2] for candidate in candidates
    ):
        return True
    return sum(candidate in normalized for candidate in candidates if len(candidate) >= 2) >= 2


def _visible_classification_notes(material: Mapping[str, Any], standard_type: str) -> list[str]:
    notes = [f"归入“{standard_type}”标准类型"]
    original = [_text(value) for value in (material.get("gpc_notes") or [])]
    if any("宽口径" in value for value in original):
        notes.append("参考目录为宽口径映射，具体采购语义以标准类型为准")
    for value in original:
        if any(term in value for term in ("NXT-", "非 GPC", "非GPC", "Nexterp", "GPC Brick", "GPC 边界")):
            continue
        _append_unique(notes, value)
        if len(notes) >= 3:
            break
    return notes


def _sanitize_basis(value: Any) -> str:
    text = _text(value)
    text = re.sub(r"NXT-[A-Z0-9-]+", "", text)
    for old in (
        "非GPC内部类目",
        "非 GPC 内部类目",
        "Nexterp内部末级类目",
        "Nexterp 内部末级类目",
        "Nexterp内部类目",
        "Nexterp 内部类目",
    ):
        text = text.replace(old, "物料标准类型")
    return re.sub(r"\s{2,}", " ", text).strip()


def canonical_material_name(
    material: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
) -> str:
    """Build a deterministic name with the standard type in the first slot.

    Standard types share the same field order.  Fasteners additionally keep
    material/surface and performance grade in a fixed position, so grades such
    as 4.8 and 8.8 can never drift between the start and end of similar names.
    """

    standard_type = canonical_standard_type(material.get("standard_type"))
    if not standard_type:
        return _text(material.get("material_name"))
    parts = [standard_type]
    if standard_type == "PPR接头":
        for field in (
            "procurement_attributes.接头类型",
            "procurement_attributes.规格",
            "procurement_attributes.公称压力",
        ):
            _append_unique(parts, _field_value(material, field))
        return "｜".join(parts)
    if any(term in standard_type for term in FASTENER_TYPE_TERMS):
        for field in _FASTENER_FIELD_ORDER:
            value = _field_value(material, field)
            if field == "procurement_attributes.规格":
                value = _clean_fastener_spec(value)
            _append_unique(parts, value)
        return "｜".join(parts)

    identity_fields = list(dict(profile or {}).get("sku_identity_fields") or [])
    if not identity_fields:
        identity_fields = [
            f"procurement_attributes.{key}"
            for key in dict(material.get("procurement_attributes") or {})
        ]
    for field in identity_fields:
        _append_unique(parts, _display_identity_value(_text(field), _field_value(material, _text(field))))
    # Preserve concise facts that were present in an already-reviewed name but
    # were accidentally omitted from its type profile (for example a 45° elbow
    # angle or a supplied support frame).  The standard type itself remains the
    # first slot and duplicated identity values are not repeated.
    old_name_parts = [_text(value) for value in _text(material.get("material_name")).split("｜")]
    for value in old_name_parts[1:]:
        if not _covered_by_parts(value, parts):
            _append_unique(parts, value)
    return "｜".join(parts)


def normalize_workbench_catalog(
    materials: Iterable[Mapping[str, Any]],
    profiles: Iterable[Mapping[str, Any]],
    extensions: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return a fully typed hierarchy without mutating the supplied rows."""

    prepared_materials, prepared_profiles, prepared_extensions, hierarchy_report = (
        prepare_uniform_six_level_hierarchy(materials, profiles, extensions)
    )
    material_rows, profile_rows, extension_rows, numbering_report = renumber_internal_hierarchy(
        prepared_materials, prepared_profiles, prepared_extensions
    )
    for row in extension_rows:
        row.setdefault("catalog_origin", "nexterp")
        for field in ("definition_working", "includes_working", "excludes_working"):
            value = _text(row.get(field))
            value = value.replace("Nexterp 内部物料族", "物料族")
            value = value.replace("Nexterp 内部", "")
            row[field] = value
    extension_by_code = {_text(row.get("code")): row for row in extension_rows}
    type_by_parent_name: dict[tuple[str, str], str] = {}
    type_code_redirects: dict[str, str] = {}
    for row in sorted(extension_rows, key=lambda item: _text(item.get("code"))):
        if _text(row.get("kind")) != "internal_type":
            continue
        code = _text(row.get("code"))
        canonical_type = canonical_standard_type(row.get("working_name"))
        row["working_name"] = canonical_type
        key = (_text(row.get("parent_code")), canonical_type)
        keeper = type_by_parent_name.setdefault(key, code)
        if keeper != code:
            type_code_redirects[code] = keeper
    profile_by_id = {_text(row.get("profile_id")): row for row in profile_rows}
    target_by_source_type: dict[tuple[str, str], str] = {}
    created_codes: list[str] = []
    migrated_materials = 0
    renamed_materials = 0
    canonicalized_fastener_value_count = 0

    def family_parent_code(source_code: str) -> str:
        family_name = FAMILY_NAME_BY_BRICK.get(source_code)
        if not family_name:
            return source_code
        for row in extension_rows:
            if (
                _text(row.get("kind")) == "internal_family"
                and _text(row.get("parent_code")) == source_code
                and _text(row.get("working_name")) == family_name
            ):
                return _text(row.get("code"))
        return source_code

    def next_child_code(parent_code: str) -> str:
        used = {
            int(_text(row.get("code"))[-2:])
            for row in extension_rows
            if _text(row.get("parent_code")) == parent_code
            and _text(row.get("code")).startswith(parent_code)
            and len(_text(row.get("code"))) == len(parent_code) + 2
            and _text(row.get("code"))[-2:].isdigit()
        }
        for ordinal in range(1, 100):
            if ordinal not in used:
                return hierarchical_child_code(parent_code, ordinal)
        raise ValueError(f"同一父级已达到 99 个直接子级：{parent_code}")

    def target_code(source_code: str, standard_type: str) -> str:
        canonical_type = canonical_standard_type(standard_type)
        source_node = extension_by_code.get(source_code)
        if source_node and _text(source_node.get("kind")) == "internal_type":
            return type_code_redirects.get(source_code, source_code)
        parent_code = family_parent_code(source_code)
        existing = type_by_parent_name.get((parent_code, canonical_type))
        if existing:
            return existing
        code = next_child_code(parent_code)
        if code not in extension_by_code:
            parent_level = int(extension_by_code.get(parent_code, {}).get("level", 3))
            row = {
                "code": code,
                "parent_code": parent_code,
                "kind": "internal_type",
                "level": parent_level + 1,
                "working_name": canonical_type,
                "definition_working": f"用于归集“{canonical_type}”的实际采购规格。",
                "includes_working": "",
                "excludes_working": "",
                "catalog_origin": "nexterp",
            }
            extension_rows.append(row)
            extension_by_code[code] = row
            created_codes.append(code)
        type_by_parent_name[(parent_code, canonical_type)] = code
        return code

    for material in material_rows:
        source_code = _text(material.get("gpc_brick_code"))
        old_type = _text(material.get("standard_type"))
        canonical_type = canonical_standard_type(old_type)
        target = target_code(source_code, canonical_type)
        target_by_source_type[(source_code, canonical_type)] = target
        if target != source_code:
            migrated_materials += 1
        material["standard_type"] = canonical_type
        material["gpc_brick_code"] = target
        material["classification_source"] = "nexterp_internal"
        material["internal_category_code"] = target
        if canonical_type == "PPR接头":
            attributes = dict(material.get("procurement_attributes") or {})
            prices = dict(material.get("price_drivers") or {})
            fitting_kind = PPR_FITTING_KIND_BY_TYPE.get(old_type)
            if fitting_kind:
                attributes["接头类型"] = fitting_kind
            if fitting_kind == "弯头" and not _text(attributes.get("角度")):
                angle = re.search(r"\b(\d+(?:\.\d+)?)\s*°", _text(material.get("material_name")))
                if angle:
                    attributes["角度"] = f"{angle.group(1)}°"
            diameter = _text(attributes.pop("公称直径", ""))
            main_diameter = _text(attributes.pop("主管直径", ""))
            branch_diameter = _text(attributes.pop("支管直径", ""))
            angle_value = _text(attributes.pop("角度", ""))
            specification_parts = [value for value in (main_diameter or diameter, branch_diameter, angle_value) if value]
            if specification_parts:
                attributes["规格"] = "×".join(specification_parts)
            # PPR 水管接头的介质和材质由标准类型表达，不应挤占施工
            # 采购界面最多四个必选属性；材质仍保留为价格/适配信息。
            attributes.pop("介质", None)
            material_value = _text(attributes.pop("材质", ""))
            prices.setdefault("材质", material_value or "PPR")
            material["procurement_attributes"] = attributes
            material["price_drivers"] = prices
        if any(term in canonical_type for term in FASTENER_TYPE_TERMS):
            canonicalized_fastener_value_count += _canonicalize_fastener_fields(material)
        if canonical_type == "六角螺栓":
            attributes = dict(material.get("procurement_attributes") or {})
            prices = dict(material.get("price_drivers") or {})
            attributes.setdefault("供货范围", "单件")
            thread_form = _text(attributes.pop("螺纹形式", ""))
            if thread_form and thread_form not in _text(attributes.get("规格")):
                attributes["规格"] = f"{_text(attributes.get('规格'))}（{thread_form}）"
            surface = _text(prices.pop("表面处理", ""))
            if surface:
                prices.setdefault("材质/表面处理", surface)
            grade = _text(attributes.pop("性能等级", ""))
            if grade:
                prices.setdefault("性能/质量等级", grade)
            prices.pop("质量要求", None)
            material["procurement_attributes"] = attributes
            material["price_drivers"] = prices
        if canonical_type == "内六角螺钉":
            attributes = dict(material.get("procurement_attributes") or {})
            prices = dict(material.get("price_drivers") or {})
            attributes["规格"] = _clean_fastener_spec(attributes.get("规格"))
            attributes.setdefault("头型", "圆柱头")
            attributes.setdefault("供货范围", "单件")
            grade = _text(attributes.pop("性能等级", "")) or _text(prices.pop("性能等级", ""))
            if grade:
                prices.setdefault("性能/质量等级", grade)
            surface = (
                _text(prices.pop("材质/表面", ""))
                or _text(prices.pop("表面处理", ""))
            )
            if surface:
                prices.setdefault("材质/表面处理", surface)
            prices.pop("质量要求", None)
            material["procurement_attributes"] = attributes
            material["price_drivers"] = prices
        material["gpc_notes"] = _visible_classification_notes(material, canonical_type)
        material["specification_basis"] = _sanitize_basis(material.get("specification_basis"))
        old_name = _text(material.get("material_name"))
        material["material_name"] = canonical_material_name(
            material,
            profile_by_id.get(_text(material.get("procurement_profile_id"))),
        )
        if material["material_name"] != old_name:
            renamed_materials += 1

    for profile in profile_rows:
        source_code = _text(profile.get("gpc_brick_code"))
        canonical_type = canonical_standard_type(profile.get("standard_type"))
        target = target_by_source_type.get((source_code, canonical_type)) or target_code(source_code, canonical_type)
        profile["standard_type"] = canonical_type
        profile["gpc_brick_code"] = target

    # Aliases can make two historical profiles converge on one business type
    # (notably 外六角螺栓 -> 六角螺栓).  Keep the profile with the widest source
    # coverage, merge its governance fields, and repoint every material.
    grouped_profiles: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for profile in profile_rows:
        key = (_text(profile.get("gpc_brick_code")), _text(profile.get("standard_type")))
        grouped_profiles.setdefault(key, []).append(profile)
    merged_profiles: list[dict[str, Any]] = []
    profile_redirects: dict[str, str] = {}
    merged_profile_count = 0
    for rows in grouped_profiles.values():
        keeper = max(
            rows,
            key=lambda row: (
                len(list(row.get("source_material_ids") or [])),
                _text(row.get("status")) == "golden",
                _text(row.get("profile_id")),
            ),
        )
        keeper_id = _text(keeper.get("profile_id"))
        for field in ("constraint_ids", "source_material_ids"):
            keeper[field] = list(dict.fromkeys(
                _text(value)
                for row in rows
                for value in (row.get(field) or [])
                if _text(value)
            ))
        if any(_text(row.get("status")) == "golden" for row in rows):
            keeper["status"] = "golden"
        if _text(keeper.get("standard_type")) == "内六角螺钉":
            keeper["sku_identity_fields"] = [
                "procurement_attributes.规格",
                "procurement_attributes.头型",
                "procurement_attributes.供货范围",
                "price_drivers.材质/表面处理",
                "price_drivers.性能/质量等级",
            ]
            keeper["transaction_fields"] = []
            keeper["offer_fields"] = []
        if _text(keeper.get("standard_type")) == "PPR接头":
            keeper["sku_identity_fields"] = [
                "procurement_attributes.接头类型",
                "procurement_attributes.规格",
                "procurement_attributes.公称压力",
                "price_drivers.材质",
            ]
        for row in rows:
            old_id = _text(row.get("profile_id"))
            if old_id != keeper_id:
                profile_redirects[old_id] = keeper_id
                merged_profile_count += 1
        merged_profiles.append(keeper)
    profile_rows = sorted(merged_profiles, key=lambda row: _text(row.get("profile_id")))
    for material in material_rows:
        profile_id = _text(material.get("procurement_profile_id"))
        if profile_id in profile_redirects:
            material["procurement_profile_id"] = profile_redirects[profile_id]

    if type_code_redirects:
        extension_rows = [
            row for row in extension_rows
            if _text(row.get("code")) not in type_code_redirects
        ]

    report = {
        "material_count": len(material_rows),
        "profile_count": len(profile_rows),
        "merged_profile_count": merged_profile_count,
        "created_standard_type_count": len(created_codes),
        "migrated_material_count": migrated_materials,
        "renamed_material_count": renamed_materials,
        "canonicalized_fastener_value_count": canonicalized_fastener_value_count,
        "direct_gpc_material_count": sum(
            _text(row.get("gpc_brick_code")) not in extension_by_code for row in material_rows
        ),
        "private_origin_tag_count": sum(
            _text(row.get("classification_source")) == "nexterp_internal" for row in material_rows
        ),
        "renumbered_internal_node_count": numbering_report["renumbered_internal_node_count"],
        **hierarchy_report,
        "legacy_nxt_reference_count": json.dumps(
            {"materials": material_rows, "profiles": profile_rows, "extensions": extension_rows},
            ensure_ascii=False,
        ).count("NXT-"),
        "code_map": numbering_report["code_map"],
    }
    return material_rows, profile_rows, extension_rows, report


__all__ = [
    "FAMILY_NAME_BY_BRICK",
    "STANDARD_TYPE_ALIASES",
    "canonical_material_name",
    "canonical_fastener_value",
    "canonical_standard_type",
    "hierarchical_child_code",
    "normalize_workbench_catalog",
    "prepare_uniform_six_level_hierarchy",
    "renumber_internal_hierarchy",
]
