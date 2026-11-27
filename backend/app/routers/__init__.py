"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。

同一组路由按两个前缀各注册一次：

* ``/api`` —— 独立站点（旧地址，收藏链接继续可用）
* ``/portal/api`` —— 教务门户子路径

两者指向同一个 :class:`app.store.Store` 实例。回执路由必须先于通用
``/{module}`` 注册，否则 ``/api/receipts`` 会被当成一个业务模块。
"""
from __future__ import annotations

from app.routers import distributions, resource

ROUTERS = [distributions, resource]

# 旧引用：根路径那一套。
LEGACY = [module.legacy_router for module in ROUTERS]
PORTAL = [module.portal_router for module in ROUTERS]

# 每个前缀内部：固定路径（回执）在前，通用资源在后。
distribution_legacy_router = distributions.legacy_router
distribution_portal_router = distributions.portal_router
resource_legacy_router = resource.legacy_router
resource_portal_router = resource.portal_router

ALL = [distribution_legacy_router, resource_legacy_router,
       distribution_portal_router, resource_portal_router]
