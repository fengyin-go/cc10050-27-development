"""规格匹配器领域服务：把站点SKU匹配到商品档案的归一规格，负责匹配置信度判定与人工复核分流。

数据链路位置：规格对齐层，消费规格归一器推送的候选规格与商品档案中心的主数据，
低置信度结果转人工复核队列，高置信度结果回填商品档案。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class SkuMatchService(BaseModuleService):
    MODULE = "sku_match"
    ENTITY = "匹配记录"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["匹配批次", "商品档案", "候选规格", "匹配置信度", "匹配状态"]
    REQUIRED_FIELDS = ["匹配批次", "商品档案", "候选规格"]
    STATUS_ORDER = ["待匹配", "已匹配", "人工复核", "匹配失败"]
    ACTION_RULES = {"执行匹配": "已匹配", "转人工复核": "人工复核"}
    NEGATIVE_ACTIONS = []

    # ---- 规格同步候选：候选实际取自同步数据，确认与撤回处理写回交接回执 ----

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _sync_rows() -> list[dict[str, Any]]:
        return store.rows("spec_sync")

    @staticmethod
    def _receipt_rows() -> list[dict[str, Any]]:
        return store.rows("spec_receipt")

    def _find_batch(self, batch_id: int) -> dict[str, Any] | None:
        for row in self._sync_rows():
            if int(row.get("id", 0)) == batch_id:
                return row
        return None

    def _receipt_for(self, batch_code: str) -> dict[str, Any] | None:
        return next(
            (r for r in self._receipt_rows() if r.get("同步批次") == batch_code), None
        )

    def _order_for(self, batch: dict[str, Any]) -> dict[str, Any] | None:
        match_id = batch.get("匹配记录ID")
        if match_id:
            order = store.find(self.MODULE, int(match_id))
            if order is not None:
                return order
        return next(
            (r for r in store.rows(self.MODULE)
             if r.get("同步批次") == batch.get("同步批次")), None
        )

    def sync_candidates(self) -> dict[str, Any]:
        """候选规格实际取自规格同步数据（快照+规则版本），不按名称现查规则。"""
        items = []
        for batch in self._sync_rows():
            if batch.get("同步状态") not in ("待匹配", "匹配中", "撤回中"):
                continue
            order = self._order_for(batch) or {}
            items.append({
                "同步批次ID": batch.get("id"),
                "同步批次": batch.get("同步批次"),
                "商品标识": batch.get("商品标识"),
                "候选规格": batch.get("归一规格"),
                "规则版本": batch.get("规则版本"),
                "同步状态": batch.get("同步状态"),
                "撤回原因": batch.get("撤回原因", ""),
                "匹配记录ID": order.get("id"),
                "匹配单状态": order.get("匹配状态", ""),
                "资格": order.get("资格", ""),
            })
        return {"ok": True, "items": items, "total": len(items)}

    def start_sync_match(self, batch_id: int) -> dict[str, Any]:
        """开始匹配同步候选：待匹配 → 匹配中，重复开始不产生第二条记录。"""
        batch = self._find_batch(batch_id)
        if batch is None:
            return {"ok": False, "message": f"同步批次 {batch_id} 不存在"}
        state = str(batch.get("同步状态", ""))
        if state == "匹配中":
            return {"ok": True, "message": "该候选已在匹配中，重复开始不产生第二条记录", "batch": batch}
        if state != "待匹配":
            return {"ok": False, "message": f"当前状态 {state} 不能开始匹配", "batch": batch}
        goods = str(batch.get("商品标识", ""))
        if not any(g.get("商品标识") == goods for g in store.rows("goods_registry")):
            return {"ok": False, "message": f"商品 {goods} 未登记，候选不可继续", "batch": batch}
        now = self._now()
        batch["同步状态"] = "匹配中"
        batch["status"] = "匹配中"
        batch["更新时间"] = now
        order = self._order_for(batch)
        if order is not None:
            order["匹配状态"] = "匹配中"
        receipt = self._receipt_for(str(batch.get("同步批次", "")))
        if receipt is not None:
            receipt["匹配方处理批次"] = batch.get("匹配批次", "")
            receipt["匹配方处理结果"] = "匹配中"
            receipt["更新时间"] = now
        return {"ok": True, "message": f"候选 {batch.get('同步批次')} 开始匹配", "batch": batch}

    def confirm_sync_match(self, batch_id: int) -> dict[str, Any]:
        """写确认：同步批次转已确认，重复确认不产生相斥结果。"""
        batch = self._find_batch(batch_id)
        if batch is None:
            return {"ok": False, "message": f"同步批次 {batch_id} 不存在"}
        state = str(batch.get("同步状态", ""))
        if state == "已确认":
            return {"ok": True, "message": "确认已存在，重复提交不产生相斥确认结果", "batch": batch}
        if state == "撤回中":
            return {"ok": False, "message": "撤回处理中，请先处理撤回再决定是否确认", "batch": batch}
        if state != "匹配中":
            return {"ok": False, "message": f"当前状态 {state} 不能写确认，需先开始匹配", "batch": batch}
        now = self._now()
        batch["同步状态"] = "已确认"
        batch["status"] = "已确认"
        batch["确认时间"] = now
        batch["更新时间"] = now
        batch["pending"] = False
        order = self._order_for(batch)
        if order is not None:
            order["status"] = "已匹配"
            order["匹配状态"] = "已确认"
            order["资格"] = "有效"
            if not str(order.get("匹配置信度", "") or "").strip():
                order["匹配置信度"] = "0.99"
            order["pending"] = False
        receipt = self._receipt_for(str(batch.get("同步批次", "")))
        if receipt is not None:
            receipt["匹配方处理批次"] = batch.get("匹配批次", "")
            receipt["匹配方处理结果"] = "已确认"
            receipt["旧成果可用性"] = "可用"
            receipt["撤回待办"] = "无"
            receipt["status"] = "已办结"
            receipt["pending"] = False
            receipt["更新时间"] = now
        return {
            "ok": True,
            "message": (
                f"批次 {batch.get('同步批次')} 已按 {batch.get('规则版本')}"
                f"（{batch.get('归一规格')}）确认"
            ),
            "batch": batch,
        }

    def resolve_sync_withdrawal(self, batch_id: int, mode: str) -> dict[str, Any]:
        """处理撤回：在途记录可用旧版处理完，或明示需用新版重做。"""
        batch = self._find_batch(batch_id)
        if batch is None:
            return {"ok": False, "message": f"同步批次 {batch_id} 不存在"}
        state = str(batch.get("同步状态", ""))
        if state != "撤回中":
            if state in ("已确认", "已撤回"):
                return {"ok": True, "message": f"撤回已办结（{state}），重复处理不产生新结果", "batch": batch}
            return {"ok": False, "message": f"当前状态 {state} 无需处理撤回", "batch": batch}
        now = self._now()
        order = self._order_for(batch)
        receipt = self._receipt_for(str(batch.get("同步批次", "")))
        if mode == "finish_old":
            batch["同步状态"] = "已确认"
            batch["status"] = "已确认"
            batch["确认时间"] = now
            batch["pending"] = False
            if order is not None:
                order["status"] = "已匹配"
                order["匹配状态"] = "旧版办结"
                order["资格"] = "有效"
                if not str(order.get("匹配置信度", "") or "").strip():
                    order["匹配置信度"] = "0.99"
                order["pending"] = False
            if receipt is not None:
                receipt["匹配方处理结果"] = "旧版办结"
                receipt["旧成果可用性"] = "可用"
                receipt["撤回待办"] = "无"
            message = f"在途记录已用旧版 {batch.get('规则版本')}（{batch.get('归一规格')}）处理完"
        elif mode == "redo_new":
            batch["同步状态"] = "已撤回"
            batch["status"] = "已撤回"
            batch["pending"] = False
            if order is not None:
                order["匹配状态"] = "需新版重做"
                order["资格"] = "已撤回"
                order["pending"] = False
            if receipt is not None:
                receipt["匹配方处理结果"] = "需新版重做"
                receipt["旧成果可用性"] = "需重做"
                receipt["撤回待办"] = "撤回已办结；需按当前规则版本重新发起同步"
            message = "已明示需用新版重做，原同步撤回"
        else:
            return {"ok": False, "message": f"未知的撤回处理方式：{mode}"}
        batch["更新时间"] = now
        if receipt is not None:
            receipt["匹配方处理批次"] = batch.get("匹配批次", "")
            receipt["status"] = "已办结"
            receipt["pending"] = False
            receipt["更新时间"] = now
        return {"ok": True, "message": message, "batch": batch, "receipt": receipt}

    def confirmed_sync_history(self, keyword: str = "") -> dict[str, Any]:
        """已确认历史匹配回查：保留资格与规则实用版本，不随规则更正回溯。"""
        items = []
        for batch in self._sync_rows():
            if batch.get("同步状态") != "已确认":
                continue
            order = self._order_for(batch) or {}
            items.append({
                "同步批次": batch.get("同步批次"),
                "商品标识": batch.get("商品标识"),
                "归一规格": batch.get("归一规格"),
                "规则版本": batch.get("规则版本"),
                "资格": order.get("资格", "有效"),
                "匹配单状态": order.get("匹配状态", ""),
                "确认时间": batch.get("确认时间", ""),
            })
        if keyword:
            items = [
                item for item in items
                if keyword.casefold() in str(item.get("同步批次", "")).casefold()
                or keyword.casefold() in str(item.get("商品标识", "")).casefold()
            ]
        return {"ok": True, "items": items, "total": len(items)}

    # ---- 业务扩展：规格匹配与置信度分流 ----

    def run_match(self, entry_id: int, confidence: float) -> dict[str, Any]:
        """执行规格匹配，按置信度分流到已匹配或人工复核。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"{self.ENTITY} {entry_id} 不存在"}
        goods_name = entry.get("商品档案", "")
        goods = next(
            (g for g in store.rows("goods_registry") if g.get("商品标识") == goods_name), None
        )
        if goods is None:
            entry["status"] = "匹配失败"
            entry["abnormal"] = True
            return {"ok": False, "message": f"商品档案 {goods_name} 不存在"}
        if confidence >= 0.95:
            entry["status"] = "已匹配"
            entry["pending"] = False
        else:
            entry["status"] = "人工复核"
            entry["pending"] = True
        entry["匹配置信度"] = f"{confidence:.2f}"
        return {
            "ok": True,
            "message": "匹配执行完成",
            "result_status": entry.get("status"),
            "confidence": entry.get("匹配置信度"),
        }

    def escalate_review(self, entry_id: int) -> dict[str, Any]:
        """把低置信度匹配记录升级到人工复核队列。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "人工复核":
            return {"ok": False, "message": "记录不存在或不处于人工复核状态"}
        rows = store.rows("match_review")
        rid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append({
            "id": rid,
            "记录编号": f"SM-{entry_id}-{rid}",
            "匹配记录": str(entry.get("id", "")),
            "复核结论": f"置信度 {entry.get('匹配置信度', '')}",
            "复核角色": "规格审核员",
            "复核时间": datetime.now(timezone.utc).isoformat(),
            "status": "待复核",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": "已升级人工复核", "review_id": rid}

    def apply_review_result(self, entry_id: int, approved: bool) -> dict[str, Any]:
        """应用复核结论：通过则回填档案，驳回则进失败隔离。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "记录不存在"}
        if approved:
            entry["status"] = "已匹配"
            entry["pending"] = False
            return {"ok": True, "message": "复核通过，匹配已确认"}
        entry["status"] = "匹配失败"
        entry["abnormal"] = True
        rows = store.rows("failure_quarantine")
        fid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append({
            "id": fid,
            "样本指纹": f"match-{entry_id}",
            "失败阶段": "匹配",
            "失败原因": "人工复核驳回",
            "隔离时间": datetime.now(timezone.utc).isoformat(),
            "重试次数": "0",
            "status": "待处理",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": "复核驳回，样本已隔离", "quarantine_id": fid}

    def consume_normalized(self, entry_id: int) -> dict[str, Any]:
        """消费规格归一器推送的候选规格完成对齐。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "记录不存在"}
        spec = entry.get("候选规格", "")
        matched_rule = next(
            (r for r in store.rows("spec_normalizer")
             if r.get("status") == "已启用" and r.get("归一规格") == spec), None
        )
        if matched_rule is None:
            entry["status"] = "匹配失败"
            entry["abnormal"] = True
            return {"ok": False, "message": f"候选规格 {spec} 没有启用中的归一规则"}
        entry["匹配状态"] = "归一对齐"
        return {
            "ok": True,
            "message": "候选规格已对齐归一规则",
            "rule": matched_rule.get("规则名称", ""),
        }

    def link_goods_baseline(self, entry_id: int) -> dict[str, Any]:
        """检查匹配成功后商品是否具备基线价格。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已匹配":
            return {"ok": False, "message": "记录不存在或未匹配"}
        goods_name = entry.get("商品档案", "")
        has_baseline = any(
            b.get("商品标识") == goods_name and b.get("status") == "已生效"
            for b in store.rows("price_baseline")
        )
        return {
            "ok": True,
            "message": "基线关联检查完成",
            "goods": goods_name,
            "has_baseline": has_baseline,
        }

    def batch_summary(self, batch: str) -> dict[str, Any]:
        """汇总匹配批次内各状态数量并上报指标。"""
        rows = [r for r in store.rows(self.MODULE) if r.get("匹配批次") == batch]
        if not rows:
            return {"ok": False, "message": f"批次 {batch} 不存在"}
        matched = sum(1 for r in rows if r.get("status") == "已匹配")
        review = sum(1 for r in rows if r.get("status") == "人工复核")
        return {
            "ok": True,
            "message": "批次汇总完成",
            "total": len(rows),
            "matched": matched,
            "need_review": review,
            "failed": len(rows) - matched - review,
        }
