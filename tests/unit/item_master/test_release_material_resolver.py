from __future__ import annotations

from nexterp_agent.item_master.release_resolver import ReleaseMaterialResolver


def test_exact_item_code_resolves_ready() -> None:
    resolver = ReleaseMaterialResolver()

    result = resolver.resolve("SAFE-000005")

    assert result["status"] == "ready"
    assert result["resolved"]["item_code"] == "SAFE-000005"
    assert result["resolved"]["stock_uom"] == "双"


def test_canvas_glove_returns_candidates_instead_of_guessing() -> None:
    resolver = ReleaseMaterialResolver()

    result = resolver.resolve("帆布手套")

    assert result["status"] == "needs_confirmation"
    assert result["resolved"] is None
    codes = {candidate["item_code"] for candidate in result["candidates"]}
    assert {"SAFE-000096", "SAFE-000005", "SAFE-000001"} <= codes
    assert result["questions"]


def test_68_bolt_with_size_requires_explicit_confirmation() -> None:
    resolver = ReleaseMaterialResolver()

    result = resolver.resolve("6.8级螺栓 M12*40")

    assert result["status"] == "needs_confirmation"
    assert result["resolved"] is None
    assert result["candidates"][0]["item_code"] == "SPARE-000071-68"


def test_88_bolt_with_size_requires_explicit_confirmation() -> None:
    resolver = ReleaseMaterialResolver()

    result = resolver.resolve("8.8级螺栓 M12*40")

    assert result["status"] == "needs_confirmation"
    assert result["resolved"] is None
    assert result["candidates"][0]["item_code"] == "SPARE-000071"


def test_generic_bolt_does_not_auto_select() -> None:
    resolver = ReleaseMaterialResolver()

    result = resolver.resolve("螺栓")

    assert result["status"] == "needs_clarification"
    assert result["resolved"] is None
    assert "补充" in result["questions"][0]


def test_removed_ordinary_bolt_name_is_not_auto_selected() -> None:
    resolver = ReleaseMaterialResolver()

    result = resolver.resolve("普通螺栓")

    assert result["status"] in {"not_found", "needs_clarification"}
    assert result["resolved"] is None


def test_unknown_material_enters_not_found_flow() -> None:
    resolver = ReleaseMaterialResolver()

    result = resolver.resolve("星际泡泡机")

    assert result["status"] == "not_found"
    assert result["resolved"] is None
    assert "新增物料" in result["questions"][0]
