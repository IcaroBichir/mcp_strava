from __future__ import annotations

import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

CONFIG_DIR = Path.home() / ".config" / "strava-mcp"
TOKENS_FILE = CONFIG_DIR / "tokens.json"

_AUTH_URL = "https://www.strava.com/oauth/authorize"
_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
_REDIRECT_PORT = 8765
_REDIRECT_URI = f"http://localhost:{_REDIRECT_PORT}"
_SCOPES = "activity:read_all,profile:read_all"


class _CallbackHandler(BaseHTTPRequestHandler):
    auth_code: str | None = None

    def do_GET(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        _CallbackHandler.auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<h1>Authorization complete!</h1>"
            b"<p>You can close this tab and return to the terminal.</p>"
        )

    def log_message(self, *args) -> None:
        pass  # suppress request logs


def run_oauth_flow(client_id: str, client_secret: str) -> dict:
    query = urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": _REDIRECT_URI,
        "scope": _SCOPES,
        "approval_prompt": "auto",
    })
    auth_url = f"{_AUTH_URL}?{query}"

    print("Opening browser for Strava authorization...")
    print(f"If the browser does not open, visit:\n  {auth_url}")
    webbrowser.open(auth_url)

    print(f"Waiting for callback on http://localhost:{_REDIRECT_PORT}...")
    server = HTTPServer(("localhost", _REDIRECT_PORT), _CallbackHandler)
    server.handle_request()

    code = _CallbackHandler.auth_code
    if not code:
        raise RuntimeError("No authorization code received — was the request denied?")

    print("Exchanging authorization code for tokens...")
    resp = httpx.post(_TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    token_data = resp.json()
    _save(client_id, client_secret, token_data)
    return token_data


def _save(client_id: str, client_secret: str, token_data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": token_data["expires_at"],
        "athlete_id": token_data.get("athlete", {}).get("id"),
    }
    TOKENS_FILE.write_text(json.dumps(payload, indent=2))
    TOKENS_FILE.chmod(0o600)


def load_tokens() -> dict:
    if not TOKENS_FILE.exists():
        raise FileNotFoundError(
            "Not authenticated. Run `strava-mcp auth` to connect your Strava account."
        )
    return json.loads(TOKENS_FILE.read_text())


def refresh_if_needed() -> dict:
    tokens = load_tokens()
    if tokens["expires_at"] > time.time() + 60:
        return tokens

    resp = httpx.post(_TOKEN_URL, data={
        "client_id": tokens["client_id"],
        "client_secret": tokens["client_secret"],
        "refresh_token": tokens["refresh_token"],
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    new_data = resp.json()
    _save(tokens["client_id"], tokens["client_secret"], new_data)
    return {**tokens, **new_data}
