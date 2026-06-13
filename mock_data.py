"""
Mock data for development and testing.
Replaces real API connectors until they are wired in Phase 8.
"""

MOCK_JIRA: list[dict] = [
    {
        "id": "JIRA-1001",
        "source": "jira",
        "text": (
            "User reports Visa card top-up failing repeatedly. "
            "Error code E5001 appears after entering card details and clicking confirm."
        ),
        "images": [],
        "timestamp": "2026-06-10T09:00:00",
    },
    {
        "id": "JIRA-1002",
        "source": "jira",
        "text": (
            "QR code scan not working at Highlands Coffee on Nguyen Hue street. "
            "Camera focuses but nothing happens. Multiple users affected since 8am."
        ),
        "images": [],
        "timestamp": "2026-06-10T10:00:00",
    },
    {
        "id": "JIRA-1003",
        "source": "jira",
        "text": (
            "OTP not received on registered phone number after login attempt. "
            "User waited over 15 minutes. Tried resending 3 times."
        ),
        "images": [],
        "timestamp": "2026-06-10T10:30:00",
    },
    {
        "id": "JIRA-1004",
        "source": "jira",
        "text": (
            "App crashes immediately on launch. "
            "Samsung Galaxy S21, Android 13, Zalopay version 4.2.1."
        ),
        "images": [],
        "timestamp": "2026-06-10T11:00:00",
    },
    {
        "id": "JIRA-1005",
        "source": "jira",
        "text": (
            "User charged twice for a single Grab top-up transaction. "
            "Both charges reflected in bank statement but only one in Zalopay history."
        ),
        "images": [],
        "timestamp": "2026-06-10T11:30:00",
    },
]

MOCK_SOCIAL: list[dict] = [
    # ── Negative posts (should pass sentiment filter) ──────────────────
    {
        "id": "FB-2001",
        "source": "facebook",
        "text": "Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!!",
        "images": [],
        "timestamp": "2026-06-10T08:30:00",
    },
    {
        "id": "FB-2002",
        "source": "facebook",
        "text": "Quét QR không được tại Circle K. Đứng xếp hàng mà thanh toán không qua, xấu hổ vl.",
        "images": [],
        "timestamp": "2026-06-10T07:15:00",
    },
    {
        "id": "FB-2003",
        "source": "facebook",
        "text": "App Zalopay crash liên tục khi mở lên. Xóa cài lại vẫn bị. Dùng iPhone 14.",
        "images": [],
        "timestamp": "2026-06-10T06:50:00",
    },
    {
        "id": "TH-3001",
        "source": "threads",
        "text": "Zalopay không gửi OTP về điện thoại. Đăng nhập không được luôn, ai gặp chưa?",
        "images": [],
        "timestamp": "2026-06-10T07:00:00",
    },
    {
        "id": "TH-3002",
        "source": "threads",
        "text": "Nạp tiền bằng thẻ Visa bị lỗi E5001 hoài. Thẻ vẫn còn tiền mà không nạp được.",
        "images": [],
        "timestamp": "2026-06-10T08:00:00",
    },
    {
        "id": "TH-3003",
        "source": "threads",
        "text": "Bị trừ tiền 2 lần khi thanh toán đơn Shopee qua Zalopay. Tiền mất mà đơn không xác nhận.",
        "images": [],
        "timestamp": "2026-06-10T09:15:00",
    },
    # ── Positive posts (should be filtered OUT by sentiment) ───────────
    {
        "id": "FB-2004",
        "source": "facebook",
        "text": "Zalopay tiện lợi lắm, dùng mấy năm rồi không có vấn đề gì!",
        "images": [],
        "timestamp": "2026-06-10T08:45:00",
    },
    {
        "id": "TH-3004",
        "source": "threads",
        "text": "Great app, been using Zalopay for years. Super fast transfers!",
        "images": [],
        "timestamp": "2026-06-10T09:30:00",
    },
]


def get_mock_jira() -> list[dict]:
    return [item.copy() for item in MOCK_JIRA]


def get_mock_social() -> list[dict]:
    return [item.copy() for item in MOCK_SOCIAL]
