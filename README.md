# gold

Distributed, multi-provider LLM-driven media synthesis and content scheduling pipeline.

**Live demo:** [CONFIRM] · **Walkthrough:** [CONFIRM]

## Problem

Producing publication-ready short-form video at scale requires reliably chaining multiple specialized services: LLM ideation and scripting, multi-engine text-to-speech, background media sourcing (AI-generated or stock), platform-specific rendering, quality assurance, and time-zone-aware scheduling to multiple platforms. Doing this robustly means managing state, retries, rate limits, and platform-specific constraints across multiple accounts.

## What it does

- **Claude-driven content creation** with per-niche domain constraints: generates 3 ideas, selects top 1, writes publication-ready scripts with hooks and voiceover text
- **Multi-style video rendering** via Remotion (React/TypeScript): gameplay backgrounds, stock footage, AI-generated video (fal.ai Flux, ComfyUI), image-to-video, slides, ken burns, infographics
- **Multi-voice TTS**: routes dialogue to per-speaker voices across OpenAI, ElevenLabs, and Fish Audio; detects speaker changes in script
- **Platform variants**: renders platform-specific edits (duration, speed, captions, CTAs, hashtags) for Facebook, Instagram, YouTube, TikTok
- **Quality gates**: duration validation, audio presence, content moderation, thumbnail extraction; gates publishing until ready
- **Async content state machine**: GENERATING → PENDING_REVIEW → READY → POSTED (with FAILED, REJECTED terminal states) persisted in SQLite; automatic retry on platform failures
- **Time-zone-aware scheduler**: APScheduler daemon manages per-platform posting windows with per-account jitter and configurable rate limits
- **Multi-account orchestration**: independent content buffers per account, niche-specific context, all backed by FastAPI dashboard at `:8420` showing queue depth, content status, posting logs, engagement metrics
- **Dry-run mode**: render without posting; useful for preview and validation

## Stack

- **Python 3.11+**: async/await first throughout
- **FastAPI + Uvicorn**: dashboard and monitoring
- **SQLAlchemy 2.0 + Alembic + SQLite**: schema versioning, queryable content state
- **APScheduler**: background scheduling with timezone support
- **Remotion 4.0**: React/TypeScript rendering, captions, video composition
- **Claude API** (Anthropic): ideation and scripting
- **OpenAI, ElevenLabs, Fish Audio**: text-to-speech
- **fal.ai Flux, ComfyUI (vast.ai), stock video APIs**: media sourcing
- **Google, Meta, TikTok APIs**: platform posting
- **FFmpeg**: audio/video composition

## Architecture

```
Idea Generation (Claude)
    ↓
Script Writing (Claude + niche context)
    ↓
Media Sourcing (stock / AI generators)
    ↓
Multi-Voice TTS (OpenAI / ElevenLabs / Fish)
    ↓
Subtitle Generation
    ↓
Remotion Render (React/TS video composition)
    ↓
Platform Variants (captions, speed, CTAs)
    ↓
Quality Gates (duration, audio, moderation)
    ↓
SQLite Persistence (state machine: GENERATING → READY → POSTED)
    ↓
APScheduler Daemon (timezone-aware posting with jitter)
    ↓
Platform APIs (Facebook / Instagram / YouTube / TikTok)
```

**Multi-account**: Each account has independent niche, buffer, and posting schedule.
**State machine**: Content lifecycle tracked in DB; failures trigger retry and alert notifications.
**Async-first**: Rendering, API calls, and scheduling are non-blocking; dashboard reflects live queue/status.

## Run it

```bash
# Install
pip install -e .

# Configure secrets and accounts
cp secrets/.env.example secrets/.env
# Edit secrets/.env with API keys (Claude, OpenAI, Google, Meta, TikTok)
# Edit config/accounts.yaml with account details and posting schedules

# Start the platform (scheduler + dashboard on :8420)
python -m gold

# Or run just the dashboard
python -m gold --dashboard-only

# Or generate + render without posting (dry-run)
python -m gold --dry-run --generate <account_id>

# Or generate for all accounts
python -m gold --dry-run --generate all
```

The dashboard is live at http://localhost:8420 while the scheduler runs.

---

**License**: [CONFIRM]  
**Maintenance**: [CONFIRM]  
**Deployment**: [CONFIRM] (local or cloud infrastructure)
