from __future__ import annotations

import base64
import html
import json
import os
import re
import socket
import time
from io import BytesIO
from pathlib import Path

import requests
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

BASE_DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
EXCLUSION_DATA_DIR = Path(
    os.getenv("EXCLUSION_DATA_DIR", str(BASE_DATA_DIR / "exclusion_builder"))
)

DEFAULT_MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "400"))
DEFAULT_REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
CONVERT_TO_JPEG = os.getenv("CONVERT_TO_JPEG", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

SYSTEM_INSTRUCTION = (
    "You are a careful assistant that extracts wireless frequencies from images. "
    'Return ONLY valid JSON with the schema: {"frequencies_mhz": [numbers], '
    '"ranges_mhz": [[start,end], ...]}. '
    "If a frequency is given in kHz, convert to MHz. "
    "If units are missing, assume MHz. "
    "Only include frequencies that are clearly present in the image."
)

THEME_STYLE = """<style>
  @import url("https://fonts.googleapis.com/css2?family=Manrope:wght@500;700;800&family=Space+Grotesk:wght@400;500;700&display=swap");

  :root {
    --bg: #070b13;
    --panel: #0f1728;
    --panel-soft: #121d33;
    --text: #e8eefb;
    --muted: #9aabc8;
    --line: #28344f;
    --accent: #22d3ee;
    --accent-strong: #06b6d4;
    --shadow: 0 18px 40px rgba(0, 0, 0, 0.36);
    color-scheme: dark;
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    min-height: 100vh;
    font-family: "Space Grotesk", "Manrope", sans-serif;
    color: var(--text);
    background:
      radial-gradient(1100px 600px at -10% -20%, #1f2940 0%, transparent 58%),
      radial-gradient(900px 500px at 110% -10%, #0f4a63 0%, transparent 48%),
      linear-gradient(180deg, #070b13 0%, #0a1020 58%, #070b13 100%);
  }

  .wrap { max-width: 980px; margin: 0 auto; padding: 26px 16px 46px; }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
  }

  .brand {
    font-family: "Manrope", "Space Grotesk", sans-serif;
    font-weight: 800;
    letter-spacing: .03em;
    font-size: 1.08rem;
  }

  .nav { display: flex; gap: 10px; flex-wrap: wrap; }

  .nav a {
    text-decoration: none;
    color: var(--muted);
    border: 1px solid var(--line);
    padding: .45rem .72rem;
    border-radius: 999px;
    font-size: .88rem;
    transition: .2s ease;
    background: rgba(9, 14, 25, .55);
  }

  .nav a:hover { color: var(--text); border-color: #3a4b70; }

  .card {
    background: linear-gradient(180deg, rgba(17, 27, 45, .94), rgba(13, 21, 36, .94));
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 22px;
    box-shadow: var(--shadow);
    backdrop-filter: blur(4px);
  }

  h1 {
    margin: 0;
    font-family: "Manrope", "Space Grotesk", sans-serif;
    font-size: clamp(1.55rem, 3.1vw, 2rem);
    letter-spacing: .01em;
  }

  .lead { margin: 10px 0 0; color: var(--muted); line-height: 1.55; max-width: 75ch; }
  .note { color: var(--muted); margin-top: .7rem; }
  .footer { margin-top: 14px; color: var(--muted); font-size: .92rem; }

  label { display: block; margin: 14px 0 6px; font-weight: 700; color: #d5e5ff; }
  input[type=file], textarea {
    width: 100%;
    border: 1px solid var(--line);
    background: rgba(10, 17, 29, .72);
    color: var(--text);
    border-radius: 10px;
    padding: 10px 12px;
    font-family: inherit;
  }
  textarea { height: 120px; resize: vertical; }

  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .items { list-style: none; margin: 14px 0; padding: 0; display: grid; gap: 8px; }
  .items li {
    border: 1px solid var(--line);
    border-radius: 10px;
    background: rgba(10, 17, 29, .72);
    padding: .62rem .72rem;
  }

  .btn {
    display: inline-block;
    text-decoration: none;
    font-weight: 700;
    border-radius: 10px;
    padding: .62rem .9rem;
    border: 1px solid var(--accent-strong);
    background: linear-gradient(180deg, var(--accent), var(--accent-strong));
    color: #041017;
    cursor: pointer;
  }
  button.btn { width: auto; }

  .subtle {
    border-color: var(--line);
    background: rgba(10, 17, 29, .6);
    color: var(--text);
  }

  pre {
    white-space: pre-wrap;
    border: 1px solid #33486e;
    border-radius: 10px;
    background: rgba(10, 17, 29, .72);
    padding: .8rem;
    color: #f2f6ff;
  }

  @media (max-width: 680px) {
    .topbar { flex-direction: column; align-items: flex-start; }
    button.btn { width: 100%; }
  }
</style>"""

INDEX_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Frequency Exclusion Builder</title>
  __STYLE__
</head>
<body>
  <div class="wrap">
    <header class="topbar">
      <div class="brand">WWB TOOLS</div>
      <nav class="nav">
        <a href="/">Inclusion Lists</a>
        <a href="/exclusion-builder/">Exclusion Builder</a>
        <a href="/debug">Debug</a>
      </nav>
    </header>
    <main class="card">
      <h1>Frequency Exclusion Builder</h1>
      <p class="lead">Upload an image, extract frequencies with OpenAI, and generate WWB exclusion files.</p>
      <form action="/exclusion-builder/process" method="post" enctype="multipart/form-data">
        <label for="image">Image</label>
        <input type="file" id="image" name="image" accept="image/*,.heic,.heif,.dng" required />

        <label for="prompt">Additional prompt (optional)</label>
        <textarea id="prompt" name="prompt" placeholder="Example: Only include UHF wireless mic channels; ignore stage notes."></textarea>

        <div class="actions">
          <button class="btn" type="submit">Process</button>
          <a class="btn subtle" href="/">Back to Inclusion Lists</a>
        </div>
      </form>
      <p class="footer">Outputs: CSV, TXT, JSON, FXL</p>
    </main>
  </div>
</body>
</html>""".replace("__STYLE__", THEME_STYLE)

RESULT_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Exclusion Result</title>
  __STYLE__
</head>
<body>
  <div class="wrap">
    <header class="topbar">
      <div class="brand">WWB TOOLS</div>
      <nav class="nav">
        <a href="/">Inclusion Lists</a>
        <a href="/exclusion-builder/">Exclusion Builder</a>
        <a href="/debug">Debug</a>
      </nav>
    </header>
    <main class="card">
      <h1>Exclusion Result</h1>
      <p class="note">Frequencies detected:</p>
      <ul class="items">__ENTRIES__</ul>
      <div class="actions">
        <a class="btn" href="__CSV__">Download CSV</a>
        <a class="btn" href="__TXT__">Download TXT</a>
        <a class="btn" href="__JSON__">Download JSON</a>
        <a class="btn" href="__FXL__">Download FXL</a>
        <a class="btn subtle" href="/exclusion-builder/">Back</a>
      </div>
    </main>
  </div>
</body>
</html>""".replace("__STYLE__", THEME_STYLE)

ERROR_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Exclusion Builder Error</title>
  __STYLE__
</head>
<body>
  <div class="wrap">
    <header class="topbar">
      <div class="brand">WWB TOOLS</div>
      <nav class="nav">
        <a href="/">Inclusion Lists</a>
        <a href="/exclusion-builder/">Exclusion Builder</a>
        <a href="/debug">Debug</a>
      </nav>
    </header>
    <main class="card">
      <h1>Processing failed</h1>
      <p class="note">The request could not be completed.</p>
      <pre>__MESSAGE__</pre>
      <div class="actions">
        <a class="btn subtle" href="/exclusion-builder/">Back to builder</a>
      </div>
    </main>
  </div>
</body>
</html>""".replace("__STYLE__", THEME_STYLE)

JOB_RE = re.compile(r"^[A-Za-z0-9_-]+$")

router = APIRouter(prefix="/exclusion-builder", tags=["exclusion-builder"])


def _ensure_output_dir() -> None:
    EXCLUSION_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _mime_from_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    name = filename.lower()
    if name.endswith(".heic"):
        return "image/heic"
    if name.endswith(".heif"):
        return "image/heif"
    if name.endswith(".dng"):
        return "image/x-adobe-dng"
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".gif"):
        return "image/gif"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".tif") or name.endswith(".tiff"):
        return "image/tiff"
    return None


def _ensure_jpeg(
    image_bytes: bytes, mime_type: str | None, filename: str | None
) -> tuple[bytes, str]:
    is_jpeg = (mime_type or "").lower() in ("image/jpeg", "image/jpg")
    if not is_jpeg and filename:
        lower_name = filename.lower()
        if lower_name.endswith(".jpg") or lower_name.endswith(".jpeg"):
            is_jpeg = True
    if is_jpeg:
        return image_bytes, "image/jpeg"

    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(
            "Image conversion requires Pillow. Add pillow to requirements."
        ) from exc

    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        out = BytesIO()
        img.save(out, format="JPEG", quality=92)
        return out.getvalue(), "image/jpeg"
    except Exception as exc:
        raise RuntimeError(
            "Failed to convert image to JPEG. For HEIC/HEIF or DNG, install extra codecs."
        ) from exc


def _call_openai(image_bytes: bytes, mime_type: str, extra_prompt: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    data_url = "data:{};base64,{}".format(
        mime_type, base64.b64encode(image_bytes).decode("ascii")
    )

    user_prompt = SYSTEM_INSTRUCTION
    if extra_prompt:
        user_prompt = user_prompt + "\n\nAdditional instructions: " + extra_prompt

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_prompt},
                    {"type": "input_image", "image_url": data_url, "detail": "auto"},
                ],
            }
        ],
        "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
    }

    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError("OpenAI error: {}".format(resp.text))
    return resp.json()


def _extract_text_from_response(resp_json: dict) -> str | None:
    output = resp_json.get("output", [])
    for item in output:
        if item.get("type") == "message":
            for content in item.get("content", []):
                ctype = content.get("type")
                if ctype in ("output_text", "text"):
                    return content.get("text") or content.get("value")
    if "output_text" in resp_json:
        return resp_json.get("output_text")
    return None


def _parse_json_payload(text: str | None) -> dict:
    if not text:
        raise ValueError("No text output returned from model")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_value(value: float) -> float:
    if value > 3000:
        return value / 1000.0
    return value


def _normalize_frequencies(payload: dict) -> tuple[list[float], list[list[float]]]:
    freqs = payload.get("frequencies_mhz", []) or []
    ranges = payload.get("ranges_mhz", []) or []

    normalized_freqs: list[float] = []
    for freq in freqs:
        if isinstance(freq, (int, float)):
            normalized_freqs.append(_normalize_value(float(freq)))
            continue
        if isinstance(freq, str):
            value = (
                freq.strip().replace("MHz", "").replace("mhz", "").replace(",", "")
            )
            try:
                normalized_freqs.append(_normalize_value(float(value)))
            except ValueError:
                pass

    normalized_ranges: list[list[float]] = []
    for item in ranges:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            try:
                start = _normalize_value(float(item[0]))
                end = _normalize_value(float(item[1]))
                if start > end:
                    start, end = end, start
                normalized_ranges.append([start, end])
            except (TypeError, ValueError):
                continue
            continue
        if isinstance(item, str):
            value = item.replace("MHz", "").replace("mhz", "").replace(",", "")
            parts = re.split(r"[-–]\s*", value)
            if len(parts) != 2:
                continue
            try:
                start = _normalize_value(float(parts[0].strip()))
                end = _normalize_value(float(parts[1].strip()))
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            normalized_ranges.append([start, end])

    return normalized_freqs, normalized_ranges


def _format_khz(value_mhz: float) -> str:
    return str(int(round(value_mhz * 1000)))


def _write_fxl(path: Path, freqs_mhz: list[float], ranges_mhz: list[list[float]]) -> None:
    now = time.localtime()
    date_str = time.strftime("%a %b %d %Y", now)
    time_str = time.strftime("%H:%M:%S", now)
    hostname = socket.gethostname()
    compat_id = "6cbbb7e8-55ab-e4bb-f5c7-1b86242f7fd2"

    freqs_khz = [_format_khz(freq) for freq in freqs_mhz]
    ranges_khz = [[_format_khz(start), _format_khz(end)] for start, end in ranges_mhz]

    lines = [
        '<global_exclusions version="1.1" date="{date}" time="{time}" source="{source}" appl_version="7.7.0.117">'.format(
            date=date_str, time=time_str, source=hostname
        ),
        "    <frequency_exclusions>",
    ]

    for freq in freqs_khz:
        lines.extend(
            [
                "        <channel>",
                '            <frequency units="kHz">{}</frequency>'.format(freq),
                "            <series>Generic Device - IMD</series>",
                "            <manufacturer/>",
                "            <model/>",
                "            <band>Wideband</band>",
                "            <tx_profile/>",
                "            <compat_prof_id>{}</compat_prof_id>".format(compat_id),
                "            <source>User defined</source>",
                "            <notes/>",
                "            <exclude>1</exclude>",
                "        </channel>",
            ]
        )
    lines.append("    </frequency_exclusions>")
    lines.append("    <compat_profiles>")
    lines.extend(
        [
            '        <compat_profile version="0.0.0.1" imd_source="1" synthesizable="0" name="Standard" id="{}">'.format(
                compat_id
            ),
            '            <spacing freq_units="KHz">',
            "                <ch_ch>800</ch_ch>",
            "                <imd_2t3o>400</imd_2t3o>",
            "                <imd_2t5o>0</imd_2t5o>",
            "                <imd_2t7o>0</imd_2t7o>",
            "                <imd_2t9o>0</imd_2t9o>",
            "                <imd_3t3o>0</imd_3t3o>",
            "            </spacing>",
            '            <filter type="1">',
            "                <filter_start>-100000</filter_start>",
            "                <filter_end>100000</filter_end>",
            "                <filter_center>0</filter_center>",
            "            </filter>",
            "        </compat_profile>",
        ]
    )
    lines.append("    </compat_profiles>")
    lines.append("    <freq_range_exclusions>")
    for start, end in ranges_khz:
        lines.extend(
            [
                "        <range>",
                '            <frequency units="kHz">',
                "                <start>{}</start>".format(start),
                "                <end>{}</end>".format(end),
                "            </frequency>",
                "            <source>User defined</source>",
                "            <notes/>",
                "            <exclude>1</exclude>",
                "        </range>",
            ]
        )
    lines.append("    </freq_range_exclusions>")
    lines.append("</global_exclusions>")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_outputs(
    job_id: str,
    freqs: list[float],
    ranges: list[list[float]],
    raw_json: dict,
) -> dict[str, Path]:
    _ensure_output_dir()

    csv_path = EXCLUSION_DATA_DIR / (job_id + ".csv")
    txt_path = EXCLUSION_DATA_DIR / (job_id + ".txt")
    json_path = EXCLUSION_DATA_DIR / (job_id + ".json")
    fxl_path = EXCLUSION_DATA_DIR / (job_id + ".fxl")

    with open(csv_path, "w", encoding="utf-8") as handle:
        handle.write("frequency_mhz\n")
        for freq in freqs:
            handle.write("{:.3f}\n".format(freq))
        for start, end in ranges:
            handle.write("{:.3f}-{:.3f}\n".format(start, end))

    with open(txt_path, "w", encoding="utf-8") as handle:
        for freq in freqs:
            handle.write("{:.3f}\n".format(freq))
        for start, end in ranges:
            handle.write("{:.3f}-{:.3f}\n".format(start, end))

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(raw_json, handle, indent=2)

    _write_fxl(fxl_path, freqs, ranges)

    return {
        "csv": csv_path,
        "txt": txt_path,
        "json": json_path,
        "fxl": fxl_path,
    }


def _build_error_page(message: str) -> str:
    return ERROR_PAGE.replace("__MESSAGE__", html.escape(message))


@router.get("/", response_class=HTMLResponse)
async def exclusion_builder_index() -> HTMLResponse:
    return HTMLResponse(INDEX_PAGE)


@router.post("/process", response_class=HTMLResponse)
async def exclusion_builder_process(
    image: UploadFile = File(...),
    prompt: str = Form(default=""),
) -> HTMLResponse:
    try:
        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Invalid image")

        mime_type = (
            image.content_type
            or _mime_from_filename(image.filename)
            or "application/octet-stream"
        )

        try:
            if CONVERT_TO_JPEG:
                image_bytes, mime_type = _ensure_jpeg(
                    image_bytes, mime_type, image.filename
                )

            resp_json = _call_openai(image_bytes, mime_type, prompt)
            text = _extract_text_from_response(resp_json)
            payload = _parse_json_payload(text)
            freqs, ranges = _normalize_frequencies(payload)
            job_id = str(int(time.time() * 1000))
            _write_outputs(job_id, freqs, ranges, payload)
        except Exception as exc:
            return HTMLResponse(
                _build_error_page("Processing error: {}".format(str(exc))),
                status_code=500,
            )

        entries: list[str] = []
        for freq in freqs:
            entries.append("        <li>{:.3f} MHz</li>".format(freq))
        for start, end in ranges:
            entries.append("        <li>{:.3f} - {:.3f} MHz</li>".format(start, end))
        if not entries:
            entries.append("        <li>No frequencies found.</li>")

        body = RESULT_PAGE
        body = body.replace("__ENTRIES__", "\n".join(entries))
        body = body.replace(
            "__CSV__", f"/exclusion-builder/download?job={job_id}&format=csv"
        )
        body = body.replace(
            "__TXT__", f"/exclusion-builder/download?job={job_id}&format=txt"
        )
        body = body.replace(
            "__JSON__", f"/exclusion-builder/download?job={job_id}&format=json"
        )
        body = body.replace(
            "__FXL__", f"/exclusion-builder/download?job={job_id}&format=fxl"
        )
        return HTMLResponse(body)
    finally:
        # Explicitly close Starlette's upload handle so any spooled temp file is removed.
        try:
            await image.close()
        except Exception:
            pass


@router.get("/download")
async def exclusion_builder_download(
    job: str = Query(...),
    format: str = Query(...),
):
    if not JOB_RE.match(job):
        raise HTTPException(status_code=400, detail="Invalid job id")

    allowed = {"csv", "txt", "json", "fxl"}
    if format not in allowed:
        raise HTTPException(status_code=400, detail="Invalid format")

    path = EXCLUSION_DATA_DIR / f"{job}.{format}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "text/plain; charset=utf-8"
    headers: dict[str, str] | None = None
    if format == "json":
        media_type = "application/json; charset=utf-8"
    if format == "fxl":
        # Force download with .fxl extension; some browsers map XML media types to .xml.
        media_type = "application/octet-stream"
        headers = {
            "Content-Disposition": 'attachment; filename="frequencies.fxl"',
            "X-Content-Type-Options": "nosniff",
        }

    return FileResponse(
        path,
        media_type=media_type,
        filename=f"frequencies.{format}",
        headers=headers,
    )
