"""双入口路由级测试：直接驱动 ASGI 应用，不依赖额外 HTTP 客户端。

校验两套前缀（``/api`` 与 ``/portal/api``）在同一个进程里指向同一业务实例，
并覆盖页面资源、下载接口与演示实例拒收写入。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.main import app
from app.services import distribution
from app.store import store


def reset_all() -> None:
    store.reset()
    distribution.ledger.reset()


@pytest.fixture(autouse=True)
def clean():
    reset_all()
    yield
    reset_all()


def http(method: str, path: str, body: dict | None = None) -> tuple[int, dict[str, Any]]:
    """最小的 ASGI 调用器：够用就好，避免给运行时加测试专用依赖。"""
    raw = json.dumps(body).encode() if body is not None else b""
    sent: list[dict[str, Any]] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path.split("?")[0],
        "raw_path": path.split("?")[0].encode(),
        "query_string": path.split("?", 1)[1].encode() if "?" in path else b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(raw)).encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": raw, "more_body": False}
        # 流式响应会并行监听断开事件：稍等片刻，让响应体先发完。
        await asyncio.sleep(0.05)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))

    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), 0)
    payload = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    headers = next(
        (dict(m.get("headers") or []) for m in sent if m["type"] == "http.response.start"), {}
    )
    if b"application/json" in headers.get(b"content-type", b""):
        return status, json.loads(payload or b"{}")
    return status, {"_raw": payload.decode("utf-8", "replace"),
                    "_content_type": headers.get(b"content-type", b"").decode()}


def create_meeting(site: str, prefix: str, receipt: str = "M-56") -> int:
    status, body = http("POST", f"{prefix}/review_meeting?site={site}", {
        "values": {
            "会议主题": f"迁移期复盘 {receipt}",
            "参会人员": "全体教师",
            "召开日期": "2026-11-01",
            "决议事项": "成立任务组并落实改进",
            "备注说明": f"回执 {receipt}",
        }
    })
    assert status == 200 and body["ok"], body
    return body["entry"]["id"]


class TestDualPrefix:
    def test_health_and_overview_agree_on_instance(self):
        _, legacy = http("GET", "/api/health")
        _, portal = http("GET", "/portal/api/health")
        assert legacy["instance"] == portal["instance"] == store.instance_id

    def test_both_prefixes_read_same_records(self):
        _, legacy = http("GET", "/api/review_meeting")
        _, portal = http("GET", "/portal/api/review_meeting")
        assert [row["id"] for row in legacy["items"]] == [row["id"] for row in portal["items"]]

    def test_asset_and_export_paths_work_on_both_entries(self):
        status, body = http("GET", "/api/review_meeting/export")
        assert status == 200 and body["_content_type"].startswith("text/csv")
        status, body = http("GET", "/portal/api/review_meeting/export")
        assert status == 200 and body["_content_type"].startswith("text/csv")
        assert "id," in body["_raw"]


class TestDemoInstanceRejected:
    def test_write_to_demo_instance_is_409(self):
        status, body = http(
            "POST", "/portal/api/review_meeting?instance=demo-0001&site=portal",
            {"values": {"会议主题": "演示", "参会人员": "无", "召开日期": "2026-01-01"}},
        )
        assert status == 409
        assert "演示实例" in body["detail"]
        assert not any(
            row.get("会议主题") == "演示" for row in store.rows("review_meeting")
        )


class TestEndToEndReceiptFlow:
    def test_in_flight_then_distribute_then_claim_across_entries(self):
        meeting_id = create_meeting("legacy", "/api")
        http("POST", f"/api/review_meeting/{meeting_id}/actions?site=legacy",
             {"action": "签认纪要"})
        http("POST", "/api/receipts", {"meetingId": meeting_id, "receipt": "M-56", "site": "legacy"})

        status, portal_try = http(
            "POST",
            f"/portal/api/review_meeting/{meeting_id}/actions?site=portal&receipt=M-56",
            {"action": "分发给教师"},
        )
        assert status == 200 and portal_try["ok"] is False
        assert portal_try["status"] == "尚待原入口处理"
        assert portal_try["entry"] is None

        status, legacy_done = http(
            "POST",
            f"/api/review_meeting/{meeting_id}/actions?site=legacy&receipt=M-56",
            {"action": "分发给教师"},
        )
        assert status == 200 and legacy_done["ok"] is True
        task_id = legacy_done["entry"]["taskId"]

        status, portal_dup = http(
            "POST",
            f"/portal/api/review_meeting/{meeting_id}/actions?site=portal&receipt=M-56",
            {"action": "分发给教师"},
        )
        assert status == 200 and portal_dup["status"] == "可续办"

        # 任务页只出现一项实际发出的任务。
        _, tasks = http("GET", "/portal/api/improve_task?site=portal")
        auto = [row for row in tasks["items"] if f"meeting:{meeting_id}" in str(row["任务描述"])]
        assert len(auto) == 1 and auto[0]["id"] == task_id
        assert auto[0]["receiptStatus"] == "可续办"

        # 门户领取
        status, claim = http(
            "POST",
            f"/portal/api/improve_task/{task_id}/actions?site=portal&receipt=M-56",
            {"action": "认领任务"},
        )
        assert status == 200 and claim["ok"] is True
        assert claim["entry"]["claimedSite"] == "教务门户"

        # 回原入口核对：任务编号仍指回原纪要。
        _, legacy_task = http("GET", f"/api/improve_task/{task_id}?site=legacy")
        _, legacy_meeting = http("GET", f"/api/review_meeting/{meeting_id}?site=legacy")
        assert legacy_task["来源会议"] == meeting_id
        assert legacy_meeting["taskId"] == task_id
        assert legacy_meeting["receipt"] == "M-56"

        # 旧收藏的纪要深链与门户链接读到同一条记录。
        status, old_link = http("GET", f"/api/review_meeting/{meeting_id}")
        status_portal, portal_link = http("GET", f"/portal/api/review_meeting/{meeting_id}")
        assert status == 200 and status_portal == 200
        assert old_link["id"] == portal_link["id"] == meeting_id
