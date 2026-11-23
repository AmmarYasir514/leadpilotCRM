"""Parse messy pasted Upwork job-page text into structured fields.

This module uses the Python standard library only. It never opens a
network connection and never fetches, opens or automates Upwork. The
only input is text the user pasted from a browser.

Public API:
    parse_job_text(text) -> dict with title, description, budget,
        skills (list of str) and url. Missing values are '' or [].
    is_valid_job_url(url) -> bool
    normalize_job_url(url) -> str

None of these functions raise on bad input.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Hard cap on the returned description. Longer bodies are truncated.
DESCRIPTION_MAX_CHARS = 20000

_EMPTY = {
    "title": "",
    "description": "",
    "budget": "",
    "skills": [],
    "url": "",
}

# Known ad and analytics query keys. Any key starting with utm_ is also dropped.
_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "msclkid",
    "twclid",
    "li_fat_id",
    "mc_cid",
    "mc_eid",
    "_ga",
    "yclid",
    "igshid",
    "ref",
    "referrer",
}

# Browser chrome and nav labels that are never a job title.
_CHROME = {
    "back",
    "save job",
    "flag as inappropriate",
    "find work",
    "job details",
    "job post",
    "search",
    "messages",
    "notifications",
    "saved jobs",
    "upwork",
    "home",
    "proposals",
    "share",
    "saved",
    "apply now",
    "share job",
    "report",
}

# Section headings that end the description or the skills list.
_STOP_HEADINGS = (
    "about the client",
    "activity on this job",
    "preferred qualifications",
    "screening questions",
    "client's recent history",
    "clients recent history",
    "proposal extras",
    "you will be asked",
    "job activity",
)

# Hyphen plus common dash characters that appear in copied hourly ranges.
_DASH_CHARS = "-" + "\u2013" + "\u2014"

_MONEY_RE = re.compile(
    r"\$\s*\d[\d,]*(?:\.\d{1,2})?"
    r"(?:\s*[" + re.escape(_DASH_CHARS) + r"]\s*\$?\s*\d[\d,]*(?:\.\d{1,2})?)?",
    re.I,
)

_URL_RE = re.compile(
    r"(https?://[^\s<>\"']*upwork\.com[^\s<>\"']*"
    r"|(?:www\.)?upwork\.com[^\s<>\"']*)",
    re.I,
)

# Job paths named in the brief. Other Upwork paths (proposals, messages) are rejected.
_JOB_PATH_RE = re.compile(
    r"(?i)^/jobs/"
    r"|^/freelance-jobs/apply/"
    r"|^/nx/search/jobs/details/"
)

_POSTED_RE = re.compile(r"^Posted\b", re.I)
_HOURLY_RE = re.compile(r"^Hourly\b", re.I)
_FIXED_RE = re.compile(r"^Fixed[-\s]?price\b", re.I)
_BUDGET_LABEL_RE = re.compile(
    r"^(?:Est\.?\s*budget|Budget|Client'?s\s+budget)\b",
    re.I,
)
_META_START_RE = re.compile(
    r"^(?:Hourly|Fixed[-\s]?price|Worldwide|Remote|"
    r"Entry\s+level|Entry|Intermediate|Expert|"
    r"Est\.?\s*budget|Budget|Client'?s\s+budget|"
    r"Location|Experience|Duration|Proposals)\b",
    re.I,
)


def _as_text(value):
    """Coerce input to a string. None and non-strings become ''."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _split_lines(text):
    return _as_text(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _clean_money(text):
    """Return a $amount or $x-$y range with a plain hyphen, or ''."""
    match = _MONEY_RE.search(text or "")
    if not match:
        return ""
    raw = re.sub(r"\s+", "", match.group(0))
    raw = raw.replace("\u2013", "-").replace("\u2014", "-")
    return raw


def _host_ok(host):
    host = (host or "").lower().rstrip(".")
    return host in ("upwork.com", "www.upwork.com")


def normalize_job_url(url):
    """Strip whitespace and tracking query strings from a job URL.

    A missing scheme on an upwork.com host is stored as https://.
    Fragments and tracking parameters (utm_*, fbclid, gclid and similar)
    are removed. Returns '' when the input is empty or cannot be cleaned.
    Never raises. Never fetches the URL.
    """
    try:
        raw = _as_text(url).strip()
        if not raw:
            return ""
        raw = raw.strip("<>\"'").rstrip(").,]}>\"'")
        if not raw:
            return ""
        if raw.lower().startswith("javascript:") or raw.lower().startswith("data:"):
            return raw
        if not re.match(r"^[a-z][a-z0-9+.-]*:", raw, re.I):
            if "upwork.com" in raw.lower():
                raw = "https://" + raw.lstrip("/")
            else:
                return ""
        parsed = urlparse(raw)
        kept = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            lower = key.lower()
            if lower.startswith("utm_") or lower in _TRACKING_KEYS:
                continue
            kept.append((key, value))
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path or "",
            parsed.params,
            urlencode(kept, doseq=True),
            "",
        ))
    except Exception:
        return ""


def is_valid_job_url(url):
    """Return True if url is an https Upwork job link.

    Accepted path shapes (host must be upwork.com or www.upwork.com):
        https://www.upwork.com/jobs/~01abc...
        https://www.upwork.com/freelance-jobs/apply/...~01...
        https://www.upwork.com/nx/search/jobs/details/~01...

    Other domains, http links, javascript: and data: links are rejected.
    Whitespace and tracking query strings are ignored (see normalize_job_url).
    Never raises. Never fetches the URL.
    """
    try:
        raw = _as_text(url).strip()
        if not raw:
            return False
        lower = raw.lower()
        if lower.startswith("javascript:") or lower.startswith("data:"):
            return False
        cleaned = normalize_job_url(raw)
        if not cleaned:
            return False
        parsed = urlparse(cleaned)
        if (parsed.scheme or "").lower() != "https":
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        if not _host_ok(parsed.hostname):
            return False
        path = parsed.path or ""
        return bool(_JOB_PATH_RE.search(path))
    except Exception:
        return False


def _extract_url(text):
    """Return the first valid Upwork job URL in text, or ''."""
    for line in _split_lines(text):
        if "upwork.com" not in line.lower():
            continue
        match = _URL_RE.search(line)
        raw = (match.group(1) if match else line).strip()
        cleaned = normalize_job_url(raw)
        if is_valid_job_url(cleaned):
            return cleaned
    return ""


def _is_chrome(line):
    low = (line or "").strip().lower().rstrip(":")
    return low in _CHROME


def _is_skills_header(line):
    low = (line or "").strip().lower()
    if low in ("skills", "skills:") or low.startswith("skills:"):
        return True
    if low == "skills and expertise" or low.startswith("skills and expertise"):
        return True
    return False


def _is_stop_heading(line):
    low = (line or "").strip().lower().rstrip(":")
    if _is_skills_header(line):
        return True
    return any(low == heading or low.startswith(heading) for heading in _STOP_HEADINGS)


def _is_meta_line(line):
    text = (line or "").strip()
    if not text:
        return True
    low = text.lower()
    if _POSTED_RE.match(text):
        return True
    if _META_START_RE.match(text):
        return True
    if "total price of project" in low:
        return True
    if _MONEY_RE.search(text) and len(text) <= 40:
        return True
    if _is_chrome(text):
        return True
    if "upwork.com" in low and _URL_RE.search(text):
        return True
    return False


def _first_budget(lines):
    """Return the first hourly range or fixed budget string, or ''."""
    pending_kind = ""
    for line in lines:
        text = line.strip()
        if not text:
            continue
        low = text.lower()
        if "total price of project" in low:
            continue
        money = _clean_money(text)
        if _HOURLY_RE.match(text):
            if money:
                return "Hourly: " + money
            pending_kind = "Hourly"
            continue
        if _FIXED_RE.match(text):
            if money:
                return "Fixed-price: " + money
            pending_kind = "Fixed-price"
            continue
        if _BUDGET_LABEL_RE.match(text) and money:
            if pending_kind:
                return pending_kind + ": " + money
            return money
        if money and (pending_kind or "budget" in low or len(text) <= 40):
            if pending_kind:
                return pending_kind + ": " + money
            return money
    return ""


def _pick_title(lines, url):
    """Return the first meaningful line, preferring the line above 'Posted'."""
    posted_idx = None
    for index, line in enumerate(lines):
        if _POSTED_RE.match(line.strip()):
            posted_idx = index
            break

    def usable(index, text):
        stripped = text.strip()
        if not stripped:
            return False
        if _is_chrome(stripped) or _is_meta_line(stripped):
            return False
        if url and stripped == url:
            return False
        return True

    if posted_idx is not None:
        for index in range(posted_idx - 1, -1, -1):
            if usable(index, lines[index]):
                return lines[index].strip()

    for index, line in enumerate(lines):
        if usable(index, line):
            return line.strip()
    return ""


def _skills_from(lines):
    """Return skill lines after the Skills header, up to the next section."""
    start = None
    inline = ""
    for index, line in enumerate(lines):
        if _is_skills_header(line):
            start = index
            heading = line.strip()
            inline = re.sub(
                r"(?i)^(?:skills and expertise|skills)\s*:?\s*",
                "",
                heading,
            ).strip()
            break
    if start is None:
        return []
    parts = [inline] if inline else []
    for line in lines[start + 1:]:
        if _is_stop_heading(line) and not _is_skills_header(line):
            break
        # A second skills header should not be kept as a skill name.
        if _is_skills_header(line):
            continue
        stripped = line.strip()
        if stripped:
            parts.append(stripped)
    return parts


def _description_from(lines, title, end_idx):
    """Return the main body, starting after the title and leading meta lines."""
    start_idx = 0
    posted_idx = None
    for index, line in enumerate(lines):
        if _POSTED_RE.match(line.strip()):
            posted_idx = index
            break
    if posted_idx is not None:
        start_idx = posted_idx + 1
    elif title:
        for index, line in enumerate(lines):
            if line.strip() == title:
                start_idx = index + 1
                break

    while start_idx < end_idx and _is_meta_line(lines[start_idx]):
        start_idx += 1

    body = lines[start_idx:end_idx]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if body and body[-1].strip().lower() in ("more", "see more", "read more"):
        body.pop()
    text = "\n".join(body).strip()
    if len(text) > DESCRIPTION_MAX_CHARS:
        text = text[:DESCRIPTION_MAX_CHARS]
    return text


def parse_job_text(text):
    """Best-effort parse of text copied from an Upwork job page.

    Always returns a dict with keys title, description, budget, skills and
    url. skills is a list of strings; the other values are strings. Missing
    fields are '' or []. The description is cut off at 20000 characters.

    If the paste is plain text with no job-page structure, the first line
    is the title and the rest is the description.

    Never raises. Never fetches a URL.
    """
    out = {
        "title": "",
        "description": "",
        "budget": "",
        "skills": [],
        "url": "",
    }
    try:
        raw = _as_text(text)
        lines = _split_lines(raw)
        out["url"] = _extract_url(raw)
        out["title"] = _pick_title(lines, out["url"])
        out["budget"] = _first_budget(lines)
        out["skills"] = _skills_from(lines)

        end_idx = len(lines)
        for index, line in enumerate(lines):
            if _is_skills_header(line) or (
                _is_stop_heading(line) and not _is_skills_header(line)
            ):
                end_idx = index
                break
        out["description"] = _description_from(lines, out["title"], end_idx)
    except Exception:
        pass
    return out
