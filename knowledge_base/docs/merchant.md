# Merchant Issues

**Domain:** Merchant
**Segments:** POS, Settlement, Onboarding

---

## POS Terminal Not Receiving Payments

**Symptoms:** Merchant's Zalopay POS device shows transactions as pending, or customer payments do not appear on the POS screen in real time.

**Cause A:** POS device has lost its WebSocket connection to Zalopay's notification server.
**Cause B:** Merchant's network has a restrictive firewall blocking WebSocket (port 443 with upgrade headers).
**Cause C:** POS software is outdated — older versions have a known WebSocket reconnect bug.

## Suggested Approach

1. Check POS software version — must be v3.2.0 or newer. Update via `POS Menu → System → Check for Updates`.
2. Restart the POS application (not the device) — this re-establishes the WebSocket connection.
3. If on corporate network: ask merchant's IT team to whitelist `pos-ws.zalopay.vn:443` for WebSocket connections.
4. Manual workaround: merchant can verify payments manually at `merchant.zalopay.vn → Transactions` while the real-time connection is being fixed.
5. Escalate to POS engineering team if restart does not fix within 10 minutes — include merchant ID and POS device serial.

---

## Settlement Delay or Missing Settlement

**Symptoms:** Merchant's daily settlement has not arrived in their bank account by the expected time (typically T+1 by 10:00 AM).

**Cause A:** Bank processing delay — especially common after public holidays.
**Cause B:** Merchant's bank account details are outdated in Zalopay system.
**Cause C:** Settlement amount is below the merchant's configured minimum threshold.

## Suggested Approach

1. Check settlement status in merchant dashboard: `merchant.zalopay.vn → Finance → Settlement History`.
2. If status is "Pending": bank processing delay — typical SLA is T+1 by 14:00. Advise merchant to wait and check bank statement.
3. If status is "Failed": bank account details likely changed. Merchant must update bank account in dashboard and contact merchant support to re-process the failed settlement.
4. Minimum settlement threshold default is 100,000 VND. Amounts below this accumulate and settle when the threshold is reached.
5. For urgent cases (settlement >3 days overdue): escalate to finance team with merchant ID and settlement batch ID.

---

## Merchant Onboarding Issues

**Symptoms:** New merchant cannot complete KYB (Know Your Business) verification. Business registration documents rejected.

## Suggested Approach

1. Accepted business registration documents: Giấy phép kinh doanh (Business License) — must be valid, not expired, matching the applicant's name.
2. Common rejection reasons: blurry scan, expired license, name mismatch between document and registered Zalopay email.
3. For individual sellers (Hộ kinh doanh cá thể): CCCD of the business owner is sufficient — no formal business license required for tier 1 merchant.
4. Resubmit via: `merchant.zalopay.vn → Onboarding → Upload Documents`.
5. If rejected 3+ times with correct documents: escalate to KYB compliance team for manual review.
