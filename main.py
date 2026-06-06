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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from router import router as playlist_router

# ──────────────────────────────────────────────
#  Logging configuration
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s",
    datefmt="%H:%M:%S",
)

# ──────────────────────────────────────────────
#  FastAPI application
# ──────────────────────────────────────────────
app = FastAPI(
    title="AI Playlist Orchestrator",
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

# ──────────────────────────────────────────────
#  Register routers
# ──────────────────────────────────────────────
app.include_router(playlist_router)


# ──────────────────────────────────────────────
#  Health check
# ──────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok", "service": "ai-playlist-orchestrator"}
