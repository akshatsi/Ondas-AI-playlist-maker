"""
router.py — FastAPI router for the playlist generation pipeline.

Defines:
  POST /api/v1/playlists/generate

This is the orchestrator layer.  It wires together the three core
services (LLM Engine → Spotify Client → Constraint Solver) into a
single request/response cycle.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
#local files 
from llm_engine import generate_candidate_pool
from schemas import FinalPlaylistResponse, PlaylistRequest
from solver import DEFAULT_TOLERANCE_SECONDS, SolverError, solve_playlist_knapsack
from spotify_client import verify_and_fetch_metadata, export_to_spotify_account, get_spotify_oauth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Playlist"])


@router.post(
    "/api/v1/playlists/generate",
    response_model=FinalPlaylistResponse,
    summary="Generate an optimised playlist from a creative prompt",
    response_description="A mathematically time-matched playlist preserving the narrative arc.",
)
async def generate_playlist(payload: PlaylistRequest, request: Request) -> FinalPlaylistResponse:
    """
    Full orchestration pipeline:

    1. **LLM Engine** — over-generates a pool of candidate tracks based
       on the user's narrative prompt.
    2. **Spotify Client** — verifies each candidate and enriches it with
       real duration data (mocked for now).
    3. **Constraint Solver** — runs a Subset Sum / 0-1 Knapsack DP
       algorithm to select the subset whose total duration best matches
       the user's requested time, within a ±45 s tolerance window.
    """

    # ── Stage 1: LLM candidate generation ────────────────────────────
    try:
        pool = await generate_candidate_pool(
            prompt=payload.prompt,
            target_minutes=payload.target_duration_minutes,
        )
    except ValueError as exc:
        logger.error("LLM pipeline failure: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"LLM service returned invalid data: {exc}",
        )
    except Exception as exc:
        logger.error("Unexpected LLM error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error during candidate generation. Please retry.",
        )

    if not pool.candidate_tracks:
        raise HTTPException(
            status_code=500,
            detail="LLM returned an empty candidate pool.",
        )

    logger.info(
        "Stage 1 complete  |  concept='%s'  |  candidates=%d",
        pool.playlist_concept,
        len(pool.candidate_tracks),
    )

    # ── Stage 2: Spotify verification & enrichment ───────────────────
    try:
        verified = await verify_and_fetch_metadata(pool.candidate_tracks)
    except Exception as exc:
        logger.error("Spotify verification failure: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Failed to verify tracks against Spotify. Please retry.",
        )

    if not verified:
        raise HTTPException(
            status_code=500,
            detail=(
                "All candidate tracks failed Spotify verification. "
                "The LLM may have hallucinated tracks."
            ),
        )

    logger.info("Stage 2 complete  |  verified=%d tracks", len(verified))

    # ── Stage 3: Constraint solving (DP) ─────────────────────────────
    try:
        result = solve_playlist_knapsack(
            tracks=verified,
            target_minutes=payload.target_duration_minutes,
        )
    except SolverError as exc:
        logger.error("Solver failure: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Could not assemble a playlist within tolerance: {exc}",
        )
    except Exception as exc:
        logger.error("Unexpected solver error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error in the constraint solver.",
        )

    logger.info(
        "Stage 3 complete  |  selected=%d tracks  |  duration=%d s  |  Δ=%d s",
        len(result.selected_tracks),
        result.total_duration_seconds,
        result.deviation_seconds,
    )

    # ── Stage 4: Export to Spotify (if authenticated) ────────────────
    spotify_url = None
    token_info = request.session.get("token_info")
    if token_info:
        # Strict scope validation to prevent stale tokens from causing 403 Forbidden
        scope = token_info.get("scope", "")
        if "playlist-modify-public" not in scope or "playlist-modify-private" not in scope:
            logger.error(f"Stale token detected! Scopes found: {scope}")
            raise HTTPException(
                status_code=401, 
                detail="Your Spotify token is stale and lacks playlist creation permissions. You MUST click 'Log out' and log back in to fix the 403 error!"
            )
            
        sp_oauth = get_spotify_oauth()
        if sp_oauth.is_token_expired(token_info):
            try:
                token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
                request.session["token_info"] = token_info
            except Exception as e:
                logger.error("Failed to refresh Spotify token: %s", e)
                request.session.pop("token_info", None)
                token_info = None

        if token_info:
            try:
                logger.info("Exporting to Spotify account...")
                spotify_url = await export_to_spotify_account(
                    token_info=token_info,
                    playlist_name=f"Sondas: {pool.playlist_concept.title()}",
                    tracks=result.selected_tracks
                )
            except Exception as exc:
                logger.error("Failed to export to Spotify: %s", exc, exc_info=True)
                # We don't fail the request, just return without the URL

    # ── Assemble response ────────────────────────────────────────────
    return FinalPlaylistResponse(
        concept=pool.playlist_concept,
        target_duration_seconds=result.target_duration_seconds,
        total_duration_seconds=result.total_duration_seconds,
        tolerance_seconds=DEFAULT_TOLERANCE_SECONDS,
        tracks=result.selected_tracks,
        track_count=len(result.selected_tracks),
        spotify_playlist_url=spotify_url,
    )
