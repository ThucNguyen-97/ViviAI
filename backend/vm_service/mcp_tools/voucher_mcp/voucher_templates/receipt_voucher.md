<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<style>
    @page {
        size: A5 landscape;
        margin: 8mm 12mm;
        background-color: #ffffff;
    }
    * {
        box-sizing: border-box;
        padding: 5px;
    }
    body {
        font-family: "Times New Roman", Times, serif;
        font-size: 12pt;
        color: #000000;
        line-height: 1.35;
        margin: 0;
        padding: 0;
    }

    .header-table {
        width: 100%;
        border-collapse: collapse;
        border: none !important;
        margin-bottom: 5px;
    }
    .header-table td {
        border: none !important;
        padding: 0;
        vertical-align: top;
    }

    .logo-box {
        width: 100px;
        height: 100px;
        border: 1px dashed #666;
        display: inline-block;
        text-align: center;
        line-height: 45px;
        font-size: 9.5pt;
        color: #666;
    }

    .text-right { text-align: right; }
    .text-center { text-align: center; }
    .bold { font-weight: bold; }
    .italic { font-style: italic; }

    /* Khối Mẫu số: Chữ căn giữa, nhưng toàn bộ khối đẩy sát lề phải */
    .sample-code-box {
        display: inline-block;
        float: right;
        text-align: center;
    }

    .main-title-table {
        width: 100%;
        border-collapse: collapse;
        border: none !important;
    }
    .main-title-table td {
        border: none !important;
        padding: 0;
    }

    .form-title {
        font-size: 18pt;
        font-weight: bold;
        text-transform: uppercase;
        margin: 0;
    }

    .info-section {
        line-height: 1.6;
    }

    .signature-table {
        width: 100%;
        border-collapse: collapse;
        border: none !important;
    }
    .signature-table td {
        border: none !important;
        padding: 2px 0;
        vertical-align: top;
        text-align: center;
    }

    .footer-notes {
        margin-top: 40px;
        line-height: 1.45;
        font-size: 12pt;
    }
</style>
</head>
<body>

<!-- Phần 1: Đơn vị / Địa chỉ (Trái) & Mẫu số / Thông tư (Phải) -->
<table class="header-table" width="100%">
    <tr>
        <td width="50%">
            <span class="bold">ĐƠN VỊ:</span> {{company_name}}<br>
            <span class="bold">Địa chỉ:</span> {{company_address}}
        </td>
        <td width="50%">
            <div class="sample-code-box">
                <span class="bold">Mẫu số: 01 - TT</span><br>
                <span class="italic" style="font-size: 12pt;">(Kèm theo Thông tư số 99/2025/TT-BTC<br>ngày 27 tháng 10 năm 2025 của Bộ trưởng Bộ Tài chính)</span>
            </div>
        </td>
    </tr>
</table>

<!-- Phần 2: Logo (Trái) & Tiêu đề PHIẾU THU (Giữa) -->
<table class="main-title-table">
    <tr>
        <td width="20%" style="vertical-align: top;">
            <div class="logo-box">{{company_logo}}</div>
        </td>
        <td width="60%" class="text-center" style="vertical-align: top; padding-top: 15px">
            <div class="form-title">PHIẾU THU</div>
            <span class="italic">Ngày {{receipt_day}} tháng {{receipt_month}} năm {{receipt_year}}</span>
        </td>
        <td width="20%"></td>
    </tr>
    <!-- Dòng hiển thị Số, Nợ, Có ở góc phải, ngay bên dưới tiêu đề -->
    <tr>
        <td colspan="3" class="text-right">
            <div style="line-height: 1.4; display: inline-block; text-align: left;">
                Số: {{receipt_number}}<br>
                Nợ: {{debit_account}}<br>
                Có: {{credit_account}}
            </div>
        </td>
    </tr>
</table>

<div class="info-section">
    Họ và tên người nộp tiền:{{payer_name}}<br>
    Đơn vị: {{payer_unit}}<br>
    Địa chỉ: {{payer_address}}<br>
    Lý do nộp: {{payment_reason}}<br>
    Số tiền: {{amount}} (Viết bằng chữ): {{amount_in_words}}<br>
    Kèm theo: {{attachment_count}} Chứng từ gốc:{{original_document}}
</div>

<div>
    <div class="text-right italic" style="margin-bottom: 3px; padding-right: 15px;">
        Ngày....... tháng....... năm..........
    </div>
    <table class="signature-table">
        <tr class="bold">
            <td width="25%">Giám đốc</td>
            <td width="25%">Kế toán trưởng</td>
            <td width="25%">Người nộp tiền</td>
            <td width="25%">Người lập phiếu</td>
        </tr>
        <tr class="italic" style="font-size: 12pt;">
            <td>(Ký, họ tên, đóng dấu)</td>
            <td>(Ký, họ tên)</td>
            <td>(Ký, họ tên)</td>
            <td>(Ký, họ tên)</td>
        </tr>
        <tr style="height: 45px;">
            <td id="director_signature"></td>
            <td id="chief_accountant_signature"></td>
            <td id="payer_signature"></td>
            <td id="creator_signature"></td>
        </tr>
    </table>
</div>

<div class="footer-notes">
    Đã nhận đủ số tiền (viết bằng chữ): {{received_amount_in_words}}<br>
    + Tỷ giá ngoại tệ (vàng, bạc, đá quý):.................................................................................................................................. <br>
    + Số tiền quy đổi:..................................................................................................................................................................<br>
</div>

<div class="italic" style="font-size: 12pt; margin-top: 2px;">
    (Liên gửi ra ngoài phải đóng dấu)
</div>

</body>
</html>