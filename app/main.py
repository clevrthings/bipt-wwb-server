from __future__ import annotations
import os
import base64
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .storage import init_db, inc_counter, inc_download, get_stats, mark_unique
from .bipt_wwb import nightly_check_and_update, list_available_files

from pathlib import Path
from fastapi.templating import Jinja2Templates

DEBUG_USER = os.getenv("DEBUG_USER", "admin")
DEBUG_PASS = os.getenv("DEBUG_PASS", "change-me")
CHECK_HOUR = int(os.getenv("CHECK_HOUR", "2"))
CHECK_MINUTE = int(os.getenv("CHECK_MINUTE", "15"))
LANG = os.getenv("LANG_CODE", "NL")
LIST_NAME = os.getenv("LIST_NAME", "Belgium (BIPT zones)")

DATA_DIR = os.getenv("DATA_DIR", "/data")

app = FastAPI(title="BIPT → WWB Inclusion List")

BASE_DIR = Path(__file__).resolve().parent  # .../app
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def _check_basic_auth(req: Request) -> None:
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
    user, pwd = raw.split(":", 1)
    if user != DEBUG_USER or pwd != DEBUG_PASS:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})

@app.on_event("startup")
async def startup():
    init_db()

    # Run once on boot (so you have a file immediately if possible)
    try:
        nightly_check_and_update(lang=LANG, list_name=LIST_NAME)
    except Exception:
        # we don't want the app to fail booting because BIPT is temporarily down
        pass

    scheduler = AsyncIOScheduler(timezone=os.getenv("TZ", "Europe/Brussels"))
    scheduler.add_job(
        func=lambda: nightly_check_and_update(lang=LANG, list_name=LIST_NAME),
        trigger=CronTrigger(hour=CHECK_HOUR, minute=CHECK_MINUTE),
        id="nightly_bipt_check",
        replace_existing=True,
    )
    scheduler.start()

@app.middleware("http")
async def count_visits(request: Request, call_next):
    # Count only "human" pages (skip static download responses below)
    path = request.url.path
    if path == "/" or path == "/debug":
        inc_counter("pageviews", 1)
        # Unique visitors (hash of ip+ua) - no raw IP stored
        ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("User-Agent", "")
        mark_unique(f"{ip}|{ua}")

    return await call_next(request)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    files = list_available_files()
    return templates.TemplateResponse("index.html", {"request": request, "files": files})

@app.get("/download/{filename}")
async def download(filename: str):
    # basic safe path check
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    inc_download(filename, 1)
    return FileResponse(path, media_type="application/octet-stream", filename=filename)

@app.get("/debug", response_class=HTMLResponse)
async def debug(request: Request):
    _check_basic_auth(request)
    stats = get_stats()
    files = list_available_files()
    return templates.TemplateResponse(
        "debug.html",
        {"request": request, "stats": stats, "files": files},
    )

@app.post("/debug/run-check")
async def run_check(request: Request):
    _check_basic_auth(request)
    changed = nightly_check_and_update(lang=LANG, list_name=LIST_NAME)
    return RedirectResponse(url="/debug", status_code=303)
