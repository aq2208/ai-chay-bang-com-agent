# Payment Issues

**Domain:** Payment
**Segments:** Top-up, Transfer, Withdrawal, Billing
**Error codes:** E5001, E5002, E5003, E4001, E4002

---

## Visa / Mastercard Top-up Failure (E5001, E5002)

**Symptoms:** User attempts to top-up via Visa or Mastercard. Transaction fails after card details are entered. Error codes E5001 or E5002 displayed.

**Cause:** 3D Secure (3DS) authentication timeout. The Zalopay gateway waits up to 10 seconds for the bank's 3DS redirect, but some issuing banks take 12–20 seconds, causing a timeout before the OTP confirmation page loads.

## Suggested Approach

1. Check payment gateway logs for the specific transaction ID — confirm if timeout occurred at 3DS handshake or post-authentication.
2. Increase 3DS timeout window from 10s to 30s in the payment gateway config (`gateway.yml → 3ds_timeout_ms: 30000`).
3. If E5002 (card declined by issuer): user should contact their bank to whitelist Zalopay as a merchant. Some Vietnamese banks block international gateway transactions by default.
4. Temporary workaround for users: top-up via bank transfer instead of card.
5. Escalate to payment gateway team if affecting >5% of top-up transactions.

---

## Duplicate Charge / Double Deduction

**Symptoms:** User is charged twice for one transaction. One charge shows in Zalopay history, both show in bank statement.

**Cause:** Network timeout during payment confirmation step. User's bank processed the payment but the confirmation callback to Zalopay was lost. User retried, triggering a second charge.

## Suggested Approach

1. Pull transaction logs for the user's account — identify both transaction IDs.
2. Verify with payment gateway whether one or both transactions reached "settled" status.
3. If double-settled: initiate refund for the duplicate via the admin refund portal (`admin.zalopay.vn/refunds`). SLA: 3–5 business days.
4. If one transaction is in "pending" state: it will auto-void within 24 hours — inform the user and set a reminder to follow up.
5. Add idempotency key check to the retry logic to prevent future occurrences — raise as a bug ticket.

---

## Transfer Failure (E4001, E4002)

**Symptoms:** Peer-to-peer transfer fails. E4001 = recipient not found, E4002 = transfer limit exceeded.

## Suggested Approach

- **E4001:** Verify recipient's phone number is registered with Zalopay. Check if account is suspended.
- **E4002:** Daily transfer limit is 100M VND for unverified accounts, 500M VND for verified. User must complete eKYC to raise the limit. Direct to: `app → Profile → Verify Identity`.

---

## Withdrawal Failure

**Symptoms:** User cannot withdraw Zalopay balance to linked bank account.

**Cause:** Bank account linking expired (token rotated by bank), or bank maintenance window.

## Suggested Approach

1. Ask user to re-link bank account: `app → Wallet → Linked Accounts → Re-link`.
2. Check bank maintenance schedule — most Vietnamese banks maintain 00:00–02:00 daily.
3. If persists: escalate to bank integration team with user ID and linked bank code.
