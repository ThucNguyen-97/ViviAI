import json

from _1__ai_firewall.schemas import ExecutionPlan, ExecutionStep, Intent, ProcessedFile, UserContext
from llm.router import llm_router
from llm.schemas import LlmGenerateRequest, LlmMessage
from _3__executor.mcp_tools.mcp_catalog import render_for_planner
from runtime.rag_catalog import refresh_rag_catalog


def _json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def intent_from_plan(plan: ExecutionPlan) -> Intent:
    actions = {step.action for step in plan.steps if step.action}
    if any(action.startswith("mcp:") or action == "mcp_tool" for action in actions):
        return "task_execution"
    if "sql_query" in actions:
        return "business_query"
    if "rag_search" in actions:
        return "rag_query"
    return "general_chat"


async def create_execution_plan(
    message: str,
    user: UserContext,
    files: list[ProcessedFile],
) -> ExecutionPlan:
    rag_knowledge_catalog = await refresh_rag_catalog()
    file_summary = [
        {"file_name": file.original_file_name, "file_type": file.file_type, "flags": file.flags}
        for file in files
    ]
    prompt = f"""
Ban la AI Planner cho VietMAS. Hay phan tich yeu cau nguoi dung va sinh ra Ke hoach thuc thi (Execution Plan) gom chuoi cac buoc (steps) can thuc hien.
Chi tra ve JSON hop le theo cau truc:
{{
  "plan_name": "Kế hoạch xử lý yêu cầu",
  "total_steps": 2,
  "steps": [
    {{
      "step_number": 1,
      "step_name": "Tra cứu trí thức RAG",
      "action": "rag_search",
      "action_input": {{}},
      "thought": "Tìm kiếm chính sách bán hàng liên quan trong RAG"
    }},
    {{
      "step_number": 2,
      "step_name": "Tổng hợp câu trả lời",
      "action": "llm_synthesize",
      "thought": "Tổng hợp thông tin RAG để trả lời người dùng"
    }}
  ]
}}

Cac loai action hop le:
- rag_search: truy van tri thuc RAG
- sql_query: truy van du lieu CSDL nghiep vu
- mcp_tool: danh dau buoc thao tac tool/file khi can phan tich file dinh kem
- llm_synthesize: tong hop ket qua tu cac buoc va sinh phan hoi cuoi cung
- mcp:<mcp_name>.<tool_name>: goi dung MCP tool trong danh muc

RAG knowledge catalog hien co:
{json.dumps(rag_knowledge_catalog, ensure_ascii=False, indent=2)}

Files dinh kem:
{json.dumps(file_summary, ensure_ascii=False)}

Quy tac lap ke hoach:
- Neu co file dinh kem, uu tien buoc phan tich file (llm_synthesize) va/hoac MCP tool phu hop.
- Neu cau hoi ve tri thuc noi bo/chinh sach/cong ty/he thong, dung rag_search roi llm_synthesize.
- Neu can so lieu nghiep vu dong tu CSDL, dung sql_query roi llm_synthesize.
- Neu can thao tac email/tool, dung mcp:<mcp_name>.<tool_name>; co the ket hop llm_synthesize sau do.
- Ket thuc bang llm_synthesize de tra loi nguoi dung, tru khi chi gui email bang send_email.

Message: {message}
Role: {user.role}

DANH MUC MCP TOOL DUOC PHEP LUA CHON:
{render_for_planner()}

Neu dung MCP, action phai dung dinh dang `mcp:<mcp_name>.<tool_name>` va phai
chon dung mot tool co trong danh muc. Khong tu sang tao ten MCP/tool.
"""
    try:
        response = await llm_router.generate(
            LlmGenerateRequest(
                phase="default",
                max_output_tokens=384,
                temperature=0,
                messages=[LlmMessage(role="user", content=prompt)],
                metadata={"planner": "execution_plan", "user_id": user.user_id},
            )
        )
        parsed = _json_object(response.content)
        return ExecutionPlan.model_validate(parsed)
    except Exception:
        if files:
            return ExecutionPlan(
                plan_name="Phân tích file đính kèm",
                total_steps=1,
                steps=[
                    ExecutionStep(
                        step_number=1,
                        step_name="Phân tích nội dung file",
                        action="llm_synthesize",
                        thought="Phân tích file đính kèm và trả lời người dùng",
                    )
                ],
            )
        return ExecutionPlan(
            plan_name="Trả lời yêu cầu",
            total_steps=1,
            steps=[
                ExecutionStep(
                    step_number=1,
                    step_name="Tổng hợp câu trả lời",
                    action="llm_synthesize",
                    thought="Trả lời trực tiếp yêu cầu của người dùng",
                )
            ],
        )
