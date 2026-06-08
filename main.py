"""
main.py — Application entry point.

Run with:
    uvicorn main:app --reload

Interactive docs at:
    http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
import os

load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import spotipy

from router import router as playlist_router
from spotify_client import get_spotify_oauth


#  Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s",
    datefmt="%H:%M:%S",
)

#  FastAPI application
app = FastAPI(
    title="Sondas",
    version="0.1.0",
    summary=(
        "Translates creative narrative prompts into mathematically "
        "time-optimised playlists using an LLM → Spotify → DP-solver pipeline."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow broad CORS for local frontend development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "super-secret-key-123"))

app.mount("/static", StaticFiles(directory="static"), name="static")



# ──────────────────────────────────────────────
#  Register routers
# ──────────────────────────────────────────────
app.include_router(playlist_router)


# ──────────────────────────────────────────────
#  Web Portal & Auth Routes
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, tags=["portal"])
async def portal():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/login", tags=["auth"])
async def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return RedirectResponse(auth_url)

@app.get("/callback", tags=["auth"])
async def callback(request: Request, code: str):
    sp_oauth = get_spotify_oauth()
    token_info = sp_oauth.get_access_token(code)
    request.session["token_info"] = token_info
    return RedirectResponse("/")

@app.get("/logout", tags=["auth"])
async def logout(request: Request):
    request.session.pop("token_info", None)
    return RedirectResponse("/")

@app.get("/api/v1/me", tags=["auth"])
async def get_me(request: Request):
    token_info = request.session.get("token_info")
    if not token_info:
        raise HTTPException(status_code=401, detail="Not logged in")
        
    scope = token_info.get("scope", "")
    if "playlist-modify-public" not in scope or "playlist-modify-private" not in scope:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Scope missing, forcing re-login")
    
    sp_oauth = get_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        request.session["token_info"] = token_info
        
    sp = spotipy.Spotify(auth=token_info["access_token"])
    return sp.current_user()

# ──────────────────────────────────────────────
#  Health check
# ──────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok", "service": "Sondas"}
