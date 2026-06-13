# Domain & Segment Taxonomy

Grounding reference for classification. One section per segment: a short definition plus
example complaint phrasings (Vietnamese + English). Indexed into the `taxonomy` collection
and retrieved by the classifier to ground domain/segment decisions in real examples.

This file is NOT a solution doc — it has no "## Suggested Approach" sections and is excluded
from the knowledge_base (solution) collection.

---

## Payment / Top-up
**Domain:** Payment
**Segment:** Top-up
Definition: Adding money into the Zalopay wallet from a card or bank fails or errors.
Examples:
- "Không nạp tiền được bằng thẻ Visa, báo lỗi E5001"
- "Nạp tiền vào ví mãi không thành công"
- "Top-up with Mastercard keeps failing at the confirmation step"

---

## Payment / Transfer
**Domain:** Payment
**Segment:** Transfer
Definition: Peer-to-peer money transfers between Zalopay users or to bank accounts fail.
Examples:
- "Chuyển tiền cho bạn mà báo lỗi người nhận không tồn tại"
- "Chuyển khoản bị treo, tiền trừ rồi mà người nhận không nhận được"
- "P2P transfer failed with limit exceeded error"

---

## Payment / Withdrawal
**Domain:** Payment
**Segment:** Withdrawal
Definition: Withdrawing the wallet balance out to a linked bank account fails.
Examples:
- "Rút tiền về ngân hàng không được"
- "Rút tiền mãi không thấy về tài khoản"
- "Cannot withdraw balance to my linked bank"

---

## Payment / Billing
**Domain:** Payment
**Segment:** Billing
Definition: Bill payments, duplicate charges, or incorrect deductions.
Examples:
- "Bị trừ tiền hai lần cho một giao dịch"
- "Thanh toán hóa đơn điện nhưng bị trừ tiền mà chưa ghi nhận"
- "Charged twice for one payment, refund not received"

---

## QR Code / Payment
**Domain:** QR Code
**Segment:** Payment
Definition: Paying by scanning a QR code fails or the QR is rejected.
Examples:
- "Quét QR thanh toán không được"
- "Mã QR báo hết hạn ngay khi vừa tạo"
- "QR payment fails at checkout"

---

## QR Code / Generation
**Domain:** QR Code
**Segment:** Generation
Definition: Generating / displaying a QR code in the app fails.
Examples:
- "Không tạo được mã QR để nhận tiền"
- "Màn hình tạo QR bị trắng, không hiện mã"
- "My QR code won't generate"

---

## QR Code / Merchant
**Domain:** QR Code
**Segment:** Merchant
Definition: Scanning a merchant's QR at a store/terminal fails.
Examples:
- "Quét QR ở Circle K không thanh toán được"
- "QR tại quán không nhận, đứng xếp hàng mãi"
- "Merchant QR at Highlands not scanning"

---

## Account / Login
**Domain:** Account
**Segment:** Login
Definition: Cannot sign in to the Zalopay account.
Examples:
- "Đăng nhập không được"
- "App báo sai mật khẩu dù nhập đúng"
- "Cannot log in, keeps rejecting my credentials"

---

## Account / OTP
**Domain:** Account
**Segment:** OTP
Definition: One-time password / verification code not received or rejected.
Examples:
- "OTP không về điện thoại, đợi 10 phút vẫn chưa thấy"
- "Mã xác thực gửi về bị sai/hết hạn"
- "OTP never arrives on my phone"

---

## Account / Registration
**Domain:** Account
**Segment:** Registration
Definition: Creating a new account or completing eKYC verification fails.
Examples:
- "Đăng ký tài khoản mới không được"
- "Xác minh danh tính (eKYC) báo lỗi liên tục"
- "Registration / identity verification keeps failing"

---

## Account / Profile
**Domain:** Account
**Segment:** Profile
Definition: Updating profile info, linked accounts, or settings fails.
Examples:
- "Không đổi được số điện thoại trong hồ sơ"
- "Liên kết ngân hàng bị mất, không cập nhật được"
- "Can't update my profile / linked bank"

---

## App Performance / Crash
**Domain:** App Performance
**Segment:** Crash
Definition: The app closes unexpectedly or freezes.
Examples:
- "App bị crash khi mở lên"
- "Mở app là tự thoát ra ngay"
- "App keeps crashing on launch"

---

## App Performance / Loading
**Domain:** App Performance
**Segment:** Loading
Definition: The app is stuck loading, very slow, or spins forever.
Examples:
- "App load mãi không vào được"
- "Màn hình quay vòng tròn không dừng"
- "App stuck on loading spinner"

---

## App Performance / UI Bug
**Domain:** App Performance
**Segment:** UI Bug
Definition: Visual glitches, broken layout, or buttons that don't respond.
Examples:
- "Giao diện bị lỗi, nút bấm không ăn"
- "Chữ bị chồng lên nhau, hiển thị sai"
- "UI is broken, buttons don't respond"

---

## Merchant / POS
**Domain:** Merchant
**Segment:** POS
Definition: Merchant point-of-sale terminal issues accepting Zalopay.
Examples:
- "Máy POS của cửa hàng không nhận thanh toán Zalopay"
- "Quẹt ở máy bán hàng báo lỗi kết nối"
- "POS terminal won't accept Zalopay"

---

## Merchant / Settlement
**Domain:** Merchant
**Segment:** Settlement
Definition: Merchant payout/settlement of collected funds is delayed or wrong.
Examples:
- "Tiền bán hàng chưa về tài khoản cửa hàng"
- "Đối soát doanh thu bị sai số"
- "Merchant settlement delayed / amount incorrect"

---

## Merchant / Onboarding
**Domain:** Merchant
**Segment:** Onboarding
Definition: Registering or activating a merchant account fails.
Examples:
- "Đăng ký cửa hàng làm merchant không duyệt được"
- "Hồ sơ mở merchant bị treo"
- "Merchant onboarding application stuck"

---

## Other / General
**Domain:** Other
**Segment:** General
Definition: Anything that does not fit the categories above (general feedback, unclear reports).
Examples:
- "App dùng khó hiểu quá"
- "Có vấn đề chung chung không rõ thuộc mục nào"
- "General complaint that doesn't fit a specific area"
