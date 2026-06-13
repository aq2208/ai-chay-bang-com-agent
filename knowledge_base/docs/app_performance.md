# App Performance Issues

**Domain:** App Performance
**Segments:** Crash, Loading, UI Bug

---

## App Crash on Launch

**Symptoms:** Zalopay crashes immediately when opened. Happens consistently — not a one-time crash. Affects specific Android or iOS versions.

**Cause A:** Corrupted local cache from a failed or interrupted update.
**Cause B:** Incompatible app version with OS version (common after major Android/iOS updates).
**Cause C:** Insufficient device storage — app cannot write to its data directory.

## Suggested Approach

1. Ask the user for: device model, OS version, Zalopay app version.
2. **First fix — clear cache:** `Device Settings → Apps → Zalopay → Storage → Clear Cache` (do NOT clear Data — that removes saved credentials). Relaunch.
3. **If still crashing:** uninstall and reinstall Zalopay from the official app store. Do not sideload APKs.
4. **If Android 12+ with crash:** check if user has `Developer Options → "Don't keep activities"` enabled — disable it.
5. **If iOS crash after update:** force-quit all apps, restart device, relaunch Zalopay.
6. **Storage check:** Zalopay requires minimum 200MB free storage. If device is full, some features will crash.
7. If crashing persists after reinstall on a supported OS version: collect crash log (Android: logcat; iOS: Settings → Privacy → Analytics → Zalopay crash log) and escalate to mobile engineering team.

**Supported OS versions:** Android 8.0+, iOS 14+. Devices below these versions are not supported.

---

## App Loading Slowly / Freezing

**Symptoms:** Zalopay takes >10 seconds to load home screen, or freezes on a specific screen (wallet, QR, transfer).

**Cause A:** Slow internet connection — Zalopay home screen requires live API calls.
**Cause B:** Server-side latency (check if widespread reports).
**Cause C:** Memory-heavy background processes on user's device.

## Suggested Approach

1. Ask user to run a speed test — Zalopay requires minimum 1 Mbps for normal operation.
2. Check Zalopay API status: `status.zalopay.vn` — if there's an active incident, inform user and set ETA.
3. If no incident: advise user to close background apps, clear Zalopay cache, and try again on WiFi.
4. If a specific screen always freezes (e.g., always on "Wallet" screen): capture the API call failing in network logs — likely a specific endpoint timing out.

---

## UI Bug / Display Issue

**Symptoms:** Buttons misaligned, text overlapping, wrong language displayed, dark mode rendering incorrectly.

## Suggested Approach

1. Confirm device model, OS version, app version, and language setting.
2. Try force-closing and reopening the app — most UI bugs are fixed by a fresh render.
3. If wrong language: `app → Profile → Settings → Language`. If Vietnamese shows as gibberish: device system language may not be set to UTF-8 encoding.
4. If dark mode issue: `app → Profile → Settings → Appearance → Light Mode` as a workaround. Log bug with screenshot and device info for the UI team.
5. Submit bug with screenshot to the mobile team — include: exact steps to reproduce, device model, OS, app version.
