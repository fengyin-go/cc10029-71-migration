"""分发回执接口：两个入口共用，用于查询/登记同一笔分发的处理状态。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas import ActionResult, DistributionBeginPayload
from app.services import distribution
from app.store import store


def site_of(request: Request) -> str:
    return "portal" if request.url.path.startswith("/portal") else "legacy"


def _check_instance(instance: str | None) -> None:
    if instance and not store.accepts_writes(instance):
        raise HTTPException(
            status_code=409,
            detail=(
                f"实例 {instance} 是演示实例，不能接收写入；"
                f"当前业务实例为 {store.instance_id}"
            ),
        )


def build_router(prefix: str, *, tag: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("/receipts")
    def list_receipts(
        request: Request, meetingId: int | None = Query(default=None)
    ) -> dict[str, Any]:
        site = site_of(request)
        items = (
            distribution.ledger.for_meeting(meetingId, requester=site)
            if meetingId is not None
            else distribution.ledger.all(requester=site)
        )
        return {"items": items, "total": len(items), "instance": store.instance_id}

    @router.get("/receipts/{receipt}")
    def get_receipt(receipt: str, request: Request) -> dict[str, Any]:
        view = distribution.get_by_receipt(receipt, requester=site_of(request))
        if view is None:
            raise HTTPException(status_code=404, detail=f"回执 {receipt} 尚未登记")
        return view

    @router.get("/meetings/{meeting_id}/receipt")
    def get_meeting_receipt(meeting_id: int, request: Request) -> dict[str, Any]:
        view = distribution.get_by_meeting(meeting_id, requester=site_of(request))
        if view is None:
            raise HTTPException(status_code=404, detail=f"会议纪要 {meeting_id} 暂无分发回执")
        return view

    @router.post("/receipts", response_model=ActionResult)
    def begin_receipt(payload: DistributionBeginPayload, request: Request) -> ActionResult:
        """原入口在发出分发请求前登记回执，另一个入口可据此显示「尚待原入口处理」。"""
        _check_instance(payload.instance)
        try:
            # 未声明来源时按访问前缀判断；原入口在根路径发出时就记为 legacy。
            view = distribution.register_pending(
                receipt=payload.receipt,
                meeting_id=payload.meetingId,
                site=payload.site or site_of(request),
            )
        except ValueError as error:
            return ActionResult(ok=False, message=str(error))
        return ActionResult(
            ok=True,
            message=f"分发回执 {view['receipt']} 已登记，尚待原入口处理",
            status=view["status"],
            receipt=view,
        )

    return router


legacy_router = build_router("/api", tag="分发回执")
portal_router = build_router("/portal/api", tag="分发回执（教务门户）")
router = legacy_router
