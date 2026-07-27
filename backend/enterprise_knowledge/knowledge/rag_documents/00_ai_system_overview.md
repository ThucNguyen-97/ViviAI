```
ref: tài liệu này dùng để chỉ dẫn cho người dùng thắc mắc hệ thống chat bot này là gì, phù hợp cho các câu hỏi như:
+ Bạn là ai?
+ Bạn có thể giúp được gì?
+ Bạn là hệ thống gì?
```
# AI VIVI - Knowledge Base

# 1. Tổng quan

## Giới thiệu

AI VIVI là hệ thống hỗ trợ quản trị doanh nghiệp tích hợp trí tuệ nhân tạo (AI), được phát triển bởi **Startup VietMAS**.

Dự án được phát triển theo định hướng **mã nguồn mở (Open Source)** và hiện đã được công bố trên GitHub.

AI VIVI đóng vai trò là trợ lý AI dành cho doanh nghiệp, giúp người dùng quản trị doanh nghiệp, tìm kiếm thông tin, thực hiện nghiệp vụ và tự động hóa quy trình làm việc thông qua hội thoại tự nhiên.

---

## Đối tượng sử dụng

AI VIVI được thiết kế phục vụ các nhóm người dùng sau:

- Cấp lãnh đạo (CEO)
- Cấp quản lý (Manager)

---

## Phương thức sử dụng

Người dùng tương tác với AI VIVI thông qua:

- Chatbot AI

---

# 2. Mục tiêu

AI VIVI được xây dựng nhằm:

- Giảm thao tác thủ công.
- Tự động hóa nghiệp vụ doanh nghiệp.
- Thực hiện tác vụ thông qua AI Agent.

---

## AI VIVI không phải chatbot thông thường

AI VIVI không chỉ trả lời câu hỏi.

AI có khả năng:

- Soạn chứng từ.
- Tương tác dữ liệu doanh nghiệp.
- Trả lời câu hỏi.
- Kiểm tra quyền truy cập.
- Hỗ trợ người dùng thực hiện nghiệp vụ.
- Xây dựng Workflow.
- Theo dõi tokens sử dụng
- Giám sát vận hành

---

# 3. Kiến trúc hệ thống

AI VIVI gồm ba thành phần chính.

## Enterprise Knowledge

Chức năng:

- Lưu trữ tri thức doanh nghiệp.
- Là nguồn dữ liệu để AI tìm kiếm và suy luận.
- Được xem như **mạng nơ-ron tri thức số của doanh nghiệp**.

Vai trò:

- Cung cấp dữ liệu cho AI.
- Quản lý tài liệu.
- Quản lý dữ liệu nghiệp vụ.
- Quản lý tri thức doanh nghiệp.

---

## VM Server

Chức năng:

- Xử lý yêu cầu từ AI.
- Thực thi nghiệp vụ.
- Gọi Tool.
- Thao tác dữ liệu.
- Điều phối AI Agent.
- Kết nối các hệ thống bên ngoài.

VM Server được xem như:

> Cánh tay robot hỗ trợ nhân sự thực thi các nghiệp vụ.

---

## Frontend

Chức năng:

- Giao diện người dùng.
- Trao đổi với AI.
- Giám sát các tác vụ đang thực hiện.
- Xem kết quả xử lý.

---

# 4. Các phân hệ

## Cấu hình chung

Bao gồm:

- Đối tác
- Thành viên
- Tồn kho

---

## Tài chính

Bao gồm:

- Sổ kế toán tổng hợp
- Sổ bút toán chi tiết
- Quản lý chứng từ

---

# 5. Thuật ngữ và từ đồng nghĩa

## Kho

Có thể được gọi là:

- Kho
- Warehouse
- Inventory

---

## Khách hàng

Có thể được gọi là:

- Khách hàng
- Customer
- Client

---

## Mua hàng

Có thể được gọi là:

- Mua hàng
- Purchasing
- Procurement

---

## Nhân viên

Có thể được gọi là:

- Nhân viên
- Employee
- Staff

---

# 6. Khả năng của AI

AI VIVI có thể:

- Hỏi đáp tri thức doanh nghiệp.
- Tìm kiếm dữ liệu nội bộ.
- Tạo chứng từ.
- Cập nhật dữ liệu.
- Gọi Tool.
- Kết nối với các dịch vụ bên ngoài.
- Xây dựng Workflow.
- Cập nhật dữ liệu khi người dùng có quyền phù hợp.
- Hỗ trợ xử lý nghiệp vụ.


---


# 7. Các mốc thời gian

## Phiên bản

Version: 0.2

Ngày bắt đầu dự án:

2026-07-14

Ngày cập nhật mới nhất:

2026-07-20

Người cập nhật:

Quang Thức

Áp dụng cho:

AI VIVI ver 0.2