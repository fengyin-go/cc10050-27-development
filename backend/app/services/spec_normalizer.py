"""规格归一器领域服务：管理各平台规格文本的归一规则与单位换算，负责统一规格口径。

数据链路位置：数据标准化层，把解析层产出的多平台规格文本归一为统一规格，
归一结果供价格基线库与规格匹配器消费。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class SpecNormalizerService(BaseModuleService):
    MODULE = "spec_normalizer"
    ENTITY = "规格归一规则"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["规则名称", "源规格文本", "归一规格", "单位换算", "映射优先级"]
    REQUIRED_FIELDS = ["规则名称", "源规格文本", "归一规格"]
    STATUS_ORDER = ["草稿", "已启用", "已停用"]
    ACTION_RULES = {"启用规则": "已启用", "停用规则": "已停用"}
    NEGATIVE_ACTIONS = ["停用规则"]

    # 同步批次状态机：撤回与不可继续是两个不同的终态，已确认历史不回溯。
    SYNC_STATUSES = ["待匹配", "匹配中", "已确认", "撤回中", "已撤回", "不可继续"]
    SYNC_TERMINAL = ("已撤回", "不可继续")

    # ---- 规格同步批次与交接回执 ----

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _sync_rows() -> list[dict[str, Any]]:
        return store.rows("spec_sync")

    @staticmethod
    def _receipt_rows() -> list[dict[str, Any]]:
        return store.rows("spec_receipt")

    @staticmethod
    def _rule_version(rule: dict[str, Any]) -> str:
        return str(rule.get("规则版本") or "v1")

    @staticmethod
    def _bump_version(version: str) -> str:
        digits = "".join(ch for ch in version if ch.isdigit())
        return f"v{int(digits) + 1}" if digits else f"{version}+1"

    def _find_batch(self, batch_id: int) -> dict[str, Any] | None:
        for row in self._sync_rows():
            if int(row.get("id", 0)) == batch_id:
                return row
        return None

    def _receipt_for(self, batch_code: str) -> dict[str, Any] | None:
        return next(
            (r for r in self._receipt_rows() if r.get("同步批次") == batch_code), None
        )

    def _match_order_for(self, batch: dict[str, Any]) -> dict[str, Any] | None:
        match_id = batch.get("匹配记录ID")
        if match_id:
            order = store.find("sku_match", int(match_id))
            if order is not None:
                return order
        return next(
            (r for r in store.rows("sku_match")
             if r.get("同步批次") == batch.get("同步批次")), None
        )

    @staticmethod
    def _goods_registered(goods: str) -> bool:
        return any(g.get("商品标识") == goods for g in store.rows("goods_registry"))

    def enabled_rule_view(self) -> dict[str, Any]:
        """运营核对页：已启用归一规格及其当前规则实用版本。"""
        rules = [
            {
                "id": rule.get("id"),
                "规则名称": rule.get("规则名称", ""),
                "规则版本": self._rule_version(rule),
                "源规格文本": rule.get("源规格文本", ""),
                "归一规格": rule.get("归一规格", ""),
                "单位换算": rule.get("单位换算", ""),
                "status": rule.get("status"),
            }
            for rule in store.rows(self.MODULE)
            if rule.get("status") == "已启用"
        ]
        return {"ok": True, "rules": rules}

    def sync_batches(self, keyword: str = "", status: str = "") -> dict[str, Any]:
        """查询同步批次：按原批次号或商品检索，返回规格快照与规则实用版本。"""
        rows = list(self._sync_rows())
        if keyword:
            rows = [
                row for row in rows
                if keyword.casefold() in str(row.get("同步批次", "")).casefold()
                or keyword.casefold() in str(row.get("商品标识", "")).casefold()
            ]
        if status:
            rows = [row for row in rows if row.get("同步状态") == status]
        return {"ok": True, "items": rows, "total": len(rows)}

    def handover_receipts(self, keyword: str = "") -> dict[str, Any]:
        """查询规格交接回执：匹配方实际处理批次与撤回待办。"""
        rows = list(self._receipt_rows())
        if keyword:
            rows = [
                row for row in rows
                if keyword.casefold() in str(row.get("同步批次", "")).casefold()
                or keyword.casefold() in str(row.get("回执编号", "")).casefold()
            ]
        return {"ok": True, "items": rows, "total": len(rows)}

    def _next_batch_code(self, rule_name: str, goods: str) -> str:
        base = f"SYNC-{rule_name}-{goods}"
        existing = {str(r.get("同步批次", "")) for r in self._sync_rows()}
        if base not in existing:
            return base
        seq = 2
        while f"{base}-{seq}" in existing:
            seq += 1
        return f"{base}-{seq}"

    @staticmethod
    def _create_match_order(
        *, batch_code: str, rule_id: Any, version: str, spec: str, goods: str,
    ) -> int:
        """按同步快照落一条原匹配单；候选规格取自同步数据而非现查规则。"""
        rows = store.rows("sku_match")
        mid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append({
            "id": mid,
            "匹配批次": goods,
            "商品档案": goods,
            "候选规格": spec,
            "匹配置信度": "",
            "匹配状态": "待匹配",
            "同步批次": batch_code,
            "规则ID": rule_id,
            "规则版本": version,
            "资格": "有效",
            "status": "待匹配",
            "pending": True,
            "abnormal": False,
        })
        return mid

    def _create_receipt(self, batch: dict[str, Any], now: str) -> dict[str, Any]:
        rows = self._receipt_rows()
        receipt = {
            "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
            "回执编号": f"RCPT-{batch['同步批次']}",
            "同步批次": batch["同步批次"],
            "规则ID": batch["规则ID"],
            "规则名称": batch["规则名称"],
            "规则版本": batch["规则版本"],
            "商品标识": batch["商品标识"],
            "归一规格": batch["归一规格"],
            "匹配方处理批次": "",
            "匹配方处理结果": "待处理",
            "旧成果可用性": "待判定",
            "撤回待办": "无",
            "交接时间": now,
            "更新时间": now,
            "status": "待处理",
            "pending": True,
            "abnormal": False,
        }
        rows.append(receipt)
        return receipt

    def submit_sync(self, rule_id: int, goods: str) -> dict[str, Any]:
        """发起规格同步：锁定规则实用版本快照，幂等键防中断后重复提交。"""
        rule = store.find(self.MODULE, rule_id)
        if rule is None:
            return {"ok": False, "message": f"归一规则 {rule_id} 不存在"}
        if rule.get("status") != "已启用":
            return {"ok": False, "message": "归一规则未启用，不能发起同步"}
        goods = goods.strip()
        if not goods:
            return {"ok": False, "message": "商品标识不能为空"}
        if not self._goods_registered(goods):
            return {"ok": False, "message": f"商品 {goods} 未在商品登记中心登记"}
        version = self._rule_version(rule)
        idem_key = f"{rule_id}|{version}|{goods}"
        # 中断后重复提交：命中未完结的同一同步，直接返回原批次，
        # 不产生第二条等待匹配，也不会出现相斥确认。
        for row in self._sync_rows():
            if row.get("幂等键") == idem_key and row.get("同步状态") not in self.SYNC_TERMINAL:
                return {
                    "ok": True,
                    "reused": True,
                    "message": f"同一同步已存在（{row.get('同步批次')}，{row.get('同步状态')}），继续原同步",
                    "batch": row,
                }
        now = self._now()
        batch_code = self._next_batch_code(str(rule.get("规则名称", "")), goods)
        match_id = self._create_match_order(
            batch_code=batch_code, rule_id=rule_id, version=version,
            spec=str(rule.get("归一规格", "")), goods=goods,
        )
        batch = {
            "id": max((int(r.get("id", 0)) for r in self._sync_rows()), default=0) + 1,
            "同步批次": batch_code,
            "规则ID": rule_id,
            "规则名称": rule.get("规则名称", ""),
            "规则版本": version,
            "商品标识": goods,
            "归一规格": rule.get("归一规格", ""),
            "源规格文本": rule.get("源规格文本", ""),
            "幂等键": idem_key,
            "匹配记录ID": match_id,
            "匹配批次": goods,
            "同步状态": "待匹配",
            "撤回原因": "",
            "创建时间": now,
            "更新时间": now,
            "确认时间": "",
            "status": "待匹配",
            "pending": True,
            "abnormal": False,
        }
        self._sync_rows().append(batch)
        self._create_receipt(batch, now)
        return {
            "ok": True,
            "reused": False,
            "message": f"同步批次 {batch_code} 已交接匹配工作台",
            "batch": batch,
        }

    def continue_sync(self, batch_id: int) -> dict[str, Any]:
        """中断后继续原同步：幂等返回当前状态，必要时按快照补建原匹配单。"""
        batch = self._find_batch(batch_id)
        if batch is None:
            return {"ok": False, "message": f"同步批次 {batch_id} 不存在"}
        state = str(batch.get("同步状态", ""))
        if state == "已撤回":
            return {"ok": False, "message": "该同步已撤回，请按当前规则版本重新发起", "batch": batch}
        if state == "不可继续":
            reason = batch.get("撤回原因") or "商品或规则不可用"
            return {"ok": False, "message": f"该同步不可继续（{reason}），与撤回状态区分处理", "batch": batch}
        if state == "已确认":
            return {"ok": True, "message": "该同步已确认，重复提交不会产生相斥确认", "batch": batch}
        if state == "撤回中":
            return {"ok": True, "message": "撤回处理中，等待匹配方处理原匹配单", "batch": batch}
        goods = str(batch.get("商品标识", ""))
        if not self._goods_registered(goods):
            now = self._now()
            batch["同步状态"] = "不可继续"
            batch["status"] = "不可继续"
            batch["撤回原因"] = f"商品 {goods} 已不在商品登记中心"
            batch["更新时间"] = now
            order = self._match_order_for(batch)
            if order is not None:
                order["匹配状态"] = "不可继续"
                order["资格"] = "不可继续"
            receipt = self._receipt_for(str(batch.get("同步批次", "")))
            if receipt is not None:
                receipt["匹配方处理结果"] = "不可继续"
                receipt["撤回待办"] = "无"
                receipt["status"] = "已办结"
                receipt["pending"] = False
                receipt["更新时间"] = now
            return {"ok": False, "message": f"商品 {goods} 已不可匹配，同步转为不可继续", "batch": batch}
        if self._match_order_for(batch) is None:
            # 中断丢单恢复：按同步快照补建，不按名称现查规则。
            batch["匹配记录ID"] = self._create_match_order(
                batch_code=str(batch.get("同步批次", "")),
                rule_id=batch.get("规则ID"),
                version=str(batch.get("规则版本", "v1")),
                spec=str(batch.get("归一规格", "")),
                goods=goods,
            )
            batch["更新时间"] = self._now()
            return {"ok": True, "message": "原匹配单缺失，已按同步快照补建，继续原同步", "batch": batch}
        return {
            "ok": True,
            "message": f"继续原同步（{state}），未产生重复等待匹配",
            "batch": batch,
        }

    def withdraw_sync(self, batch_id: int, reason: str = "") -> dict[str, Any]:
        """从规格页面申请同步撤回：接收方同时操作原匹配单。"""
        batch = self._find_batch(batch_id)
        if batch is None:
            return {"ok": False, "message": f"同步批次 {batch_id} 不存在"}
        state = str(batch.get("同步状态", ""))
        if state == "已确认":
            return {"ok": False, "message": "已确认的历史匹配不可撤回，可回查资格与版本", "batch": batch}
        if state == "不可继续":
            return {"ok": False, "message": "该同步当前不可继续，与撤回状态区分，无需再撤回", "batch": batch}
        if state == "已撤回":
            return {"ok": True, "message": "该同步已撤回，重复申请不产生新撤回单", "batch": batch}
        if state == "撤回中":
            return {"ok": True, "message": "撤回申请已存在，等待匹配方处理原匹配单", "batch": batch}
        now = self._now()
        batch["同步状态"] = "撤回中"
        batch["status"] = "撤回中"
        batch["撤回原因"] = reason.strip() or "运营申请撤回"
        batch["更新时间"] = now
        order = self._match_order_for(batch)
        if order is not None:
            order["匹配状态"] = "撤回中"
        receipt = self._receipt_for(str(batch.get("同步批次", "")))
        if receipt is not None:
            receipt["撤回待办"] = f"待匹配方处理原匹配单 {batch.get('匹配批次', '')}"
            receipt["更新时间"] = now
        return {
            "ok": True,
            "message": "撤回申请已提交，匹配方同步处理原匹配单",
            "batch": batch,
            "receipt": receipt,
        }

    def correct_rule(self, rule_id: int, new_spec: str, new_source: str = "") -> dict[str, Any]:
        """规则更正：升级规则实用版本，在途同步触发撤回，已确认历史不回溯。"""
        rule = store.find(self.MODULE, rule_id)
        if rule is None:
            return {"ok": False, "message": f"归一规则 {rule_id} 不存在"}
        new_spec = new_spec.strip()
        if not new_spec:
            return {"ok": False, "message": "新归一规格不能为空"}
        old_version = self._rule_version(rule)
        new_version = self._bump_version(old_version)
        rule["规则版本"] = new_version
        rule["归一规格"] = new_spec
        if new_source.strip():
            rule["源规格文本"] = new_source.strip()
        withdrawn: list[str] = []
        for batch in list(self._sync_rows()):
            if int(batch.get("规则ID", 0)) != rule_id:
                continue
            if batch.get("规则版本") != old_version:
                continue
            if batch.get("同步状态") not in ("待匹配", "匹配中"):
                continue
            result = self.withdraw_sync(
                int(batch["id"]), reason=f"规则更正为 {new_version}（{new_spec}）"
            )
            if result.get("ok"):
                withdrawn.append(str(batch.get("同步批次", "")))
        return {
            "ok": True,
            "message": (
                f"规则已更正为 {new_version}（{new_spec}），"
                f"在途撤回 {len(withdrawn)} 批，已确认历史仍可回查"
            ),
            "规则版本": new_version,
            "withdrawn": withdrawn,
        }

    # ---- 业务扩展：规格归一与口径统一 ----

    def enable_rule(self, entry_id: int) -> dict[str, Any]:
        """启用归一规则，检查源文本与归一规格是否成对配置。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"{self.ENTITY} {entry_id} 不存在"}
        source = entry.get("源规格文本", "")
        target = entry.get("归一规格", "")
        if not source or not target:
            return {"ok": False, "message": "源规格文本与归一规格必须成对配置"}
        priority = str(entry.get("映射优先级", "") or "")
        if not priority.isdigit():
            entry["映射优先级"] = "1"
        entry["status"] = "已启用"
        entry["pending"] = False
        return {"ok": True, "message": f"规则 {entry.get('规则名称', '')} 已启用"}

    def normalize_text(self, entry_id: int, raw_text: str) -> dict[str, Any]:
        """按归一规则把原始规格文本转换为统一规格口径。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已启用":
            return {"ok": False, "message": "归一规则不存在或未启用"}
        source = entry.get("源规格文本", "")
        if source and source not in raw_text:
            return {"ok": False, "message": "规格文本与规则源文本不匹配"}
        unit = entry.get("单位换算", "")
        normalized = entry.get("归一规格", raw_text)
        return {
            "ok": True,
            "message": "规格已归一",
            "normalized": normalized,
            "unit": unit,
            "priority": entry.get("映射优先级", "1"),
        }

    def sync_to_baseline(self, entry_id: int) -> dict[str, Any]:
        """把归一规格同步到价格基线库，标记对应基线待重算。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "归一规则不存在"}
        normalized = entry.get("归一规格", "")
        affected = 0
        for base in store.rows("price_baseline"):
            if base.get("归一规格") == normalized:
                base["status"] = "待重算"
                base["pending"] = True
                affected += 1
        return {
            "ok": True,
            "message": "归一规格已同步基线",
            "affected_baselines": affected,
            "normalized": normalized,
        }

    def push_to_sku_match(self, entry_id: int) -> dict[str, Any]:
        """把归一规则推送到规格匹配器作为候选规格。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已启用":
            return {"ok": False, "message": "归一规则不存在或未启用"}
        rows = store.rows("sku_match")
        mid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append({
            "id": mid,
            "匹配批次": f"norm-{entry_id}-{datetime.now(timezone.utc).timestamp():.0f}",
            "商品档案": "",
            "候选规格": entry.get("归一规格", ""),
            "匹配置信度": "1.00",
            "匹配状态": "待匹配",
            "status": "待匹配",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": "候选规格已推送匹配器", "match_id": mid}

    def detect_conflicts(self, entry_id: int) -> dict[str, Any]:
        """检测与其他启用规则是否存在源文本重叠冲突。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "归一规则不存在"}
        source = entry.get("源规格文本", "")
        conflicts = [
            r.get("规则名称", "") for r in store.rows(self.MODULE)
            if r.get("id") != entry.get("id") and r.get("status") == "已启用"
            and source and source in str(r.get("源规格文本", ""))
        ]
        if conflicts:
            entry["status"] = "草稿"
            entry["pending"] = True
        return {
            "ok": True,
            "message": "冲突检测完成",
            "conflicts": conflicts,
            "rule_status": entry.get("status"),
        }

    def archive_stale_rules(self, days: int = 30) -> dict[str, Any]:
        """停用长期未启用的规则并归档到审计明细。"""
        now = datetime.now(timezone.utc)
        stale = [
            r for r in store.rows(self.MODULE) if r.get("status") == "草稿"
        ]
        for rule in stale:
            rule["status"] = "已停用"
            rule["abnormal"] = False
        rows = store.rows("parse_audit")
        aid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append({
            "id": aid,
            "审计时间": now.isoformat(),
            "解析模板": "规格归一规则清理",
            "样本总数": str(len(stale)),
            "字段命中率": "100.00%",
            "失败原因分布": "",
            "status": "正常",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"已停用 {len(stale)} 条草稿规则", "archived": len(stale)}
