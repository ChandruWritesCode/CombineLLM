"""OpenRouter PKCE login; browser passwords and issued API keys never enter frontend JS."""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/api/v1/oauth/openrouter", tags=["settings"])
COOKIE = "combinellm_oauth"


@router.post("/{model_id}/start")
async def start(model_id: str, request: Request):
    config = request.app.state.connections.get(model_id)
    if config["kind"] != "openrouter":
        raise HTTPException(422, "Browser login is available for OpenRouter connections")
    pending = request.app.state.oauth_pending
    for key in list(pending):
        if pending[key]["expires"] < time.monotonic():
            del pending[key]
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    binding = secrets.token_urlsafe(32)
    pending[state] = {
        "verifier": verifier,
        "binding": binding,
        "model_id": model_id,
        "expires": time.monotonic() + 600,
    }
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    callback = (
        request.app.state.settings.public_base_url.rstrip("/")
        + "/api/v1/oauth/openrouter/callback?"
        + urlencode({"state": state})
    )
    url = "https://openrouter.ai/auth?" + urlencode(
        {"callback_url": callback, "code_challenge": challenge, "code_challenge_method": "S256"}
    )
    from fastapi.responses import JSONResponse

    response = JSONResponse({"url": url})
    response.set_cookie(
        COOKIE,
        binding,
        httponly=True,
        samesite="lax",
        max_age=600,
        secure=callback.startswith("https://"),
        path="/api/v1/oauth/openrouter",
    )
    return response


@router.get("/callback")
async def callback(request: Request, state: str = "", code: str = "", error: str = ""):
    pending = request.app.state.oauth_pending
    flow = pending.get(state)
    if (
        not flow
        or flow["expires"] < time.monotonic()
        or not secrets.compare_digest(flow["binding"], request.cookies.get(COOKIE, ""))
    ):
        raise HTTPException(400, "Login session is missing or expired. Start again from Settings.")
    del pending[state]
    result = "failed"
    try:
        if error or not code or len(code) > 4096:
            raise ValueError("Login was not completed")
        config = request.app.state.connections.get(flow["model_id"])
        if config["kind"] != "openrouter":
            raise ValueError("Connection changed during login")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/auth/keys",
                json={
                    "code": code,
                    "code_verifier": flow["verifier"],
                    "code_challenge_method": "S256",
                },
            )
            response.raise_for_status()
            key = response.json()["key"]
        if not isinstance(key, str) or not key or len(key) > 8192:
            raise ValueError("Missing key")
        encrypted = request.app.state.connections.cipher.encrypt(key.encode()).decode()
        with request.app.state.store.connect() as db:
            db.execute(
                "UPDATE model_connections SET credential=?,auth_method='openrouter_login' "
                "WHERE id=?",
                (encrypted, flow["model_id"]),
            )
        result = "connected"
    except (httpx.HTTPError, ValueError, KeyError, TypeError, HTTPException):
        pass
    redirect = RedirectResponse("/settings?login=" + result, status_code=303)
    redirect.delete_cookie(COOKIE, path="/api/v1/oauth/openrouter")
    redirect.headers["Referrer-Policy"] = "no-referrer"
    redirect.headers["Cache-Control"] = "no-store"
    return redirect
