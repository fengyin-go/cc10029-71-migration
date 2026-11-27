"""模块服务基类：共享查询、登记、动作和统计骨架，业务差异留在各模块文件。"""
from __future__ import annotations

from typing import Any

from app.context import current_context, normalize_receipt
from app.store import store


class WriteRejected(Exception):
    """写入被拒：请求试图落到演示实例或非当前业务实例上。"""


class BaseModuleService:
    MODULE = ""
    ENTITY = ""
    LIST_FIELDS: list[str] = []
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER: list[str] = []
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS: list[str] = []

    # ------------------------------------------------------------------ 写入守卫
    def ensure_writable(self) -> None:
        """只允许写入当前业务实例；同编号的演示实例一律拒收。"""
        context = current_context()
        if not context.instance:
            return
        if not store.accepts_writes(context.instance):
            raise WriteRejected(
                f"请求指向实例 {context.instance}，当前业务实例为 {store.instance_id}，"
                f"演示实例不能接收写入"
            )

    def stamp(self, entry: dict[str, Any], action: str | None = None) -> None:
        """在业务记录上留下最后一次写入的入口与回执，便于回切核验。"""
        context = current_context()
        entry["lastActionSite"] = context.label
        if action:
            entry["lastAction"] = action
        if context.receipt:
            entry["lastActionReceipt"] = normalize_receipt(context.receipt)
        entry["storeInstance"] = store.instance_id

    # ------------------------------------------------------------------ 查询
    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(self.MODULE))
        for field, expected in (filters or {}).items():
            if field in self.LIST_FIELDS:
                rows = [
                    row for row in rows
                    if expected.casefold() in str(row.get(field, "")).casefold()
                ]
        if keyword and self.LIST_FIELDS:
            field = self.LIST_FIELDS[0]
            rows = [row for row in rows if keyword.casefold() in str(row.get(field, "")).casefold()]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = (page - 1) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(self.MODULE, entry_id)

    # ------------------------------------------------------------------ 登记
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        self.ensure_writable()
        missing = [
            field for field in self.REQUIRED_FIELDS
            if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, missing
        rows = store.rows(self.MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in self.LIST_FIELDS})
        entry["status"] = self.STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        self.stamp(entry)
        rows.append(entry)
        return entry, []

    # ------------------------------------------------------------------ 动作
    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        self.ensure_writable()
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        target = self.ACTION_RULES.get(action)
        if target is None:
            return None, f"动作「{action}」不属于{self.MODULE}可执行范围"
        entry["status"] = target
        entry["pending"] = target != self.STATUS_ORDER[-1]
        entry["abnormal"] = action in self.NEGATIVE_ACTIONS
        self.stamp(entry, action)
        return entry, f"{self.ENTITY}已{action}"

    # ------------------------------------------------------------------ 统计
    def domain_snapshot(self) -> dict[str, Any]:
        """返回本模块的状态统计与业务对象，供其他模块读取。"""
        rows = store.rows(self.MODULE)
        by_status = {
            status: sum(1 for row in rows if row.get("status") == status)
            for status in self.STATUS_ORDER
        }
        return {
            "module": self.MODULE,
            "entity": self.ENTITY,
            "artifact": f"{self.ENTITY}状态记录",
            "count": len(rows),
            "by_status": by_status,
            "abnormal": sum(1 for row in rows if row.get("abnormal")),
        }
