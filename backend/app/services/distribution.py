"""分发回执账本：独立站点与教务门户共享同一份分发记录。

背景
----
工作台从独立站点根路径迁移到教务门户子路径期间，两个入口会同时在线：

* 教师在旧地址（``/``）点「分发给教师」时，请求可能还在途中；
* 门户（``/portal``）的诊改任务页已经可以打开，可能收到同一笔分发的第二份请求。

两份请求必须落到**同一个业务实例**上，并且只能生成一项诊改任务。本模块用
进程内账本按回执号（如 ``M-56``，缺省为 ``M-<会议编号>``）串起多次请求，
对外给出三种查询状态：

``已分发``
    该回执已经完成分发，任务已实际发出；再次提交不会重复写入。
``可续办``
    分发已完成，但另一入口又提交过同一回执，且任务仍待认领，可在当前入口续办。
``尚待原入口处理``
    原入口的分发请求仍在途中（或尚未满足分发条件），当前入口只登记、不写入，
    需要回到原入口核验原回执。

账本只保存回执的元信息，业务数据仍然只存在于 :mod:`app.store` 里唯一的一份，
因此两个入口看到的任务编号完全一致；同编号的演示实例不会收到写入。
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any

from app.context import (
    ActionContext,
    RECEIPT_PATTERN,
    default_receipt,
    normalize_receipt,
    site_label,
)
from app.store import store

STATUS_DISTRIBUTED = "已分发"
STATUS_RESUMABLE = "可续办"
STATUS_AWAITING_ORIGIN = "尚待原入口处理"

PENDING = "pending"
DISTRIBUTED = "distributed"

__all__ = [
    "STATUS_DISTRIBUTED",
    "STATUS_RESUMABLE",
    "STATUS_AWAITING_ORIGIN",
    "ActionContext",
    "DistributionLedger",
    "default_receipt",
    "extract_receipt",
    "get_by_meeting",
    "get_by_receipt",
    "ledger",
    "normalize_receipt",
    "register_pending",
    "site_label",
]


def extract_receipt(text: str | None) -> str | None:
    """从备注/说明里识别 M-56 形式的回执号。"""
    if not text:
        return None
    match = RECEIPT_PATTERN.search(str(text))
    return match.group(0).upper() if match else None


class DistributionLedger:
    """线程安全的分发回执账本，挂在唯一 store 实例上。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    # ------------------------------------------------------------------ 基础
    def _key(self, receipt: str) -> str:
        return str(receipt).strip().casefold()

    def get(self, receipt: str | None) -> dict[str, Any] | None:
        if not receipt:
            return None
        with self._lock:
            record = self._records.get(self._key(receipt))
            return dict(record) if record is not None else None

    def _raw(self, receipt: str) -> dict[str, Any] | None:
        return self._records.get(self._key(receipt))

    def all(self, requester: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self.serialize(record, requester=requester)
                for record in self._records.values()
            ]

    def for_meeting(
        self, meeting_id: int, requester: str | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self.serialize(record, requester=requester)
                for record in self._records.values()
                if int(record.get("meetingId", -1)) == int(meeting_id)
            ]

    def reset(self) -> None:
        with self._lock:
            self._records.clear()

    # ------------------------------------------------------------------ 内部
    def _new_record(
        self, receipt: str, meeting_id: int, origin_site: str, state: str
    ) -> dict[str, Any]:
        now = time.time()
        record: dict[str, Any] = {
            "receipt": receipt,
            "meetingId": int(meeting_id),
            "taskId": None,
            "state": state,
            "originSite": origin_site,
            "sites": [origin_site],
            "requests": 0,
            "events": [],
            "duplicate": False,
            "claimed": False,
            "claimedSite": None,
            "lastError": "",
            "storeInstance": store.instance_id,
            "createdAt": now,
            "updatedAt": now,
        }
        self._records[self._key(receipt)] = record
        return record

    def _touch(self, record: dict[str, Any]) -> None:
        record["updatedAt"] = time.time()
        record["storeInstance"] = store.instance_id

    def _ensure(
        self, receipt: str, meeting_id: int, site: str, state: str
    ) -> dict[str, Any]:
        record = self._raw(receipt)
        if record is None:
            return self._new_record(receipt, meeting_id, site, state)
        if int(record.get("meetingId", -1)) != int(meeting_id):
            raise ValueError(
                f"分发回执 {receipt} 已绑定会议纪要 #{record.get('meetingId')}，"
                f"不能用于 #{meeting_id}"
            )
        if site not in record["sites"]:
            record["sites"].append(site)
            if site != record.get("originSite"):
                record["duplicate"] = True
        return record

    def adopt_origin(self, receipt: str, meeting_id: int, site: str) -> dict[str, Any]:
        """把回执归到真正完成分发的入口名下。

        场景：原入口先用默认回执号 ``M-<纪要编号>`` 预告在途，随后实际用的却是
        另一个回执号（如 ``M-56``）。真正落地的入口在完成分发时调用本方法，
        把在途占位记录迁移到实际回执号上，避免出现两张回执、两项任务。
        """
        with self._lock:
            actual = self._raw(receipt)
            placeholder = self._raw(default_receipt(meeting_id))
            if (
                placeholder is not None
                and placeholder is not actual
                and placeholder.get("state") == PENDING
                and int(placeholder.get("meetingId", -1)) == int(meeting_id)
            ):
                del self._records[self._key(default_receipt(meeting_id))]
                if actual is None:
                    placeholder["receipt"] = receipt
                    self._records[self._key(receipt)] = placeholder
                    actual = placeholder
            return self._ensure(receipt, meeting_id, site, PENDING)

    # ------------------------------------------------------------------ 状态变更
    def begin(self, receipt: str, meeting_id: int, site: str) -> dict[str, Any]:
        """登记一笔分发请求；同回执重复调用只累加请求数、补记来源入口。"""
        with self._lock:
            record = self._ensure(receipt, meeting_id, site, PENDING)
            record["requests"] = int(record.get("requests", 0)) + 1
            record.setdefault("events", []).append(
                {"site": site, "outcome": "request", "at": time.time()}
            )
            self._touch(record)
            return dict(record)

    def note_request(self, receipt: str, site: str, outcome: str) -> dict[str, Any] | None:
        """记录一次重复/被拦截的请求，不改变业务状态。"""
        with self._lock:
            record = self._raw(receipt)
            if record is None:
                return None
            record["requests"] = int(record.get("requests", 0)) + 1
            if site not in record["sites"]:
                record["sites"].append(site)
                if site != record.get("originSite"):
                    record["duplicate"] = True
            record.setdefault("events", []).append(
                {"site": site, "outcome": outcome, "at": time.time()}
            )
            self._touch(record)
            return dict(record)

    def note_completed(
        self,
        receipt: str,
        meeting_id: int,
        task_id: int | None,
        site: str = "legacy",
    ) -> dict[str, Any]:
        """标记回执已完成分发；同回执只补全任务号，不重复建任务。"""
        with self._lock:
            record = self._ensure(receipt, meeting_id, site, DISTRIBUTED)
            record["state"] = DISTRIBUTED
            if task_id is not None:
                record["taskId"] = int(task_id)
            # 完成分发的入口就是原入口；另一入口再提交时才记为重复/可续办。
            record["originSite"] = site
            record["lastError"] = ""
            self._touch(record)
            return dict(record)

    def mark_pending(self, receipt: str, error: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._raw(receipt)
            if record is None:
                return None
            record["state"] = PENDING
            record["lastError"] = str(error or "")
            self._touch(record)
            return dict(record)

    def mark_claimed(self, receipt: str | None, site: str) -> None:
        if not receipt:
            return
        with self._lock:
            record = self._raw(receipt)
            if record is None:
                return
            record["claimed"] = True
            record["claimedSite"] = site
            self._touch(record)

    # ------------------------------------------------------------------ 查询
    def status_of(self, receipt: str | None) -> str:
        record = self.get(receipt)
        if record is None:
            return ""
        return str(self.serialize(record)["status"])

    def is_distributed(self, receipt: str | None) -> bool:
        record = self.get(receipt)
        return bool(record and record.get("state") == DISTRIBUTED)

    def task_id_of(self, receipt: str | None) -> int | None:
        record = self.get(receipt)
        if not record:
            return None
        task_id = record.get("taskId")
        return int(task_id) if task_id is not None else None

    def serialize(
        self,
        record: dict[str, Any],
        *,
        requester: str | None = None,
        just_completed: bool = False,
    ) -> dict[str, Any]:
        """把内部记录整理成教学端可读的回执视图。

        ``requester`` 是当前查看/提交的入口：同一张回执从另一个入口再提交时，
        返回「可续办」，便于负责教师判断该在哪边继续办。
        """
        record = dict(record)
        task_id = record.get("taskId")
        task = store.find("improve_task", int(task_id)) if task_id is not None else None
        state = str(record.get("state") or PENDING)

        # 「可续办」只对另一个入口成立：任务已实际发出、仍待认领，
        # 且当前查看/提交的不是完成分发的那个入口。原入口始终看到「已分发」。
        task_open = task is not None and str(task.get("status")) in ("草稿", "待认领")
        from_other_entry = bool(requester and requester != record.get("originSite"))

        if state == PENDING:
            status = STATUS_AWAITING_ORIGIN
        elif just_completed:
            status = STATUS_DISTRIBUTED
        elif task_open and from_other_entry:
            status = STATUS_RESUMABLE
        else:
            status = STATUS_DISTRIBUTED

        if status == STATUS_AWAITING_ORIGIN:
            message = (
                f"分发回执 {record['receipt']} 尚待原入口处理"
                f"（原入口：{site_label(record.get('originSite'))}）"
            )
        elif status == STATUS_RESUMABLE:
            message = (
                f"分发回执 {record['receipt']} {STATUS_RESUMABLE}："
                f"已分发，任务 #{task_id} 可在当前入口续办"
            )
        else:
            message = f"分发回执 {record['receipt']} {STATUS_DISTRIBUTED}"
            if task_id is not None:
                message += f"，对应任务 #{task_id}"

        return {
            "requester": requester,
            "receipt": record.get("receipt"),
            "meetingId": record.get("meetingId"),
            "taskId": task_id,
            "taskStatus": task.get("status") if task else None,
            "status": status,
            "distributed": state == DISTRIBUTED,
            "canResume": status == STATUS_RESUMABLE,
            "awaitingOriginal": status == STATUS_AWAITING_ORIGIN,
            "duplicate": bool(record.get("duplicate")),
            "claimed": bool(record.get("claimed")),
            "originSite": record.get("originSite"),
            "originSiteLabel": site_label(record.get("originSite")),
            "sites": list(record.get("sites") or []),
            "requestCount": int(record.get("requests", 0)),
            "lastError": record.get("lastError", ""),
            "storeInstance": record.get("storeInstance") or store.instance_id,
            "updatedAt": record.get("updatedAt"),
            "message": message,
        }


ledger = DistributionLedger()

# 挂到 store 上，便于服务层与巡检脚本从同一处读取。
store.attach_ledger(ledger)


def get_by_receipt(
    receipt: str | None, requester: str | None = None
) -> dict[str, Any] | None:
    record = ledger.get(receipt)
    if record is not None:
        return ledger.serialize(record, requester=requester)
    # M-56 这类回执号也允许回退按会议编号回查，兼容只记了纪要编号的场景。
    match = re.fullmatch(r"[Mm]-(\d+)", str(receipt or "").strip())
    if match:
        records = ledger.for_meeting(int(match.group(1)), requester=requester)
        if records:
            latest = sorted(records, key=lambda item: item.get("updatedAt") or 0)[-1]
            if requester:
                raw = ledger.get(latest.get("receipt"))
                if raw is not None:
                    return ledger.serialize(raw, requester=requester)
            return latest
    return None


def get_by_meeting(meeting_id: int, requester: str | None = None) -> dict[str, Any] | None:
    records = ledger.for_meeting(meeting_id)
    if not records:
        return None
    latest_raw = max(
        (ledger.get(item.get("receipt")) for item in records),
        key=lambda item: (item or {}).get("updatedAt") or 0,
        default=None,
    )
    latest = (
        ledger.serialize(latest_raw, requester=requester)
        if latest_raw is not None
        else sorted(records, key=lambda item: item.get("updatedAt") or 0)[-1]
    )
    latest["receipts"] = records
    return latest


def register_pending(
    receipt: str | None, meeting_id: int, site: str = "legacy"
) -> dict[str, Any]:
    """显式登记一笔尚在途中的分发（可由原入口在发出请求前调用）。"""
    normalized = normalize_receipt(receipt, meeting_id)
    record = ledger.begin(normalized, meeting_id, site)
    return ledger.serialize(record)
