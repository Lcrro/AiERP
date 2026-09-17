"""Compare declaration-catalog profiles with the extracted 2026 tariff leaves."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def _codes(path: Path, *, tariff_nodes: bool = False) -> set[str]:
    result: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            code = str(row.get("code") or "")
            if len(code) != 8 or not code.isdigit():
                continue
            if tariff_nodes and row.get("kind") != "sku":
                continue
            result.add(code)
    return result


def audit(profiles_path: Path, tariff_nodes_path: Path, output: Path) -> dict[str, object]:
    profiles = _codes(profiles_path)
    tariff = _codes(tariff_nodes_path, tariff_nodes=True)
    missing = sorted(tariff - profiles)
    extra = sorted(profiles - tariff)
    result: dict[str, object] = {
        "declaration_profiles": len(profiles),
        "tariff_leaf_codes": len(tariff),
        "matched_codes": len(profiles & tariff),
        "coverage_ratio": round(len(profiles & tariff) / len(tariff), 6) if tariff else 0,
        "missing_codes": missing,
        "extra_codes": extra,
        "missing_by_chapter": dict(sorted(Counter(code[:2] for code in missing).items())),
        "notes": [
            "涉税规范申报目录是申报要素证据源，不保证覆盖税则中不需要规范申报要素的每个八位税号。",
            "missing_codes 需在后续物料准入时回到税则原文或官方查询逐项核对，不得自动补写申报属性。",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="核验申报目录与税则八位税号覆盖")
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--tariff-nodes", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.profiles, args.tariff_nodes, args.output)
    print(json.dumps({key: result[key] for key in ("declaration_profiles", "tariff_leaf_codes", "matched_codes", "coverage_ratio")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
