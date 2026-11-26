"""规格同步交接接口：归一器与匹配工作台之间的同步批次、撤回与交接回执。

状态流转全部落在 app/services，路由只负责参数解析与分派。
注意：本路由必须先于通用资源路由注册，否则 /api/spec-sync/xxx
会被 /api/{module}/{entry_id} 抢先匹配。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services import service_for
from app.services.sku_match import SkuMatchService
from app.services.spec_normalizer import SpecNormalizerService

router = APIRouter(prefix="/api/spec-sync", tags=["规格同步交接"])


def _normalizer() -> SpecNormalizerService:
    service = service_for("spec_normalizer")
    assert isinstance(service, SpecNormalizerService)
    return service


def _matcher() -> SkuMatchService:
    service = service_for("sku_match")
    assert isinstance(service, SkuMatchService)
    return service


class SubmitSyncPayload(BaseModel):
    rule_id: int
    goods: str = ""


class WithdrawPayload(BaseModel):
    reason: str = ""


class CorrectPayload(BaseModel):
    归一规格: str
    源规格文本: str = ""


class ResolvePayload(BaseModel):
    mode: str = Field(pattern="^(finish_old|redo_new)$")


# ---- 归一器侧：核对已启用规格、查询原批次、发起/继续/撤回同步 ----

@router.get("/enabled-rules")
def enabled_rules() -> dict[str, Any]:
    """运营核对：已启用归一规格及当前规则实用版本。"""
    return _normalizer().enabled_rule_view()


@router.get("/batches")
def sync_batches(
    keyword: str = Query(default=""),
    status: str = Query(default=""),
) -> dict[str, Any]:
    """查询原同步批次：商品、规格快照与规则实用版本。"""
    return _normalizer().sync_batches(keyword=keyword.strip(), status=status.strip())


@router.post("/batches")
def submit_sync(payload: SubmitSyncPayload) -> dict[str, Any]:
    """发起规格同步；同一同步中断后重复提交按幂等键归并。"""
    return _normalizer().submit_sync(payload.rule_id, payload.goods)


@router.post("/batches/{batch_id}/continue")
def continue_sync(batch_id: int) -> dict[str, Any]:
    """中断后继续原同步，不产生第二条等待匹配。"""
    return _normalizer().continue_sync(batch_id)


@router.post("/batches/{batch_id}/withdraw")
def withdraw_sync(batch_id: int, payload: WithdrawPayload) -> dict[str, Any]:
    """从规格页面申请撤回，接收方同时操作原匹配单。"""
    return _normalizer().withdraw_sync(batch_id, payload.reason)


@router.post("/rules/{rule_id}/correct")
def correct_rule(rule_id: int, payload: CorrectPayload) -> dict[str, Any]:
    """规则更正：升级规则实用版本并对在途同步触发撤回。"""
    return _normalizer().correct_rule(rule_id, payload.归一规格, payload.源规格文本)


@router.get("/receipts")
def handover_receipts(keyword: str = Query(default="")) -> dict[str, Any]:
    """规格交接回执：匹配方实际处理批次与撤回待办。"""
    return _normalizer().handover_receipts(keyword=keyword.strip())


# ---- 匹配工作台侧：从同步数据选取候选、写确认、处理撤回 ----

@router.get("/candidates")
def sync_candidates() -> dict[str, Any]:
    """候选规格实际取自规格同步数据。"""
    return _matcher().sync_candidates()


@router.post("/batches/{batch_id}/start")
def start_match(batch_id: int) -> dict[str, Any]:
    return _matcher().start_sync_match(batch_id)


@router.post("/batches/{batch_id}/confirm")
def confirm_match(batch_id: int) -> dict[str, Any]:
    return _matcher().confirm_sync_match(batch_id)


@router.post("/batches/{batch_id}/resolve")
def resolve_withdrawal(batch_id: int, payload: ResolvePayload) -> dict[str, Any]:
    return _matcher().resolve_sync_withdrawal(batch_id, payload.mode)


@router.get("/confirmed")
def confirmed_history(keyword: str = Query(default="")) -> dict[str, Any]:
    """已确认历史匹配回查：资格与规则实用版本。"""
    return _matcher().confirmed_sync_history(keyword=keyword.strip())
