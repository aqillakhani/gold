"""FastAPI dashboard on localhost:8420."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from ..config import Config
from ..models.analytics import EngagementMetric, PostLog
from ..models.content import Content, ContentStatus
from ..models.db import get_sync_session
from ..models.queue import QueueItem, QueueStatus

app = FastAPI(title="Gold Dashboard", version="0.1.0")
_config: Config | None = None


def create_dashboard(config: Config) -> FastAPI:
    global _config
    _config = config
    return app


@app.get("/", response_class=HTMLResponse)
async def index():
    session = get_sync_session()
    try:
        # Queue stats
        queue_stats = {}
        for status in QueueStatus:
            stmt = select(func.count(QueueItem.id)).where(QueueItem.status == status)
            queue_stats[status.value] = session.execute(stmt).scalar() or 0

        # Content stats
        total_content = session.execute(select(func.count(Content.id))).scalar() or 0
        ready_content = session.execute(
            select(func.count(Content.id)).where(Content.status == ContentStatus.READY)
        ).scalar() or 0
        pending_review = session.execute(
            select(func.count(Content.id)).where(Content.status == ContentStatus.PENDING_REVIEW)
        ).scalar() or 0

        # Recent posts
        recent_stmt = (
            select(PostLog)
            .order_by(PostLog.posted_at.desc())
            .limit(20)
        )
        recent_posts = session.execute(recent_stmt).scalars().all()

        # Dead letters
        dead_stmt = (
            select(QueueItem)
            .where(QueueItem.status == QueueStatus.DEAD_LETTER)
            .order_by(QueueItem.updated_at.desc())
            .limit(10)
        )
        dead_letters = session.execute(dead_stmt).scalars().all()

        posts_html = ""
        for p in recent_posts:
            posts_html += (
                f"<tr><td>{p.account_id}</td><td>{p.platform}</td>"
                f"<td>{p.status}</td><td>{p.posted_at}</td>"
                f"<td>{p.platform_post_id or '-'}</td></tr>"
            )

        dead_html = ""
        for d in dead_letters:
            dead_html += (
                f"<tr><td>{d.account_id}</td><td>{d.platform}</td>"
                f"<td>{d.retry_count}</td>"
                f"<td>{(d.error_message or '')[:80]}</td>"
                f"<td><a href='/api/retry/{d.id}'>Retry</a></td></tr>"
            )

        return f"""<!DOCTYPE html>
<html><head><title>Gold Dashboard</title>
<style>
  body {{ font-family: system-ui; margin: 2rem; background: #0d1117; color: #c9d1d9; }}
  h1 {{ color: #f0c040; }}
  h2 {{ color: #58a6ff; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #30363d; padding: 8px; text-align: left; }}
  th {{ background: #161b22; }}
  .stat {{ display: inline-block; margin: 0.5rem 1rem; padding: 1rem;
           background: #161b22; border-radius: 8px; min-width: 120px; text-align: center; }}
  .stat .num {{ font-size: 2rem; font-weight: bold; color: #f0c040; }}
  .stat .label {{ font-size: 0.85rem; color: #8b949e; }}
  a {{ color: #58a6ff; }}
</style>
<meta http-equiv="refresh" content="60">
</head><body>
<nav><a href="/" style="color:#58a6ff;margin-right:1rem">Dashboard</a><a href="/review" style="color:#58a6ff">Review ({pending_review})</a></nav>
<h1>Gold Platform Dashboard</h1>

<h2>Queue Status</h2>
<div>
  {"".join(f'<div class="stat"><div class="num">{v}</div><div class="label">{k}</div></div>' for k, v in queue_stats.items())}
</div>

<h2>Content</h2>
<div>
  <div class="stat"><div class="num">{total_content}</div><div class="label">Total</div></div>
  <div class="stat"><div class="num">{pending_review}</div><div class="label">Pending Review</div></div>
  <div class="stat"><div class="num">{ready_content}</div><div class="label">Ready</div></div>
</div>

<h2>Recent Posts</h2>
<table>
  <tr><th>Account</th><th>Platform</th><th>Status</th><th>Posted At</th><th>Post ID</th></tr>
  {posts_html or "<tr><td colspan='5'>No posts yet</td></tr>"}
</table>

<h2>Dead Letters</h2>
<table>
  <tr><th>Account</th><th>Platform</th><th>Retries</th><th>Error</th><th>Action</th></tr>
  {dead_html or "<tr><td colspan='5'>None</td></tr>"}
</table>
</body></html>"""
    finally:
        session.close()


@app.get("/review", response_class=HTMLResponse)
async def review_page():
    session = get_sync_session()
    try:
        # Get all PENDING_REVIEW content
        pending_stmt = (
            select(Content)
            .where(Content.status == ContentStatus.PENDING_REVIEW)
            .order_by(Content.created_at.desc())
        )
        pending = session.execute(pending_stmt).scalars().all()

        # Load topic overrides
        import pathlib
        overrides_path = pathlib.Path(_config.root / "data" / "topic_overrides.json") if _config else None
        overrides = {}
        if overrides_path and overrides_path.exists():
            overrides = json.loads(overrides_path.read_text())

        # Get active niches
        active_niches = _config.get("app.active_niches", []) if _config else []

        cards_html = ""
        for c in pending:
            script_preview = (c.script or "")[:300] + ("..." if len(c.script or "") > 300 else "")
            video_link = f'<a href="/api/download/{c.id}">Download Video</a>' if c.master_video_path else "No video"
            thumb_link = f'<a href="/api/download/{c.id}?type=thumb">Thumbnail</a>' if c.thumbnail_path else ""
            cards_html += f"""
            <div class="card">
              <h3>{c.title}</h3>
              <div class="meta">{c.niche} &middot; #{c.id} &middot; {c.created_at.strftime('%Y-%m-%d %H:%M')}</div>
              <div class="script">{script_preview}</div>
              <div class="actions">
                {video_link} {thumb_link}
                <form method="POST" action="/api/review/{c.id}" style="display:inline">
                  <input type="hidden" name="action" value="approve">
                  <button class="btn approve">Approve</button>
                </form>
                <form method="POST" action="/api/review/{c.id}" style="display:inline">
                  <input type="hidden" name="action" value="reject">
                  <button class="btn reject">Reject</button>
                </form>
              </div>
            </div>"""

        if not cards_html:
            cards_html = '<p class="empty">No content pending review.</p>'

        # Topic override form
        override_inputs = ""
        for niche in active_niches:
            current = overrides.get(niche, [])
            current_str = ", ".join(current) if current else ""
            override_inputs += f"""
            <div class="override-row">
              <label>{niche}:</label>
              <input type="text" name="override_{niche}" value="{current_str}" placeholder="Topic 1, Topic 2...">
            </div>"""

        return f"""<!DOCTYPE html>
<html><head><title>Gold - Content Review</title>
<style>
  body {{ font-family: system-ui; margin: 2rem; background: #0d1117; color: #c9d1d9; }}
  h1 {{ color: #f0c040; }}
  h2 {{ color: #58a6ff; }}
  a {{ color: #58a6ff; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; margin: 1rem 0; }}
  .card h3 {{ color: #f0c040; margin: 0 0 0.5rem; }}
  .meta {{ color: #8b949e; font-size: 0.85rem; margin-bottom: 0.5rem; }}
  .script {{ font-size: 0.9rem; color: #c9d1d9; white-space: pre-wrap; margin: 0.5rem 0; padding: 0.5rem; background: #0d1117; border-radius: 4px; }}
  .actions {{ margin-top: 0.75rem; display: flex; gap: 0.5rem; align-items: center; }}
  .btn {{ padding: 6px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }}
  .btn.approve {{ background: #238636; color: white; }}
  .btn.reject {{ background: #da3633; color: white; }}
  .btn.approve:hover {{ background: #2ea043; }}
  .btn.reject:hover {{ background: #f85149; }}
  .empty {{ color: #8b949e; }}
  .override-row {{ margin: 0.5rem 0; display: flex; gap: 0.5rem; align-items: center; }}
  .override-row label {{ min-width: 150px; color: #58a6ff; }}
  .override-row input {{ flex: 1; padding: 6px; background: #0d1117; border: 1px solid #30363d; color: #c9d1d9; border-radius: 4px; }}
  .save-btn {{ background: #1f6feb; color: white; padding: 8px 24px; border: none; border-radius: 4px; cursor: pointer; margin-top: 0.5rem; }}
  nav {{ margin-bottom: 1rem; }}
  nav a {{ margin-right: 1rem; }}
</style>
</head><body>
<nav><a href="/">Dashboard</a> <a href="/review">Review</a></nav>
<h1>Content Review</h1>
<p>{len(pending)} item(s) pending review</p>
{cards_html}

<h2>Topic Overrides (Tomorrow)</h2>
<form method="POST" action="/api/topic-overrides">
  {override_inputs}
  <button type="submit" class="save-btn">Save Overrides</button>
</form>
</body></html>"""
    finally:
        session.close()


@app.post("/api/review/{content_id}")
async def api_review(content_id: int, request: Request):
    form = await request.form()
    action = form.get("action", "")
    session = get_sync_session()
    try:
        stmt = select(Content).where(Content.id == content_id)
        content = session.execute(stmt).scalar_one_or_none()
        if not content:
            return HTMLResponse("<script>alert('Not found');history.back()</script>")
        if action == "approve":
            content.status = ContentStatus.READY
        elif action == "reject":
            content.status = ContentStatus.REJECTED
        session.commit()
        return HTMLResponse("<script>window.location='/review'</script>")
    finally:
        session.close()


@app.get("/api/download/{content_id}")
async def api_download(content_id: int, request: Request):
    from fastapi.responses import FileResponse
    import pathlib
    type_ = request.query_params.get("type", "video")
    session = get_sync_session()
    try:
        stmt = select(Content).where(Content.id == content_id)
        content = session.execute(stmt).scalar_one_or_none()
        if not content:
            return {"error": "Not found"}
        path = content.thumbnail_path if type_ == "thumb" else content.master_video_path
        if path and pathlib.Path(path).exists():
            return FileResponse(path)
        return {"error": "File not found"}
    finally:
        session.close()


@app.post("/api/topic-overrides")
async def api_topic_overrides(request: Request):
    import pathlib
    form = await request.form()
    overrides = {}
    for key, value in form.items():
        if key.startswith("override_") and value.strip():
            niche = key[len("override_"):]
            topics = [t.strip() for t in value.split(",") if t.strip()]
            if topics:
                overrides[niche] = topics
    overrides_path = pathlib.Path(_config.root / "data" / "topic_overrides.json") if _config else None
    if overrides_path:
        overrides_path.parent.mkdir(parents=True, exist_ok=True)
        overrides_path.write_text(json.dumps(overrides, indent=2))
    return HTMLResponse("<script>window.location='/review'</script>")


@app.get("/api/stats")
async def api_stats():
    session = get_sync_session()
    try:
        stats = {}
        for status in QueueStatus:
            stmt = select(func.count(QueueItem.id)).where(QueueItem.status == status)
            stats[status.value] = session.execute(stmt).scalar() or 0
        return {"queue": stats}
    finally:
        session.close()


@app.post("/api/retry/{item_id}")
async def api_retry(item_id: int):
    session = get_sync_session()
    try:
        stmt = select(QueueItem).where(QueueItem.id == item_id)
        item = session.execute(stmt).scalar_one_or_none()
        if not item:
            return {"error": "Item not found"}
        item.status = QueueStatus.RETRY
        item.retry_count = 0
        session.commit()
        return {"status": "queued for retry", "id": item_id}
    finally:
        session.close()


@app.get("/api/jobs")
async def api_jobs():
    return {"message": "Use scheduler.get_jobs() — not exposed via API yet"}
