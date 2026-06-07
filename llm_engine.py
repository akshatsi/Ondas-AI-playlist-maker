"""
llm_engine.py — Service A: The LLM candidate-pool generator.

Responsible for:
  1. Building a strict system prompt that forces JSON-only output.
  2. Calculating the over-generation factor (2.5× the estimated track count).
  3. Returning a validated LLMTrackPool ready for downstream enrichment.

The `_call_llm` coroutine hits the Gemini API to generate the track pool.
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
    2. Builds the systeqm prompt.
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
