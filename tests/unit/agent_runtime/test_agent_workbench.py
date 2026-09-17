from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from nexterp_agent.erpnext.schemas import ToolResult
from nexterp_agent.item_master import (
    HighRecallBatchResult,
    MaterialIntakeDecision,
    MaterialTypeClassifier,
    RuntimeMaterialPublicationStore,
    build_material_drafts,
)


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "agent_workbench.py"
SPEC = importlib.util.spec_from_file_location("agent_workbench", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_employee_catalog_does_not_expose_credentials() -> None:
    employees = MODULE.employee_catalog()

    assert len(employees) == 8
    assert all("api_key" not in employee and "api_secret" not in employee for employee in employees)
    assert {employee["employee_name"] for employee in employees} >= {"张振光", "潘丰", "毛晓泉", "胡银虎", "方文倩"}


def test_runtime_explorer_is_served_from_a_separate_auditable_page() -> None:
    html = MODULE.RUNTIME_EXPLORER_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "runtime-explorer.js").read_text(encoding="utf-8")

    assert "Agent 运行剖面" in html
    assert 'id="flowMap"' in html
    assert 'id="traceTimeline"' in html
    assert 'id="diagnosis"' in html
    assert "/api/session?" in script
    assert "不包含模型隐藏思维过程" in script
    assert "renderDiagnosis" in script


def test_runtime_compare_page_is_preview_only_and_shows_both_runtimes() -> None:
    html = MODULE.RUNTIME_COMPARE_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "runtime-compare.js").read_text(encoding="utf-8")

    assert "Agent Runtime 对比实验" in html
    assert "现有 Nexterp Runtime" in html
    assert "OpenClaw 说明书 Runtime" in html
    assert "禁止写入 ERPNext" in html
    assert 'id="includeExisting"' in html
    assert "小助理正在处理" in html
    assert "/api/agent-runtime/compare" in script
    assert "loaded_nodes" in script
    assert "include_existing" in script
    assert "progressPhases" in script


def test_material_item_lab_exposes_safe_preview_flow() -> None:
    html = MODULE.MATERIAL_ITEM_LAB_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "material-item-lab.js").read_text(encoding="utf-8")

    assert "标准物料建档实验室" in html
    assert "/api/agent/turn/start" in script
    assert "/api/agent/confirm" in script
    assert "needs_confirmation" in script
    assert "确认创建" in html


def test_material_intake_lab_exposes_four_queue_batch_preview() -> None:
    html = MODULE.MATERIAL_INTAKE_LAB_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "material-intake-lab.js").read_text(encoding="utf-8")

    assert "采购清单物料准入实验室" in html
    assert "分析不写入，确认后发布并回读" in html
    assert "/api/material-intake/analyze" in script
    assert all(queue in html + script for queue in ("existing_sku", "new_sku", "new_type", "needs_input"))
    assert "draft_updates" in script
    assert "request_id" in script
    assert "ERPNext 回读一致" in script
    assert "创建标准类型及首个 SKU" in script


def test_material_marketplace_exposes_catalogue_and_safe_handoff() -> None:
    html = MODULE.MATERIAL_MARKETPLACE_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "material-marketplace.js").read_text(encoding="utf-8")
    stylesheet = (MODULE.ASSET_DIR / "material-marketplace.css").read_text(encoding="utf-8")

    assert "物料商城" in html
    assert "采购申请清单" in html
    assert "物料采购申请" in html
    assert "请选择你要申请采购的物料" in html
    assert "已审核物料" not in html
    assert "categoryTree" in script and "data-toggle-category" in script
    assert "不会直接写入 ERPNext" in html
    assert "/api/material-marketplace/catalog" in script
    assert "nexterp.material-marketplace.handoff" in script
    assert "不要自动提交" in script
    assert ".product-grid" in stylesheet and ".request-panel" in stylesheet


def test_material_marketplace_service_bounds_page_and_keeps_catalog_read_only() -> None:
    calls: list[dict[str, object]] = []

    class FakeIndex:
        def material_catalog(self, **kwargs):
            calls.append(kwargs)
            return {"rows": [{"material_id": "MAT-1"}], "total": 1, "offset": kwargs["offset"], "limit": kwargs["limit"]}

    service = object.__new__(MODULE.AgentWorkbenchService)
    service._gpc_reference_index = lambda: FakeIndex()
    payload = service.material_marketplace_catalog(page=2, page_size=500, query="螺栓")

    assert calls == [{
        "query": "螺栓",
        "segment_code": "",
        "category_code": "",
        "standard_type": "",
        "stock_uom": "",
        "sort": "name",
        "offset": 60,
        "limit": 60,
    }]
    assert payload["rows"][0]["material_id"] == "MAT-1"
    assert payload["price_status"] == "not_maintained"
    assert payload["stock_status"] == "query_on_request"


def test_chatgpt_classification_catalog_is_switchable_and_read_only(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "chatgpt-browser.json"
    snapshot_path.write_text(json.dumps({
        "release_hash": "test-release",
        "summary": {"sku_count": 2, "material_family_count": 1, "top_group_count": 1},
        "rows": [
            {
                "item_code": "MAT0001-V001",
                "material_id": "MAT0001-V001",
                "material_family": "测试接头",
                "material_name": "测试接头｜DN20",
                "standard_type": "测试接头",
                "segment_code": "CHATGPT-L1-管件",
                "segment_name": "管件",
                "category_code": "CHATGPT-L2-管件|PPR",
                "top_group": "管件",
                "sub_group": "PPR",
                "family_code": "MAT0001",
                "stock_uom": "个",
                "search_text": "mat0001-v001 测试接头 dn20",
                "procurement_attributes": {"规格": "DN20"},
                "price_drivers": {"规格": "DN20"},
                "classification_path": [{"code": "CHATGPT-L1-管件", "name": "管件"}],
            },
            {
                "item_code": "MAT0001-V002",
                "material_id": "MAT0001-V002",
                "material_family": "测试接头",
                "material_name": "测试接头｜DN25",
                "standard_type": "测试接头",
                "segment_code": "CHATGPT-L1-管件",
                "segment_name": "管件",
                "category_code": "CHATGPT-L2-管件|PPR",
                "top_group": "管件",
                "sub_group": "PPR",
                "family_code": "MAT0001",
                "stock_uom": "个",
                "search_text": "mat0001-v002 测试接头 dn25",
                "procurement_attributes": {"规格": "DN25"},
                "price_drivers": {"规格": "DN25"},
                "classification_path": [{"code": "CHATGPT-L1-管件", "name": "管件"}],
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    server_module = sys.modules[MODULE.AgentWorkbenchService.__module__]
    monkeypatch.setattr(server_module, "CHATGPT_CLASSIFICATION_DATA_PATH", snapshot_path)

    service = object.__new__(MODULE.AgentWorkbenchService)
    payload = service.material_marketplace_catalog(classification_source="chatgpt_v4", page=1, page_size=24, group_variants=True)

    assert payload["classification_source"] == "chatgpt_v4"
    assert payload["erpnext_sync_status"] == "classification_only"
    assert payload["price_status"] == "not_bound"
    assert payload["stock_status"] == "not_bound"
    assert payload["total"] == 1
    assert payload["sku_total"] == 2
    assert payload["rows"][0]["record_kind"] == "standard_type_group"
    assert payload["rows"][0]["classification_source"] == "chatgpt_v4"

    summary = service.classification_source_summary("chatgpt_v4")
    assert summary["read_only"] is True
    assert summary["sku_count"] == 2


def test_chatgpt_catalog_snapshot_remains_available_after_reference_index_load(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "chatgpt-browser.json"
    snapshot_path.write_text(json.dumps({
        "release_hash": "test-release",
        "summary": {"sku_count": 1, "material_family_count": 1, "top_group_count": 1},
        "rows": [{
            "item_code": "MAT0001-V001",
            "material_id": "MAT0001-V001",
            "material_family": "测试接头",
            "material_name": "测试接头｜DN20",
            "standard_type": "测试接头",
            "segment_code": "CHATGPT-L1-管件",
            "segment_name": "管件",
            "category_code": "CHATGPT-L2-管件|PPR",
            "top_group": "管件",
            "sub_group": "PPR",
            "family_code": "MAT0001",
            "stock_uom": "个",
            "search_text": "mat0001-v001 测试接头 dn20",
        }],
    }, ensure_ascii=False), encoding="utf-8")
    server_module = sys.modules[MODULE.AgentWorkbenchService.__module__]
    monkeypatch.setattr(server_module, "CHATGPT_CLASSIFICATION_DATA_PATH", snapshot_path)

    service = object.__new__(MODULE.AgentWorkbenchService)
    # The taxonomy page may load the hierarchy before the marketplace asks for
    # the raw rows.  These two caches must not overwrite one another.
    service._chatgpt_classification_index()
    payload = service.material_marketplace_catalog(classification_source="chatgpt_v4", page_size=24)

    assert payload["sku_total"] == 1
    assert payload["rows"][0]["item_code"] == "MAT0001-V001"


def test_material_marketplace_falls_back_to_last_synced_catalog_when_erpnext_is_offline(tmp_path, monkeypatch) -> None:
    mapping_path = tmp_path / "material-item-code-map.json"
    mapping_path.write_text(
        json.dumps({"material_item_codes": {"MAT-1": "100031850101001"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[MODULE.AgentWorkbenchService.__module__], "MATERIAL_ITEM_CODE_MAP_PATH", mapping_path)
    calls: list[dict[str, object]] = []

    class FakeIndex:
        def material_catalog(self, **kwargs):
            calls.append(kwargs)
            return {"rows": [{"material_id": "MAT-1"}], "total": 1}

    class FakeClient:
        timeout = 90.0

        def search_documents(self, *_args, **_kwargs):
            return SimpleNamespace(ok=False, user_message="无法连接 ERPNext", error="offline")

    service = object.__new__(MODULE.AgentWorkbenchService)
    service._material_catalog_sync_cache = {}
    service.business_context = lambda _cookie="": {"user": "material@example.com"}
    service.client = lambda _user: FakeClient()
    service._gpc_reference_index = lambda: FakeIndex()

    payload = service.material_marketplace_catalog(verify_erpnext=True)

    assert payload["erpnext_sync_status"] == "erpnext_unavailable"
    assert "最近同步目录" in payload["erpnext_sync_message"]
    assert calls[0]["allowed_material_ids"] == {"MAT-1"}
    assert payload["rows"][0]["item_code"] == "100031850101001"
    assert service._material_catalog_sync_cache["material@example.com"]["expires_at"] > 0


def test_gpc_reference_profile_exposes_numeric_item_code_without_replacing_source_id(tmp_path, monkeypatch) -> None:
    mapping_path = tmp_path / "material-item-code-map.json"
    mapping_path.write_text(
        json.dumps({"material_item_codes": {"REF-HIST-1": "100031850101001"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[MODULE.AgentWorkbenchService.__module__], "MATERIAL_ITEM_CODE_MAP_PATH", mapping_path)

    class FakeIndex:
        def profile(self, code):
            return {"code": code, "actual_materials": [{"material_id": "REF-HIST-1"}]}

    service = object.__new__(MODULE.AgentWorkbenchService)
    service._gpc_reference_index = lambda: FakeIndex()

    payload = service.reference_catalog_profile("gpc", "100031850101")

    assert payload["actual_materials"] == [{
        "material_id": "REF-HIST-1",
        "item_code": "100031850101001",
    }]


def test_procurement_batch_pilot_page_exposes_local_first_100_review_flow() -> None:
    html = MODULE.PROCUREMENT_BATCH_PILOT_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "procurement-batch-pilot.js").read_text(encoding="utf-8")
    stylesheet = (MODULE.ASSET_DIR / "procurement-batch-pilot.css").read_text(encoding="utf-8")

    assert "实际采购清单" in html and "前 100" in html
    assert "历史表不参与" in html and "无 ERPNext 写入" in html
    assert "禁止笛卡尔积" in html
    assert "/api/procurement-batch-pilot/jobs" in script
    assert "/api/procurement-batch-pilot/latest" in script
    assert "metric-tokens" in html + script and "metric-cost" in html + script
    assert "needs_review" in script and "ready_new_type" in script
    assert ".progress-card" in stylesheet and ".decision" in stylesheet


def test_procurement_batch_pilot_service_delegates_without_erpnext() -> None:
    calls: list[tuple[str, object]] = []

    class FakeManager:
        def start(self, **kwargs):
            calls.append(("start", kwargs))
            return {"job_id": "pilot-1", "status": "queued"}

        def status(self, job_id):
            calls.append(("status", job_id))
            return {"job_id": job_id, "status": "completed"}

        def result(self, job_id):
            calls.append(("result", job_id))
            return {"audit": {"writes_erpnext": False}}

        def latest(self):
            calls.append(("latest", None))
            return {"available": True, "job_id": "pilot-1"}

        def cancel(self, job_id):
            calls.append(("cancel", job_id))
            return {"job_id": job_id, "status": "cancel_requested"}

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.procurement_batch_pilot = FakeManager()

    assert service.procurement_batch_pilot_start({"limit": 100, "use_deepseek": True})["job_id"] == "pilot-1"
    assert service.procurement_batch_pilot_status("pilot-1")["status"] == "completed"
    assert service.procurement_batch_pilot_result("pilot-1")["audit"]["writes_erpnext"] is False
    assert service.procurement_batch_pilot_latest()["available"] is True
    assert service.procurement_batch_pilot_cancel("pilot-1")["status"] == "cancel_requested"
    assert calls[0] == ("start", {"limit": 100, "use_deepseek": True})


def test_tariff_extraction_lab_exposes_safe_progress_pipeline() -> None:
    html = MODULE.TARIFF_EXTRACTION_LAB_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "tariff-extraction-lab.js").read_text(encoding="utf-8")
    stylesheet = (MODULE.ASSET_DIR / "tariff-extraction-lab.css").read_text(encoding="utf-8")

    assert "2026 税则多层目录提取台" in html
    assert "全量模式 · 下载并解析 1492 页" in html
    assert "不会写入 ERPNext" in html
    assert "/api/tariff-extraction/jobs" in script
    assert "/api/tariff-extraction/job?job_id=" in script
    assert "recent_nodes" in script
    assert "throughput" in html + script + stylesheet


def test_tariff_declaration_lab_exposes_read_only_attribute_pipeline() -> None:
    html = MODULE.TARIFF_DECLARATION_LAB_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "tariff-declaration-lab.js").read_text(encoding="utf-8")
    assert "涉税规范申报目录" in html
    assert "局部模式" in html and "不会写入 ERPNext" in html
    assert "/api/tariff-declaration/jobs" in script
    assert "/api/tariff-declaration/job?job_id=" in script
    assert "classification_attributes" in script
    assert "chapters" in script


def test_tariff_family_review_browser_is_read_only_and_filterable() -> None:
    html = MODULE.TARIFF_FAMILY_REVIEW_BROWSER_PATH.read_text(encoding="utf-8")
    assert "只读审阅" in html
    assert "不会创建标准类型，不会写入 ERPNext" in html
    assert "/api/tariff-family-review/summary" in html
    assert "/api/tariff-family-review/rows" in html
    assert "review_status" in html
    assert "download" in html
    assert "approve" in html and "reject" in html and "revise" in html
    assert "tariff_family_decisions.tsv" in html
    assert "7317/7318" in html
    assert "attribute-status" in html
    assert "来源属性证据" in html
    assert "tariff_attribute_decisions.tsv" in html
    assert "attribute_decision" in html


def test_tariff_taxonomy_browser_exposes_complete_lazy_tree_and_search() -> None:
    html = MODULE.TARIFF_TAXONOMY_BROWSER_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "tariff-taxonomy-browser.js").read_text(encoding="utf-8")
    stylesheet = (MODULE.ASSET_DIR / "tariff-taxonomy-browser.css").read_text(encoding="utf-8")

    assert "21 类" in html
    assert "四位品目" in html and "六位子目" in html and "八位税号" in html
    assert "/api/tariff-taxonomy/summary" in script
    assert "/api/tariff-taxonomy/children" in script
    assert "/api/tariff-taxonomy/search" in script
    assert "/api/reference-catalog/revision?catalog=gpc" in script
    assert "pollCatalogRevision" in script and "refreshCatalogRevision" in script
    assert "setInterval(pollCatalogRevision, 2500)" in script
    assert "expandNode" in script and "collapseNode" in script and "revealPath" in script
    assert "renderProfileTermResult" in script and "highlightProfileTerm" in script
    assert "profile-term-result" in stylesheet and "profile-term-highlight" in stylesheet
    assert "定义 / 包含范围" in html and "排除范围" in html and "查看官方英文" in html
    assert "includes_working" in script and "excludes_working" in script
    assert "隐藏无实际物料目录" in html
    assert "actual-materials-section" in html
    assert "materialized_only" in script and "renderActualMaterials" in script
    assert 'completeness_status === "完整"' in script
    assert "procurement_attributes" in script and "price_drivers" in script and "gpc_notes" in script
    assert "采购必选" in script and "价格 / 适配关键" in script and "分类依据" in script
    assert "非 GPC" not in script and "非GPC" not in script
    assert "code.hidden = state.catalog" not in script
    assert ".level-internal_type > span" in stylesheet
    assert ".kind-internal_family .node-code, .kind-internal_type .node-code" in stylesheet
    assert "主模板：" in script and "查看属性角色" in script and "record_policy_label" in script
    assert "采购包装：" not in script and "规格依据：" not in script
    assert ".material-review-status.complete" in stylesheet and ".material-field-group" in stylesheet
    assert ".material-procurement-policy" in stylesheet and ".material-role-details" in stylesheet
    assert ".actual-material-card" in stylesheet and ".material-count-badge" in stylesheet
    assert "classification-source" in html
    assert "ChatGPT 分类（龙华 V4）" in html and "switchClassificationSource" in script
    assert "classification_source" in script
    assert "material-variant-dialog" in html
    assert "openMaterialVariantSelector" in script
    assert "matchingMaterialVariants" in script
    assert '"公称直径"' in script and '"长度/牙型"' in script
    assert script.index('"性能/质量等级"') < script.index('"材质/表面处理"')
    assert ".material-variant-options" in stylesheet
    assert ".taxonomy-tree" in stylesheet and ".search-results" in stylesheet
    assert ".loading-state[hidden] { display: none; }" in stylesheet


def test_tariff_taxonomy_browser_loads_attributes_on_eight_digit_selection() -> None:
    html = MODULE.TARIFF_TAXONOMY_BROWSER_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "tariff-taxonomy-browser.js").read_text(encoding="utf-8")
    stylesheet = (MODULE.ASSET_DIR / "tariff-taxonomy-browser.css").read_text(encoding="utf-8")

    assert "申报属性证据" in html
    assert "detail-classification-attributes" in html
    assert "/api/tariff-declaration/profile?code=" in script
    assert "loadAttributeEvidence" in script
    assert ".attribute-chip" in stylesheet
    assert ".attribute-status.available" in stylesheet


def test_tariff_declaration_profile_lookup_is_read_only_and_code_scoped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "tariff-declaration"
    job_dir = runtime_root / "full-job"
    job_dir.mkdir(parents=True)
    (job_dir / "manifest.json").write_text('{"mode":"full","profiles":1}', encoding="utf-8")
    (job_dir / "tariff-declaration-profiles.jsonl").write_text(
        '{"code":"25059000","name":"其他","heading_code":"2505","subheading_code":"250590",'
        '"heading_name":"各种天然砂","declaration_attributes":["来源"],'
        '"classification_attributes":["来源"],"page":105,"source_text":"2505.9000 -其他"}\n',
        encoding="utf-8",
    )
    server_module = sys.modules[MODULE.AgentWorkbenchService.__module__]
    monkeypatch.setattr(server_module, "TARIFF_DECLARATION_RUNTIME_ROOT", runtime_root)
    service = object.__new__(MODULE.AgentWorkbenchService)

    available = service.tariff_declaration_profile("25059000")
    missing = service.tariff_declaration_profile("25051000")
    assert available["status"] == "available"
    assert available["profile"]["declaration_attributes"] == ["来源"]
    assert missing["status"] == "not_available"


def test_request_logging_tolerates_detached_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    handler_module = sys.modules[MODULE.AgentWorkbenchHandler.__module__]
    monkeypatch.setattr(handler_module.sys, "stderr", None)
    handler = object.__new__(MODULE.AgentWorkbenchHandler)

    handler.log_message("%s", "request")


def test_tariff_family_review_rows_merges_source_backed_attributes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    family_dir = tmp_path / "review"
    family_dir.mkdir()
    (family_dir / "tariff_family_summary.json").write_text('{"row_count": 1}', encoding="utf-8")
    (family_dir / "tariff_family_candidates.tsv").write_text(
        "code\tsource_name\tnormalized_name\tparent_name\treview_status\n"
        "73181510\t其他螺钉及螺栓\t其他螺钉及螺栓\t钢铁制的螺钉\tcandidate\n",
        encoding="utf-8",
    )
    attribute_path = family_dir / "tariff_attribute_candidates.tsv"
    attribute_path.write_text(
        "code\tattribute_status\tattributes\n"
        '73181510\treview_required\t{"tensile_strength":{"value": ">=800 MPa"}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(MODULE, "TARIFF_FAMILY_REVIEW_DIR", family_dir)
    monkeypatch.setattr(MODULE, "TARIFF_ATTRIBUTE_REVIEW_PATH", attribute_path)
    service = object.__new__(MODULE.AgentWorkbenchService)

    result = service.tariff_family_review_rows(attribute_status="review_required", query=">=800 MPa")

    assert result["total"] == 1
    assert result["rows"][0]["attribute_status"] == "review_required"
    assert result["rows"][0]["attributes"]["tensile_strength"]["value"] == ">=800 MPa"


def _material_publish_service(tmp_path: Path, *, readback_uom: str = ""):
    classifier = MaterialTypeClassifier()
    type_row = next(item for item in classifier.types if classifier.release_rows_for_type(item.type_id))
    release_row = classifier.release_rows_for_type(type_row.type_id)[0]
    decision = MaterialIntakeDecision(
        row_id="1",
        raw_name=type_row.standard_name,
        raw_spec="测试规格",
        qty=1,
        uom=str(release_row.get("stock_uom") or "个"),
        queue="new_sku",
        queue_label="现有类型新增 SKU",
        type_id=type_row.type_id,
        normalized_attributes={
            "uom": str(release_row.get("stock_uom") or "个"),
            "material": "发布测试材质",
        },
        reason="测试用已复核结论",
    )
    result = HighRecallBatchResult(
        total_rows=1,
        queue_counts={"existing_sku": 0, "new_sku": 1, "new_type": 0, "needs_input": 0},
        decisions=[decision],
    )
    batch = build_material_drafts("analysis-publish", result, classifier)

    class FakeClient:
        def __init__(self):
            self.documents = {}
            self.create_count = 0

        def get_logged_user(self):
            return ToolResult(ok=True, data="buyer@example.com")

        def search_documents(self, doctype, **_kwargs):
            assert doctype == "Item"
            return ToolResult(ok=True, data=[{"item_code": code} for code in self.documents])

        def document_exists(self, doctype, name):
            if doctype == "Item":
                return ToolResult(ok=True, data={"exists": name in self.documents, "name": name})
            return ToolResult(ok=True, data={"exists": True, "name": name})

        def create_document(self, doctype, data):
            assert doctype == "Item"
            self.create_count += 1
            document = {**data, "doctype": doctype, "name": data["item_code"], "docstatus": 0}
            self.documents[data["item_code"]] = document
            return ToolResult(ok=True, data=document)

        def get_document(self, doctype, name):
            assert doctype == "Item"
            document = dict(self.documents[name])
            if readback_uom:
                document["stock_uom"] = readback_uom
            return ToolResult(ok=True, data=document)

    client = FakeClient()
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service._run_lock = threading.Lock()
    service._material_draft_batches = {batch.analysis_id: batch}
    service.material_intake = SimpleNamespace(retriever=SimpleNamespace(classifier=classifier))
    service.material_publications = RuntimeMaterialPublicationStore(tmp_path / "publications.jsonl")
    service.client = lambda _user: client
    cache = {}
    service._idempotency_context = lambda _user, _project, _conversation, request_id: (cache.get(request_id), None)
    service._remember_idempotent_result = lambda _context, request_id, payload: cache.__setitem__(request_id, payload)
    return service, client, batch


def test_material_draft_publish_is_idempotent_and_readback_verified(tmp_path: Path) -> None:
    service, client, batch = _material_publish_service(tmp_path)
    draft = batch.drafts[0]
    request = {
        "analysis_id": batch.analysis_id,
        "user": "buyer@example.com",
        "request_id": "publish-request-1",
        "conversation_id": "material-intake-test",
        "draft_ids": [draft.draft_id],
        "draft_hashes": [{"draft_id": draft.draft_id, "frozen_hash": draft.frozen_hash}],
    }

    first = service.confirm_material_intake_drafts(request)
    replay = service.confirm_material_intake_drafts(request)

    assert first["status"] == "completed"
    assert first["readback_verified"] is True
    assert first["created"][0]["readback"]["mismatches"] == {}
    assert client.create_count == 1
    assert replay["idempotent_replay"] is True
    assert client.create_count == 1
    assert service.material_publications.active()[0].sku.item_code == draft.item_code


def test_material_draft_revision_refreshes_frozen_preview_without_writing(tmp_path: Path) -> None:
    service, client, batch = _material_publish_service(tmp_path)
    draft = batch.drafts[0]

    revised = service.revise_material_intake_drafts({
        "analysis_id": batch.analysis_id,
        "user": "buyer@example.com",
        "draft_updates": [{
            "draft_id": draft.draft_id,
            "stock_uom": "箱",
            "normalized_attributes": {"material": "发布测试材质"},
        }],
    })

    assert revised["drafts"][0]["stock_uom"] == "箱"
    assert revised["drafts"][0]["revision"] == 2
    assert revised["drafts"][0]["frozen_hash"] != draft.frozen_hash
    assert client.create_count == 0
    assert client.documents == {}


def test_material_draft_publish_reports_post_write_readback_mismatch(tmp_path: Path) -> None:
    service, client, batch = _material_publish_service(tmp_path, readback_uom="错误单位")

    result = service.confirm_material_intake_drafts({
        "analysis_id": batch.analysis_id,
        "user": "buyer@example.com",
        "request_id": "publish-request-mismatch",
        "draft_ids": [batch.drafts[0].draft_id],
        "draft_hashes": [{"draft_id": batch.drafts[0].draft_id, "frozen_hash": batch.drafts[0].frozen_hash}],
    })

    assert result["status"] == "partial"
    assert result["writes_erpnext"] is True
    assert result["readback_verified"] is False
    assert result["failed"][0]["error_type"] == "readback_mismatch"
    assert result["failed"][0]["write_succeeded"] is True
    assert "stock_uom" in result["failed"][0]["readback"]["mismatches"]
    assert client.create_count == 1
    assert service.material_publications.active() == []


def test_material_draft_publish_requires_request_id(tmp_path: Path) -> None:
    service, _client, batch = _material_publish_service(tmp_path)

    with pytest.raises(ValueError, match="request_id"):
        service.confirm_material_intake_drafts({
            "analysis_id": batch.analysis_id,
            "user": "buyer@example.com",
            "draft_ids": [batch.drafts[0].draft_id],
        })


def test_material_draft_publish_rejects_stale_frozen_hash(tmp_path: Path) -> None:
    service, client, batch = _material_publish_service(tmp_path)
    draft = batch.drafts[0]

    with pytest.raises(ValueError, match="冻结摘要"):
        service.confirm_material_intake_drafts({
            "analysis_id": batch.analysis_id,
            "user": "buyer@example.com",
            "request_id": "publish-stale-hash",
            "draft_ids": [draft.draft_id],
            "draft_hashes": [{"draft_id": draft.draft_id, "frozen_hash": "stale"}],
        })

    assert client.create_count == 0


def test_runtime_compare_defaults_to_openclaw_without_calling_existing_runtime() -> None:
    existing_calls: list[dict] = []
    openclaw_calls: list[dict] = []
    service = object.__new__(MODULE.AgentWorkbenchService)
    service.run = lambda request: existing_calls.append(request)  # type: ignore[method-assign]
    service.openclaw_preview = SimpleNamespace(run=lambda **kwargs: openclaw_calls.append(kwargs) or {
        "runtime": "openclaw_manual",
        "status": "ok",
        "message": "已准备材料申请",
        "duration_ms": 10,
        "steps": [],
        "questions": [],
        "question_count": 0,
        "tool_summary": {"calls": 1, "tools": ["nexterp_prepare_operation"], "failures": 0},
    })

    result = service.compare_runtimes({
        "user": "mao.xiaoquan@stec-up.local",
        "project_code": "PRJ-HL-13",
        "text": "申请20包水泥",
    })

    assert result["mode"] == "openclaw_only"
    assert result["existing"]["status"] == "disabled"
    assert result["openclaw"]["status"] == "ok"
    assert existing_calls == []
    assert len(openclaw_calls) == 1


def test_operation_model_explorer_shows_relational_slot_prototype() -> None:
    html = MODULE.OPERATION_MODEL_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "operation-model.js").read_text(encoding="utf-8")

    assert "字段槽位与操作模型" in html
    assert 'id="slotRows"' in html
    assert 'id="toolCall"' in html
    assert 'id="project"></select>' in html
    assert 'id="itemSearch"' in html
    assert "/api/operation-model/material-request" in script
    assert "/api/operation-model/options" in script
    assert "/api/operation-model/compile" in script


def test_result_document_links_build_internal_workbench_route() -> None:
    result = {
        "tool_result": {"data": {"doctype": "Material Request", "name": "MAT-MR-2026-00001"}},
        "tool_results": [],
    }

    assert MODULE.result_document_links(result, "http://localhost:8002") == [
        {
            "doctype": "Material Request",
            "name": "MAT-MR-2026-00001",
            "url": "#document/Material%20Request/MAT-MR-2026-00001",
        }
    ]


def test_item_result_builds_internal_workbench_route() -> None:
    result = {
        "tool_results": [{"data": {"doctype": "Item", "name": "FAST-000124"}}],
    }

    assert MODULE.result_document_links(result, "http://localhost:8002") == [
        {
            "doctype": "Item",
            "name": "FAST-000124",
            "url": "#document/Item/FAST-000124",
        }
    ]


def test_compact_chat_result_preserves_item_creation_confirmation() -> None:
    summary = {
        "title": "创建标准物料",
        "item_code": "FAST-000124",
        "sku_name": "内六角螺丝 M9*47 碳钢 8.8 镀锌",
        "item_group": "紧固件与连接件/螺丝/螺栓",
        "stock_uom": "个",
    }
    result = MODULE.compact_chat_result(
        {
            "status": "needs_confirmation",
            "message": "请确认创建标准物料。",
            "pending_tool_call": {
                "tool": "nexterp_execute_prepared_operation",
                "arguments": {"pending_id": "pending-item"},
                "summary": summary,
            },
        },
        "http://localhost:8002",
    )

    assert result["confirmation"] == summary
    assert result["pending_tool_call"]["arguments"]["pending_id"] == "pending-item"


def test_item_detail_uses_direct_document_read_without_workflow_api() -> None:
    calls = []

    class FakeClient:
        def get_document(self, doctype, name):
            calls.append(("get_document", doctype, name))
            return SimpleNamespace(
                ok=True,
                data={
                    "doctype": "Item",
                    "name": name,
                    "item_code": name,
                    "item_name": "内六角螺丝 M9*47",
                    "item_group": "紧固件与连接件/螺丝/螺栓",
                    "stock_uom": "个",
                    "disabled": 0,
                },
                user_message=None,
                error=None,
            )

        def call_method(self, method, arguments):
            calls.append(("call_method", method, arguments))
            raise AssertionError("Item 不应读取单据工作流")

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()

    detail = service.document("manager@example.com", "Item", "FAST-000124")

    assert detail["label"] == "标准物料"
    assert detail["process"]["state"] == "已启用"
    assert detail["process"]["can_submit"] is False
    assert calls == [("get_document", "Item", "FAST-000124")]


def test_pending_confirmation_history_is_explicitly_not_created() -> None:
    result = MODULE.compact_chat_result(
        {
            "status": "needs_confirmation",
            "message": "创建材料申请草稿",
            "pending_tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}},
        },
        "http://localhost:8002",
    )

    assert result["message"] == "我已准备好创建材料申请草稿，但尚未写入 ERPNext。请确认后再执行。"


def test_compact_candidate_keeps_governed_reference_price() -> None:
    candidates = MODULE.compact_chat_candidates([{
        "item_code": "MAT-CEM-000008",
        "sku_name": "水泥 42.5 袋装 50kg",
        "stock_uom": "包",
        "estimated_rate": "28.00",
        "currency": "CNY",
        "price_basis": "测试参考价",
        "data": {"private": "discard"},
    }])

    assert candidates == [{
        "item_code": "MAT-CEM-000008",
        "sku_name": "水泥 42.5 袋装 50kg",
        "stock_uom": "包",
        "estimated_rate": "28.00",
        "currency": "CNY",
        "price_basis": "测试参考价",
    }]


def test_successful_document_is_not_shown_failed_when_final_reply_failed() -> None:
    tool_result = {
        "ok": True,
        "data": {"doctype": "Material Request", "name": "MAT-MR-2026-00015"},
    }

    result = MODULE.compact_chat_result(
        {
            "status": "failed",
            "message": "DeepSeek规划失败：finish.arguments.message is required",
            "tool_result": tool_result,
            "tool_results": [tool_result],
        },
        "http://localhost:8002",
    )

    assert result["status"] == "completed"
    assert "MAT-MR-2026-00015 已在 ERPNext 中执行成功" in result["message"]


def test_business_error_card_explains_precondition_and_next_action() -> None:
    result = MODULE.compact_chat_result(
        {
            "status": "failed",
            "message": "无法创建询价单。",
            "steps": [{
                "result": {
                    "type": "business_action_error",
                    "error": "Material Request MAT-MR-0001 当前状态不能执行询价。",
                },
            }],
        },
        "http://localhost:8002",
    )

    assert result["business_errors"] == [{
        "category": "business_precondition",
        "title": "当前业务状态不允许这样操作",
        "summary": "Material Request MAT-MR-0001 当前状态不能执行询价。",
        "next_actions": ["请先处理来源单据状态或选择符合条件的单据。"],
        "retryable": True,
    }]


def test_business_error_card_preserves_specific_clarification_question() -> None:
    cards = MODULE.business_error_cards({
        "status": "needs_clarification",
        "steps": [{
            "result": {
                "type": "business_action_error",
                "error": "询价单缺少候选供应商。",
                "questions": ["请选择至少一家要询价的供应商。"],
            },
        }],
    })

    assert cards[0]["category"] == "missing_information"
    assert cards[0]["next_actions"] == ["请选择至少一家要询价的供应商。"]


def test_document_process_without_workflow_explains_direct_submission() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "status": "Draft", "_assign": "[]"},
    )

    assert process["state"] == "草稿"
    assert process["workflow_configured"] is False
    assert process["can_submit"] is True
    assert "直接成为已提交状态" in process["description"]
    assert process["notification"] == "当前没有审批待办接收人"


def test_document_process_shows_workflow_state_and_assignees() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "workflow_state": "等待项目经理审批", "_assign": '["manager@example.com"]'},
    )

    assert process["state"] == "等待项目经理审批"
    assert process["workflow_configured"] is True
    assert process["assignees"] == ["manager@example.com"]
    assert process["notification"] == "已生成审批分配"


def test_document_process_exposes_only_current_users_workflow_actions() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "workflow_state": "待材料设备主管审批", "_assign": "[]"},
        ["批准", "驳回"],
    )

    assert process["available_actions"] == ["批准", "驳回"]
    assert process["can_submit"] is False
    assert process["notification"] == "当前账号可执行：批准、驳回"


def test_workbench_workflow_button_executes_erpnext_directly_without_agent() -> None:
    calls = []

    class FakeClient:
        def get_workflow_actions(self, doctype, name):
            calls.append(("get_workflow_actions", doctype, name))
            return SimpleNamespace(ok=True, data=[{"action": "提交申请"}], user_message=None, error=None)

        def call_method(self, method, arguments):
            calls.append(("call_method", method, arguments))
            return SimpleNamespace(ok=True, data={"name": arguments["name"]}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.document = lambda user, doctype, name: {"doctype": doctype, "name": name, "user": user}

    result = service.apply_workflow_action(
        "clerk@example.com",
        "Material Request",
        "MAT-MR-0001",
        "提交申请",
    )

    assert result["name"] == "MAT-MR-0001"
    assert calls == [
        ("get_workflow_actions", "Material Request", "MAT-MR-0001"),
        (
            "call_method",
            "agent_bridge.api.apply_workflow_action_with_comment",
            {"doctype": "Material Request", "name": "MAT-MR-0001", "action": "提交申请", "comment": ""},
        ),
    ]


def test_direct_submit_rejects_documents_with_workflow() -> None:
    class FakeClient:
        def get_document(self, doctype, name):
            return SimpleNamespace(
                ok=True,
                data={"doctype": doctype, "name": name, "workflow_state": "草稿"},
                user_message=None,
                error=None,
            )

        def submit_document(self, _doctype, _name):
            raise AssertionError("workflow document must not be submitted directly")

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()

    with pytest.raises(ValueError, match="已启用审批工作流"):
        service.submit_document("clerk@example.com", "Material Request", "MAT-MR-0001")


def test_workbench_rejection_requires_and_forwards_reason() -> None:
    calls = []

    class FakeClient:
        def get_workflow_actions(self, doctype, name):
            return SimpleNamespace(ok=True, data=[{"action": "驳回"}], user_message=None, error=None)

        def call_method(self, method, arguments):
            calls.append((method, arguments))
            return SimpleNamespace(ok=True, data={"name": arguments["name"]}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.document = lambda user, doctype, name: {"doctype": doctype, "name": name, "user": user}

    with pytest.raises(ValueError, match="驳回时必须填写原因"):
        service.apply_workflow_action("manager@example.com", "Material Request", "MR-1", "驳回")

    service.apply_workflow_action(
        "manager@example.com",
        "Material Request",
        "MR-1",
        "驳回",
        comment="规格不明确，请补充。",
    )

    assert calls == [(
        "agent_bridge.api.apply_workflow_action_with_comment",
        {
            "doctype": "Material Request",
            "name": "MR-1",
            "action": "驳回",
            "comment": "规格不明确，请补充。",
        },
    )]


def test_document_includes_workflow_history_and_business_comments() -> None:
    class FakeClient:
        def call_method(self, method, arguments):
            assert method == "agent_bridge.api.get_document_with_workflow_actions"
            return SimpleNamespace(ok=True, data={
                "document": {"name": "MR-1", "docstatus": 0, "workflow_state": "草稿"},
                "actions": [{"action": "提交申请"}],
                "workflow_history": [{"status": "Completed", "completed_by": "manager@example.com"}],
                "workflow_comments": [{"content": "工作流动作：驳回\n原因：请补充规格。"}],
            }, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()

    result = service.document("clerk@example.com", "Material Request", "MR-1")

    assert result["process"]["history"][0]["completed_by"] == "manager@example.com"
    assert "请补充规格" in result["process"]["comments"][0]["content"]


def test_pending_procurement_enriches_remaining_demand_inventory_and_supplier() -> None:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    class FakeClient:
        def get_pending_procurement_items(self, *, project, warehouses, limit):
            assert project == "PROJ-0010"
            assert warehouses == ["合流1.3标仓库 - SD", "中心仓 - SD"]
            assert limit == 500
            return SimpleNamespace(ok=True, data={
                "rows": [{
                    "material_request": "MAT-MR-TEST-1",
                    "material_request_item": "MRI-1",
                    "item_code": "MAT-CEM-000008",
                    "item_name": "水泥 42.5 袋装 50kg",
                    "qty": 20,
                    "ordered_qty": 5,
                    "remaining_qty": 15,
                    "uom": "包",
                    "schedule_date": tomorrow,
                    "warehouse": "合流1.3标仓库 - SD",
                    "project": "PROJ-0010",
                    "rate": 28,
                }],
                "inventory": [{
                    "item_code": "MAT-CEM-000008",
                    "warehouse": "中心仓 - SD",
                    "actual_qty": 8,
                    "reserved_qty": 2,
                }],
                "summary": {"row_count": 1, "remaining_qty": 15},
            }, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.erpnext_project_name = lambda _client, _project: "PROJ-0010"
    service.procurement_inventory_warehouses = lambda _project, include_all=False: [
        "合流1.3标仓库 - SD", "中心仓 - SD"
    ]

    result = service.pending_procurement("buyer@example.com", "PRJ-HL-13")

    row = result["rows"][0]
    assert row["remaining_qty"] == 15
    assert row["urgency"] == "urgent"
    assert row["total_available_qty"] == 6
    assert row["inventory_coverage"] == "shortage"
    assert row["estimated_amount"] == 420
    assert {stock["warehouse"] for stock in row["inventory"]} == {
        "合流1.3标仓库 - SD", "中心仓 - SD"
    }
    assert row["supplier_suggestions"][0]["supplier_name"] == "测试综合供应商"
    assert result["aggregate"][0]["total_remaining_qty"] == 15
    assert result["summary"]["shortage_rows"] == 1


def test_pending_procurement_all_scope_keeps_cross_project_sources() -> None:
    calls = []

    class FakeClient:
        def get_pending_procurement_items(self, *, project, warehouses, limit):
            calls.append((project, warehouses, limit))
            rows = []
            for index, project_name in enumerate(("PROJ-0010", "PROJ-0020"), start=1):
                rows.append({
                    "material_request": f"MR-{index}",
                    "material_request_item": f"MRI-{index}",
                    "item_code": "MAT-CEM-000008",
                    "qty": 5,
                    "ordered_qty": 0,
                    "remaining_qty": 5,
                    "uom": "包",
                    "project": project_name,
                    "schedule_date": "2099-01-01",
                })
            return SimpleNamespace(ok=True, data={"rows": rows, "inventory": [], "summary": {}}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.procurement_inventory_warehouses = lambda _project, include_all=False: ["中心仓 - SD"]

    result = service.pending_procurement("buyer@example.com", "PRJ-HL-13", scope="all")

    assert calls == [(None, ["中心仓 - SD"], 500)]
    assert len(result["rows"]) == 2
    assert result["aggregate"][0]["total_remaining_qty"] == 10
    assert result["aggregate"][0]["projects"] == ["PROJ-0010", "PROJ-0020"]


def test_reset_documents_cancels_submitted_documents_before_deleting() -> None:
    calls = []

    class FakeClient:
        def cancel_document(self, doctype, name):
            calls.append(("cancel", doctype, name))
            return SimpleNamespace(ok=True, user_message=None, error=None)

        def delete_document(self, doctype, name):
            calls.append(("delete", doctype, name))
            return SimpleNamespace(ok=True, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.documents = lambda user, project, **kwargs: {
        "erpnext_project": "PROJ-0010",
        "modules": [{"groups": [
            {"doctype": "Material Request", "documents": [{"name": "MR-1", "docstatus": 1}]},
            {"doctype": "Purchase Invoice", "documents": [{"name": "PI-1", "docstatus": 0}]},
            {"doctype": "Request for Quotation", "documents": [{"name": "RFQ-KEEP", "docstatus": 0}]},
        ]}],
    }
    service.client = lambda user: FakeClient()

    result = service.reset_documents("buyer@example.com", "PRJ-HL-13")

    assert calls == [
        ("delete", "Purchase Invoice", "PI-1"),
        ("delete", "Request for Quotation", "RFQ-KEEP"),
        ("cancel", "Material Request", "MR-1"),
        ("delete", "Material Request", "MR-1"),
    ]
    assert result["deleted_count"] == 3
    assert result["failed_count"] == 0


def test_create_rfq_reloads_pending_rows_and_preserves_material_request_links() -> None:
    calls = []

    class FakeClient:
        def get_document(self, doctype, name):
            assert (doctype, name) == ("Item", "MAT-CEM-000008")
            return SimpleNamespace(ok=True, data={"item_name": "水泥 42.5 袋装 50kg", "stock_uom": "包", "disabled": 0})

        def create_document(self, doctype, data):
            calls.append((doctype, data))
            return SimpleNamespace(ok=True, data={"name": "PUR-RFQ-0001", "docstatus": 0}, status_code=200, raw_status_code=200)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.pending_procurement = lambda *_args, **_kwargs: {"rows": [{
        "material_request": "MAT-MR-1",
        "material_request_item": "MRI-1",
        "item_code": "MAT-CEM-000008",
        "remaining_qty": 15,
        "uom": "包",
        "schedule_date": "2026-07-20",
        "warehouse": "合流1.3标仓库 - SD",
        "project": "PROJ-0010",
    }]}
    service.document = lambda _user, doctype, name: {"doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)

    result = service.create_request_for_quotation(
        "buyer@example.com",
        "PRJ-HL-13",
        ["MAT-MR-1:MRI-1"],
        ["SUP-TEST-A"],
    )

    assert result["name"] == "PUR-RFQ-0001"
    data = calls[0][1]
    assert data["suppliers"] == [{"supplier": "测试建材供应商甲"}]
    assert data["items"][0]["qty"] == 15
    assert data["items"][0]["material_request"] == "MAT-MR-1"
    assert data["items"][0]["material_request_item"] == "MRI-1"


def test_create_supplier_quotation_requires_submitted_rfq_and_preserves_rfq_row() -> None:
    calls = []

    class FakeClient:
        def get_document(self, doctype, name):
            if doctype == "Item":
                return SimpleNamespace(ok=True, data={"item_name": "水泥 42.5 袋装 50kg", "stock_uom": "包", "disabled": 0})
            assert (doctype, name) == ("Request for Quotation", "PUR-RFQ-0001")
            return SimpleNamespace(ok=True, data={
                    "name": name,
                    "docstatus": 1,
                    "suppliers": [{"supplier": "测试建材供应商甲"}],
                    "items": [{
                        "name": "RFQI-1",
                        "item_code": "MAT-CEM-000008",
                        "qty": 15,
                        "uom": "包",
                        "schedule_date": "2026-07-20",
                    }],
                }, user_message=None, error=None)

        def create_document(self, doctype, data):
            calls.append((doctype, data))
            return SimpleNamespace(ok=True, data={"name": "PUR-SQ-0001", "docstatus": 0}, status_code=200, raw_status_code=200)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.document = lambda _user, doctype, name: {"doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)

    result = service.create_supplier_quotation(
        "buyer@example.com",
        "PRJ-HL-13",
        "PUR-RFQ-0001",
        "SUP-TEST-A",
        [{"request_for_quotation_item": "RFQI-1", "rate": 27.5}],
        terms="月结30天",
    )

    assert result["name"] == "PUR-SQ-0001"
    data = calls[0][1]
    assert data["supplier"] == "测试建材供应商甲"
    assert data["items"][0]["request_for_quotation"] == "PUR-RFQ-0001"
    assert data["items"][0]["request_for_quotation_item"] == "RFQI-1"
    assert data["items"][0]["rate"] == 27.5


def test_create_supplier_quotation_rejects_zero_rate() -> None:
    class FakeClient:
        def get_document(self, _doctype, name):
            return SimpleNamespace(ok=True, data={
                "name": name,
                "docstatus": 1,
                "suppliers": [{"supplier": "测试建材供应商甲"}],
                "items": [{"name": "RFQI-1", "item_code": "MAT-CEM-000008", "qty": 1, "uom": "包"}],
            }, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service._idempotency_context = lambda *_args: (None, None)

    with pytest.raises(ValueError, match="单价必须大于 0"):
        service.create_supplier_quotation(
            "buyer@example.com", "PRJ-HL-13", "PUR-RFQ-0001", "SUP-TEST-A",
            [{"request_for_quotation_item": "RFQI-1", "rate": 0}],
        )


def test_create_purchase_order_from_supplier_quotation_uses_specialized_tool(monkeypatch) -> None:
    calls = []

    class FakeAdapter:
        def __init__(self, client):
            assert client == "client"

        def execute(self, call):
            calls.append(call)
            return SimpleNamespace(ok=True, data={"doctype": "Purchase Order", "name": "PO-1"}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    monkeypatch.setattr(sys.modules[service.__class__.__module__], "ERPNextAdapter", FakeAdapter)
    service.client = lambda _user: "client"
    service.document = lambda user, doctype, name: {"user": user, "doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)
    service._remember_idempotent_result = lambda *_args: None

    result = service.create_purchase_order_from_supplier_quotation(
        "buyer@example.com",
        "PRJ-HL-13",
        "SQ-1",
        request_id="req-1",
    )

    assert result["name"] == "PO-1"
    assert result["source_supplier_quotation"] == "SQ-1"
    assert calls[0]["tool"] == "erpnext.buying.create_purchase_order_from_supplier_quotation_draft"
    assert calls[0]["arguments"]["supplier_quotation"] == "SQ-1"


def test_create_purchase_receipt_from_purchase_order_uses_specialized_tool(monkeypatch) -> None:
    calls = []

    class FakeAdapter:
        def __init__(self, client):
            assert client == "client"

        def execute(self, call):
            calls.append(call)
            return SimpleNamespace(ok=True, data={"doctype": "Purchase Receipt", "name": "PR-1"}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    monkeypatch.setattr(sys.modules[service.__class__.__module__], "ERPNextAdapter", FakeAdapter)
    service.client = lambda _user: "client"
    service.document = lambda user, doctype, name: {"user": user, "doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)
    service._remember_idempotent_result = lambda *_args: None

    result = service.create_purchase_receipt_from_purchase_order(
        "storekeeper@example.com",
        "PRJ-HL-13",
        "PO-1",
        selected_items=[{"purchase_order_item": "POI-1", "qty": 2, "warehouse": "Stores - A"}],
        request_id="req-1",
    )

    assert result["name"] == "PR-1"
    assert result["source_purchase_order"] == "PO-1"
    assert calls[0]["tool"] == "erpnext.buying.create_purchase_receipt_from_purchase_order_draft"
    assert calls[0]["arguments"]["selected_items"][0]["qty"] == 2


def test_purchase_receipt_discrepancy_and_return_use_specialized_tools(monkeypatch) -> None:
    calls = []

    class FakeAdapter:
        def __init__(self, client):
            assert client == "client"

        def execute(self, call):
            calls.append(call)
            if call["tool"].endswith("record_purchase_receipt_discrepancy"):
                return SimpleNamespace(ok=True, data={"status": "Discrepancy Recorded"}, user_message=None, error=None)
            return SimpleNamespace(ok=True, data={"doctype": "Purchase Receipt", "name": "RET-1"}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    monkeypatch.setattr(sys.modules[service.__class__.__module__], "ERPNextAdapter", FakeAdapter)
    service.client = lambda _user: "client"
    service.document = lambda user, doctype, name: {"user": user, "doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)
    service._remember_idempotent_result = lambda *_args: None

    discrepancy = service.record_purchase_receipt_discrepancy(
        "storekeeper@example.com", "PRJ-HL-13", "PR-1", "规格不符",
        items=[{"purchase_receipt_item": "PRI-1", "qty": 2}], assigned_to="buyer@example.com",
    )
    returned = service.create_purchase_return_from_receipt(
        "storekeeper@example.com", "PRJ-HL-13", "PR-1", "整批退回",
        items=[{"purchase_receipt_item": "PRI-1", "qty": 2}],
    )

    assert discrepancy["discrepancy"]["status"] == "Discrepancy Recorded"
    assert returned["name"] == "RET-1"
    assert calls[0]["tool"] == "erpnext.buying.record_purchase_receipt_discrepancy"
    assert calls[0]["arguments"]["assigned_to"] == "buyer@example.com"
    assert calls[1]["tool"] == "erpnext.buying.create_purchase_receipt_return_draft"
    assert calls[1]["arguments"]["reason"] == "整批退回"


def test_project_catalog_contains_project_specific_and_organization_employees() -> None:
    projects = {row["project_code"]: row for row in MODULE.project_catalog()}
    names = {row["employee_name"] for row in projects["PRJ-HL-13"]["employees"]}

    assert projects["PRJ-HL-13"]["project_short_name"] == "合流1.3标"
    assert {"张振光", "林乔航", "毛晓泉", "徐溥祺"} <= names
    assert "梁志华" not in names


def test_employee_catalog_exposes_role_focused_workbench_views() -> None:
    employees = {row["employee_name"]: row for row in MODULE.employee_catalog()}

    assert employees["毛晓泉"]["workbench_view"]["default_panel"] == "mine"
    assert employees["潘丰"]["workbench_view"]["recommended_panels"] == ["inbox", "pending", "progress", "exceptions"]
    assert employees["胡银虎"]["workbench_view"]["default_panel"] == "inbox"
    assert MODULE.WORKBENCH_ROLE_VIEWS["采购员"]["default_panel"] == "pending"
    assert MODULE.WORKBENCH_ROLE_VIEWS["仓管员"]["recommended_panels"] == ["progress", "exceptions", "recent"]


def test_session_history_restores_visible_chat_and_reset_clears_context(tmp_path: Path) -> None:
    user = "mao.xiaoquan@stec-up.local"
    store = MODULE.RuntimeSessionStore(tmp_path)
    session = store.load(user, profile="project")
    session.pending_action = {"tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}}}
    session.add_turn({
        "user_text": "帮我采购点水泥",
        "result": {
            "status": "needs_clarification",
            "message": "请选择具体水泥。",
            "questions": ["请选择具体水泥。"],
            "candidates": [{
                "item_code": "MAT-CEM-000011",
                "sku_name": "水泥 PC425 袋装 50kg",
                "stock_uom": "包",
                "required_specs": "强度等级：42.5",
                "search_keywords": "不应传给网页",
            }],
        },
    })
    store.save(session)
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.session_store = store
    service.base_url = "http://localhost:8002"

    history = service.session_history(user)

    assert history["latest_user_text"] == "帮我采购点水泥"
    assert history["turns"][0]["result"]["message"] == "请选择具体水泥。"
    assert history["turns"][0]["result"]["candidates"] == [{
        "item_code": "MAT-CEM-000011",
        "sku_name": "水泥 PC425 袋装 50kg",
        "required_specs": "强度等级：42.5",
        "stock_uom": "包",
    }]
    assert service.reset_session(user) == {"reset": True, "had_history": True}
    assert service.session_history(user)["turns"] == []


def test_conversations_are_isolated_by_employee_project_and_conversation(tmp_path: Path) -> None:
    user = "mao.xiaoquan@stec-up.local"
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.session_store = MODULE.RuntimeSessionStore(tmp_path)
    service.base_url = "http://localhost:8002"

    first = service.scoped_session_store(user, "PRJ-HL-13", "conversation-a")
    session = first.load(user, profile="project")
    session.add_turn({"user_text": "合流项目要水泥", "result": {"message": "收到"}})
    first.save(session)

    assert service.session_history(user, "PRJ-HL-13", "conversation-a")["turns"]
    assert service.session_history(user, "PRJ-HL-13", "conversation-b")["turns"] == []
    assert service.session_history(user, "PRJ-NJ-01", "conversation-a")["turns"] == []


def test_documents_are_loaded_by_module_with_page_offset() -> None:
    calls = []
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service._project_name_cache = {}
    service.client = lambda _user: object()
    service.erpnext_project_name = lambda _client, _project: "ERP-PROJECT"

    def load_group(user, doctype, label, project_child, project, limit, offset, status, owner):
        calls.append((doctype, limit, offset, status, owner))
        return {"doctype": doctype, "label": label, "documents": []}

    service._load_document_group = load_group
    result = service.documents(
        "buyer@example.com",
        "PRJ-HL-13",
        module="buying",
        status="Draft",
        page=3,
        page_size=10,
        mine_only=True,
    )

    assert result["module"] == "buying"
    assert {call[0] for call in calls} == set(MODULE.MODULE_DOCTYPES["buying"])
    assert all(call[1:] == (10, 20, "Draft", "buyer@example.com") for call in calls)


def test_documents_use_one_module_batch_request_when_bridge_supports_it() -> None:
    calls = []

    class FakeClient:
        def call_method(self, method, arguments):
            calls.append((method, arguments))
            return SimpleNamespace(ok=True, data={
                "groups": {"Material Request": [{"name": "MR-1"}]},
                "errors": {},
            })

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service._project_name_cache = {}
    service.client = lambda _user: FakeClient()
    service.erpnext_project_name = lambda _client, _project: "ERP-PROJECT"
    result = service.documents("buyer@example.com", "PRJ-HL-13", module="buying")

    assert len(calls) == 1
    assert calls[0][0] == "agent_bridge.api.list_workbench_documents"
    assert result["modules"][0]["groups"][0]["documents"] == [{"name": "MR-1"}]


def test_supplier_quotation_project_scope_follows_rfq_and_material_request() -> None:
    documents = {
        ("Supplier Quotation", "SQ-1"): {
            "name": "SQ-1",
            "items": [{
                "request_for_quotation": "RFQ-1",
                "request_for_quotation_item": "RFQI-1",
            }],
        },
        ("Request for Quotation", "RFQ-1"): {
            "name": "RFQ-1",
            "items": [{
                "name": "RFQI-1",
                "material_request": "MR-1",
                "material_request_item": "MRI-1",
            }],
        },
        ("Material Request", "MR-1"): {
            "name": "MR-1",
            "items": [{"name": "MRI-1", "project": "ERP-PROJECT"}],
        },
    }

    class FakeClient:
        def get_document(self, doctype, name):
            document = documents.get((doctype, name))
            return SimpleNamespace(ok=document is not None, data=document)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()

    rows = service.filter_parent_documents_by_project(
        "buyer@example.com",
        "Supplier Quotation",
        [{"name": "SQ-1"}, {"name": "SQ-OTHER"}],
        "ERP-PROJECT",
    )

    assert rows == [{"name": "SQ-1"}]


def test_project_document_filter_uses_one_bridge_request() -> None:
    calls = []

    class FakeClient:
        def call_method(self, method, arguments):
            calls.append((method, arguments))
            return SimpleNamespace(ok=True, data={"names": ["MR-2"]})

        def get_document(self, _doctype, _name):
            raise AssertionError("batch bridge path must not fetch documents one by one")

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    rows = service.filter_parent_documents_by_project(
        "buyer@example.com",
        "Material Request",
        [{"name": "MR-1"}, {"name": "MR-2"}],
        "ERP-PROJECT",
    )

    assert rows == [{"name": "MR-2"}]
    assert calls == [(
        "agent_bridge.api.filter_documents_by_project",
        {
            "doctype": "Material Request",
            "names": ["MR-1", "MR-2"],
            "project": "ERP-PROJECT",
        },
    )]


def test_inbox_uses_open_erpnext_workflow_actions_and_real_transitions() -> None:
    class FakeClient:
        def search_documents(self, doctype, **kwargs):
            assert doctype == "Workflow Action"
            assert kwargs["filters"] == {"status": "Open"}
            return SimpleNamespace(ok=True, data=[{
                "name": "WA-1",
                "reference_doctype": "Material Request",
                "reference_name": "MR-1",
                "workflow_state": "待材料设备主管审批",
                "modified": "2026-07-15 12:00:00",
            }], user_message=None, error=None)

        def call_method(self, method, arguments):
            assert method == "agent_bridge.api.get_document_with_workflow_actions"
            assert arguments == {"doctype": "Material Request", "name": "MR-1"}
            return SimpleNamespace(ok=True, data={
                "document": {"name": "MR-1", "title": "手套申请", "owner": "clerk@example.com"},
                "actions": [{"action": "批准"}, {"action": "驳回"}],
            })

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.erpnext_project_name = lambda _client, _project: ""

    result = service.inbox("supervisor@example.com")

    assert result["count"] == 1
    assert result["items"][0]["actions"] == ["批准", "驳回"]
    assert result["items"][0]["title"] == "手套申请"
