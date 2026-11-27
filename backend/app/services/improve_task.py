"""诊改任务领域服务：任务分解、认领、执行、验收，含跨模块关联方案校验。

迁移期要点
----------
任务页里的「认领任务」只能领取**实际发出**的那一项：

* 如果任务带 ``回执编号``，会先查分发账本；回执仍「尚待原入口处理」时拒绝认领，
  要求回到原入口核验原回执；
* 同回执的多入口请求都落在同一项任务上，不会凭空多出一条。
"""
from __future__ import annotations

from typing import Any

from app.context import current_context, normalize_receipt
from app.services import distribution
from app.services.base import BaseModuleService
from app.services.cross_module import check_entity_status
from app.store import store


class ImproveTaskService(BaseModuleService):
    MODULE = "improve_task"
    ENTITY = "诊改任务"
    OPERATION_TERM = "认领任务"
    LIST_FIELDS = ["任务描述", "承接方案", "执行人员", "起止日期", "验收标准", "督办人员", "任务权重", "备注说明"]
    REQUIRED_FIELDS = ["任务描述", "承接方案", "执行人员"]
    STATUS_ORDER = ["草稿", "待认领", "执行中", "已验收"]
    ACTION_RULES = {"认领任务": "执行中", "启动执行": "执行中", "申请验收": "已验收"}
    NEGATIVE_ACTIONS = []

    def list_entries(self, **kwargs: Any):
        """任务列表统一带上回执视图，任务页据此显示可领取范围。"""
        items, total = super().list_entries(**kwargs)
        for item in items:
            self._annotate_task(item)
        return items, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = super().get_entry(entry_id)
        if entry is not None:
            self._annotate_task(entry)
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """创建诊改任务：承接方案引用必须是已审核通过的改进方案。"""
        source_plan = str(values.get("承接方案", "") or "").strip()

        # 尝试解析方案ID引用
        if source_plan.startswith("plan:"):
            plan_id_str = source_plan.split(":", 1)[1]
            try:
                plan_id = int(plan_id_str)
                check_entity_status(
                    "improve_plan", plan_id, ["审核通过"],
                    "诊改任务的承接方案"
                )
            except ValueError:
                pass

        return super().create_entry(values)

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """执行动作，含状态推进约束。"""
        self.ensure_writable()
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"

        self._annotate_task(entry)

        # 认领任务：只能认领实际发出的那一项
        if action == "认领任务":
            receipt, blocker = self._resolve_receipt(entry)
            if blocker:
                return None, blocker
            if entry.get("status") not in ("待认领", "草稿"):
                return None, f"{self.ENTITY} {entry_id} 当前状态为'{entry.get('status')}'，不可认领"
            result = super().run_action(entry_id, action)
            if result[0] is not None:
                distribution.ledger.mark_claimed(receipt, current_context().site)
                result[0]["claimedReceipt"] = receipt
                result[0]["claimedSite"] = current_context().label
            return result

        # 申请验收：必须已在执行中
        if action == "申请验收":
            if entry.get("status") != "执行中":
                return None, f"{self.ENTITY} {entry_id} 当前状态为'{entry.get('status')}'，必须先执行再申请验收"

        return super().run_action(entry_id, action)

    # ------------------------------------------------------------------ 回执核验
    def _annotate_task(self, entry: dict[str, Any]) -> None:
        """任务记录带上回执视图：任务页据此显示已分发/可续办/尚待原入口处理。"""
        context = current_context()
        receipt = normalize_receipt(
            entry.get("回执编号") or extract_from_entry(entry),
            int(entry.get("来源会议") or 0) or None,
        )
        if not receipt:
            return
        record = distribution.ledger.get(receipt)
        if record is None:
            return
        entry["receipt"] = receipt
        entry["receiptView"] = distribution.ledger.serialize(record, requester=context.site)
        entry["receiptStatus"] = entry["receiptView"]["status"]

    def _resolve_receipt(self, entry: dict[str, Any]) -> tuple[str | None, str | None]:
        """确认任务对应的回执确实已分发；返回 (回执号, 拦截原因)。"""
        context = current_context()
        receipt = normalize_receipt(
            context.receipt or entry.get("回执编号") or extract_from_entry(entry),
            int(entry.get("来源会议") or 0) or None,
        )

        meeting_id = entry.get("来源会议")
        if receipt and meeting_id is None:
            record = distribution.ledger.get(receipt)
            if record:
                meeting_id = record.get("meetingId")

        if not receipt or not meeting_id:
            # 手工登记的任务没有回执，按普通任务处理。
            return receipt or None, None

        record = distribution.ledger.get(receipt)
        if record is None:
            # 没有账本记录时，只有纪要本身就标着已分发/带任务号才允许认领。
            meeting = store.find("review_meeting", int(meeting_id))
            if meeting is not None and meeting.get("status") != "已分发":
                return receipt, (
                    f"{self.ENTITY} {entry.get('id')} 对应的回执 {receipt} 尚待原入口处理，"
                    f"请回到原入口核验原回执后再认领"
                )
            return receipt, None

        if int(record.get("taskId") or 0) not in (0, int(entry.get("id", 0))):
            return receipt, (
                f"{self.ENTITY} {entry.get('id')} 不是回执 {receipt} 实际发出的任务"
                f"（实际任务 #{record.get('taskId')}），请领取实际发出的那一项"
            )

        view = distribution.ledger.serialize(record, requester=context.site)
        if view["status"] == distribution.STATUS_AWAITING_ORIGIN:
            return receipt, (
                f"分发回执 {receipt} 尚待原入口处理"
                f"（原入口：{view.get('originSiteLabel')}），请回到原入口核验原回执后再认领"
            )
        return receipt, None


def extract_from_entry(entry: dict[str, Any]) -> str | None:
    for field in ("备注说明", "任务描述"):
        receipt = distribution.extract_receipt(str(entry.get(field, "") or ""))
        if receipt:
            return receipt
    return None
