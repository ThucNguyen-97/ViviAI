from pathlib import Path
from typing import Any, Optional

import httpx

from core.config import settings


class EnterpriseKnowledgeClient:
    def __init__(self) -> None:
        self.base_url = settings.EK_SERVICE_URL.rstrip("/")
        self.headers = {"X-Internal-Api-Key": settings.EK_INTERNAL_API_KEY}

    async def create_conversation(self, *, user_id: str, title: str, summary: Optional[str] = None) -> str:
        payload = {"user_id": user_id, "title": title, "summary": summary}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{self.base_url}/internal/v1/conversations", headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()["id"]

    async def create_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        status: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> dict[str, Any]:
        payload = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "status": status,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{self.base_url}/internal/v1/messages", headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def rag_search(self, *, query: str, top_k: int = 5, score_threshold: float = 0.7) -> dict[str, Any]:
        payload = {"query": query, "top_k": top_k, "score_threshold": score_threshold}
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(f"{self.base_url}/internal/v1/rag/search", headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def rag_catalog(self, *, since: Optional[str] = None) -> dict[str, Any]:
        params = {"since": since} if since else None
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{self.base_url}/internal/v1/rag/catalog",
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def business_overview(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/internal/v1/business/overview", headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def upload_clean_file(
        self,
        *,
        path: Path,
        original_file_name: str,
        uploaded_by: str,
        file_type: str,
        mime_type: Optional[str],
        raw_vm_path: Optional[str],
        sanitized: bool,
        firewall_result: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        data = {
            "original_file_name": original_file_name,
            "uploaded_by": uploaded_by,
            "file_type": file_type,
            "status": "ready",
            "mime_type": mime_type or "",
            "raw_vm_path": raw_vm_path or "",
            "sanitized": str(sanitized).lower(),
            "firewall_result": __import__("json").dumps(firewall_result),
            "metadata": __import__("json").dumps(metadata),
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            with path.open("rb") as handle:
                files = {"file": (path.name, handle, mime_type or "application/octet-stream")}
                response = await client.post(
                    f"{self.base_url}/internal/v1/clean-files",
                    headers=self.headers,
                    data=data,
                    files=files,
                )
            response.raise_for_status()
            return response.json()

    async def create_agent_plan(
        self,
        *,
        message_id: str,
        plan_name: Optional[str] = "Kế hoạch thực thi tác vụ",
        raw_plan: dict[str, Any],
        steps: list[dict[str, Any]],
        mcp_tools: Optional[list] = None,
        total_steps: int = 0,
        status: str = "success",
    ) -> dict[str, Any]:
        payload = {
            "message_id": message_id,
            "plan_name": plan_name,
            "raw_plan": raw_plan,
            "steps": steps,
            "mcp_tools": mcp_tools or [],
            "total_steps": total_steps or len(steps),
            "status": status,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.base_url}/internal/v1/agent-plans",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()



ek_client = EnterpriseKnowledgeClient()
