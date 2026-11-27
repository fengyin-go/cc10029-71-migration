"""教学诊改协同台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000

接口同时挂在两个前缀下，供迁移期的两个入口使用：

* 独立站点：``/api/...``
* 教务门户：``/portal/api/...``

健康检查：``GET /api/health`` / ``GET /portal/api/health``
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ALL as ALL_ROUTERS
from app.routers import distribution_legacy_router, resource_legacy_router
from app.routers import distribution_portal_router, resource_portal_router
from app.services import distribution
from app.store import store

app = FastAPI(title="教学诊改协同台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def mark_entry_site(request: Request, call_next):
    """按访问路径判断入口，回执查询/健康检查也能说明请求来自哪边。"""
    request.state.site = "portal" if request.url.path.startswith("/portal") else "legacy"
    response = await call_next(request)
    response.headers["X-Workbench-Site"] = request.state.site
    response.headers["X-Workbench-Instance"] = store.instance_id
    return response


def _health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {
        "ok": True,
        "app": settings.app_name,
        "modules": len(store.module_names()),
        "instance": store.instance_id,
        "prefixes": ["/api", "/portal/api"],
    }


def _overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()


# 固定路径必须在动态路径 ``/api/{module}`` 之前注册。
app.add_api_route("/api/health", _health, methods=["GET"], tags=["入口"])
app.add_api_route("/portal/api/health", _health, methods=["GET"], tags=["入口"])
app.add_api_route("/api/overview", _overview, methods=["GET"], tags=["入口"])
app.add_api_route("/portal/api/overview", _overview, methods=["GET"], tags=["入口"])


@app.get("/api/instance")
def instance_info() -> dict[str, object]:
    """业务实例信息：两个入口看到的 instance 必须一致。"""
    return store.info()


@app.get("/portal/api/instance")
def portal_instance_info() -> dict[str, object]:
    return store.info()


@app.post("/api/admin/reset")
@app.post("/portal/api/admin/reset")
def reset_demo_state() -> dict[str, object]:
    """演示/联调重置：恢复示例数据并清空分发账本。"""
    store.reset()
    distribution.ledger.reset()
    return {"ok": True, "instance": store.instance_id}


# 资源路由含 /api/{module}，必须放在固定路径之后、且回执路由之前注册，
# 否则固定路径会被动态路径抢先匹配。
app.include_router(distribution_legacy_router)
app.include_router(resource_legacy_router)
app.include_router(distribution_portal_router)
app.include_router(resource_portal_router)
