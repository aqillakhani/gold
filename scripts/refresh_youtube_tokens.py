"""Re-authorize YouTube OAuth2 for accounts with expired tokens.

Opens browser for each account — log in with the correct Google account,
authorize, and the refresh token is saved to secrets/.env automatically.
"""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

ENV_PATH = Path(__file__).parent.parent / "secrets" / ".env"
load_dotenv(ENV_PATH, override=True)

ACCOUNTS = [
    ("TECH", "ToolStack", "toolstack88@gmail.com"),
    ("TRUECRIME", "Cold Cases", "coldcases88@gmail.com"),
    ("FINANCE", "SmartStack", "smartstack88@gmail.com"),
    ("ENGLISH", "FluentIn60", "fluentin60@gmail.com"),
]


def update_env_value(env_path: Path, key: str, new_value: str) -> None:
    """Update a single key in the .env file."""
    content = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf'^{re.escape(key)}=.*$', re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(f'{key}={new_value}', content)
    else:
        content += f'\n{key}={new_value}\n'
    env_path.write_text(content, encoding="utf-8")


def authorize_account(suffix: str, name: str, email: str) -> str | None:
    """Run OAuth flow for one account, return new refresh token."""
    client_id = os.environ.get(f"YOUTUBE_CLIENT_ID_{suffix}")
    client_secret = os.environ.get(f"YOUTUBE_CLIENT_SECRET_{suffix}")

    if not client_id or not client_secret:
        print(f"  SKIP — missing CLIENT_ID or CLIENT_SECRET for {suffix}")
        return None

    print(f"\n{'='*60}")
    print(f"  Authorizing: {name} ({email})")
    print(f"  Suffix: {suffix}")
    print(f"{'='*60}")
    print(f"  >>> Log in with: {email}")
    print(f"  >>> Browser will open automatically...")
    print()

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost:9090/"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )

    creds = flow.run_local_server(port=9090, prompt="consent", access_type="offline")

    if creds.refresh_token:
        print(f"  Got refresh token for {name}")
        return creds.refresh_token
    else:
        print(f"  WARNING: No refresh token returned for {name}")
        return None


def main():
    print("YouTube Token Refresh — 4 accounts")
    print("You'll need to log in to each Google account in the browser.\n")

    results = []

    for suffix, name, email in ACCOUNTS:
        try:
            token = authorize_account(suffix, name, email)
            if token:
                key = f"YOUTUBE_REFRESH_TOKEN_{suffix}"
                update_env_value(ENV_PATH, key, token)
                print(f"  SAVED {key} to .env")
                results.append((name, "OK"))
            else:
                results.append((name, "NO TOKEN"))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append((name, f"FAILED: {e}"))

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    for name, status in results:
        print(f"  {name:15s} — {status}")


if __name__ == "__main__":
    main()
