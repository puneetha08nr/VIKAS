"""One-time OAuth 2.0 token generator for Google Search Console.

Run once to authorize access and persist the refresh token:
    python scripts/gsc_auth.py

Opens a browser at localhost:8080 for the OAuth consent screen.
Saves gsc_token.json and prints the env var values to add to .env.
"""
import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
CLIENT_SECRETS = "gsc_oauth_client.json"
TOKEN_FILE = "gsc_token.json"


def generate_token() -> None:
    if not os.path.exists(CLIENT_SECRETS):
        raise FileNotFoundError(
            f"{CLIENT_SECRETS} not found. Download it from:\n"
            "console.cloud.google.com → vikas-495217 → APIs & Services → Credentials\n"
            "→ Create Credentials → OAuth 2.0 Client ID → Desktop app → vikas-gsc-oauth\n"
            "→ Download JSON → save as gsc_oauth_client.json"
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    creds = flow.run_local_server(port=8080)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nToken saved to {TOKEN_FILE}")
    print("\nAdd these to .env:")
    print(f"GSC_CLIENT_ID={creds.client_id}")
    print(f"GSC_CLIENT_SECRET={creds.client_secret}")
    print(f"GSC_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    generate_token()
