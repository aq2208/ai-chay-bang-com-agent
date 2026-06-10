# QR Code Issues

**Domain:** QR Code
**Segments:** Payment, Generation, Merchant
**Error codes:** QR-001, QR-002, QR-003

---

## QR Scan Failure at Merchant Terminal

**Symptoms:** User opens ZaloPay, points camera at merchant QR code, nothing happens. Camera focuses but payment does not initiate. Affects multiple users at the same merchant.

**Cause A (most common):** Merchant QR code is damaged, faded, or printed at wrong size. Minimum QR display size is 3×3 cm. Laminated or screen-glare QR codes frequently fail.
**Cause B:** Merchant's static QR code has expired. Static QRs expire after 12 months.
**Cause C:** User's phone camera has low resolution or AR mode interfering with QR detection.

## Suggested Approach

1. Ask if multiple users are affected at the same merchant — if yes, issue is with the merchant's QR, not the user's app.
2. Check merchant QR expiry in merchant dashboard (`merchant.zalopay.vn → QR Management`). Regenerate if expired.
3. Advise merchant to reprint QR at minimum 5×5 cm, matte finish (no lamination glare), black on white background only.
4. If single user affected: check ZaloPay app camera permissions (`phone settings → ZaloPay → Camera → Allow`). Re-grant if denied.
5. Temporary fix: user can manually enter merchant code instead of scanning.

---

## Dynamic QR Generation Failure

**Symptoms:** Cashier's ZaloPay POS cannot generate a QR code for the transaction. Screen shows loading spinner indefinitely.

**Cause:** Merchant's device has no internet connectivity, or the QR generation API endpoint is down.

## Suggested Approach

1. Verify merchant device's internet connection — open a browser and test.
2. Check ZaloPay QR API status at `status.zalopay.vn`.
3. If API is up but merchant still fails: clear merchant app cache (`Settings → Apps → ZaloPay → Clear Cache`) and retry.
4. Escalate to merchant support team if >3 merchants report simultaneously — likely infrastructure issue.

---

## QR Payment Deducted but Merchant Not Notified

**Symptoms:** User's ZaloPay balance is deducted but merchant POS shows no payment confirmation. Merchant asks user to pay again.

**Cause:** Webhook notification to merchant's system failed (merchant server down or webhook URL changed).

## Suggested Approach

1. Pull transaction from ZaloPay admin to confirm it was settled on ZaloPay's side.
2. Show user the transaction receipt screenshot as proof.
3. Contact merchant's technical team — their webhook endpoint may be down. They can verify in `merchant.zalopay.vn → Transaction History`.
4. Do NOT advise user to pay again until both sides are confirmed. If double payment occurs, initiate refund immediately.
