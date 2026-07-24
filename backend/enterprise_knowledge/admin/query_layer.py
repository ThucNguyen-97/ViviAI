from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from admin.auth import AdminViewer, visible_email_for
from admin.schemas import (
    AdminOverviewResponse,
    AdminUserListResponse,
    AdminUserRead,
    AgentPlanRead,
    AgentStepRead,
    ConversationLogDetailResponse,
    ConversationLogItem,
    ConversationLogListResponse,
    LlmProviderStatus,
    LlmProvidersStatusResponse,
    MessageLogRead,
    RagDocumentStats,
    RagStatsResponse,
    StatusCount,
    UsageStats,
)
from core.config import settings
from db.models import (
    AgentPlan,
    AgentStep,
    Chunk,
    Conversation,
    Document,
    LlmProviderCall,
    Message,
    RagDocument,
    User,
    Voucher,
)



LLM_ROUTING_ROLES = {
    "google": ["primary"],
    "anthropic": ["fallback"],
}


def _decimal(value) -> Decimal:
    return value if value is not None else Decimal("0")


def _usd_to_vnd(value) -> Decimal:
    return _decimal(value) * settings.USD_TO_VND_RATE


def _status_label(value: Optional[str]) -> str:
    return value or "unknown"


def _usage_from_conversation(conversation: Conversation) -> UsageStats:
    return UsageStats(
        input_tokens=conversation.input_tokens or 0,
        output_tokens=conversation.output_tokens or 0,
        total_tokens=conversation.total_tokens or 0,
        input_token_cost=_decimal(conversation.input_token_cost),
        output_token_cost=_decimal(conversation.output_token_cost),
        total_cost=_decimal(conversation.total_cost),
    )


def _user_read(
    viewer: AdminViewer,
    user: User,
    *,
    total_tokens: int = 0,
    total_cost_usd: Decimal = Decimal("0"),
) -> AdminUserRead:
    visible_email = visible_email_for(
        viewer,
        target_user_id=user.id,
        target_role=user.role,
        email=user.email,
    )
    return AdminUserRead(
        id=user.id,
        email=visible_email,
        email_hidden=visible_email is None,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login_id=user.last_login_id,
        total_tokens=total_tokens or 0,
        total_cost_usd=_decimal(total_cost_usd),
        total_cost_vnd=_usd_to_vnd(total_cost_usd),
        created_at=user.created_at,
    )


async def _user_usage_map(
    db: AsyncSession,
    user_ids: set[str],
) -> dict[str, dict[str, Decimal | int]]:
    if not user_ids:
        return {}

    rows = (
        await db.execute(
            select(
                Conversation.user_id,
                func.coalesce(func.sum(Conversation.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(Conversation.total_cost), 0).label("total_cost_usd"),
            )
            .where(Conversation.user_id.in_(user_ids))
            .group_by(Conversation.user_id)
        )
    ).all()
    return {
        user_id: {
            "total_tokens": total_tokens or 0,
            "total_cost_usd": _decimal(total_cost_usd),
        }
        for user_id, total_tokens, total_cost_usd in rows
    }


async def get_overview(db: AsyncSession) -> AdminOverviewResponse:
    user_row = (
        await db.execute(
            select(
                func.count(User.id),
                func.count(User.id).filter(User.is_active.is_(True)),
            )
        )
    ).one()

    conversation_row = (
        await db.execute(
            select(
                func.count(Conversation.id),
                func.coalesce(func.sum(Conversation.input_tokens), 0),
                func.coalesce(func.sum(Conversation.output_tokens), 0),
                func.coalesce(func.sum(Conversation.total_tokens), 0),
                func.coalesce(func.sum(Conversation.input_token_cost), 0),
                func.coalesce(func.sum(Conversation.output_token_cost), 0),
                func.coalesce(func.sum(Conversation.total_cost), 0),
            )
        )
    ).one()

    total_messages = await db.scalar(select(func.count(Message.id)))
    failed_messages = await db.scalar(
        select(func.count(Message.id)).where(Message.status == "failed")
    )
    total_agent_plans = await db.scalar(select(func.count(AgentPlan.id)))
    failed_agent_plans = await db.scalar(
        select(func.count(AgentPlan.id)).where(AgentPlan.status == "failed")
    )
    total_agent_steps = await db.scalar(select(func.count(AgentStep.id)))
    failed_agent_steps = await db.scalar(
        select(func.count(AgentStep.id)).where(AgentStep.status == "failed")
    )
    rag_documents = await db.scalar(select(func.count(RagDocument.id)))
    rag_chunks = await db.scalar(select(func.count(Chunk.id)))
    user_files = await db.scalar(select(func.count(Document.id)))
    vouchers = await db.scalar(select(func.count(Voucher.id)))

    message_status_rows = (
        await db.execute(
            select(Message.status, func.count(Message.id))
            .group_by(Message.status)
            .order_by(func.count(Message.id).desc())
        )
    ).all()
    step_status_rows = (
        await db.execute(
            select(AgentStep.status, func.count(AgentStep.id))
            .group_by(AgentStep.status)
            .order_by(func.count(AgentStep.id).desc())
        )
    ).all()

    return AdminOverviewResponse(
        total_users=user_row[0] or 0,
        active_users=user_row[1] or 0,
        total_conversations=conversation_row[0] or 0,
        total_messages=total_messages or 0,
        failed_messages=failed_messages or 0,
        total_agent_plans=total_agent_plans or 0,
        failed_agent_plans=failed_agent_plans or 0,
        total_agent_steps=total_agent_steps or 0,
        failed_agent_steps=failed_agent_steps or 0,
        rag_documents=rag_documents or 0,
        rag_chunks=rag_chunks or 0,
        user_files=user_files or 0,
        vouchers=vouchers or 0,
        usage=UsageStats(
            input_tokens=conversation_row[1] or 0,
            output_tokens=conversation_row[2] or 0,
            total_tokens=conversation_row[3] or 0,
            input_token_cost=_decimal(conversation_row[4]),
            output_token_cost=_decimal(conversation_row[5]),
            total_cost=_decimal(conversation_row[6]),
        ),
        message_statuses=[
            StatusCount(status=_status_label(row[0]), total=row[1] or 0)
            for row in message_status_rows
        ],
        agent_step_statuses=[
            StatusCount(status=_status_label(row[0]), total=row[1] or 0)
            for row in step_status_rows
        ],
    )



async def list_users(
    db: AsyncSession,
    viewer: AdminViewer,
    *,
    search: Optional[str],
    role: Optional[str],
    limit: int,
    offset: int,
) -> AdminUserListResponse:
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
                User.id.ilike(pattern),
            )
        )
    if role:
        filters.append(User.role == role)

    base = (
        select(
            User,
            func.coalesce(func.sum(Conversation.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(Conversation.total_cost), 0).label("total_cost_usd"),
        )
        .outerjoin(Conversation, Conversation.user_id == User.id)
        .where(and_(*filters))
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    total = await db.scalar(select(func.count()).select_from(User).where(and_(*filters)))
    result = await db.execute(base.limit(limit).offset(offset))

    return AdminUserListResponse(
        total=total or 0,
        limit=limit,
        offset=offset,
        usd_to_vnd_rate=settings.USD_TO_VND_RATE,
        users=[
            _user_read(
                viewer,
                user,
                total_tokens=total_tokens or 0,
                total_cost_usd=_decimal(total_cost_usd),
            )
            for user, total_tokens, total_cost_usd in result.all()
        ],
    )


async def list_conversations(
    db: AsyncSession,
    viewer: AdminViewer,
    *,
    user_id: Optional[str],
    status: Optional[str],
    search: Optional[str],
    limit: int,
    offset: int,
) -> ConversationLogListResponse:
    filters = []
    if user_id:
        filters.append(Conversation.user_id == user_id)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(Conversation.title.ilike(pattern), Conversation.summary.ilike(pattern)))
    if status:
        filters.append(Conversation.messages.any(Message.status == status))

    total = await db.scalar(select(func.count()).select_from(Conversation).where(and_(*filters)))
    rows = (
        await db.execute(
            select(
                Conversation,
                User,
                func.count(Message.id).label("message_count"),
            )
            .outerjoin(User, User.id == Conversation.user_id)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(and_(*filters))
            .group_by(Conversation.id, User.id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    usage_by_user = await _user_usage_map(
        db,
        {user.id for _, user, _ in rows if user is not None},
    )

    return ConversationLogListResponse(
        total=total or 0,
        limit=limit,
        offset=offset,
        conversations=[
            ConversationLogItem(
                id=str(conversation.id),
                user_id=conversation.user_id,
                user=_user_read(
                    viewer,
                    user,
                    **usage_by_user.get(user.id, {}),
                )
                if user
                else None,
                title=conversation.title,
                summary=conversation.summary,
                message_count=message_count or 0,
                usage=_usage_from_conversation(conversation),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            for conversation, user, message_count in rows
        ],
    )


async def get_conversation_detail(
    db: AsyncSession,
    viewer: AdminViewer,
    conversation_id: UUID,
) -> Optional[ConversationLogDetailResponse]:
    result = await db.execute(
        select(Conversation)
        .options(
            selectinload(Conversation.messages)
            .selectinload(Message.agent_plans)
            .selectinload(AgentPlan.steps)
        )
        .where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        return None

    user = await db.get(User, conversation.user_id)
    usage_by_user = await _user_usage_map(db, {conversation.user_id})
    messages = sorted(conversation.messages, key=lambda message: message.created_at)

    return ConversationLogDetailResponse(
        id=str(conversation.id),
        user_id=conversation.user_id,
        user=_user_read(
            viewer,
            user,
            **usage_by_user.get(user.id, {}),
        )
        if user
        else None,
        title=conversation.title,
        summary=conversation.summary,
        message_count=len(messages),
        usage=_usage_from_conversation(conversation),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            MessageLogRead(
                id=str(message.id),
                role=message.role,
                content=message.content,
                status=message.status,
                input_tokens=message.input_tokens or 0,
                output_tokens=message.output_tokens or 0,
                total_tokens=message.total_tokens or 0,
                documents_source_url=message.documents_source_url,
                vouchers_source_url=message.vouchers_source_url,
                created_at=message.created_at,
                agent_plans=[
                    AgentPlanRead(
                        id=str(plan.id),
                        plan_name=plan.plan_name,
                        raw_plan=plan.raw_plan,
                        mcp_tools=plan.mcp_tools,
                        total_steps=plan.total_steps,
                        status=plan.status,
                        input_tokens=plan.input_tokens or 0,
                        output_tokens=plan.output_tokens or 0,
                        total_tokens=plan.total_tokens or 0,
                        created_at=plan.created_at,
                        steps=[
                            AgentStepRead(
                                id=str(step.id),
                                step_number=step.step_number,
                                step_name=step.step_name,
                                thought=step.thought,
                                action=step.action,
                                action_input=step.action_input,
                                action_output=step.action_output,
                                status=step.status,
                                input_tokens=step.input_tokens or 0,
                                output_tokens=step.output_tokens or 0,
                                total_tokens=step.total_tokens or 0,
                                error_message=step.error_message,
                                started_at=step.started_at,
                                ended_at=step.ended_at,
                            )
                            for step in sorted(plan.steps, key=lambda step: step.step_number)
                        ],
                    )
                    for plan in sorted(message.agent_plans, key=lambda plan: plan.created_at)
                ],
            )
            for message in messages
        ],
    )



async def get_rag_stats(db: AsyncSession) -> RagStatsResponse:
    rows = (
        await db.execute(
            select(
                RagDocument,
                func.count(Chunk.id).label("chunk_count"),
            )
            .outerjoin(Chunk, Chunk.rag_document_id == RagDocument.id)
            .group_by(RagDocument.id)
            .order_by(RagDocument.created_at.desc())
        )
    ).all()
    total_chunks = await db.scalar(select(func.count(Chunk.id)))

    return RagStatsResponse(
        total_documents=len(rows),
        total_chunks=total_chunks or 0,
        documents=[
            RagDocumentStats(
                id=str(document.id),
                file_name=document.file_name,
                file_type=document.file_type,
                file_size=document.file_size,
                storage_url=document.storage_url,
                file_modified_at=document.file_modified_at,
                created_at=document.created_at,
                chunk_count=chunk_count or 0,
            )
            for document, chunk_count in rows
        ],
    )


async def get_llm_providers_status_placeholder() -> LlmProvidersStatusResponse:
    return await get_llm_providers_status(None)


async def get_llm_providers_status(db: Optional[AsyncSession]) -> LlmProvidersStatusResponse:
    latest_by_provider = {}
    if db is not None:
        rows = (
            await db.execute(
                select(LlmProviderCall)
                .order_by(LlmProviderCall.provider.asc(), LlmProviderCall.created_at.desc())
            )
        ).scalars().all()
        for row in rows:
            latest_by_provider.setdefault(row.provider, row)

    providers = [
        _llm_provider_status(
            provider="google",
            display_name="Google Gemini",
            model=settings.GOOGLE_LLM_MODEL,
            configured=bool(settings.GOOGLE_API_KEY.strip()),
            latest=latest_by_provider.get("google"),
        ),
        _llm_provider_status(
            provider="anthropic",
            display_name="Anthropic Claude",
            model=settings.ANTHROPIC_LLM_MODEL,
            configured=bool(settings.ANTHROPIC_API_KEY.strip()),
            latest=latest_by_provider.get("anthropic"),
        ),
    ]
    return LlmProvidersStatusResponse(
        source="llm_provider_calls",
        note="Google key được sử dụng trước tiên cho tất cả yêu cầu; Claude key được sử dụng làm phương án dự phòng (fallback) nếu Google lỗi.",
        providers=providers,
    )


def _llm_provider_status(
    *,
    provider: str,
    display_name: str,
    model: str,
    configured: bool,
    latest: Optional[LlmProviderCall],
) -> LlmProviderStatus:
    if not configured:
        status = "missing"
    elif latest is None:
        status = "configured"
    elif latest.status == "success":
        status = "healthy"
    else:
        status = latest.status

    return LlmProviderStatus(
        provider=provider,
        display_name=display_name,
        model=model,
        configured=configured,
        status=status,
        routing_roles=LLM_ROUTING_ROLES[provider],
        last_called_at=latest.created_at if latest else None,
        last_latency_ms=latest.latency_ms if latest else None,
        last_error_type=latest.error_type if latest else None,
    )
