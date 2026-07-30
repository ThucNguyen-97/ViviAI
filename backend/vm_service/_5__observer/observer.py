from typing import Any, Optional
from ek_client import ek_client
from _1__ai_firewall.schemas import ExecutionPlan


async def create_conversation(*, user_id: str, title: str) -> str:
    """Tạo cuộc trò chuyện mới và trả về conversation_id."""
    return await ek_client.create_conversation(user_id=user_id, title=title)


async def record_user_message(*, conversation_id: str, content: str) -> dict[str, Any]:
    """Ghi nhận tin nhắn người dùng."""
    return await ek_client.create_message(
        conversation_id=conversation_id,
        role="user",
        content=content,
        status="completed",
    )


async def record_assistant_message(
    *,
    conversation_id: str,
    content: str,
    status: str = "completed",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict[str, Any]:
    """Ghi nhận phản hồi của AI assistant."""
    return await ek_client.create_message(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        status=status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


async def record_agent_plan(
    *,
    assistant_message_id: str,
    plan: ExecutionPlan,
) -> None:
    """Ghi nhận agent execution plan."""
    step_payloads = [
        {
            "step_number": step.step_number,
            "step_name": step.step_name,
            "action": step.action,
            "thought": step.thought,
            "action_input": __import__("json").dumps(step.action_input, ensure_ascii=False),
            "status": "completed",
        }
        for step in plan.steps
    ]
    selected_mcp_tools = []
    for step in plan.steps:
        if not step.action or not step.action.startswith("mcp:"):
            continue
        qualified_name = step.action.removeprefix("mcp:").strip()
        if "." not in qualified_name:
            continue
        mcp_name, tool_name = qualified_name.split(".", 1)
        selected_mcp_tools.append(
            {
                "mcp_name": mcp_name,
                "tool_name": tool_name,
                "qualified_name": qualified_name,
                "step_number": step.step_number,
            }
        )
    try:
        await ek_client.create_agent_plan(
            message_id=assistant_message_id,
            plan_name=plan.plan_name,
            raw_plan=plan.model_dump(),
            steps=step_payloads,
            mcp_tools=selected_mcp_tools,
            total_steps=plan.total_steps,
            status="success",
        )
    except Exception:
        pass
