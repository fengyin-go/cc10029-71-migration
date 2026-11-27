"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。

迁移期要点
----------
独立站点根路径和教务门户子路径共用**同一个** :class:`Store` 实例。每次进程启动
都会生成一个 ``instance_id``，两个入口通过同一套接口读到同一个编号空间；即使
另有同编号的演示实例（例如预览环境里的 ``demo-*`` 实例），业务写入也只允许
落在当前业务实例上，见 :meth:`Store.accepts_writes`。
"""
from __future__ import annotations

import uuid
from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self, *, kind: str = "business", instance_id: str | None = None) -> None:
        self.kind = kind
        self.instance_id = instance_id or f"{'demo' if kind == 'demo' else 'biz'}-{uuid.uuid4().hex[:8]}"
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        self._ledger: Any | None = None
        self._demo_instances: dict[str, str] = {}

    # ------------------------------------------------------------------ 实例
    def attach_ledger(self, ledger: Any) -> None:
        """挂上分发回执账本；账本与业务数据同生命周期。"""
        self._ledger = ledger

    @property
    def ledger(self) -> Any | None:
        return self._ledger

    def register_demo_instance(self, instance_id: str) -> None:
        """登记一个同编号的演示实例，便于巡检时区分它与业务实例。"""
        if instance_id and instance_id != self.instance_id:
            self._demo_instances[instance_id] = "演示实例（只读）"

    def demo_instances(self) -> dict[str, str]:
        return dict(self._demo_instances)

    def accepts_writes(self, instance_id: str | None) -> bool:
        """只有当前业务实例可以接收写入；演示实例/同编号的其它实例一律拒绝。"""
        if self.kind == "demo":
            return False
        if not instance_id:
            return True
        if str(instance_id).strip().casefold().startswith("demo"):
            return False
        return instance_id == self.instance_id

    def info(self) -> dict[str, Any]:
        return {
            "instance": self.instance_id,
            "kind": self.kind,
            "demo": self.kind == "demo",
            "modules": len(self._tables),
            "demoInstances": self.demo_instances(),
        }

    # ------------------------------------------------------------------ 数据
    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def reset(self) -> None:
        """把业务数据恢复成示例数据（测试/演示重置用），账本由调用方决定是否清空。"""
        self._tables = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules, "instance": self.instance_id}


store = Store()
