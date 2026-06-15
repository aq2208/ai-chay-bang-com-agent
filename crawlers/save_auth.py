"""
Launch a headful Playwright browser window to let the user log in to Threads.
Once authenticated, saves cookies and local storage (storage state) to 'auth_state.json'
locally, and attempts to automatically update the 'THREADS_AUTH_STATE_JSON' GitHub Secret
using the GitHub CLI (gh) for non-interactive execution in CI/CD.
"""

import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # Launch headful browser so the user can interact
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("🚀 Navigating to Threads login page...")
        await page.goto("https://www.threads.net/login")
        
        print("📝 Please log in to your Threads account in the browser window.")
        print("   The script will wait for you to complete the login process...")
        
        # Wait until the user is logged in (including OTP/2FA verification)
        print("⏳ Waiting for you to complete the login process (and OTP/2FA if prompted)...")
        is_logged_in = False
        while not is_logged_in:
            await asyncio.sleep(1)
            current_url = page.url.lower()
            cookies = await context.cookies()
            has_session = any(cookie["name"] == "sessionid" for cookie in cookies)
            
            # We are fully logged in if:
            # 1. We have the sessionid cookie
            # 2. We are on the Threads domain (threads.net or threads.com)
            # 3. We are NOT on a login/oauth/2FA/codeentry page
            on_threads = "threads.net" in current_url or "threads.com" in current_url
            on_auth_page = any(x in current_url for x in ["/login", "/signup", "/accounts/", "oauth", "codeentry", "authorize"])
            
            if has_session and on_threads and not on_auth_page:
                is_logged_in = True
            
        print("🎉 Login completed successfully! Waiting 3 seconds to ensure all cookies are finalized...")
        await asyncio.sleep(3)
        
        # Get storage state in memory
        state = await context.storage_state()
        import json
        import subprocess
        import os
        state_json_str = json.dumps(state, indent=2)
        
        is_github_actions = os.getenv("GITHUB_ACTIONS") == "true"
          
        # Save storage state locally under data/
        auth_path = os.path.join("data", "auth_state.json")
        os.makedirs(os.path.dirname(auth_path), exist_ok=True)
        with open(auth_path, "w", encoding="utf-8") as f:
            f.write(state_json_str)
        print(f"💾 Authentication state successfully saved locally to '{auth_path}'!")
        
        
        # Automatically update GitHub Secret using gh CLI
        print("📤 Pushing authentication state to GitHub Secrets...")
        try:
            proc = subprocess.Popen(
                ["gh", "secret", "set", "THREADS_AUTH_STATE_JSON"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = proc.communicate(input=state_json_str)
            if proc.returncode == 0:
                print("🎉 GitHub Secret 'THREADS_AUTH_STATE_JSON' successfully updated via gh CLI!")
            else:
                print(f"❌ Failed to update GitHub Secret via gh CLI:\n{stderr.strip()}")
                print("👉 Make sure you run this script inside a Git repository and have run 'gh auth login'.")
        except FileNotFoundError:
            print("⚠️ 'gh' CLI not found. Please install the GitHub CLI (brew install gh) to auto-update secrets.")
        except Exception as e:
            print(f"⚠️ Error updating GitHub Secret: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
