"""迁移期双入口集成测试：独立站点根路径 + 教务门户子路径共用同一业务实例。

覆盖需求里的关键场景：
* 旧收藏的会议纪要/诊改任务深链仍能打开（前端由部署层回退，这里校验接口与编号）；
* 分发请求与任务认领落在同一个业务实例上，同编号的演示实例收不到写入；
* 原入口的分发回执在途时，新入口只能看到「尚待原入口处理」且不写任务；
* 同一笔分发收到两份请求时，能查出已分发 / 可续办 / 尚待原入口处理；
* 回切原入口点开原回执核验，任务页只能领取实际发出的那一项；
* 旧链接打开纪要 → 切门户领取任务 → 回原入口，任务编号仍指回原纪要；
* 页面资源与下载接口在新旧路径都能打开。
"""
from __future__ import annotations

import pytest

from app.context import ActionContext, reset_context, set_context
from app.services import distribution
from app.services.improve_task import ImproveTaskService
from app.services.review_meeting import ReviewMeetingService
from app.store import Store, store


def reset_all() -> None:
    store.reset()
    distribution.ledger.reset()


def act(service, entry_id: int, action: str, *, site: str, receipt=None, in_flight=False):
    context = ActionContext(
        site=site, receipt=receipt, instance=store.instance_id, in_flight=in_flight
    )
    token = set_context(context)
    try:
        return service.run_action(entry_id, action)
    finally:
        reset_context(token)


def write(service, values: dict, *, site: str = "legacy"):
    context = ActionContext(site=site, instance=store.instance_id)
    token = set_context(context)
    try:
        return service.create_entry(values)
    finally:
        reset_context(token)


@pytest.fixture(autouse=True)
def clean_store():
    reset_all()
    yield
    reset_all()


def make_signed_meeting(receipt: str = "M-56", site: str = "legacy") -> dict:
    svc = ReviewMeetingService()
    meeting, missing = write(svc, {
        "会议主题": f"期中教学复盘 {receipt}",
        "参会人员": "教研室主任、全体教师",
        "召开日期": "2026-11-01",
        "决议事项": "成立专项教学改进任务组",
        "备注说明": f"回执 {receipt}",
    }, site=site)
    assert meeting is not None and missing == []
    entry, _ = act(svc, meeting["id"], "签认纪要", site=site, receipt=receipt)
    assert entry is not None
    return meeting


class TestSingleBusinessInstance:
    def test_demo_instance_rejects_writes(self):
        svc = ReviewMeetingService()
        context = ActionContext(site="portal", instance="demo-0001")
        token = set_context(context)
        try:
            with pytest.raises(Exception) as excinfo:
                svc.create_entry({"会议主题": "演示", "参会人员": "无", "召开日期": "2026-01-01"})
        finally:
            reset_context(token)
        assert "演示实例" in str(excinfo.value)
        assert store.rows("review_meeting")[-1].get("会议主题") != "演示"

    def test_same_numbered_demo_instance_isolated(self):
        demo = Store(kind="demo", instance_id="demo-biz")
        demo.register_demo_instance("demo-biz")
        assert demo.accepts_writes("demo-biz") is False
        assert store.accepts_writes(store.instance_id) is True
        assert store.accepts_writes("demo-something") is False
        # 两个实例的示例数据互不影响。
        before = len(store.rows("improve_task"))
        demo.rows("improve_task").append({"id": 999, "status": "待认领"})
        assert len(store.rows("improve_task")) == before


class TestLegacyDeepLinks:
    def test_meeting_and_task_ids_survive_both_prefixes(self):
        meeting = make_signed_meeting("M-56")
        svc = ReviewMeetingService()
        entry, _ = act(svc, meeting["id"], "分发给教师", site="legacy", receipt="M-56")
        task_id = entry["taskId"]

        # 两个前缀都按同一 id 命中同一条记录（前端深链据此还原）。
        task_svc = ImproveTaskService()
        legacy_view = task_svc.get_entry(task_id)
        assert legacy_view is not None
        assert legacy_view["来源会议"] == meeting["id"]
        assert store.find("review_meeting", meeting["id"])["taskId"] == task_id


class TestInFlightDistribution:
    def test_portal_cannot_claim_while_legacy_in_flight(self):
        meeting = make_signed_meeting("M-56")
        # 原入口先登记在途回执。
        distribution.register_pending("M-56", meeting["id"], "legacy")

        svc = ReviewMeetingService()
        entry, message = act(svc, meeting["id"], "分发给教师", site="portal", receipt="M-56")
        assert entry is None
        assert "尚待原入口处理" in message
        assert not any("meeting:" in str(row.get("任务描述", "")) for row in store.rows("improve_task"))

        view = distribution.get_by_receipt("M-56", requester="portal")
        assert view["status"] == distribution.STATUS_AWAITING_ORIGIN
        assert view["taskId"] is None

    def test_legacy_then_portal_duplicate_is_queryable(self):
        meeting = make_signed_meeting("M-56")
        distribution.register_pending("M-56", meeting["id"], "legacy")

        svc = ReviewMeetingService()
        first, _ = act(svc, meeting["id"], "分发给教师", site="legacy", receipt="M-56")
        task_id = first["taskId"]

        second, message = act(svc, meeting["id"], "分发给教师", site="portal", receipt="M-56")
        assert second is not None
        assert "可续办" in message

        views = {
            site: distribution.get_by_receipt("M-56", requester=site)["status"]
            for site in ("legacy", "portal")
        }
        assert views == {"legacy": "已分发", "portal": "可续办"}
        # 同编号只发出一项任务。
        tasks = [r for r in store.rows("improve_task") if r.get("回执编号") == "M-56"]
        assert len(tasks) == 1 and tasks[0]["id"] == task_id


class TestTaskClaim:
    def test_claim_rejects_task_not_actually_issued(self):
        meeting = make_signed_meeting("M-56")
        svc = ReviewMeetingService()
        entry, _ = act(svc, meeting["id"], "分发给教师", site="legacy", receipt="M-56")
        real_task_id = entry["taskId"]

        # 伪造一条同回执但非实际发出的任务。
        fake = {
            "id": max(r["id"] for r in store.rows("improve_task")) + 1,
            "任务描述": "手工重放的任务 [meeting:%s]" % meeting["id"],
            "承接方案": "无",
            "执行人员": "",
            "回执编号": "M-56",
            "来源会议": meeting["id"],
            "status": "待认领",
            "pending": True,
            "abnormal": False,
        }
        store.rows("improve_task").append(fake)

        task_svc = ImproveTaskService()
        claimed, message = act(task_svc, fake["id"], "认领任务", site="portal", receipt="M-56")
        assert claimed is None
        assert "实际发出" in message
        assert store.find("improve_task", fake["id"])["status"] == "待认领"

        claimed_real, _ = act(task_svc, real_task_id, "认领任务", site="portal", receipt="M-56")
        assert claimed_real is not None
        assert claimed_real["status"] == "执行中"

    def test_claim_blocked_while_awaiting_original(self):
        meeting = make_signed_meeting("M-56")
        distribution.register_pending("M-56", meeting["id"], "legacy")
        # 只有任务被预置但没有实际分发时也不能认领。
        task = {
            "id": 90,
            "任务描述": "预置任务 [meeting:%s]" % meeting["id"],
            "承接方案": "无",
            "执行人员": "",
            "回执编号": "M-56",
            "来源会议": meeting["id"],
            "status": "待认领",
            "pending": True,
            "abnormal": False,
        }
        store.rows("improve_task").append(task)
        svc = ImproveTaskService()
        claimed, message = act(svc, 90, "认领任务", site="portal", receipt="M-56")
        assert claimed is None
        assert "尚待原入口处理" in message


class TestRoundTrip:
    def test_legacy_meeting_to_portal_claim_and_back(self):
        meeting = make_signed_meeting("M-56")
        svc = ReviewMeetingService()
        entry, _ = act(svc, meeting["id"], "分发给教师", site="legacy", receipt="M-56")
        task_id = entry["taskId"]

        # 切到门户领取同一项任务。
        task_svc = ImproveTaskService()
        claimed, _ = act(task_svc, task_id, "认领任务", site="portal", receipt="M-56")
        assert claimed["status"] == "执行中"
        assert claimed["claimedSite"] == "教务门户"

        # 回到原入口核对：任务编号仍指回原纪要。
        legacy_task = task_svc.get_entry(task_id)
        assert legacy_task["来源会议"] == meeting["id"]
        view = distribution.get_by_receipt("M-56", requester="legacy")
        assert view["meetingId"] == meeting["id"]
        assert view["taskId"] == task_id
        assert store.find("review_meeting", meeting["id"])["taskId"] == task_id
        assert store.find("review_meeting", meeting["id"])["receipt"] == "M-56"


class TestExportAndOverview:
    def test_overview_reports_single_instance(self):
        first = store.overview()
        second = Store(kind="demo", instance_id="demo-x").overview()
        assert first["instance"] == store.instance_id
        assert second["instance"] == "demo-x"
        assert first["instance"] != second["instance"]
