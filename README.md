# 🎵 AI Playlist Orchestrator

An intelligent backend that translates **creative narrative prompts** into **mathematically time-optimised playlists** using a three-stage pipeline:

```
LLM Engine → Spotify Verification → Dynamic-Programming Solver
```

> **Example prompt:** *"A 45-minute HYROX session starting with hip-hop warmup, peaking with darksynth, and cooling down with acoustic chill."*

The system over-generates candidate tracks via an LLM, verifies them against Spotify, then runs a **0-1 Knapsack / Subset Sum** solver to select the subset whose total duration best matches the user's target (within ±45 seconds).

---

## 📁 Project Structure

```
AI playlist maker/
├── main.py              # Application entry point — FastAPI app setup & health check
├── router.py            # API router — orchestrates the 3-stage pipeline
├── schemas.py           # Pydantic v2 models — strict data contracts for the entire pipeline
├── llm_engine.py        # Service A — LLM candidate-pool generator (currently mocked)
├── spotify_client.py    # Service B — Spotify metadata enrichment (currently mocked)
├── solver.py            # Service C — Dynamic Programming constraint solver
├── requirements.txt     # Python dependencies
├── pyrightconfig.json   # Pyright type-checker configuration
├── .venv/               # Python virtual environment (not committed)
└── README.md            # This file
```

### File Details

| File | Role | Description |
|---|---|---|
| **`main.py`** | Entry point | Creates the FastAPI app, configures CORS, registers routers, exposes a `/health` endpoint. |
| **`router.py`** | Orchestrator | Defines `POST /api/v1/playlists/generate`. Wires together the three services in sequence and handles errors at each stage. |
| **`schemas.py`** | Data contracts | Pydantic v2 models: `PlaylistRequest`, `CandidateTrack`, `LLMTrackPool`, `VerifiedTrack`, `FinalPlaylistResponse`. These enforce strict validation across the entire pipeline. |
| **`llm_engine.py`** | Service A | Builds the system prompt, calculates over-generation count (2.5× estimated tracks), calls the LLM, and validates the response. **Currently uses a deterministic mock** with a curated track bank — no API key needed. |
| **`spotify_client.py`** | Service B | Takes candidate tracks and "searches" Spotify to verify they exist, enriching them with `duration_ms` and `spotify_id`. **Currently mocked** with deterministic hash-based durations. |
| **`solver.py`** | Service C | The mathematical core. Runs a 0-1 Knapsack DP algorithm to find the subset of tracks whose total duration is closest to the target, within ±45s tolerance. Preserves the narrative arc ordering. |
| **`requirements.txt`** | Dependencies | Lists `fastapi`, `pydantic`, and `uvicorn`. |
| **`pyrightconfig.json`** | Type checking | Configures Pyright for Python 3.11 on macOS, pointing to the local `.venv`. |

---

## 🚀 How to Run

### Prerequisites

- **Python 3.11+**
- **pip** (comes with Python)

### 1. Create and activate a virtual environment

```bash
cd "AI playlist maker"

python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the development server

```bash
uvicorn main:app --reload
```

The server starts at **http://127.0.0.1:8000**.

### 4. Try it out

- **Interactive API docs (Swagger UI):** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **Health check:** http://127.0.0.1:8000/health

#### Example request (via curl):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/playlists/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A 30-minute synthwave run starting slow and building to an intense peak before cooling down",
    "target_duration_minutes": 30
  }'
```

#### Example request (via Swagger UI):

1. Open http://127.0.0.1:8000/docs
2. Expand **POST /api/v1/playlists/generate**
3. Click **Try it out**
4. Paste the JSON body and click **Execute**

---

## 🔧 What You Need to Add Manually (for Production)

The app runs out of the box with **mocked services** — no API keys or external accounts needed. To connect it to real services, you'll need to make the following changes:

---

### 1. 🤖 Real LLM Integration (in `llm_engine.py`)

**What:** Replace the mock LLM with a real API call (OpenAI, Google Gemini, Anthropic, etc.)

**Where:** The [`_call_llm()`](llm_engine.py) function (around **line 189**)

**How:**

1. **Install an LLM client library** — add it to `requirements.txt`:
   ```
   # Pick one:
   openai>=1.0.0
   # or
   google-generativeai>=0.5.0
   # or
   anthropic>=0.20.0
   ```

2. **Set your API key** as an environment variable:
   ```bash
   # OpenAI
   export OPENAI_API_KEY="sk-..."

   # Google Gemini
   export GOOGLE_API_KEY="..."

   # Anthropic
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

3. **Replace the body of `_call_llm()`** with a real API call. Example with OpenAI:
   ```python
   import openai

   async def _call_llm(system_prompt: str, user_prompt: str, num_tracks: int) -> dict[str, Any]:
       client = openai.AsyncOpenAI()  # reads OPENAI_API_KEY from env
       response = await client.chat.completions.create(
           model="gpt-4o",
           messages=[
               {"role": "system", "content": system_prompt},
               {"role": "user", "content": user_prompt},
           ],
           response_format={"type": "json_object"},
       )
       return json.loads(response.choices[0].message.content)
   ```

> [!IMPORTANT]
> The system prompt in `SYSTEM_PROMPT_TEMPLATE` (line 29) is already written and instructs the LLM to output JSON matching the `LLMTrackPool` schema. You **don't** need to change it — just wire up the API call.

---

### 2. 🎧 Real Spotify Integration (in `spotify_client.py`)

**What:** Replace the mock Spotify lookup with real Spotify Web API calls.

**Where:** The [`_mock_spotify_lookup()`](spotify_client.py) function (around **line 48**)

**How:**

1. **Create a Spotify Developer App:**
   - Go to https://developer.spotify.com/dashboard
   - Create an app to get your **Client ID** and **Client Secret**

2. **Install the Spotify client library** — add to `requirements.txt`:
   ```
   spotipy>=2.23.0
   ```

3. **Set environment variables:**
   ```bash
   export SPOTIPY_CLIENT_ID="your-client-id"
   export SPOTIPY_CLIENT_SECRET="your-client-secret"
   ```

4. **Replace `_mock_spotify_lookup()`** with a real search. Example:
   ```python
   import spotipy
   from spotipy.oauth2 import SpotifyClientCredentials

   sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials())

   async def _spotify_lookup(track: CandidateTrack) -> VerifiedTrack | None:
       query = f"track:{track.title} artist:{track.artist}"
       results = sp.search(q=query, type="track", limit=1)
       items = results["tracks"]["items"]
       if not items:
           return None
       hit = items[0]
       return VerifiedTrack(
           title=track.title,
           artist=track.artist,
           phase=track.phase,
           duration_ms=hit["duration_ms"],
           spotify_id=hit["id"],
       )
   ```

5. **Update `verify_and_fetch_metadata()`** to call your new function instead of `_mock_spotify_lookup()`.

---

### 3. ⚙️ Environment Variables Summary

Create a `.env` file in the project root (or export in your shell):

```bash
# ── LLM Provider (pick one) ─────────────────────
OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...
# ANTHROPIC_API_KEY=sk-ant-...

# ── Spotify ──────────────────────────────────────
SPOTIPY_CLIENT_ID=your-client-id
SPOTIPY_CLIENT_SECRET=your-client-secret
```

> [!NOTE]
> If you use a `.env` file, install `python-dotenv` and add `from dotenv import load_dotenv; load_dotenv()` at the top of `main.py`.

---

### 4. 🔒 Optional: Tighten CORS (in `main.py`)

The current CORS config allows **all origins** (`"*"`) for local development. For production, restrict it:

**Where:** [`main.py`](main.py), **lines 44–50**

```python
# Replace:
allow_origins=["*"]

# With your frontend domain(s):
allow_origins=["https://yourapp.com", "https://www.yourapp.com"]
```

---

### 5. 📊 Optional: Tune the Solver (in `solver.py`)

You can adjust these constants:

| Constant | Location | Default | Description |
|---|---|---|---|
| `DEFAULT_TOLERANCE_SECONDS` | `solver.py` line 51 | `45` | How far off (±) the total duration can be from the target. Increase for more flexibility, decrease for stricter matching. |

And in `llm_engine.py`:

| Constant | Location | Default | Description |
|---|---|---|---|
| Over-generation multiplier | `llm_engine.py` line 72 | `2.5×` | How many extra tracks the LLM generates. Higher values give the solver more options but cost more API tokens. |

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                   POST /api/v1/playlists/generate          │
│                          (router.py)                       │
└────────────────────┬───────────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   Stage 1: LLM      │  ← llm_engine.py
          │   Over-generate     │     Produces 2.5× candidate tracks
          │   candidate pool    │     in warmup → peak → cooldown order
          └──────────┬──────────┘
                     │ LLMTrackPool
          ┌──────────▼──────────┐
          │   Stage 2: Spotify  │  ← spotify_client.py
          │   Verify & enrich   │     Concurrent lookups, adds
          │   with metadata     │     duration_ms + spotify_id
          └──────────┬──────────┘
                     │ list[VerifiedTrack]
          ┌──────────▼──────────┐
          │   Stage 3: DP       │  ← solver.py
          │   Constraint Solver │     0-1 Knapsack, ±45s tolerance
          │   (Subset Sum)      │     Preserves narrative arc order
          └──────────┬──────────┘
                     │ SolverResult
          ┌──────────▼──────────┐
          │ FinalPlaylistResponse│  → JSON response to client
          └─────────────────────┘
```

---

## 📦 API Reference

### `POST /api/v1/playlists/generate`

**Request body:**

```json
{
  "prompt": "A creative description of the playlist you want (10–2000 chars)",
  "target_duration_minutes": 30
}
```

| Field | Type | Constraints | Description |
|---|---|---|---|
| `prompt` | `string` | 10–2000 characters | Creative narrative prompt describing the playlist arc |
| `target_duration_minutes` | `integer` | 5–180 | Desired playlist length in minutes |

**Response body:**

```json
{
  "concept": "Synthetic Neon Flow",
  "target_duration_seconds": 1800,
  "total_duration_seconds": 1792,
  "tolerance_seconds": 45,
  "track_count": 8,
  "tracks": [
    {
      "title": "Resonance",
      "artist": "HOME",
      "phase": "warmup",
      "duration_ms": 235000,
      "spotify_id": "abc123..."
    }
  ]
}
```

### `GET /health`

Returns `{"status": "ok", "service": "ai-playlist-orchestrator"}`.

---

## 📄 License

This project is for educational and personal use.
