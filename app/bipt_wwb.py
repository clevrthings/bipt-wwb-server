from __future__ import annotations
import os
import re
import socket
import uuid
import json
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
import pdfplumber
from bs4 import BeautifulSoup

BIPT_MICROS_URL = "https://www.bipt.be/consumenten/radiofrequenties/professioneel-gebruik/micro-s"
UA = "Mozilla/5.0 (compatible; BIPT-WWB-Server/1.0; +https://www.bipt.be/)"

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
META_FILE = DATA_DIR / "meta.json"

PDF_RE = re.compile(
    r"^https?://ihpbpmoqelm\.bipt\.be/micro/files/"
    r"(?P<code>[A-Z]+)-(?P<lang>[A-Z]{2})-(?P<yy>\d{2})-(?P<q>[1-4])\.pdf$"
)
NUM_RE = re.compile(r"^\d+(?:[.,]\d+)?$")

@dataclass(frozen=True)
class PdfItem:
    zone_name: str
    url: str
    code: str
    lang: str
    yy: int
    quarter: int

    @property
    def key(self) -> Tuple[int,int]:
        return (self.yy, self.quarter)

@dataclass(frozen=True)
class RangeKHz:
    start_khz: int
    end_khz: int

def _fetch_html() -> str:
    r = requests.get(BIPT_MICROS_URL, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text

def _parse_zone_pdfs(html: str, lang: str = "NL") -> List[PdfItem]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile(r"\btable\b"))
    if not table:
        raise RuntimeError("Zonedocumenten-tabel niet gevonden.")

    items: List[PdfItem] = []
    for row in table.select("tbody tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        zone_name = " ".join(th.get_text(" ", strip=True).split())
        for a in td.find_all("a", href=True):
            href = a["href"].strip()
            m = PDF_RE.match(href)
            if not m:
                continue
            if m.group("lang").upper() != lang.upper():
                continue
            items.append(
                PdfItem(
                    zone_name=zone_name,
                    url=href,
                    code=m.group("code").upper(),
                    lang=m.group("lang").upper(),
                    yy=int(m.group("yy")),
                    quarter=int(m.group("q")),
                )
            )
    return items

def _choose_latest_per_zone(items: List[PdfItem]) -> Dict[str, PdfItem]:
    best: Dict[str, PdfItem] = {}
    for it in items:
        if it.zone_name not in best or it.key > best[it.zone_name].key:
            best[it.zone_name] = it
    return best

def _mhz_to_khz(s: str) -> int:
    return int(round(float(s.replace(",", ".")) * 1000.0))

def _merge_ranges(ranges: List[RangeKHz]) -> List[RangeKHz]:
    if not ranges:
        return []
    ranges = sorted(ranges, key=lambda r: (r.start_khz, r.end_khz))
    merged = [ranges[0]]
    for r in ranges[1:]:
        last = merged[-1]
        if r.start_khz <= last.end_khz:
            merged[-1] = RangeKHz(last.start_khz, max(last.end_khz, r.end_khz))
        else:
            merged.append(r)
    return merged

def _is_free_line(line: str) -> bool:
    u = line.upper()
    return ("VRIJGESTELD" in u) or ("MAXIMUM 10 MW" in u) or ("MAX 10 MW" in u)

def _extract_ranges_split_from_pdf(pdf_path: Path) -> Tuple[List[RangeKHz], List[RangeKHz]]:
    text_parts: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    text = "\n".join(text_parts)

    licensed: List[RangeKHz] = []
    free: List[RangeKHz] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or "OK" not in line.upper():
            continue
        tokens = line.split()
        try:
            ok_idx = next(i for i, t in enumerate(tokens) if t.upper() == "OK")
        except StopIteration:
            continue
        nums = [t for t in tokens[:ok_idx] if NUM_RE.match(t)]
        if len(nums) < 2:
            continue
        fmin_s, fmax_s = nums[-2], nums[-1]
        start_khz = _mhz_to_khz(fmin_s)
        end_khz = _mhz_to_khz(fmax_s)
        if end_khz < start_khz:
            start_khz, end_khz = end_khz, start_khz
        rng = RangeKHz(start_khz, end_khz)
        (free if _is_free_line(line) else licensed).append(rng)

    return _merge_ranges(licensed), _merge_ranges(free)

def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

def _build_wwb_xml(list_name: str, groups: List[Tuple[str, List[RangeKHz]]]) -> str:
    now = datetime.now()
    date_str = now.strftime("%a %b %d %Y")
    time_str = now.strftime("%H:%M:%S")
    machine = socket.gethostname()

    ns = uuid.NAMESPACE_URL
    list_uuid = uuid.uuid5(ns, f"wwb-inclusion-list:{list_name}")

    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<inclusion_list active="false" user="" date="{_xml_escape(date_str)}" time="{_xml_escape(time_str)}" '
        f'version="1.0" name="{_xml_escape(list_name)}" machine="{_xml_escape(machine)}" uuid="{list_uuid}">'
    )

    for group_name, ranges in groups:
        group_uuid = uuid.uuid5(ns, f"wwb-inclusion-group:{list_name}:{group_name}")
        lines.append(
            f'    <inclusion_group color="#FFFFFF" version="1.0" name="{_xml_escape(group_name)}" uuid="{group_uuid}">'
        )
        lines.append('        <freqs units="KHz" count="0"/>')
        lines.append(f'        <freq_ranges units="KHz" count="{len(ranges)}">')
        for r in ranges:
            lines.append("            <fr>")
            lines.append(f"                <f>{r.start_khz}</f>")
            lines.append(f"                <f>{r.end_khz}</f>")
            lines.append("            </fr>")
        lines.append("        </freq_ranges>")
        lines.append("    </inclusion_group>")
    lines.append("</inclusion_list>")
    return "\n".join(lines)

def _current_quarter(d: date) -> Tuple[int,int]:
    q = ((d.month - 1) // 3) + 1
    return (d.year, q)

def _quarter_to_int(year: int, q: int) -> int:
    return year * 10 + q

def _load_meta() -> dict:
    if META_FILE.exists():
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    return {}

def _save_meta(meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")

def _safe_delete(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)  # py3.8+
    except TypeError:
        if path.exists():
            path.unlink()

def list_available_files() -> List[str]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sorted([p.name for p in DATA_DIR.glob("bipt_inclusion_list_*_Q*.ils")])

def nightly_check_and_update(lang: str = "NL", list_name: str = "Belgium (BIPT zones)") -> bool:
    """
    Returns True if a new file was generated/changed, else False.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = _load_meta()

    html = _fetch_html()
    items = _parse_zone_pdfs(html, lang=lang)
    if not items:
        return False
    selected = _choose_latest_per_zone(items)

    # Determine newest publication label (max YY/Q from zones)
    max_yy, max_q = max((it.yy, it.quarter) for it in selected.values())
    pub_year = 2000 + max_yy
    pub_q = max_q

    last_pub = meta.get("latest_publication")
    new_pub = f"{pub_year}_Q{pub_q}"
    if last_pub == new_pub:
        # Still do cleanup based on current date (quarter rollover)
        _cleanup_old_files()
        return False

    # Generate new .ils
    tmp_dir = DATA_DIR / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    groups: List[Tuple[str, List[RangeKHz]]] = []
    free_union: List[RangeKHz] = []

    for zone_name, it in sorted(selected.items(), key=lambda kv: kv[0].lower()):
        pdf_path = tmp_dir / f"{it.code}-{it.lang}-{it.yy:02d}-{it.quarter}.pdf"
        # download
        r = requests.get(it.url, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        pdf_path.write_bytes(r.content)

        licensed, free = _extract_ranges_split_from_pdf(pdf_path)
        all_usable = _merge_ranges(licensed + free)

        groups.append((zone_name, all_usable))
        free_union = _merge_ranges(free_union + free)

        _safe_delete(pdf_path)

    # global free group
    groups.append(("Vrije frequenties", free_union))

    xml = _build_wwb_xml(list_name=list_name, groups=groups)
    out_path = DATA_DIR / f"bipt_inclusion_list_{pub_year}_Q{pub_q}.ils"
    out_path.write_text(xml, encoding="utf-8")

    # update meta + cleanup
    meta["latest_publication"] = new_pub
    meta["latest_publication_ts"] = datetime.now().isoformat()
    _save_meta(meta)

    _cleanup_old_files()
    return True

def _cleanup_old_files() -> None:
    """
    Online houden:
      - huidige kwartaal file (als bestaat)
      - volgende kwartaal file (als bestaat)
    Alles ouder dan huidig kwartaal: verwijderen.
    """
    y, q = _current_quarter(date.today())
    current_tag = f"{y}_Q{q}"

    # volgende kwartaal berekenen
    if q == 4:
        ny, nq = y + 1, 1
    else:
        ny, nq = y, q + 1
    next_tag = f"{ny}_Q{nq}"

    keep = {current_tag, next_tag}

    for p in DATA_DIR.glob("bipt_inclusion_list_*_Q*.ils"):
        m = re.search(r"bipt_inclusion_list_(\d{4})_Q([1-4])\.ils$", p.name)
        if not m:
            continue
        tag = f"{m.group(1)}_Q{m.group(2)}"
        if tag not in keep:
            _safe_delete(p)
