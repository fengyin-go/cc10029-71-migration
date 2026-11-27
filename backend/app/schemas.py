"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20
    instance: str | None = None


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None
    status: str | None = None
    receipt: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None
    site: str | None = None
    instance: str | None = None
    receipt: str | None = None


class ActionPayload(BaseModel):
    action: str
    remark: str | None = None
    # 迁移期双入口信息：谁发起的、带哪张回执、指向哪个业务实例。
    site: str | None = None
    instance: str | None = None
    receipt: str | None = None
    requestId: str | None = None
    # 旧入口把分发请求发出但尚未落地时置 True：只登记回执，等原入口完成。
    inFlight: bool = False

    model_config = {"populate_by_name": True}


class DistributionBeginPayload(BaseModel):
    meetingId: int
    receipt: str | None = None
    site: str | None = None
    instance: str | None = None
