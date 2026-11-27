"""复盘会议领域服务：会议纪要登记、签认、分发，含跨模块决议分发到诊改任务。

迁移期的分发语义
----------------
同一笔分发可能从独立站点（旧地址）和教务门户各收到一份请求，任务只能实际
发出一次。本服务按回执号（``M-56``，缺省 ``M-<会议编号>``）把两份请求收敛到
同一条纪要、同一项诊改任务，并在响应里告诉老师当前属于哪种情况：

* ``已分发``：任务已发出，重复请求不再写入；
* ``可续办``：另一边也提交过但任务仍待认领，可在当前入口继续办理；
* ``尚待原入口处理``：原入口的请求仍在途中，本次只登记回执、不创建任务。
"""
from __future__ import annotations

from typing import Any

from app.context import current_context, extract_receipt, normalize_receipt, site_label
from app.services import distribution
from app.services.base import BaseModuleService
from app.store import store


class ReviewMeetingService(BaseModuleService):
    MODULE = "review_meeting"
    ENTITY = "会议纪要"
    OPERATION_TERM = "签认纪要"
    LIST_FIELDS = ["会议主题", "参会人员", "召开日期", "决议事项", "分歧观点", "记录人员", "下次会议", "备注说明"]
    REQUIRED_FIELDS = ["会议主题", "参会人员", "召开日期"]
    STATUS_ORDER = ["草稿", "待签认", "已签认", "已分发"]
    ACTION_RULES = {"签认纪要": "已签认", "提出异议": "草稿", "分发给教师": "已分发"}
    NEGATIVE_ACTIONS = []

    def list_entries(self, **kwargs: Any):
        """纪要列表带上回执视图，旧链接打开时能看到分发/任务号。"""
        items, total = super().list_entries(**kwargs)
        for item in items:
            self._annotate_meeting(item)
        return items, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = super().get_entry(entry_id)
        if entry is not None:
            self._annotate_meeting(entry)
        return entry

    def _annotate_meeting(self, meeting: dict[str, Any]) -> None:
        meeting_id = int(meeting.get("id", 0))
        receipt = meeting.get("receipt") or extract_receipt(
            str(meeting.get("备注说明", "") or "")
        )
        record = (
            distribution.ledger.get(receipt) if receipt
            else None
        )
        if record is None:
            records = distribution.ledger.for_meeting(meeting_id)
            if records:
                latest_receipt = max(
                    records, key=lambda item: item.get("updatedAt") or 0
                ).get("receipt")
                record = distribution.ledger.get(latest_receipt)
        if record is None:
            return
        meeting["receipt"] = record.get("receipt")
        meeting["taskId"] = record.get("taskId")
        meeting["receiptView"] = distribution.ledger.serialize(
            record, requester=current_context().site
        )

    # ------------------------------------------------------------------ 登记
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        entry, missing = super().create_entry(values)
        if entry is None:
            return entry, missing
        receipt = extract_receipt(str(values.get("备注说明", "") or ""))
        if receipt:
            entry["receipt"] = receipt
        return entry, missing

    # ------------------------------------------------------------------ 动作
    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """执行动作，含跨模块联动：分发时创建关联诊改任务。"""
        self.ensure_writable()
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"

        if action == "分发给教师":
            return self._distribute(entry)

        # 签认纪要先通过待签认状态
        if action == "签认纪要":
            if entry.get("status") not in ("待签认", "草稿"):
                return None, f"{self.ENTITY} {entry_id} 当前状态为'{entry.get('status')}'，不可签认"

        return super().run_action(entry_id, action)

    # ------------------------------------------------------------------ 分发
    def _receipt_of(self, meeting: dict[str, Any]) -> str:
        """回执号优先级：请求显式携带 → 纪要自身回执 → 备注里的 M-号 → M-<纪要编号>。"""
        context = current_context()
        meeting_id = int(meeting.get("id", 0))
        return normalize_receipt(
            context.receipt
            or meeting.get("receipt")
            or extract_receipt(str(meeting.get("备注说明", "") or "")),
            meeting_id,
        )

    def _distribute(self, meeting: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        context = current_context()
        meeting_id = int(meeting.get("id", 0))
        receipt = self._receipt_of(meeting)

        # 本次请求只是「已发出、尚未落地」的预告：登记回执，不写业务数据。
        if context.in_flight:
            record = distribution.ledger.get(receipt)
            if record is not None and record.get("state") == distribution.DISTRIBUTED:
                return self._repeat_distribution(meeting, receipt)
            distribution.ledger.begin(receipt, meeting_id, context.site)
            distribution.ledger.mark_pending(receipt, "原入口请求仍在途中")
            return None, (
                f"分发回执 {receipt} 已登记，尚待原入口处理"
                f"（原入口：{site_label(context.site)}），本次未写入"
            )

        # 已经分发过：重复请求只补记回执，不重复写入。
        record = distribution.ledger.get(receipt)
        if record is not None and record.get("state") == distribution.DISTRIBUTED:
            return self._repeat_distribution(meeting, receipt)

        # 原入口的请求还在途中：另一个入口只登记，不抢写业务数据。
        if (
            record is not None
            and record.get("state") == distribution.PENDING
            and context.site != record.get("originSite")
        ):
            distribution.ledger.note_request(receipt, context.site, "awaiting-origin")
            return None, (
                f"分发回执 {receipt} 尚待原入口处理"
                f"（原入口：{site_label(record.get('originSite'))}），本次未写入"
            )

        if meeting.get("status") != "已签认":
            # 尚未签认：登记回执，让另一个入口随时能查到「尚待原入口处理」。
            distribution.ledger.begin(receipt, meeting_id, context.site)
            distribution.ledger.mark_pending(receipt, "纪要尚未签认")
            return None, (
                f"{self.ENTITY} {meeting_id} 必须先签认纪要，才能分发"
                f"（回执 {receipt} 已登记，尚待原入口处理）"
            )

        with distribution.ledger.lock:
            record = distribution.ledger.get(receipt)
            if record is not None and record.get("state") == distribution.DISTRIBUTED:
                return self._repeat_distribution(meeting, receipt)

            # 首次真正分发：先登记回执，再写会议与任务，最后落账。
            distribution.ledger.adopt_origin(receipt, meeting_id, context.site)
            distribution.ledger.begin(receipt, meeting_id, context.site)
            result_entry, message = super().run_action(meeting_id, "分发给教师")
            if result_entry is None:
                distribution.ledger.mark_pending(receipt, message)
                return result_entry, message

            task = self._maybe_create_improve_task(
                str(meeting.get("会议主题", "")),
                str(meeting.get("决议事项", "")),
                meeting_id,
                receipt,
            )
            task_id = int(task["id"]) if task else None
            completed = distribution.ledger.note_completed(
                receipt, meeting_id, task_id, context.site
            )
            result_entry["receipt"] = receipt
            self._sync_meeting_links(meeting, task)
            result_entry["receiptView"] = distribution.ledger.serialize(
                completed, requester=context.site, just_completed=True
            )
            result_entry["receiptStatus"] = distribution.STATUS_DISTRIBUTED
            if task_id is not None:
                result_entry["taskId"] = task_id
                message += f"，已生成诊改任务 #{task_id}（回执 {receipt}）"
            else:
                message += f"（回执 {receipt}）"
            self.stamp(result_entry, "分发给教师")
            return result_entry, message

    def _repeat_distribution(
        self, meeting: dict[str, Any], receipt: str
    ) -> tuple[dict[str, Any] | None, str]:
        """同一回执再次分发：不重复建任务，按当前情况给已分发/可续办。"""
        context = current_context()
        with distribution.ledger.lock:
            distribution.ledger.note_request(receipt, context.site, "duplicate")
            record = distribution.ledger.get(receipt) or {}
            task_id = record.get("taskId")
            task = store.find("improve_task", int(task_id)) if task_id is not None else None
            self._sync_meeting_links(meeting, task)
            view = distribution.ledger.serialize(
                record, requester=context.site
            )
        meeting["receipt"] = receipt
        if view.get("canResume"):
            return meeting, f"分发回执 {receipt} {distribution.STATUS_RESUMABLE}：已分发，任务 #{task_id} 可在当前入口续办"
        return meeting, f"分发回执 {receipt} {distribution.STATUS_DISTRIBUTED}，无需重复创建任务（任务 #{task_id}）"

    # ------------------------------------------------------------------ 任务联动
    def _maybe_create_improve_task(
        self, theme: str, resolution: str, meeting_id: int, receipt: str | None = None
    ) -> dict[str, Any] | None:
        """根据会议决议创建诊改任务：同回执同会议只创建一次。"""
        task_rows = store.rows("improve_task")
        receipt = normalize_receipt(receipt, meeting_id)

        # 幂等检查：回执优先，其次回退到会议引用标记。
        for row in task_rows:
            if str(row.get("回执编号", "")) == receipt:
                return row
        for row in task_rows:
            if f"meeting:{meeting_id}" in str(row.get("任务描述", "")):
                return row

        if not resolution or "任务" not in str(resolution):
            return None

        new_id = max((int(r.get("id", 0)) for r in task_rows), default=0) + 1
        task = {
            "id": new_id,
            "任务描述": f"会议决议：{theme} [meeting:{meeting_id}]",
            "承接方案": resolution,
            "执行人员": "",
            "起止日期": "",
            "验收标准": "",
            "督办人员": "",
            "任务权重": "",
            "备注说明": "由复盘会议决议自动生成",
            "回执编号": receipt,
            "来源会议": int(meeting_id),
            "status": "待认领",
            "pending": True,
            "abnormal": False,
            "storeInstance": store.instance_id,
        }
        task_rows.append(task)
        return task

    def _sync_meeting_links(
        self, meeting: dict[str, Any], task: dict[str, Any] | None
    ) -> None:
        """把回执与任务号补回纪要，两个入口读到的编号保持一致。"""
        if task is None:
            return
        meeting["receipt"] = meeting.get("receipt") or task.get("回执编号")
        meeting.setdefault("taskId", int(task["id"]))
