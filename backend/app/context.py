"""请求上下文：一次动作请求从哪个入口来、带哪张回执、是否允许写入。

迁移期独立站点（``legacy``）和教务门户（``portal``）同时在线，同一个动作可能
从两边各发一次。把入口信息随请求带到领域服务里，才能做到：

* 只允许写入当前业务实例（同编号的演示实例拒收写入）；
* 同一张回执的多次请求收敛到同一条业务记录；
* 需要人工核验时，能说明「尚待原入口处理」还是「已分发/可续办」。

上下文用 :class:`contextvars.ContextVar` 传递，领域服务的方法签名不用为每个
模块都加参数，直接调用服务的旧代码（含测试）也仍然可用。
"""
from __future__ import annotations

import re
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

RECEIPT_PATTERN = re.compile(r"\bM-\d+\b", re.IGNORECASE)

SITE_LABELS = {"legacy": "独立站点", "portal": "教务门户"}


def site_label(site: str | None) -> str:
    """把内部 site 标识换成老师能看懂的中文名称。"""
    return SITE_LABELS.get(str(site or ""), str(site or "未知入口"))


def normalize_site(site: str | None) -> str:
    value = str(site or "").strip().casefold()
    return value if value in SITE_LABELS else "legacy"


def default_receipt(meeting_id: int) -> str:
    """没有显式回执号时，用会议编号生成稳定回执号（M-56 即第 56 号纪要）。"""
    return f"M-{int(meeting_id)}"


def normalize_receipt(receipt: str | None, meeting_id: int | None = None) -> str:
    value = str(receipt or "").strip()
    if not value:
        if meeting_id is None:
            return ""
        return default_receipt(meeting_id)
    return value.upper() if value.upper().startswith("M-") else value


def extract_receipt(text: str | None) -> str | None:
    """从备注/说明里识别 M-56 形式的回执号。"""
    if not text:
        return None
    match = RECEIPT_PATTERN.search(str(text))
    return match.group(0).upper() if match else None


@dataclass
class ActionContext:
    """一次动作请求的来源信息：入口、回执号、业务实例。"""

    site: str = "legacy"
    receipt: str | None = None
    instance: str | None = None
    request_id: str | None = None
    in_flight: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.site = normalize_site(self.site)
        if self.receipt:
            self.receipt = normalize_receipt(self.receipt)

    @property
    def label(self) -> str:
        return site_label(self.site)

    def copy(self, **changes: Any) -> "ActionContext":
        data = {
            "site": self.site,
            "receipt": self.receipt,
            "instance": self.instance,
            "request_id": self.request_id,
            "in_flight": self.in_flight,
            "extra": dict(self.extra),
        }
        data.update(changes)
        return ActionContext(**data)


_DEFAULT_CONTEXT = ActionContext()
_current: ContextVar[ActionContext] = ContextVar("action_context", default=_DEFAULT_CONTEXT)


def current_context() -> ActionContext:
    return _current.get()


def set_context(context: ActionContext) -> Token[ActionContext]:
    return _current.set(context)


def reset_context(token: Token[ActionContext]) -> None:
    _current.reset(token)
