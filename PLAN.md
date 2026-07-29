# Kế hoạch xây dựng hệ thống AI hỗ trợ vận hành doanh nghiệp

## 1. Tổng quan hệ thống

Hệ thống chat AI nội bộ, phục vụ demo online cho khoảng **10 người dùng đồng thời**, chia thành 4 khu vực:

**Khu vực có UI:**
- **User UI (Web App)**: giao diện chat cho người dùng cuối, có lưu lịch sử trò chuyện, có mục **Thư viện** chứa các tệp tin người dùng đã tải lên hoặc do AI chỉnh sửa/tạo sinh.
- **Admin Dashboard (Web App)**: dành cho Admin, xem log, giám sát hoạt động hệ thống, trạng thái provider LLM, request, lỗi, token và chi phí.

**Khu vực không UI:**
- **Enterprise Knowledge**: chứa tri thức doanh nghiệp, SQL, dữ liệu RAG, đồng thời là nguồn dữ liệu để Admin Dashboard hiển thị.
- **VM (Máy ảo)**: môi trường AI làm việc, nhận yêu cầu từ User UI, điều phối LangGraph, gọi LLM Router, tương tác file/MCP tools, gọi Enterprise Knowledge khi cần dữ liệu, trả kết quả về UI.

Hệ thống phục vụ hai nhóm năng lực chính:

- **RAG**: hỏi đáp dựa trên tài liệu nội bộ đã được ingest vào vector DB.
- **Thực thi tác vụ qua MCP**: xử lý yêu cầu phức tạp cần thao tác trực tiếp trên file người dùng cung cấp, ví dụ tổng hợp Excel, cập nhật Word theo ảnh/chứng từ, hoặc tạo file kết quả mới.

Kiến trúc chi tiết:

| Khu vực | Vai trò | Thành phần |
|---|---|---|
| **Admin Dashboard** *(có UI)* | Giao diện quản trị | Next.js app riêng cho Admin, xem log, thống kê, trạng thái LLM providers |
| **User UI** *(có UI)* | Giao diện người dùng | Next.js app cho User, chat, lịch sử hội thoại, mục Thư viện |
| **Enterprise Knowledge** *(không UI)* | Dữ liệu & tri thức doanh nghiệp | SQL layer, RAG (LangChain + pgvector), API log/thống kê cho Admin Dashboard |
| **VM / Máy ảo** *(không UI)* | Môi trường thực thi AI | AI orchestrator (LangGraph), hàng đợi, LLM Router đa provider chính thức, MCP tools |

Cả Admin Dashboard và User UI đều là Next.js app deploy qua Firebase Hosting, cùng dùng Firebase Authentication để đăng nhập và phân quyền.

## 2. Bảng công nghệ đã chốt

| Thành phần | Công nghệ | Ghi chú |
|---|---|---|
| LLM provider 1 | Google Gemini API, Tier 1 | Dùng 1 API key chính thức qua `GOOGLE_API_KEY` |
| LLM provider 2 | Anthropic Claude API | Dùng 1 API key chính thức qua `ANTHROPIC_API_KEY` |
| LLM Router | Provider router trong VM service | Dùng Google key trước tiên làm mặc định cho tất cả các phase; nếu lỗi thì tự động fallback sang Claude key; không dùng local fallback |
| Embedding | Gemini Embedding 2 | Dùng Google Gen AI SDK, giới hạn 8.192 token/input, lưu vector 768 chiều |
| AI orchestration | LangGraph | Điều phối AI, phân loại ý định, gọi tool qua MCP, RAG |
| RAG | LangChain | Kết nối retriever với pgvector |
| Backend | FastAPI | Enterprise Knowledge service + VM service |
| Vector DB | PGVector (extension của PostgreSQL) | Lưu embedding tài liệu |
| ORM | SQLAlchemy | Truy vấn Postgres |
| Alembic | SQLAlchemy | Quản lý Database Migration |
| Database | PostgreSQL | Dữ liệu nghiệp vụ + vector + metadata file |
| Cache / Queue | Redis | Session, cache, hàng đợi request, state tác vụ |
| Authentication | Firebase Authentication | Đăng nhập cho Admin Dashboard và User UI, phân quyền role |
| File storage | Firebase Storage | Lưu file thô và file AI tạo/sửa |
| Frontend | Next.js (static export) | 2 app: User UI và Admin Dashboard, deploy qua Firebase Hosting |
| Containerization | Docker + docker-compose | Đồng bộ môi trường dev -> production |
| Network | Cloudflare Tunnel | Expose Máy ảo ra internet an toàn |
| MCP / Tools | MCP server tùy biến | Đọc/ghi Excel, Word, Email và các tool nghiệp vụ |

## 3. Cơ chế LLM Router đa provider chính thức

- Hệ thống chỉ dùng các API key chính thức:
  - `GOOGLE_API_KEY` cho Google Gemini API.
  - `ANTHROPIC_API_KEY` cho Anthropic Claude API.
- Không dùng local fallback. Nếu provider lỗi hoặc hết quota, router sẽ trả lỗi có cấu trúc hoặc chuyển sang provider chính thức còn khả dụng theo policy nội bộ.
- Router chạy trong VM service và trừu tượng hóa các thao tác:
  - Chọn provider/model theo policy nội bộ: Dùng Google làm mặc định cho tất cả các phase; Anthropic Claude chỉ dùng làm fallback khi Google lỗi.
  - Chuẩn hóa request/response, token usage, lỗi, timeout và retry.
  - Ghi metadata provider/model/token/cost về Enterprise Knowledge để Admin Dashboard hiển thị.
- Model mặc định hiện cấu hình qua env:
  - `GOOGLE_LLM_MODEL=gemini-3.1-flash-lite`
  - `ANTHROPIC_LLM_MODEL=claude-sonnet-5`
- Policy routing là logic nội bộ của router, không cấu hình qua env.
- Admin Dashboard hiển thị trạng thái provider LLM ở endpoint `/admin/dashboard/llm-providers`, không hiển thị secret.

## 4. Lộ trình triển khai (ROADMAP)

```text
Chỉ dẫn:

1. Trước khi bắt đầu phiên làm việc, cần xem xét có câu hỏi gì cần làm rõ không, nếu có thì cập nhật file PLAN.md này và liệt kê dưới tiêu đề:
   #### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này

2. Những việc nào không thể tự làm mà cần Admin tự làm thì note lại cuối hàng theo tag `**của admin**`

3. Sau khi hoàn thành phiên làm việc, đánh dấu `[x]` vào từng việc để theo dõi tiến độ qua các phiên làm việc.
```

### Giai đoạn 0 — Hạ tầng nền (2-3 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này
- [x] Xác nhận kiến trúc triển khai vật lý `admin trả lời: Laptop Windows = Enterprise Knowledge tier; Linux VM VirtualBox = VM/AI tier`
- [x] Xác nhận cấu trúc phân quyền role `admin trả lời: admin/ceo/manager`

#### Việc cần làm giai đoạn này
- [x] Cài Docker Desktop trên Laptop Windows **của admin**
- [x] Cài Docker + Docker Compose trên Linux VM (VirtualBox) **của admin**
- [x] Viết docker-compose khung cho Laptop tier và VM tier
- [x] Khởi tạo repo với `backend/`, `frontend-user/`, `frontend-admin/`
- [x] Tạo Firebase project, bật Firebase Authentication và Firebase Storage **của admin**

### Giai đoạn 1 — Enterprise Knowledge service (4-5 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này
- [x] Embedding dùng Gemini Embedding 2 qua thư viện: `admin trả lời: google-genai`
- [x] Pipeline ingest RAG chỉ hỗ trợ Markdown `.md` đúng không: `admin trả lời: đúng vậy và các định dạng khác báo lỗi`
- [x] Dùng Alembic để quản lý migration `admin trả lời: đồng ý`
- [x] RAG pipeline trong Enterprise Knowledge chỉ trả chunk/source/score để VM xử lý câu trả lời`admin trả lời: đồng ý`
- [x] Tài liệu RAG dùng chung cho mọi role ở bước retrieval hiện tại `admin trả lời: đồng ý`
- [x] Retrieval mặc định là gì `admin trả lời:  top_k=5, score_threshold=0.7`
- [x] Admin Dashboard cần xem nội dung đầy đủ tin nhắn/request-response và metadata đúng không?: `admin trả lời: đúng`
- [x] Chuẩn bị sẵn phân quyền dashboard cho admin/ceo; ceo bị ẩn email của ceo khác `admin trả lời: đúng`

#### Việc cần làm giai đoạn này
- [x] Định nghĩa schema SQLAlchemy và chạy Alembic migration
- [x] Bổ sung/điều chỉnh các bảng nghiệp vụ theo góp ý của Admin
- [x] Viết pipeline ingest Markdown -> token gate -> chunk -> embed -> lưu pgvector
- [x] Xây SQL query layer read-only cho dữ liệu nghiệp vụ
- [x] Xây RAG retrieval API `/rag/search`
- [x] Xây API log/thống kê cho Admin Dashboard
- [x] Tạo script seed demo data cho môi trường dev/demo
- [x] Bổ sung `agent_plans.mcp_tools`
- [x] Expose API nội bộ `/internal/v1/*` cho VM gọi qua `EK_INTERNAL_API_KEY`

### Giai đoạn 2 — LLM Router đa provider chính thức (4-5 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này
- [x] Xác nhận model sử dụng `admin trả lời: Gemini 3.1 Flash-Lite và claude-sonnet-5; mỗi provider chỉ cần 1 model`
- [x] Xác nhận policy routing ban đầu `admin trả lời: Dùng Google key trước tiên cho tất cả yêu cầu, nếu bị lỗi thì dùng Claude key (fallback); policy là logic nội bộ, không cần cấu hình qua env`

#### Việc cần làm giai đoạn này
- [x] Cập nhật placeholder Admin Dashboard cho trạng thái LLM providers
- [x] Thiết kế interface LLM Router chuẩn hóa request/response/token usage/error
- [x] Viết policy chọn provider/model theo phase: Dùng Google key trước tiên cho tất cả các phase, tự động fallback sang Claude key nếu gặp lỗi; có timeout và fallback chính thức
- [x] Ghi provider/model/token/cost/error metadata về Enterprise Knowledge
- [x] Test router với request đơn, request song song và lỗi giả lập từ từng provider

### Giai đoạn 3 — AI Orchestrator + hàng đợi (4-5 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này
- [x] Multi-turn source of truth: lưu bền vững trong PostgreSQL qua `conversations/messages`; Redis chỉ giữ queue, lock, state tác vụ đang chạy và cache ngắn hạn
- [x] Giai đoạn 3 chưa cần streaming token; làm request/response non-stream trước, streaming để Giai đoạn 7
- [x] Intent ban đầu gồm `rag_query`, `business_query`, `task_execution`, `general_chat`
- [x] Endpoint public đầu tiên của VM là `POST /v1/chat`
- [x] Xác thực demo dùng header `X-User-Id`, `X-User-Email`, `X-User-Role`; Giai đoạn 5 thay bằng Firebase JWT
- [x] Redis Giai đoạn 3 dùng concurrency gate/state cơ bản, chưa cần worker process riêng
- [x] File upload tối đa 2 file/request; chỉ cho phép `.png`, `.md`; `.md` tối đa 2 MB, `.png` tối đa 10 MB
- [x] File raw mới upload lưu tạm ở VM (`backend/vm_service/storage/uploads/raw/`); file đã kiểm duyệt/làm sạch lưu tại VM (`backend/vm_service/storage/uploads/clean/`). EK chỉ chứa SQL và RAG, KHÔNG lưu tệp tin upload của người dùng.
- [x] MIME chỉ check/log phụ, không tin tuyệt đối; hard rule là extension + parser đọc được file.
- [x] AI Firewall 2 lớp:
  - **Lớp 1 (Check Role)**: Check role qua LLM dựa trên Permission Matrix, trả về JSON `{"is_valid": bool, "reason": str, "details": dict}`.
  - **Lớp 2 (Check File - 100% Backend Hard-code)**:
    - Xóa toàn bộ Metadata ẩn cho MỌI LOẠI FILE (không cần check độc hại hay không).
    - `.png`: Check Magic Bytes 8 ký tự `b"\x89PNG\r\n\x1a\n"`, resize bằng Pillow nếu kích thước lớn để tiết kiệm token.
    - `.md`: Xóa URL link `[text](url)` -> `text` trực tiếp bằng Regex `re.sub`.
- [x] VM CHỈ ĐƯỢC GỬI FILE ĐÃ CLEANED LÊN LLM API.
- [x] Bảo mật kết nối nghiêm ngặt: VM bị cấm gửi request đến domain lạ ngoài danh sách trắng (chỉ gửi tới EK Service và official LLM APIs). EK chỉ chấp nhận và thực thi các request nội bộ từ VM qua khóa `X-Internal-Api-Key`.
- [x] Agent Planner: Cấu trúc Kế hoạch thực thi (Execution Plan) chuẩn hóa gồm tên kế hoạch (`plan_name`), số bước (`total_steps`), và danh sách các bước (`steps`) chi tiết (`step_number`, tên bước `step_name`, `action`, `thought`), quản lý và lưu trữ trực tiếp bởi bảng `agent_plans` và `agent_steps` trong CSDL PostgreSQL EK.

#### Việc cần làm giai đoạn này
- [x] Thiết kế luồng làm việc: User gửi chat > AI_firewall > Planner > Execution > Response
- [x] Kết nối orchestrator với LLM Router và Enterprise Knowledge API
- [x] Xây hàng đợi/concurrency gate Redis để giãn cách khi nhiều người dùng đồng thời
- [x] Lưu hội thoại multi-turn bền vững vào Postgres qua Enterprise Knowledge; Redis giữ state runtime ngắn hạn
- [x] Xây xử lý upload file ở VM: raw upload, 100% hardcode backend validation (signature check, strip metadata cho mọi file, `.md` regex link removal, `.png` resize tiết kiệm token), lưu file sạch cục bộ tại VM (`storage/uploads/clean/`), truyền tệp `.png` và `.md` sạch trực tiếp qua Multimodal LLM Router để trả lời ngay lập tức cho người dùng trong luồng `task_execution`
- [x] Nâng cấp AI Firewall check role theo Permission Matrix và định dạng JSON `is_valid` / `reason` / `details`
- [x] Nâng cấp Agent Planner sinh Kế hoạch thực thi đa bước chi tiết (`plan_name`, `total_steps`, `step_number`, `step_name`, `action`, `thought`) và liên kết lưu trữ vào bảng `agent_plans` / `agent_steps`
- [x] Thi hành bảo mật kết nối: Khóa xác thực `X-Internal-Api-Key` cho EK và kiểm soát kết nối đầu ra cho VM





### Giai đoạn 4 — Xây dựng MCP  (4-5 ngày)
#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này



#### Việc cần làm giai đoạn này
- [x] bộ khung MCP mcp_manager
- [x] Email MCP - tool: check_email
- [x] Email MCP - tool: search_email (refresh_inbox trước, lọc partner, lưu SQLite, hỗ trợ date_from, only_unreplied)
- [x] Email MCP - cải tiến send_email: tự động refresh_inbox() trước khi gửi, đánh dấu replied_at
- [x] VM Endpoint `GET /email/history` — xem lịch sử history_message, hỗ trợ filter sender/query/date_from/only_unreplied


### Giai đoạn 5 — Authentication & Authorization (3-4 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này

#### Việc cần làm giai đoạn này
- [ ] Tích hợp Firebase Authentication cho User UI và Admin Dashboard
- [ ] Tích hợp Google Sign-In; frontend gửi ID Token/JWT qua `Authorization: Bearer ...`
- [ ] Viết middleware FastAPI xác thực token Firebase trên API công khai
- [ ] Khóa các endpoint public-ish hiện tại sau auth; VM tiếp tục dùng `/internal/v1/*`
- [ ] Phân quyền role: `admin`, `ceo`, `manager`
- [ ] Gắn `user_id` vào `conversations`, `messages`, `library_files`

### Giai đoạn 6 — Giám sát & an toàn (3-4 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này

#### Việc cần làm giai đoạn này
- [ ] Dựng hệ cơ chế nhận thông báo, chờ phê duyệt
- [ ] Ghi log request/response vào Enterprise Knowledge
- [ ] Ghi log hành động ghi/sửa dữ liệu (audit trail)
- [ ] Xây cơ chế "dừng khẩn cấp"
- [ ] Xây alerting cơ bản khi có lỗi hoặc hành động bất thường

### Giai đoạn 7 — User UI trên Firebase Hosting (4-5 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này

#### Việc cần làm giai đoạn này
- [ ] Dựng giao diện chat streaming
- [ ] Xây trang lịch sử hội thoại
- [ ] Xây mục Thư viện
- [ ] Cấu hình Next.js static export
- [ ] Deploy lên Firebase Hosting
- [ ] Kết nối frontend với API Máy ảo qua HTTPS + Firebase Auth

### Giai đoạn 8 — Admin Dashboard trên Firebase Hosting (3-4 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này

#### Việc cần làm giai đoạn này
- [ ] Dựng giao diện xem log/audit trail
- [ ] Xây trang giám sát trạng thái LLM providers
- [ ] Xây trang thống kê hoạt động tổng quan
- [ ] Xây nút kích hoạt "dừng khẩn cấp"
- [ ] Deploy lên Firebase Hosting, giới hạn truy cập theo role admin/ceo

### Giai đoạn 9 — Test tải & tinh chỉnh (3-4 ngày)

#### Những thông tin cần xác nhận từ Admin trước khi bắt đầu giai đoạn này

#### Việc cần làm giai đoạn này
- [ ] Viết kịch bản test tải 10 kết nối đồng thời
- [ ] Đo độ trễ phản hồi thực tế
- [ ] Kiểm tra hành vi router khi Google/Claude chậm, lỗi hoặc hết quota
- [ ] Điều chỉnh kích thước hàng đợi/timeout
- [ ] Chuyển triển khai từ VM dev sang VPS 16GB production

**Tổng thời gian ước tính**: khoảng 8-9 tuần nếu làm bán thời gian.
