"""
schemas.py — Pydantic v2 models for the entire data pipeline.

Defines the strict contract between every service in the orchestrator:
  User Request → LLM Candidate Pool → Verified Tracks → Final Playlist
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

# ──────────────────────────────────────────────
#  1. Inbound request from the client
# ──────────────────────────────────────────────
class PlaylistRequest(BaseModel):
    """Payload accepted by POST /api/v1/playlists/generate."""

    prompt: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Creative, narrative prompt describing the desired playlist arc.",
        examples=[
            "A 45-minute HYROX session starting with hip-hop warmup, "
            "peaking with darksynth, and cooling down with acoustic chill."
        ],
    )
    target_duration_minutes: int = Field(
        ...,
        ge=5,
        le=180,
        description="Strict target duration for the final playlist, in minutes.",
    )


# ──────────────────────────────────────────────
#  2. Intermediate models inside the pipeline
# ──────────────────────────────────────────────
PhaseType = Literal["warmup", "peak", "cooldown"]


class CandidateTrack(BaseModel):
    """A single track returned by the LLM — no duration yet."""

    title: str = Field(..., min_length=1)
    artist: str = Field(..., min_length=1)
    phase: PhaseType


class LLMTrackPool(BaseModel):
    """The full over-generated pool the LLM returns."""

    playlist_concept: str = Field(
        ...,
        description="3-word vibe summary produced by the LLM.",
    )
    candidate_tracks: list[CandidateTrack] = Field(
        ...,
        min_length=1,
        description="Ordered list of candidate tracks, sequenced by narrative arc.",
    )


class VerifiedTrack(BaseModel):
    """A candidate track enriched with Spotify metadata."""

    title: str
    artist: str
    phase: PhaseType
    duration_ms: int = Field(
        ...,
        gt=0,
        description="Track length in milliseconds from Spotify.",
    )
    spotify_id: str = Field(
        ...,
        min_length=1,
        description="Spotify track URI / ID.",
    )


# ──────────────────────────────────────────────
#  3. Final response returned to the client
# ──────────────────────────────────────────────
class FinalPlaylistResponse(BaseModel):
    """The optimised playlist after constraint solving."""

    concept: str
    target_duration_seconds: int = Field(
        ...,
        description="The original target the solver aimed for.",
    )
    total_duration_seconds: int = Field(
        ...,
        description="Actual summed duration of the selected tracks.",
    )
    tolerance_seconds: int = Field(
        default=45,
        description="Allowed deviation window (±) from the target.",
    )
    tracks: list[VerifiedTrack]
    track_count: int = Field(
        ...,
        description="Number of tracks in the final playlist.",
    )
    spotify_playlist_url: str | None = Field(
        default=None,
        description="URL to the generated playlist on Spotify (if authenticated).",
    )
