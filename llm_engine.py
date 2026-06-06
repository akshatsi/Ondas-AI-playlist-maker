"""
llm_engine.py — Service A: The LLM candidate-pool generator.

Responsible for:
  1. Building a strict system prompt that forces JSON-only output.
  2. Calculating the over-generation factor (2.5× the estimated track count).
  3. Returning a validated LLMTrackPool ready for downstream enrichment.

In production, the `_call_llm` coroutine would hit an actual LLM API
(OpenAI, Gemini, etc.).  The current implementation uses a deterministic
mock pool so the backend is immediately runnable without API keys.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any
import os

from schemas import CandidateTrack, LLMTrackPool
import google.genai as genai

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  System prompt — sent verbatim to the LLM
# ──────────────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """\
You are a headless backend data component for an advanced music orchestration \
engine.  Your sole responsibility is to translate creative user prompts into a \
structured, over-generated pool of candidate tracks.

CRITICAL OPERATIONAL DIRECTIVES:

1. STRICT OVER-GENERATION: Generate exactly {num_tracks} unique tracks.
2. LOGICAL ARC PRESERVATION: Organise tracks sequentially into three phases: \
   "warmup", "peak", "cooldown".  The proportion should roughly mirror \
   the narrative emphasis of the user prompt.
3. TRUTHFULNESS (ZERO HALLUCINATIONS): Every title + artist pair must be a \
   real, verifiable track on major streaming platforms.
4. FORMAT ENFORCEMENT: Output ONLY raw, valid JSON matching this schema — \
   no markdown fences, no commentary, no introductory text.

JSON SCHEMA:
{{
  "playlist_concept": "<3-word vibe summary>",
  "candidate_tracks": [
    {{
      "title": "<Exact Track Name>",
      "artist": "<Primary Artist>",
      "phase": "warmup | peak | cooldown"
    }}
  ]
}}
"""


def _build_system_prompt(num_tracks: int) -> str:
    """Render the system prompt with the calculated track count."""
    return SYSTEM_PROMPT_TEMPLATE.format(num_tracks=num_tracks)


def _compute_overgeneration_count(target_minutes: int) -> int:
    """
    Calculate how many candidate tracks the LLM should produce.

    Formula: max(20, ⌊(target_minutes / 3.5) × 2.5⌋)
    The 2.5× multiplier gives the downstream constraint solver enough
    combinatorial slack to find a near-perfect time match.
    """
    return max(20, int((target_minutes / 3.5) * 2.5))


# ──────────────────────────────────────────────
#  Mock LLM response (deterministic, no API key)
# ──────────────────────────────────────────────
# A curated bank of real, verifiable tracks grouped by phase.
_TRACK_BANK: dict[str, list[dict[str, str]]] = {
    "warmup": [
        {"title": "Resonance", "artist": "HOME"},
        {"title": "We're Finally Landing", "artist": "HOME"},
        {"title": "A Walk", "artist": "Tycho"},
        {"title": "Hours", "artist": "Tycho"},
        {"title": "Memory", "artist": "Com Truise"},
        {"title": "Sunset", "artist": "The Midnight"},
        {"title": "Crystalline", "artist": "The Midnight"},
        {"title": "On the Run", "artist": "Timecop1983"},
        {"title": "Nightcall", "artist": "Kavinsky"},
        {"title": "Running in the Night", "artist": "FM-84"},
        {"title": "Tech Noir", "artist": "Gunship"},
        {"title": "Overdrive", "artist": "Lazerhawk"},
        {"title": "Accelerated", "artist": "Miami Nights 1984"},
        {"title": "A Real Hero", "artist": "College"},
        {"title": "Daydream", "artist": "Tycho"},
        {"title": "Midnight City", "artist": "M83"},
        {"title": "Oblivion", "artist": "M83"},
        {"title": "Intro", "artist": "The xx"},
        {"title": "Myth", "artist": "Beach House"},
        {"title": "Space Song", "artist": "Beach House"},
    ],
    "peak": [
        {"title": "Humans Are Such Easy Prey", "artist": "Perturbator"},
        {"title": "She Is Young, She Is Beautiful, She Is Next", "artist": "Perturbator"},
        {"title": "Future Club", "artist": "Perturbator"},
        {"title": "Miami Disco", "artist": "Perturbator"},
        {"title": "Sentient", "artist": "Perturbator"},
        {"title": "Venger", "artist": "Perturbator"},
        {"title": "Turbo Killer", "artist": "Carpenter Brut"},
        {"title": "Le Perv", "artist": "Carpenter Brut"},
        {"title": "Roller Mobster", "artist": "Carpenter Brut"},
        {"title": "Cheerleader Effect", "artist": "Carpenter Brut"},
        {"title": "Paradise Warfare", "artist": "Carpenter Brut"},
        {"title": "Looking for Tracy Tzu", "artist": "Carpenter Brut"},
        {"title": "Leather Teeth", "artist": "Carpenter Brut"},
        {"title": "Robeast", "artist": "Dance With the Dead"},
        {"title": "Riot", "artist": "Dance With the Dead"},
        {"title": "Banshee", "artist": "Dance With the Dead"},
        {"title": "Andromeda", "artist": "Dance With the Dead"},
        {"title": "Behemoth", "artist": "GosT"},
        {"title": "198XAD", "artist": "Mega Drive"},
        {"title": "Star Eater", "artist": "Daniel Deluxe"},
        {"title": "Corruptor", "artist": "Daniel Deluxe"},
        {"title": "Pursuit", "artist": "Gesaffelstein"},
        {"title": "Hate or Glory", "artist": "Gesaffelstein"},
        {"title": "TEARS", "artist": "HEALTH"},
        {"title": "Shutdown", "artist": "3TEETH"},
        {"title": "Firestarter", "artist": "The Prodigy"},
        {"title": "Breathe", "artist": "The Prodigy"},
        {"title": "Smack My Bitch Up", "artist": "The Prodigy"},
        {"title": "Genesis", "artist": "Justice"},
        {"title": "Phantom Pt. II", "artist": "Justice"},
    ],
    "cooldown": [
        {"title": "Dive", "artist": "Tycho"},
        {"title": "Epoch", "artist": "Tycho"},
        {"title": "Feather", "artist": "Nujabes"},
        {"title": "Aruarian Dance", "artist": "Nujabes"},
        {"title": "Reflection Eternal", "artist": "Nujabes"},
        {"title": "Kerala", "artist": "Bonobo"},
        {"title": "Cirrus", "artist": "Bonobo"},
        {"title": "First Snow", "artist": "Emancipator"},
        {"title": "Roygbiv", "artist": "Boards of Canada"},
        {"title": "Feel It All Around", "artist": "Washed Out"},
        {"title": "Outro", "artist": "M83"},
        {"title": "Re: Stacks", "artist": "Bon Iver"},
        {"title": "Holocene", "artist": "Bon Iver"},
        {"title": "Skinny Love", "artist": "Bon Iver"},
        {"title": "On Melancholy Hill", "artist": "Gorillaz"},
    ],
}


def _build_mock_pool(prompt: str, num_tracks: int) -> dict[str, Any]:
    """
    Build a deterministic mock pool by cycling through the track bank.

    Uses a hash of the prompt to introduce slight variation in starting
    offsets so repeated calls with different prompts yield different pools.
    """
    # Derive a seed from the prompt for repeatable-yet-varied output.
    seed = int(hashlib.sha256(prompt.encode()).hexdigest(), 16) % 1000

    # Allocate tracks across phases: ~25% warmup, ~55% peak, ~20% cooldown.
    n_warmup = max(3, int(num_tracks * 0.25))
    n_cooldown = max(3, int(num_tracks * 0.20))
    n_peak = num_tracks - n_warmup - n_cooldown

    def _pick(phase: str, count: int) -> list[dict[str, str]]:
        bank = _TRACK_BANK[phase]
        offset = seed % max(1, len(bank))
        picked: list[dict[str, str]] = []
        for i in range(count):
            picked.append(bank[(offset + i) % len(bank)])
        return picked

    tracks = (
        [dict(t, phase="warmup") for t in _pick("warmup", n_warmup)]
        + [dict(t, phase="peak") for t in _pick("peak", n_peak)]
        + [dict(t, phase="cooldown") for t in _pick("cooldown", n_cooldown)]
    )

    return {
        "playlist_concept": "Synthetic Neon Flow",
        "candidate_tracks": tracks,
    }


async def _call_llm(system_prompt: str, user_prompt: str, num_tracks: int) -> dict[str, Any]:
    client = genai.Client(
        api_key=os.environ.get("GOOGLE_API_KEY"),
    )

    logger.info("Sending request to Gemini 2.5 flash.")
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )
    if response.text is None:
        raise RuntimeError("Gemini returned an empty response (no text content).")
    return json.loads(response.text)

# ──────────────────────────────────────────────
#  Public interface
# ──────────────────────────────────────────────
async def generate_candidate_pool(
    prompt: str,
    target_minutes: int,
) -> LLMTrackPool:
    """
    Top-level entry point for Service A.

    1. Computes how many tracks the LLM must generate.
    2. Builds the system prompt.
    3. Calls the LLM (mock or real).
    4. Validates the response against the Pydantic schema.

    Raises
    ------
    ValueError
        If the LLM returns data that fails schema validation.
    """
    num_tracks = _compute_overgeneration_count(target_minutes)
    system_prompt = _build_system_prompt(num_tracks)

    logger.info(
        "Generating candidate pool  |  target=%d min  |  over-gen=%d tracks",
        target_minutes,
        num_tracks,
    )

    raw: dict[str, Any] = await _call_llm(system_prompt, prompt, num_tracks)

    # Validate through Pydantic — this will raise if the LLM returned garbage.
    try:
        pool = LLMTrackPool.model_validate(raw)
    except Exception as exc:
        logger.error("LLM response failed schema validation: %s", exc)
        raise ValueError(
            f"LLM returned malformed data that does not match the "
            f"CandidateTrack schema: {exc}"
        ) from exc

    logger.info(
        "Candidate pool ready  |  concept='%s'  |  tracks=%d",
        pool.playlist_concept,
        len(pool.candidate_tracks),
    )
    return pool
