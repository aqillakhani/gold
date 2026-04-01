"""TikTok OAuth2 authorization flow for all accounts.

Opens a browser for each TikTok account to authorize the app.
Runs a local HTTP server to catch the OAuth callback and exchange
the auth code for access + refresh tokens.

Usage:
    python scripts/tiktok_oauth.py                    # All accounts
    python scripts/tiktok_oauth.py --account reddit   # Single account

The script will:
1. Open your browser to TikTok's authorization page
2. You log in and authorize the app
3. TikTok redirects back to localhost with an auth code
4. Script exchanges the code for access + refresh tokens
5. Prints the tokens and updates secrets/.env
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import httpx

# Load .env
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "secrets" / ".env")

CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:8420/auth/tiktok/callback"
SCOPES = "user.info.basic,video.publish,video.upload"

# TikTok account mapping: name -> env var suffix
ACCOUNTS = {
    "reddit": {
        "env_suffix": "REDDIT",
        "handle": "@storyvault",
        "note": "Also covers betrayal_revenge",
    },
    "tech": {
        "env_suffix": "TECH",
        "handle": "@toolstack",
    },
    "truecrime": {
        "env_suffix": "TRUECRIME",
        "handle": "@coldcases",
    },
    "finance": {
        "env_suffix": "FINANCE",
        "handle": "@smartstack",
    },
    "english": {
        "env_suffix": "ENGLISH",
        "handle": "@fluentin60",
    },
}

# Will hold the auth code from the callback
_auth_code: str | None = None
_code_verifier: str = ""
_server_ready = threading.Event()


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(43))
    # TikTok uses HEX encoding of SHA256, NOT base64url
    challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()
    print(f"  [PKCE] verifier={verifier}")
    print(f"  [PKCE] challenge={challenge}")
    return verifier, challenge


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handle the OAuth redirect callback from TikTok."""

    def do_GET(self) -> None:
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Only handle the TikTok callback path
        if parsed.path != "/auth/tiktok/callback":
            self.send_response(404)
            self.end_headers()
            return

        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:system-ui;text-align:center;padding:60px;">
                <h1 style="color:#22c55e;">Authorization Successful!</h1>
                <p>You can close this tab and return to the terminal.</p>
                </body></html>
            """)
        elif "error" in params:
            error = params.get("error", ["unknown"])[0]
            error_desc = params.get("error_description", [""])[0]
            _auth_code = None
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"""
                <html><body style="font-family:system-ui;text-align:center;padding:60px;">
                <h1 style="color:#ef4444;">Authorization Failed</h1>
                <p>{error}: {error_desc}</p>
                </body></html>
            """.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args) -> None:
        pass  # Suppress HTTP logs


def exchange_code_for_token(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    payload = {
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": _code_verifier,
    }
    # Attempt 1: form body
    print(f"  [TOKEN] Attempt 1: form-urlencoded body...")
    resp = httpx.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
    )
    data = resp.json()
    print(f"  [TOKEN] Result: {json.dumps(data)[:200]}")

    if "access_token" not in data and "verifier" in data.get("error_description", ""):
        # Attempt 2: query params
        print(f"  [TOKEN] Attempt 2: query params...")
        qs = urllib.parse.urlencode(payload)
        resp = httpx.post(
            f"https://open.tiktokapis.com/v2/oauth/token/?{qs}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
        print(f"  [TOKEN] Result: {json.dumps(data)[:200]}")

    if "access_token" not in data:
        raise RuntimeError(f"Token exchange failed: {json.dumps(data, indent=2)}")

    return data


def update_env_file(key: str, value: str) -> None:
    """Update a key in secrets/.env file."""
    env_path = Path(__file__).parent.parent / "secrets" / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def authorize_account(name: str, info: dict) -> bool:
    """Run OAuth flow for a single TikTok account."""
    global _auth_code, _code_verifier
    _auth_code = None

    suffix = info["env_suffix"]
    handle = info.get("handle", name)
    token_key = f"TIKTOK_ACCESS_TOKEN_{suffix}"
    refresh_key = f"TIKTOK_REFRESH_TOKEN_{suffix}"

    print(f"\n{'='*60}")
    print(f"  Authorizing: {handle} ({name})")
    if info.get("note"):
        print(f"  Note: {info['note']}")
    print(f"{'='*60}")

    # Generate PKCE (required by TikTok)
    _code_verifier, code_challenge = _generate_pkce()

    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={CLIENT_KEY}"
        f"&scope={SCOPES}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&state={name}"
        f"&code_challenge={urllib.parse.quote(code_challenge, safe='')}"
        f"&code_challenge_method=S256"
    )

    # Start local server
    server = http.server.HTTPServer(("localhost", 8420), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print(f"\n  Opening browser for {handle}...")
    print(f"  Log in to TikTok account: {handle}")
    print(f"  Then click 'Authorize' to grant access.\n")
    webbrowser.open(auth_url)

    # Wait for callback (up to 120 seconds)
    print("  Waiting for authorization (up to 2 minutes)...")
    server_thread.join(timeout=120)
    server.server_close()

    if not _auth_code:
        print(f"  ERROR: No authorization code received for {handle}")
        return False

    # URL-decode the auth code (TikTok may URL-encode it)
    auth_code = urllib.parse.unquote(_auth_code)
    print(f"  Got auth code: {auth_code[:10]}... (len={len(auth_code)})")

    # Exchange code for tokens
    try:
        token_data = exchange_code_for_token(auth_code)
    except Exception as e:
        print(f"  ERROR: Token exchange failed: {e}")
        return False

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 0)
    open_id = token_data.get("open_id", "")

    print(f"  Access token: {access_token[:20]}...")
    print(f"  Refresh token: {refresh_token[:20]}..." if refresh_token else "  Refresh token: (none)")
    print(f"  Expires in: {expires_in}s ({expires_in // 3600}h)")
    print(f"  Open ID: {open_id}")

    # Save to .env
    update_env_file(token_key, access_token)
    if refresh_token:
        update_env_file(refresh_key, refresh_token)

    print(f"  Saved to secrets/.env: {token_key}")
    return True


def main() -> None:
    if not CLIENT_KEY or not CLIENT_SECRET:
        print("ERROR: TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set in secrets/.env")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  TikTok OAuth2 Setup — Gold Platform")
    print("=" * 60)
    print(f"  Client Key: {CLIENT_KEY}")
    print(f"  Redirect URI: {REDIRECT_URI}")
    print(f"  Scopes: {SCOPES}")
    print(f"  Accounts to authorize: {len(ACCOUNTS)}")

    # Check for --account flag
    target = None
    if len(sys.argv) > 2 and sys.argv[1] == "--account":
        target = sys.argv[2]
        if target not in ACCOUNTS:
            print(f"\n  ERROR: Unknown account '{target}'. Available: {', '.join(ACCOUNTS.keys())}")
            sys.exit(1)

    results = {}
    accounts_to_auth = {target: ACCOUNTS[target]} if target else ACCOUNTS

    for name, info in accounts_to_auth.items():
        success = authorize_account(name, info)
        results[name] = success

        if success and name != list(accounts_to_auth.keys())[-1]:
            print("\n  Next account in 3 seconds...")
            time.sleep(3)

    # Summary
    print("\n" + "=" * 60)
    print("  AUTHORIZATION SUMMARY")
    print("=" * 60)
    for name, success in results.items():
        handle = ACCOUNTS[name].get("handle", name)
        status = "OK" if success else "FAILED"
        print(f"  {handle:20s} — {status}")

    ok = sum(1 for s in results.values() if s)
    print(f"\n  {ok}/{len(results)} accounts authorized successfully")

    if ok > 0:
        print("\n  Next steps:")
        print("  1. Add 'tiktok' to automated_platforms in config/settings.yaml")
        print("  2. Run: python -m gold  (scheduler will post to TikTok automatically)")
        print("  3. Or run: python post_today.py  (manual posting)")


if __name__ == "__main__":
    main()
