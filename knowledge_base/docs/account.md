# Account Issues

**Domain:** Account
**Segments:** Login, OTP, Registration, Profile

---

## OTP Not Received

**Symptoms:** User attempts to log in or verify a transaction. OTP SMS is not delivered to the registered phone number. User waits 5+ minutes, resends multiple times, still nothing.

**Cause A:** SMS gateway congestion — high traffic period causes OTP delivery delay of up to 10 minutes.
**Cause B:** User's carrier is blocking promotional/OTP SMS from the gateway number. Common with Vietnamobile and Reddi networks.
**Cause C:** User recently changed their SIM or ported number — registration not yet propagated to carrier.
**Cause D:** Phone has SMS spam filter enabled that blocks OTP sender IDs.

## Suggested Approach

1. Confirm which carrier the user is on — Vietnamobile and Reddi have known OTP delivery issues with our SMS gateway.
2. Check SMS delivery report in admin panel (`admin.zalopay.vn → OTP Logs → search by phone`). Confirm whether OTP was sent and the delivery status.
3. If "Delivered" but not received: phone-level spam filter. Ask user to check SMS spam folder, or whitelist sender ID "ZALOPAY".
4. If "Failed" or "Pending" for >2 minutes: switch user to OTP via ZaloApp instead of SMS — `login screen → "Receive OTP via Zalo app"`.
5. If Zalo OTP also fails: escalate to SMS gateway team with the user's phone number and timestamp.
6. Do not disable OTP requirement — it is a security requirement.

---

## Login Failure — Password / Account Locked

**Symptoms:** User cannot log in. May see "incorrect password" or "account temporarily locked".

**Cause:** 5 consecutive wrong password attempts triggers a 30-minute lockout.

## Suggested Approach

1. Advise user to wait 30 minutes for automatic unlock.
2. For immediate unlock: user must go through password reset (`login screen → Forgot Password → verify via OTP`).
3. If account is permanently suspended (different from locked): requires identity verification — escalate to compliance team.

---

## Registration Failure

**Symptoms:** New user cannot complete registration. Phone number already registered error, or identity verification step keeps failing.

## Suggested Approach

- **Phone already registered:** User may have an old account. Direct to account recovery: `login → "Forgot Password"`.
- **eKYC failure:** ID card photo not clear enough (blurry, glare, covered). Advise user to re-take in good lighting, full ID card visible, no reflections. Supported: CCCD, CMND, Passport.
- **If eKYC passes but account not created:** Check for server-side registration error in logs and retry. If persistent, escalate to identity verification team.

---

## Profile Update Failure

**Symptoms:** User cannot update phone number, linked bank, or profile photo.

## Suggested Approach

- Phone number changes require OTP to both old and new numbers — if old number is no longer accessible, escalate to customer support for manual verification.
- Bank account re-linking: see Payment → Withdrawal Failure section.
- Profile photo: must be under 5MB, JPG or PNG only. HEIC (iPhone default) is not supported — user should convert first.
