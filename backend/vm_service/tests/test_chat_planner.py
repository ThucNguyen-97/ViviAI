"""Tests for firewall -> planner -> executor chat flow (no intent classifier)."""

import asyncio
import os
import sys
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)

from _1__ai_firewall.schemas import ExecutionPlan, ExecutionStep, FirewallDecision  # noqa: E402
from llm.schemas import LlmGenerateResponse, TokenUsage  # noqa: E402
from _2__planner.planner import (  # noqa: E402
    create_execution_plan,
    intent_from_plan,
)
from _3__executor.executor import execute_plan  # noqa: E402


def _plan(*actions: str) -> ExecutionPlan:
    steps = [
        ExecutionStep(
            step_number=index,
            step_name=f"Step {index}",
            action=action,
            thought=f"Run {action}",
        )
        for index, action in enumerate(actions, start=1)
    ]
    return ExecutionPlan(plan_name="Test plan", total_steps=len(steps), steps=steps)


class IntentFromPlanTests(unittest.TestCase):
    def test_rag_plan(self):
        self.assertEqual(intent_from_plan(_plan("rag_search", "llm_synthesize")), "rag_query")

    def test_business_plan(self):
        self.assertEqual(intent_from_plan(_plan("sql_query", "llm_synthesize")), "business_query")

    def test_mcp_plan(self):
        self.assertEqual(
            intent_from_plan(_plan("mcp:email_mcp.search_email", "llm_synthesize")),
            "task_execution",
        )

    def test_general_plan(self):
        self.assertEqual(intent_from_plan(_plan("llm_synthesize")), "general_chat")


class CreateExecutionPlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_general_chat_request_is_planned_as_synthesis(self):
        planner_response = LlmGenerateResponse(
            provider="google",
            model="gemini-test",
            phase="default",
            content='{"plan_name":"Tra loi cau hoi","total_steps":1,"steps":[{"step_number":1,"step_name":"Tra loi truc tiep","action":"llm_synthesize","action_input":{},"thought":"Gioi thieu VietMAS va kha nang ho tro"}]}',
            usage=TokenUsage(),
            latency_ms=1,
        )

        with patch("_2__planner.planner.llm_router.generate", AsyncMock(return_value=planner_response)):
            with patch("_2__planner.planner.refresh_rag_catalog", AsyncMock(return_value=[])):
                with patch("_2__planner.planner.render_for_planner", return_value="(no mcp tools)"):
                    plan = await create_execution_plan(
                        "ban la ai? ban co the giup ich duoc gi?",
                        MagicMock(user_id="u1", role="admin"),
                        [],
                    )

        self.assertEqual([step.action for step in plan.steps], ["llm_synthesize"])

    async def test_check_inbox_request_is_planned_as_email_mcp_then_synthesis(self):
        planner_response = LlmGenerateResponse(
            provider="google",
            model="gemini-test",
            phase="default",
            content='{"plan_name":"Kiem tra hom thu","total_steps":2,"steps":[{"step_number":1,"step_name":"Dong bo inbox","action":"mcp:email_mcp.check_email","action_input":{},"thought":"Kiem tra email moi trong inbox"},{"step_number":2,"step_name":"Bao cao ket qua","action":"llm_synthesize","action_input":{},"thought":"Tom tat so email moi cho nguoi dung"}]}',
            usage=TokenUsage(),
            latency_ms=1,
        )

        with patch("_2__planner.planner.llm_router.generate", AsyncMock(return_value=planner_response)):
            with patch("_2__planner.planner.refresh_rag_catalog", AsyncMock(return_value=[])):
                with patch("_2__planner.planner.render_for_planner", return_value="email_mcp.check_email"):
                    plan = await create_execution_plan(
                        "hay kiem tra hom thu giup toi, xem co thu nao moi khong",
                        MagicMock(user_id="u1", role="admin"),
                        [],
                    )

        self.assertEqual(
            [step.action for step in plan.steps],
            ["mcp:email_mcp.check_email", "llm_synthesize"],
        )

    async def test_planner_fallback_without_files(self):
        with patch("_2__planner.planner.llm_router.generate", AsyncMock(side_effect=RuntimeError("planner down"))):
            with patch("_2__planner.planner.refresh_rag_catalog", AsyncMock(return_value=[])):
                with patch("_2__planner.planner.render_for_planner", return_value="(no mcp tools)"):
                    plan = await create_execution_plan("Xin chao", MagicMock(user_id="u1", role="admin"), [])

        self.assertEqual(plan.steps[0].action, "llm_synthesize")

    async def test_planner_fallback_with_files(self):
        with patch("_2__planner.planner.llm_router.generate", AsyncMock(side_effect=RuntimeError("planner down"))):
            with patch("_2__planner.planner.refresh_rag_catalog", AsyncMock(return_value=[])):
                with patch("_2__planner.planner.render_for_planner", return_value="(no mcp tools)"):
                    files = [MagicMock(original_file_name="note.md", file_type="md", flags=[])]
                    plan = await create_execution_plan("Phan tich file", MagicMock(user_id="u1", role="admin"), files)

        self.assertEqual(plan.plan_name, "Phân tích file đính kèm")
        self.assertEqual(plan.steps[0].action, "llm_synthesize")


class ExecutePlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_rag_then_synthesize(self):
        rag_payload = {"results": [{"source": {"file_name": "policy.md"}, "content": "Chiet khau 12%"}]}
        llm_response = LlmGenerateResponse(
            provider="google",
            model="gemini-test",
            phase="default",
            content="Chiet khau la 12%",
            usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            latency_ms=1,
        )

        with patch("_3__executor.executor.ek_client.rag_search", AsyncMock(return_value=rag_payload)):
            with patch("_3__executor.executor.synthesize_answer", AsyncMock(return_value=llm_response)) as synthesize:
                response, executions = await execute_plan(
                    "Chinh sach chiet khau?",
                    MagicMock(user_id="u1", role="admin"),
                    [],
                    _plan("rag_search", "llm_synthesize"),
                )

        self.assertEqual(response.content, "Chiet khau la 12%")
        self.assertEqual(executions, [])
        synthesize.assert_awaited_once()

    async def test_manager_sql_query_is_denied_in_synthesis(self):
        denied = LlmGenerateResponse(
            provider="google",
            model="policy",
            phase="default",
            content="Yeu cau cua ban khong the xu ly",
            usage=TokenUsage(),
            latency_ms=0,
        )

        with patch("_3__executor.executor._run_sql_query", AsyncMock(return_value={"denied": True, "content": denied.content})):
            with patch("_3__executor.executor.synthesize_answer", AsyncMock(return_value=denied)) as synthesize:
                response, _ = await execute_plan(
                    "Tong doanh thu?",
                    MagicMock(user_id="mgr-1", role="manager"),
                    [],
                    _plan("sql_query", "llm_synthesize"),
                )

        self.assertIn("khong the xu ly", response.content.lower())
        synthesize.assert_awaited_once()

    async def test_mcp_send_email_short_circuits_answer(self):
        with patch(
            "_3__executor.executor.dispatch_mcp_action",
            AsyncMock(return_value={"status": "sent"}),
        ) as dispatch:
            response, executions = await execute_plan(
                "Gui email nhac thanh toan",
                MagicMock(user_id="u1", role="admin"),
                [],
                _plan("mcp:email_mcp.send_email"),
            )

        dispatch.assert_awaited_once()
        self.assertEqual(response.content, "Đã gửi email thành công.")
        self.assertEqual(executions[0]["status"], "success")

    async def test_check_email_executes_with_user_scope_and_synthesizes_once(self):
        llm_response = LlmGenerateResponse(
            provider="google",
            model="gemini-test",
            phase="default",
            content="Có 2 email mới.",
            usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            latency_ms=1,
        )

        with patch(
            "_3__executor.executor.dispatch_mcp_action",
            AsyncMock(return_value={"status": "success", "imported_partner_emails": 2}),
        ) as dispatch:
            with patch("_3__executor.executor.synthesize_answer", AsyncMock(return_value=llm_response)) as synthesize:
                response, executions = await execute_plan(
                    "Hãy kiểm tra hòm thư giúp tôi, xem có thư nào mới không",
                    MagicMock(user_id="u1", role="admin"),
                    [],
                    _plan("mcp:email_mcp.check_email", "llm_synthesize"),
                )

        dispatch.assert_awaited_once_with("mcp:email_mcp.check_email", {"user_id": "u1"})
        synthesize.assert_awaited_once()
        self.assertEqual(response.content, "Có 2 email mới.")
        self.assertEqual(executions[0]["status"], "success")


class ChatEndpointFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_firewall_reject_skips_planner(self):
        from _1__ai_firewall import router as router_module

        rejected_firewall = FirewallDecision(
            is_valid=False,
            allowed=False,
            risk_level="high",
            reason="Vuot quyen",
            detected_issues=["privilege_escalation"],
        )

        @asynccontextmanager
        async def fake_gate():
            yield

        with patch.object(router_module, "redis_concurrency_gate", fake_gate):
            with patch.object(router_module, "set_runtime_state", AsyncMock()):
                with patch.object(router_module, "process_uploads", AsyncMock(return_value=[])):
                    with patch.object(router_module, "check_message", AsyncMock(return_value=rejected_firewall)):
                        with patch.object(router_module, "create_execution_plan", AsyncMock()) as planner:
                            with patch.object(router_module.observer, "create_conversation", AsyncMock(return_value="conv-1")):
                                with patch.object(
                                    router_module.observer,
                                    "record_user_message",
                                    AsyncMock(return_value={"id": "msg-u"}),
                                ):
                                    with patch.object(
                                        router_module.observer,
                                        "record_assistant_message",
                                        AsyncMock(return_value={"id": "msg-a"}),
                                    ):
                                        response = await router_module.chat(
                                            request=MagicMock(form=AsyncMock(return_value=MagicMock(getlist=lambda _: []))),
                                            message="Lay du lieu nhay cam",
                                            conversation_id=None,
                                            x_user_id="u1",
                                            x_user_email="u1@test.local",
                                            x_user_role="manager",
                                        )

        planner.assert_not_called()
        self.assertEqual(response.status, "rejected")
        self.assertEqual(response.intent, "general_chat")

    async def test_allowed_request_runs_planner_then_executor(self):
        from _1__ai_firewall import router as router_module

        allowed_firewall = FirewallDecision(is_valid=True, allowed=True, risk_level="low", reason="")
        sample_plan = _plan("llm_synthesize")
        llm_response = LlmGenerateResponse(
            provider="google",
            model="gemini-test",
            phase="default",
            content="Xin chao!",
            usage=TokenUsage(input_tokens=3, output_tokens=2, total_tokens=5),
            latency_ms=1,
        )

        @asynccontextmanager
        async def fake_gate():
            yield

        with patch.object(router_module, "redis_concurrency_gate", fake_gate):
            with patch.object(router_module, "set_runtime_state", AsyncMock()):
                with patch.object(router_module, "process_uploads", AsyncMock(return_value=[])):
                    with patch.object(router_module, "check_message", AsyncMock(return_value=allowed_firewall)):
                        with patch.object(router_module, "create_execution_plan", AsyncMock(return_value=sample_plan)) as planner:
                            with patch.object(router_module, "execute_plan", AsyncMock(return_value=(llm_response, []))) as executor:
                                with patch.object(router_module.observer, "create_conversation", AsyncMock(return_value="conv-2")):
                                    with patch.object(
                                        router_module.observer,
                                        "record_user_message",
                                        AsyncMock(return_value={"id": "msg-u2"}),
                                    ):
                                        with patch.object(
                                            router_module.observer,
                                            "record_assistant_message",
                                            AsyncMock(return_value={"id": "msg-a2"}),
                                        ):
                                            with patch.object(router_module.observer, "record_agent_plan", AsyncMock()):
                                                response = await router_module.chat(
                                                    request=MagicMock(form=AsyncMock(return_value=MagicMock(getlist=lambda _: []))),
                                                    message="Xin chao",
                                                    conversation_id=None,
                                                    x_user_id="u2",
                                                    x_user_email="u2@test.local",
                                                    x_user_role="admin",
                                                )

        planner.assert_awaited_once()
        executor.assert_awaited_once()
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.answer, "Xin chao!")
        self.assertEqual(response.intent, "general_chat")


if __name__ == "__main__":
    unittest.main()
