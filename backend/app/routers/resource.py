"""统一资源接口：查询、导出、登记和动作按模块 key 分派到领域服务。

迁移期两个入口
--------------
* 独立站点沿用根路径：``/api/...``
* 教务门户走子路径：``/portal/api/...``

两套路径由**同一批路由**、同一个 :class:`app.store.Store` 实例处理，所以任务
编号、纪要编号在两个入口完全一致；同编号的演示实例不会被写入。
"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from contextlib import contextmanager

from app.context import ActionContext, extract_receipt, reset_context, set_context
from app.schemas import (
    ActionPayload,
    ActionResult,
    DistributionBeginPayload,
    EntryPayload,
    PageResult,
)
from app.services import distribution, service_for
from app.services.base import WriteRejected
from app.store import store

LEGACY_PREFIX = "/api"
PORTAL_PREFIX = "/portal/api"


def require_service(module: str):
    service = service_for(module)
    if service is None:
        raise HTTPException(status_code=404, detail=f"未知业务模块：{module}")
    return service


def build_context(payload: ActionPayload | EntryPayload | None, request: Request) -> ActionContext:
    """从请求体 + 查询参数还原入口信息；查询参数优先便于浏览器直接打开链接。"""
    params = request.query_params
    site = params.get("site") or (getattr(payload, "site", None) if payload else None)
    instance = params.get("instance") or (getattr(payload, "instance", None) if payload else None)
    receipt = params.get("receipt") or (getattr(payload, "receipt", None) if payload else None)
    in_flight = params.get("inFlight") in ("1", "true", "True") or bool(
        getattr(payload, "inFlight", False) if payload else False
    )
    request_id = params.get("requestId") or (
        getattr(payload, "requestId", None) if payload else None
    )
    # 未显式声明时按访问前缀判断入口：门户走 /portal，旧地址走根路径。
    default_site = "portal" if request.url.path.startswith("/portal") else "legacy"
    return ActionContext(
        site=site or default_site,
        receipt=receipt,
        instance=instance,
        request_id=request_id,
        in_flight=in_flight,
    )


@contextmanager
def request_context(context: ActionContext):
    """把入口信息带进领域服务：读请求也要知道自己在哪个入口。"""
    token = set_context(context)
    try:
        yield context
    finally:
        reset_context(token)


def ensure_writable_or_400(context: ActionContext) -> None:
    if not store.accepts_writes(context.instance):
        raise HTTPException(
            status_code=409,
            detail=(
                f"实例 {context.instance} 是演示实例，不能接收写入；"
                f"当前业务实例为 {store.instance_id}"
            ),
        )


def entry_with_receipt(
    entry: dict[str, Any] | None, requester: str | None = None
) -> dict[str, Any] | None:
    """给返回的记录补上回执视图，便于前端直接渲染核验信息。"""
    if entry is None:
        return None
    enriched = dict(entry)
    receipt = entry.get("回执编号") or extract_receipt(str(entry.get("备注说明", "") or ""))
    if receipt:
        view = distribution.get_by_receipt(receipt, requester=requester)
        if view:
            enriched["receiptView"] = view
            enriched.setdefault("receipt", view.get("receipt"))
    meeting_id = entry.get("来源会议")
    if meeting_id is not None and not receipt:
        view = distribution.get_by_meeting(int(meeting_id), requester=requester)
        if view:
            enriched["receiptView"] = view
    return enriched


def site_of(request: Request) -> str:
    return "portal" if request.url.path.startswith("/portal") else "legacy"


def _list(module: str, request: Request, keyword, status, page, size) -> PageResult[dict]:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    context = build_context(None, request)
    with request_context(context):
        items, total = service.list_entries(
            filters=filters, keyword=keyword, status=status, page=page, size=size)
    return PageResult(
        items=[entry_with_receipt(item, context.site) or item for item in items],
        total=total, page=page, size=size, instance=store.instance_id,
    )


def _export(module: str, request: Request, keyword, status) -> StreamingResponse:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    with request_context(build_context(None, request)):
        items, _ = service.list_entries(
            filters=filters, keyword=keyword, status=status, page=1, size=1_000_000)
    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", *service.LIST_FIELDS, "status"])
    for item in items:
        values = [item.get("id"), *(item.get(field, "") for field in service.LIST_FIELDS),
                  item.get("status", "")]
        writer.writerow([
            "'" + str(value) if str(value or "").startswith(("=", "+", "-", "@")) else value
            for value in values
        ])
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{module}.csv"'},
    )


def _get(module: str, entry_id: int, request: Request) -> dict[str, Any]:
    service = require_service(module)
    context = build_context(None, request)
    with request_context(context):
        entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{service.ENTITY} {entry_id} 不存在或已归档")
    return entry_with_receipt(entry, context.site) or entry


def _create(module: str, payload: EntryPayload, request: Request) -> ActionResult:
    service = require_service(module)
    context = build_context(payload, request)
    ensure_writable_or_400(context)
    try:
        with request_context(context):
            entry, missing = service.create_entry(payload.values)
    except WriteRejected as error:
        return ActionResult(ok=False, message=str(error))
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(
        ok=True, message=f"{service.ENTITY}已登记",
        entry=entry_with_receipt(entry, context.site), status="created",
    )


def _action(module: str, entry_id: int, payload: ActionPayload, request: Request) -> ActionResult:
    service = require_service(module)
    context = build_context(payload, request)
    ensure_writable_or_400(context)
    try:
        with request_context(context):
            entry, message = service.run_action(entry_id, payload.action.strip())
    except WriteRejected as error:
        return ActionResult(ok=False, message=str(error))

    receipt_view = None
    receipt = context.receipt or extract_receipt(str(entry or ""))
    if entry is not None and entry.get("回执编号"):
        receipt = entry.get("回执编号")
    requester = context.site
    if receipt:
        receipt_view = distribution.get_by_receipt(str(receipt), requester=requester)
    if receipt_view is None and entry is not None and entry.get("来源会议") is not None:
        receipt_view = distribution.get_by_meeting(int(entry["来源会议"]), requester=requester)

    return ActionResult(
        ok=entry is not None,
        message=message,
        entry=entry_with_receipt(entry, context.site),
        status=receipt_view.get("status") if receipt_view else None,
        receipt=receipt_view,
    )


# ---------------------------------------------------------------------- 路由工厂
def build_router(prefix: str, *, tag: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("/{module}", response_model=PageResult[dict])
    def list_entries(
        module: str,
        request: Request,
        keyword: str | None = Query(default=None),
        status: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        size: int = Query(default=20, ge=1, le=200),
    ) -> PageResult[dict]:
        return _list(module, request, keyword, status, page, size)

    @router.get("/{module}/export")
    def export_entries(
        module: str,
        request: Request,
        keyword: str | None = Query(default=None),
        status: str | None = Query(default=None),
    ) -> StreamingResponse:
        return _export(module, request, keyword, status)

    @router.get("/{module}/{entry_id}", response_model=dict)
    def get_entry(module: str, entry_id: int, request: Request) -> dict[str, Any]:
        return _get(module, entry_id, request)

    @router.post("/{module}", response_model=ActionResult)
    def create_entry(module: str, payload: EntryPayload, request: Request) -> ActionResult:
        return _create(module, payload, request)

    @router.post("/{module}/{entry_id}/actions", response_model=ActionResult)
    def run_action(
        module: str, entry_id: int, payload: ActionPayload, request: Request
    ) -> ActionResult:
        return _action(module, entry_id, payload, request)

    return router


legacy_router = build_router(LEGACY_PREFIX, tag="业务资源")
portal_router = build_router(PORTAL_PREFIX, tag="业务资源（教务门户）")

# 兼容旧引用：默认导出根路径那一套。
router = legacy_router
