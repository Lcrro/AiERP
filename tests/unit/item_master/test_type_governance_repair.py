from __future__ import annotations

import csv
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts" / "material_master"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_type_dictionary_governance import (  # noqa: E402
    build_generation_messages,
    load_repair_feedback,
    repair_batch_id,
)
from nexterp_agent.item_master.type_governance import (  # noqa: E402
    build_family_evidence,
    pack_family_batches,
)


def _batch():
    rows = [
        {
            "item_code": "FAST-001",
            "item_name": "螺栓",
            "sku_name": "螺栓 M8x40",
            "required_specs": "规格：M8x40",
            "optional_specs": "",
            "aliases": "螺丝",
            "stock_uom": "个",
            "top_group": "紧固件与连接件",
            "material_family": "螺丝/螺栓",
        }
    ]
    return pack_family_batches(build_family_evidence(rows))[0]


def test_load_repair_feedback_keeps_actionable_sku_reviews(tmp_path: Path) -> None:
    output_dir = tmp_path
    issue_path = output_dir / "material_governance_issues.tsv"
    fields = [
        "issue_id",
        "batch_id",
        "top_group",
        "material_family",
        "current_name",
        "item_code",
        "issue_type",
        "severity",
        "detail",
        "status",
    ]
    rows = [
        ["1", "B", "紧固件与连接件", "螺丝/螺栓", "螺栓", "", "type_review_not_approved", "high", "边界重叠", "open"],
        ["2", "B", "紧固件与连接件", "螺丝/螺栓", "螺栓", "FAST-001", "sku_mapping_unresolved", "high", "未映射", "open"],
        ["4", "B", "紧固件与连接件", "螺丝/螺栓", "螺栓", "FAST-001", "detailed_mapping_not_approved", "high", "置信度不足", "open"],
        ["3", "B", "紧固件与连接件", "螺丝/螺栓", "螺栓", "", "old", "low", "已解决", "resolved"],
    ]
    with issue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)

    feedback = load_repair_feedback(output_dir)

    assert feedback == {
        ("紧固件与连接件", "螺丝/螺栓"): [
            {
                "issue_type": "type_review_not_approved",
                "current_name": "螺栓",
                "item_code": "",
                "detail": "边界重叠",
            },
            {
                "issue_type": "detailed_mapping_not_approved",
                "current_name": "螺栓",
                "item_code": "FAST-001",
                "detail": "置信度不足",
            }
        ]
    }


def test_repair_feedback_is_disclosed_in_generation_prompt() -> None:
    batch = _batch()
    feedback = {
        ("紧固件与连接件", "螺丝/螺栓"): [
            {
                "issue_type": "type_review_not_approved",
                "current_name": "螺栓",
                "detail": "边界重叠",
            }
        ]
    }

    messages = build_generation_messages(batch, feedback)

    assert "问题闭环修订" in messages[0]["content"]
    assert "边界重叠" in messages[1]["content"]


def test_final_convergence_prompts_require_neutral_fallbacks() -> None:
    batch = _batch()
    feedback = {
        ("紧固件与连接件", "螺丝/螺栓"): [
            {
                "issue_type": "type_review_not_approved",
                "current_name": "螺栓",
                "detail": "缺少头型证据",
            }
        ]
    }

    generation_messages = build_generation_messages(
        batch,
        feedback,
        final_convergence=True,
    )

    assert "中性、宽泛但真实" in generation_messages[0]["content"]
    assert '"final_convergence": true' in generation_messages[1]["content"]


def test_repair_batch_id_changes_with_review_feedback() -> None:
    batch = _batch()
    first = {
        ("紧固件与连接件", "螺丝/螺栓"): [
            {"issue_type": "review", "current_name": "螺栓", "detail": "边界重叠"}
        ]
    }
    second = {
        ("紧固件与连接件", "螺丝/螺栓"): [
            {"issue_type": "review", "current_name": "螺栓", "detail": "缺少头型"}
        ]
    }

    assert repair_batch_id(batch, first) == repair_batch_id(batch, first)
    assert repair_batch_id(batch, first) != repair_batch_id(batch, second)
    assert repair_batch_id(batch, first) != repair_batch_id(
        batch,
        first,
        mode="final_convergence",
    )
