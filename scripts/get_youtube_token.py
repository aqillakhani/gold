"""One-time script to get YouTube OAuth2 refresh token.

Run this, open the URL it prints, authorize in your browser,
then paste the code back here.
"""

import sys
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = sys.argv[1] if len(sys.argv) > 1 else input("Client ID: ")
CLIENT_SECRET = sys.argv[2] if len(sys.argv) > 2 else input("Client Secret: ")

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
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
print("\n=== SUCCESS ===")
print(f"Refresh Token: {creds.refresh_token}")
print(f"Access Token:  {creds.token}")
print("\nSave the Refresh Token — that's what goes in .env")
