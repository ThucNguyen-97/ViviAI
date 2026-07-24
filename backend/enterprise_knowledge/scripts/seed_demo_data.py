import asyncio
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.base import AsyncSessionLocal
from db.models import (
    AgentPlan,
    AgentStep,
    Conversation,
    Document,
    GeneralJournal,
    GeneralJournalLine,
    Inventory,
    Message,
    Partner,
    User,
    Voucher,
)



DEMO_USER_IDS = [
    "demo-admin-001",
    "demo-ceo-001",
    "demo-ceo-002",
    "demo-manager-001",
    "demo-manager-002",
]

DEMO_CONVERSATION_IDS = [
    uuid.UUID("10000000-0000-0000-0000-000000000001"),
    uuid.UUID("10000000-0000-0000-0000-000000000002"),
    uuid.UUID("10000000-0000-0000-0000-000000000003"),
]

DEMO_DOCUMENT_IDS = [
    uuid.UUID("20000000-0000-0000-0000-000000000001"),
    uuid.UUID("20000000-0000-0000-0000-000000000002"),
]

DEMO_VOUCHER_IDS = [
    uuid.UUID("30000000-0000-0000-0000-000000000001"),
]

DEMO_PARTNER_IDS = [
    uuid.UUID("40000000-0000-0000-0000-000000000001"),
    uuid.UUID("40000000-0000-0000-0000-000000000002"),
    uuid.UUID("40000000-0000-0000-0000-000000000003"),
]

DEMO_INVENTORY_IDS = [
    uuid.UUID("50000000-0000-0000-0000-000000000001"),
    uuid.UUID("50000000-0000-0000-0000-000000000002"),
    uuid.UUID("50000000-0000-0000-0000-000000000003"),
]

DEMO_JOURNAL_IDS = [
    uuid.UUID("60000000-0000-0000-0000-000000000001"),
    uuid.UUID("60000000-0000-0000-0000-000000000002"),
]


def now_minus(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    return datetime.utcnow() - timedelta(days=days, hours=hours, minutes=minutes)


async def clear_demo_data(session) -> None:
    await session.execute(
        delete(GeneralJournal).where(GeneralJournal.id.in_(DEMO_JOURNAL_IDS))
    )
    await session.execute(delete(Voucher).where(Voucher.id.in_(DEMO_VOUCHER_IDS)))
    await session.execute(delete(Document).where(Document.id.in_(DEMO_DOCUMENT_IDS)))
    await session.execute(
        delete(Conversation).where(Conversation.id.in_(DEMO_CONVERSATION_IDS))
    )
    await session.execute(delete(Inventory).where(Inventory.id.in_(DEMO_INVENTORY_IDS)))
    await session.execute(delete(Partner).where(Partner.id.in_(DEMO_PARTNER_IDS)))
    await session.execute(delete(User).where(User.id.in_(DEMO_USER_IDS)))
    await session.commit()


async def seed_users(session) -> None:
    users = [
        User(
            id="demo-admin-001",
            email="admin@vietmas.demo",
            google_id="google-demo-admin-001",
            full_name="Admin VietMAS",
            avatar_url="https://example.com/avatars/admin.png",
            role="admin",
            is_active=True,
            last_login_id="login-demo-admin-001",
            created_at=now_minus(days=14),
        ),
        User(
            id="demo-ceo-001",
            email="ceo.linh@vietmas.demo",
            google_id="google-demo-ceo-001",
            full_name="Nguyen Thao Linh",
            avatar_url="https://example.com/avatars/ceo-linh.png",
            role="ceo",
            is_active=True,
            last_login_id="login-demo-ceo-001",
            created_at=now_minus(days=13),
        ),
        User(
            id="demo-ceo-002",
            email="ceo.minh@vietmas.demo",
            google_id="google-demo-ceo-002",
            full_name="Tran Duc Minh",
            avatar_url="https://example.com/avatars/ceo-minh.png",
            role="ceo",
            is_active=True,
            last_login_id="login-demo-ceo-002",
            created_at=now_minus(days=12),
        ),
        User(
            id="demo-manager-001",
            email="manager.ha@vietmas.demo",
            google_id="google-demo-manager-001",
            full_name="Le Thu Ha",
            role="manager",
            is_active=True,
            last_login_id="login-demo-manager-001",
            created_at=now_minus(days=10),
        ),
        User(
            id="demo-manager-002",
            email="manager.nam@vietmas.demo",
            google_id="google-demo-manager-002",
            full_name="Pham Hoang Nam",
            role="manager",
            is_active=False,
            last_login_id=None,
            created_at=now_minus(days=9),
        ),
    ]
    session.add_all(users)


async def seed_library_files(session) -> None:
    session.add_all(
        [
            Document(
                id=DEMO_DOCUMENT_IDS[0],
                file_name="bao_cao_doanh_thu_q2.xlsx",
                file_path="/demo/uploads/bao_cao_doanh_thu_q2.xlsx",
                file_size=184320,
                file_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                source_url="https://storage.example.com/demo/bao_cao_doanh_thu_q2.xlsx",
                required_role="manager",
                created_by="demo-manager-001",
                meta_info={"source": "user_upload", "demo": True},
                created_at=now_minus(days=3, hours=2),
                updated_at=now_minus(days=3, hours=1),
            ),
            Document(
                id=DEMO_DOCUMENT_IDS[1],
                file_name="hop_dong_ban_hang_da_chinh_sua.docx",
                file_path="/demo/generated/hop_dong_ban_hang_da_chinh_sua.docx",
                file_size=97280,
                file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                source_url="https://storage.example.com/demo/hop_dong_ban_hang_da_chinh_sua.docx",
                required_role="manager",
                created_by="demo-manager-001",
                meta_info={"source": "ai_generated", "demo": True},
                created_at=now_minus(days=2, hours=4),
                updated_at=now_minus(days=2, hours=3),
            ),
        ]
    )

    session.add(
        Voucher(
            id=DEMO_VOUCHER_IDS[0],
            file_name="hoa_don_mua_hang_0001.pdf",
            file_path="/demo/vouchers/hoa_don_mua_hang_0001.pdf",
            file_size=65536,
            file_type="application/pdf",
            storage_url="https://storage.example.com/demo/hoa_don_mua_hang_0001.pdf",
            created_by="demo-manager-001",
            created_at=now_minus(days=4),
        )
    )


async def seed_conversations(session) -> None:
    conversations = [
        Conversation(
            id=DEMO_CONVERSATION_IDS[0],
            user_id="demo-manager-001",
            title="Tổng hợp doanh thu Q2",
            summary="Người dùng yêu cầu tổng hợp doanh thu theo tháng từ file Excel.",
            input_token_cost=Decimal("1200"),
            output_token_cost=Decimal("1800"),
            total_cost=Decimal("3000"),
            created_at=now_minus(days=2, hours=5),
            updated_at=now_minus(days=2, hours=4, minutes=40),
        ),
        Conversation(
            id=DEMO_CONVERSATION_IDS[1],
            user_id="demo-manager-002",
            title="Tra cứu chính sách giao hàng",
            summary="Người dùng hỏi thông tin RAG về giao hàng và đổi trả.",
            input_token_cost=Decimal("350"),
            output_token_cost=Decimal("650"),
            total_cost=Decimal("1000"),
            created_at=now_minus(days=1, hours=2),
            updated_at=now_minus(days=1, hours=1, minutes=55),
        ),
        Conversation(
            id=DEMO_CONVERSATION_IDS[2],
            user_id="demo-ceo-001",
            title="Kiểm tra lỗi xử lý hợp đồng",
            summary="Một tác vụ Word bị lỗi khi đối chiếu thông tin từ ảnh.",
            input_token_cost=Decimal("500"),
            output_token_cost=Decimal("250"),
            total_cost=Decimal("750"),
            created_at=now_minus(hours=7),
            updated_at=now_minus(hours=6, minutes=45),
        ),
    ]
    session.add_all(conversations)
    await session.flush()

    messages = [
        Message(
            conversation_id=DEMO_CONVERSATION_IDS[0],
            role="user",
            content="Hãy tạo bảng tổng hợp doanh thu từng tháng từ file Excel tôi vừa gửi.",
            status="completed",
            input_tokens=220,
            output_tokens=0,
            documents_source_url="https://storage.example.com/demo/bao_cao_doanh_thu_q2.xlsx",
            created_at=now_minus(days=2, hours=5),
        ),
        Message(
            conversation_id=DEMO_CONVERSATION_IDS[0],
            role="assistant",
            content="Tôi đã đọc file Excel, tổng hợp doanh thu theo tháng và tạo file kết quả mới trong Thư viện.",
            status="completed",
            input_tokens=800,
            output_tokens=980,
            documents_source_url="https://storage.example.com/demo/hop_dong_ban_hang_da_chinh_sua.docx",
            created_at=now_minus(days=2, hours=4, minutes=40),
        ),
        Message(
            conversation_id=DEMO_CONVERSATION_IDS[1],
            role="user",
            content="Chính sách giao hàng hiện tại của Hương Vị Việt như thế nào?",
            status="completed",
            input_tokens=90,
            output_tokens=0,
            created_at=now_minus(days=1, hours=2),
        ),
        Message(
            conversation_id=DEMO_CONVERSATION_IDS[1],
            role="assistant",
            content="Theo tài liệu FAQ đã ingest, đơn hàng nội thành thường được xử lý trong ngày và có hướng dẫn đổi trả theo điều kiện sản phẩm.",
            status="completed",
            input_tokens=350,
            output_tokens=420,
            created_at=now_minus(days=1, hours=1, minutes=55),
        ),
        Message(
            conversation_id=DEMO_CONVERSATION_IDS[2],
            role="user",
            content="Đối chiếu ảnh CCCD với hợp đồng này và sửa thông tin bên mua giúp tôi.",
            status="completed",
            input_tokens=180,
            output_tokens=0,
            documents_source_url="https://storage.example.com/demo/hop_dong_can_sua.docx",
            created_at=now_minus(hours=7),
        ),
        Message(
            conversation_id=DEMO_CONVERSATION_IDS[2],
            role="assistant",
            content="Tác vụ bị lỗi vì file ảnh đính kèm không đọc được. Vui lòng tải lại ảnh rõ hơn.",
            status="failed",
            input_tokens=420,
            output_tokens=160,
            documents_source_url="https://storage.example.com/demo/hop_dong_can_sua.docx",
            created_at=now_minus(hours=6, minutes=45),
        ),
    ]
    session.add_all(messages)
    await session.flush()

    assistant_sales_message = messages[1]
    failed_contract_message = messages[5]

    sales_plan = AgentPlan(
        message_id=assistant_sales_message.id,
        plan_name="Kế hoạch tổng hợp doanh thu Q2",
        raw_plan={
            "intent": "spreadsheet_transform",
            "steps": [
                "read_excel",
                "aggregate_monthly_revenue",
                "create_output_file",
            ],
        },
        mcp_tools=[
            {
                "name": "excel.read_workbook",
                "server": "mcp_excel",
                "purpose": "Read the uploaded Excel workbook before aggregation.",
            },
            {
                "name": "excel.aggregate",
                "server": "mcp_excel",
                "purpose": "Aggregate revenue by month from workbook rows.",
            },
            {
                "name": "excel.write_workbook",
                "server": "mcp_excel",
                "purpose": "Create the generated result workbook for the library.",
            },
        ],
        total_steps=3,
        status="success",
        input_tokens=280,
        output_tokens=170,
        created_at=now_minus(days=2, hours=4, minutes=55),
    )
    failed_plan = AgentPlan(
        message_id=failed_contract_message.id,
        plan_name="Kế hoạch sửa thông tin hợp đồng từ ảnh",
        raw_plan={
            "intent": "document_update_from_image",
            "steps": ["read_image", "read_word", "update_word"],
        },
        mcp_tools=[
            {
                "name": "image.extract_text",
                "server": "mcp_vision",
                "purpose": "Extract identity fields from the uploaded image.",
            },
            {
                "name": "word.read_document",
                "server": "mcp_word",
                "purpose": "Read the uploaded contract before editing.",
            },
            {
                "name": "word.update_document",
                "server": "mcp_word",
                "purpose": "Write corrected buyer information back to the contract.",
            },
        ],
        total_steps=3,
        status="failed",
        input_tokens=160,
        output_tokens=80,
        created_at=now_minus(hours=6, minutes=55),
    )
    session.add_all([sales_plan, failed_plan])
    await session.flush()

    session.add_all(
        [
            AgentStep(
                agent_plan_id=sales_plan.id,
                step_number=1,
                step_name="Đọc file Excel",
                thought="Cần kiểm tra các sheet và cột doanh thu trước khi tổng hợp.",
                action="excel.read_workbook",
                action_input='{"file_url":"https://storage.example.com/demo/bao_cao_doanh_thu_q2.xlsx"}',
                action_output='{"sheets":["Q2"],"rows":92}',
                status="success",
                input_tokens=120,
                output_tokens=60,
                started_at=now_minus(days=2, hours=4, minutes=54),
                ended_at=now_minus(days=2, hours=4, minutes=53),
            ),
            AgentStep(
                agent_plan_id=sales_plan.id,
                step_number=2,
                step_name="Tổng hợp doanh thu",
                thought="Nhóm dữ liệu theo tháng và cộng doanh thu thuần.",
                action="excel.aggregate",
                action_input='{"group_by":"month","metric":"net_revenue"}',
                action_output='{"2026-04":125000000,"2026-05":148000000,"2026-06":171500000}',
                status="success",
                input_tokens=90,
                output_tokens=110,
                started_at=now_minus(days=2, hours=4, minutes=52),
                ended_at=now_minus(days=2, hours=4, minutes=50),
            ),
            AgentStep(
                agent_plan_id=sales_plan.id,
                step_number=3,
                step_name="Tạo file kết quả",
                thought="Ghi bảng tổng hợp ra workbook mới và lưu vào thư viện.",
                action="excel.write_workbook",
                action_input='{"output_name":"tong_hop_doanh_thu_q2.xlsx"}',
                action_output='{"storage_url":"https://storage.example.com/demo/tong_hop_doanh_thu_q2.xlsx"}',
                status="success",
                input_tokens=70,
                output_tokens=130,
                started_at=now_minus(days=2, hours=4, minutes=49),
                ended_at=now_minus(days=2, hours=4, minutes=47),
            ),
            AgentStep(
                agent_plan_id=failed_plan.id,
                step_number=1,
                step_name="Đọc ảnh định danh",
                thought="Cần OCR ảnh trước khi cập nhật hợp đồng.",
                action="image.extract_text",
                action_input='{"file_url":"https://storage.example.com/demo/cccd_mo.jpg"}',
                action_output=None,
                status="failed",
                input_tokens=160,
                output_tokens=80,
                error_message="Ảnh quá mờ, không trích xuất được thông tin đáng tin cậy.",
                started_at=now_minus(hours=6, minutes=54),
                ended_at=now_minus(hours=6, minutes=53),
            ),
        ]
    )



async def seed_business_data(session) -> None:
    session.add_all(
        [
            Partner(
                id=DEMO_PARTNER_IDS[0],
                name="Công ty TNHH An Phát",
                phone="0901000001",
                email="muahang@anphat.demo",
                address="Quận 1, TP.HCM",
                partner_type="customer",
                created_at=now_minus(days=20),
            ),
            Partner(
                id=DEMO_PARTNER_IDS[1],
                name="Nhà cung cấp Bình Minh",
                phone="0902000002",
                email="sales@binhminh.demo",
                address="Dĩ An, Bình Dương",
                partner_type="vendor",
                created_at=now_minus(days=19),
            ),
            Partner(
                id=DEMO_PARTNER_IDS[2],
                name="Đại lý Hương Sen",
                phone="0903000003",
                email="daily@huongsen.demo",
                address="Nha Trang, Khánh Hòa",
                partner_type="partner",
                created_at=now_minus(days=18),
            ),
        ]
    )

    session.add_all(
        [
            Inventory(
                id=DEMO_INVENTORY_IDS[0],
                name="Cà phê rang mộc 500g",
                quantity=120,
                unit="gói",
                purchase_price=Decimal("52000"),
                price=Decimal("79000"),
                description="Dòng sản phẩm bán chạy trong demo.",
                created_at=now_minus(days=15),
            ),
            Inventory(
                id=DEMO_INVENTORY_IDS[1],
                name="Trà sen túi lọc",
                quantity=28,
                unit="hộp",
                purchase_price=Decimal("38000"),
                price=Decimal("59000"),
                description="Sắp cần nhập thêm nếu ngưỡng tồn kho là 30.",
                created_at=now_minus(days=14),
            ),
            Inventory(
                id=DEMO_INVENTORY_IDS[2],
                name="Mật ong hoa cà phê",
                quantity=54,
                unit="chai",
                purchase_price=Decimal("88000"),
                price=Decimal("135000"),
                description="Hàng đặc sản vùng nguyên liệu.",
                created_at=now_minus(days=13),
            ),
        ]
    )
    await session.flush()

    journal_sale = GeneralJournal(
        id=DEMO_JOURNAL_IDS[0],
        vouchers_id=DEMO_VOUCHER_IDS[0],
        storage_url="https://storage.example.com/demo/hoa_don_mua_hang_0001.pdf",
        date=now_minus(days=4),
        description="Ghi nhận bán hàng demo cho Công ty TNHH An Phát.",
        status="approved",
        approved_at=now_minus(days=3, hours=22),
        created_at=now_minus(days=4),
    )
    journal_purchase = GeneralJournal(
        id=DEMO_JOURNAL_IDS[1],
        vouchers_id=None,
        storage_url=None,
        date=now_minus(days=2),
        description="Ghi nhận nhập kho demo từ Nhà cung cấp Bình Minh.",
        status="pending",
        approved_at=None,
        created_at=now_minus(days=2),
    )
    session.add_all([journal_sale, journal_purchase])
    await session.flush()

    session.add_all(
        [
            GeneralJournalLine(
                general_journal_id=journal_sale.id,
                account_code="1111",
                account_name="Tiền mặt",
                debit=Decimal("12500000"),
                credit=Decimal("0"),
            ),
            GeneralJournalLine(
                general_journal_id=journal_sale.id,
                account_code="5111",
                account_name="Doanh thu bán hàng",
                debit=Decimal("0"),
                credit=Decimal("12500000"),
            ),
            GeneralJournalLine(
                general_journal_id=journal_purchase.id,
                account_code="1561",
                account_name="Hàng hóa",
                debit=Decimal("7800000"),
                credit=Decimal("0"),
            ),
            GeneralJournalLine(
                general_journal_id=journal_purchase.id,
                account_code="331",
                account_name="Phải trả người bán",
                debit=Decimal("0"),
                credit=Decimal("7800000"),
            ),
        ]
    )


async def seed_demo_data() -> None:
    async with AsyncSessionLocal() as session:
        await clear_demo_data(session)
        await seed_users(session)
        await seed_library_files(session)
        await seed_conversations(session)
        await seed_business_data(session)
        await session.commit()

    print("Seed demo data completed.")
    print("Users:", len(DEMO_USER_IDS))
    print("Conversations:", len(DEMO_CONVERSATION_IDS))
    print("Documents:", len(DEMO_DOCUMENT_IDS))
    print("Vouchers:", len(DEMO_VOUCHER_IDS))
    print("Partners:", len(DEMO_PARTNER_IDS))
    print("Inventory items:", len(DEMO_INVENTORY_IDS))
    print("Journal entries:", len(DEMO_JOURNAL_IDS))


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
