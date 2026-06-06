"""
solver.py — Service C: The Dynamic Programming constraint solver.

This is the mathematical core of the playlist orchestrator.  It solves a
variant of the **Subset Sum / 0-1 Knapsack** problem:

    Given a set of N tracks with known durations (in seconds), select a
    subset whose total duration is as close as possible to a target T,
    within a tolerance window of ±ε seconds.

Algorithm
---------
1.  Convert all durations from milliseconds → seconds to shrink the
    DP table and reduce memory consumption.

2.  Build a 1-D boolean DP array of size (target_seconds + 1).
        dp[s] = True  ⟺  some subset of the first k tracks sums to
                          exactly s seconds.

3.  Alongside `dp`, maintain a *predecessor* array that records which
    track index flipped each reachable sum to True.  This lets us
    backtrack from the best sum to recover the actual selected tracks.

4.  After processing all tracks, scan the tolerance window
    [T - ε, T + ε] for reachable sums.  Pick the one closest to T.

5.  Backtrack through the predecessor chain to collect selected indices.

6.  Sort the selected indices by their *original* position in the LLM
    output.  This preserves the narrative phase ordering (warmup →
    peak → cooldown) without re-sorting by phase label.

Complexity
----------
- Time:  O(N × T)   where N = number of verified tracks, T = target in seconds.
- Space: O(T)        for the two 1-D arrays.

For typical inputs (N ≈ 40, T ≈ 3 600) this runs in under 1 ms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from schemas import VerifiedTrack

logger = logging.getLogger(__name__)

# Default tolerance: ±45 seconds from the target.
DEFAULT_TOLERANCE_SECONDS = 45


@dataclass(frozen=True, slots=True)
class SolverResult:
    """Immutable container for the solver's output."""

    selected_tracks: list[VerifiedTrack]
    total_duration_seconds: int
    target_duration_seconds: int
    deviation_seconds: int


class SolverError(Exception):
    """Raised when no valid subset exists within the tolerance window."""


def solve_playlist_knapsack(
    tracks: list[VerifiedTrack],
    target_minutes: int,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> SolverResult:
    """
    Find the subset of `tracks` whose total duration (in seconds) is
    closest to `target_minutes × 60`, within ±`tolerance_seconds`.

    Parameters
    ----------
    tracks : list[VerifiedTrack]
        Verified tracks with `duration_ms` populated.
    target_minutes : int
        The user's requested playlist length.
    tolerance_seconds : int
        Allowed deviation from the target (default ±45 s).

    Returns
    -------
    SolverResult
        The optimal subset, preserving original LLM ordering.

    Raises
    ------
    SolverError
        If no combination of tracks falls within the tolerance window.
    """
    n = len(tracks)
    target_sec = target_minutes * 60

    if n == 0:
        raise SolverError("No verified tracks available for the solver.")

    # ── Step 1: Downsample durations to seconds ──────────────────────
    durations = [t.duration_ms // 1000 for t in tracks]

    total_available = sum(durations)
    logger.info(
        "Solver invoked  |  tracks=%d  |  target=%d s  |  available=%d s  |  ε=±%d s",
        n,
        target_sec,
        total_available,
        tolerance_seconds,
    )

    # Quick sanity check: is the total pool even large enough?
    if total_available < target_sec - tolerance_seconds:
        raise SolverError(
            f"Total pool duration ({total_available} s) is less than the "
            f"minimum acceptable ({target_sec - tolerance_seconds} s).  "
            f"Not enough material to fill the playlist."
        )

    # ── Step 2: Determine DP table capacity ──────────────────────────
    # We only need to track sums up to the upper bound of the window.
    # But some subsets may overshoot slightly, so we cap at
    # target + tolerance (no point tracking beyond that).
    capacity = target_sec + tolerance_seconds

    # ── Step 3: Initialise DP arrays ─────────────────────────────────
    # dp[s] = True means "sum s is reachable with some subset".
    dp: list[bool] = [False] * (capacity + 1)
    dp[0] = True  # The empty subset sums to 0.

    # predecessor[s] stores the track index that was added last to
    # reach sum s.  -1 means "no track" (unreachable or base case).
    predecessor: list[int] = [-1] * (capacity + 1)

    # ── Step 4: Fill the DP table (0-1 knapsack style) ───────────────
    for idx in range(n):
        dur = durations[idx]

        # Traverse RIGHT → LEFT so each track is used at most once.
        # If we went left → right, we'd allow the same track to be
        # picked multiple times (unbounded knapsack — not what we want).
        for s in range(capacity, dur - 1, -1):
            if dp[s - dur] and not dp[s]:
                # Flipping dp[s] to True: we can reach sum s by adding
                # track `idx` to whatever subset reached (s - dur).
                dp[s] = True
                predecessor[s] = idx

    # ── Step 5: Find the best reachable sum in the tolerance window ──
    window_lo = max(0, target_sec - tolerance_seconds)
    window_hi = min(capacity, target_sec + tolerance_seconds)

    best_sum = -1
    best_deviation = tolerance_seconds + 1  # Start worse than any valid hit.

    for s in range(window_lo, window_hi + 1):
        if dp[s]:
            dev = abs(s - target_sec)
            if dev < best_deviation:
                best_deviation = dev
                best_sum = s

    if best_sum == -1:
        raise SolverError(
            f"No subset of tracks sums to within ±{tolerance_seconds} s "
            f"of the target ({target_sec} s).  Try increasing the "
            f"candidate pool size or relaxing the tolerance."
        )

    logger.info(
        "Solver found feasible sum  |  best=%d s  |  deviation=%d s",
        best_sum,
        best_deviation,
    )

    # ── Step 6: Backtrack to find which tracks were selected ─────────
    selected_indices: list[int] = []
    remaining = best_sum

    while remaining > 0 and predecessor[remaining] != -1:
        idx = predecessor[remaining]
        selected_indices.append(idx)
        remaining -= durations[idx]

    # ── Step 7: Sort by original index to preserve narrative arc ─────
    # The LLM returned tracks in phase order (warmup → peak → cooldown).
    # By sorting selected indices ascending, we restore that sequence.
    selected_indices.sort()

    selected_tracks = [tracks[i] for i in selected_indices]

    logger.info(
        "Solver complete  |  selected=%d tracks  |  total=%d s  |  target=%d s  |  Δ=%d s",
        len(selected_tracks),
        best_sum,
        target_sec,
        best_deviation,
    )

    return SolverResult(
        selected_tracks=selected_tracks,
        total_duration_seconds=best_sum,
        target_duration_seconds=target_sec,
        deviation_seconds=best_deviation,
    )
