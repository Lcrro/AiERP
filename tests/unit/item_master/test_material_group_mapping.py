import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "export_material_group_mapping.py"
SPEC = importlib.util.spec_from_file_location("export_material_group_mapping", SCRIPT_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
canonicalize = module.canonicalize


def test_ppe_glove_aliases_share_canonical_group() -> None:
    left = canonicalize("劳保耗材/手套")
    right = canonicalize("劳保用品/手套")

    assert left.canonical_group_path == "劳保用品/手部防护/手套"
    assert right.canonical_group_path == left.canonical_group_path
    assert not left.needs_human_review


def test_manual_tool_structures_are_merged() -> None:
    generic = canonicalize("工具/手动工具")
    wrench = canonicalize("手动工具/扳手")

    assert generic.canonical_group_path == "工具器具/手动工具/通用手动工具"
    assert wrench.canonical_group_path == "工具器具/手动工具/扳手"
    assert wrench.confidence >= 0.9


def test_breakers_roll_up_under_low_voltage_electrical() -> None:
    parent = canonicalize("电气材料/低压电器")
    breaker = canonicalize("电气/断路器")

    assert parent.canonical_group_path == "电气与自动化/低压电器/低压电器"
    assert breaker.canonical_group_path == "电气与自动化/低压电器/断路器"
    assert breaker.canonical_level2 == parent.canonical_level2


def test_high_risk_lifting_group_requires_review() -> None:
    row = canonicalize("吊装索具/卸扣")

    assert row.canonical_group_path == "吊装索具/吊装连接件/卸扣吊钩"
    assert row.needs_human_review
