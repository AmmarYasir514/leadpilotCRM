"""Write a proposal page: URL-based job fetch and AI proposal drafting.

Job details come from (1) Fetch Job Details via the CRM browser window-read
hook, (2) Paste from clipboard, or (3) manual typing. Generate / Draft Proposal
do not write database rows. Save Draft uses drafts_store.
Budget, Skills and Submitted proposal link are not shown or filled on this page.
"""

from __future__ import annotations

import queue
import re
import threading
from datetime import datetime
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk

# Emerald & White defaults for this page (caller may pass a matching ui dict).
UI = {
    "bg": "#FAFAF8",
    "card": "#FFFFFF",
    "line": "#E7ECE9",
    "text": "#17211F",
    "muted": "#718078",
    "side": "#FFFFFF",
    "side2": "#FAFAF8",
    "side_text": "#17211F",
    "accent": "#00866A",
    "accent2": "#005B4B",
    "mint": "#DDF5EC",
    "green": "#16A34A",
    "red": "#EF4444",
}

# Copied from leadpilot_crm.py (do not import that module from here).
def _norm_title(t):
    """Title key for duplicate matching: lower case, trimmed, single spaces, no trailing punctuation."""
    return re.sub(r"\s+", " ", (t or "")).strip().strip(" .-|").lower()


def _url_key(u):
    """Proposal/job key from an Upwork link (the long number or ~id), so different link formats still match."""
    m = re.search(r"(?:proposals/|~)(\w{10,})", u or "")
    return m.group(1).lower() if m else (u or "").strip().rstrip("/").lower() or None


# Headings that are page chrome, not a job title.
_CHROME_TITLES = {
    "find work", "job details", "job post", "search", "messages",
    "notifications", "saved jobs", "upwork", "home", "proposals",
}

# Section headings that end the description or the skills list.
_STOP_HEADINGS = (
    "skills and expertise",
    "about the client",
    "activity on this job",
    "preferred qualifications",
    "screening questions",
    "client's recent history",
    "proposal extras",
    "you will be asked",
    "job activity",
)

_DASH = "-" + chr(0x2013) + chr(0x2014)
_MONEY_RE = re.compile(
    r"\$\s*\d[\d,]*(?:\.\d{1,2})?(?:\s*[" + re.escape(_DASH) + r"]\s*\$?\s*\d[\d,]*(?:\.\d{1,2})?)?",
    re.I,
)
_URL_RE = re.compile(
    r"(https?://[^\s]*upwork\.com[^\s]*|(?:www\.)?upwork\.com[^\s]*)",
    re.I,
)

NO_URL_MESSAGE = (
    "I could not find an Upwork job link in what you pasted. "
    "Paste the job link together with the job post."
)
EMPTY_PASTE_MESSAGE = "Paste the job link and the job post first."
SUBMIT_OK_MESSAGE = "Saved. This job is now in Submitted Proposals."
PAGE_SUBTITLE = (
    "Paste an Upwork job URL, fetch the details, add instructions, "
    "generate a draft, then copy it to Upwork yourself."
)
PASTE_HINT = (
    "Paste the job link and the job post you copied from Upwork "
    "(Ctrl+A, then Ctrl+C in your browser)."
)
EMPTY_STATE_TEXT = "No drafts yet. Click New job to start."
SECTION_FIND_JOB = "Find an Upwork Job"
LABEL_JOB_URL = "Paste Upwork Job URL"
BTN_FETCH = "Fetch Job Details"
BTN_DRAFT = "Draft Proposal"
BTN_GENERATE = "Generate Proposal"
BTN_REGENERATE = "Regenerate Proposal"
BTN_SAVE_DRAFT = "Save Draft"
MSG_GENERATING = "Writing your proposal..."
MSG_REVISING = "Revising your draft..."
MSG_GEN_READY = "Draft ready. Review it, then Copy or Regenerate."
MSG_REV_READY = "Draft revised. Review it, then Copy."
_SPIN_FRAMES = ("|", "/", "-", "\\")
MSG_FETCHING = "Opening the job in your browser and reading the page..."
MSG_FETCH_FAIL = (
    "Could not read the job from your browser. Keep the Upwork job page open "
    "(and logged in), or copy it (Ctrl+A, Ctrl+C) and click Paste from clipboard."
)
MSG_FETCH_BAD_URL = "Paste a valid Upwork job URL first."
MSG_DRAFT_SAVED = "Draft saved on this computer."
MSG_DRAFT_SAVE_FAIL = "Could not save the draft. Try again."
MSG_RECORDING = "Recording... Click the mic again or press Stop when you finish."
MSG_TRANSCRIBING = "Turning your voice into text..."
MSG_VOICE_READY = "Click the mic to speak your instructions."
MSG_VOICE_OFF = "Voice not available"


def _store():
    import drafts_store
    return drafts_store


def _writer():
    import proposal_ui
    return proposal_ui


def _is_stop_heading(line):
    low = (line or "").strip().lower().rstrip(":")
    return any(low == h or low.startswith(h) for h in _STOP_HEADINGS)


def _clean_money(text):
    """Return a $ amount or $x-$y range with a plain hyphen, or empty."""
    m = _MONEY_RE.search(text or "")
    if not m:
        return ""
    raw = re.sub(r"\s+", "", m.group(0))
    for ch in _DASH[1:]:
        raw = raw.replace(ch, "-")
    return raw


def extract_job_url(text):
    """Return (url, line_index) from the first line that contains upwork.com.

    The URL is never fetched. A missing scheme is stored as https://.
    Returns ("", None) when no Upwork link is present.
    """
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(lines):
        if "upwork.com" not in line.lower():
            continue
        m = _URL_RE.search(line)
        raw = (m.group(1) if m else line).strip().rstrip(").,]}>\"'")
        if not raw:
            continue
        if not re.match(r"^https?://", raw, re.I):
            raw = "https://" + raw.lstrip("/")
        try:
            host = (urlparse(raw).hostname or "").lower().rstrip(".")
        except Exception:
            continue
        if host == "upwork.com" or host.endswith(".upwork.com"):
            return raw, i
    return "", None


def parse_job_text(text):
    """Best-effort parse of a pasted Upwork job (link plus page text).

    Always returns a dict with title, budget_text, skills, description and
    job_url as strings. Never raises. Never uses 'total price of project'
    as the budget.
    """
    out = {
        "title": "",
        "budget_text": "",
        "skills": "",
        "description": "",
        "job_url": "",
    }
    try:
        raw = text or ""
        lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        url, url_idx = extract_job_url(raw)
        out["job_url"] = url

        def _skip_line(i, s):
            if not s:
                return True
            if url_idx is not None and i == url_idx:
                return True
            if "upwork.com" in s.lower() and _URL_RE.search(s):
                return True
            if s.lower().rstrip(":") in _CHROME_TITLES:
                return True
            return False

        posted_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^Posted\b", line.strip(), re.I):
                posted_idx = i
                break

        if posted_idx is not None:
            for j in range(posted_idx - 1, -1, -1):
                s = lines[j].strip()
                if _skip_line(j, s):
                    continue
                out["title"] = s
                break

        if not out["title"]:
            for i, line in enumerate(lines):
                s = line.strip()
                if _skip_line(i, s):
                    continue
                if re.match(r"^Posted\b", s, re.I):
                    continue
                out["title"] = s
                break

        kind = ""
        money = ""
        client_budget = ""
        for line in lines:
            s = line.strip()
            if not s:
                continue
            low = s.lower()
            if "total price of project" in low:
                continue
            if low.startswith("client's budget:") or low.startswith("clients budget:"):
                rest = s.split(":", 1)[-1].strip()
                client_budget = _clean_money(rest) or rest
                continue
            if re.match(r"^Fixed[-\s]?price\b", s, re.I):
                kind = "Fixed-price"
                money = money or _clean_money(s)
                continue
            if re.match(r"^Hourly\b", s, re.I):
                kind = "Hourly"
                money = money or _clean_money(s)
                continue
            if _MONEY_RE.search(s) and ("budget" in low or len(s) <= 40):
                money = money or _clean_money(s)

        if client_budget and kind:
            out["budget_text"] = kind + ", " + client_budget
        elif client_budget:
            out["budget_text"] = client_budget
        elif kind and money:
            out["budget_text"] = kind + ", " + money
        else:
            out["budget_text"] = kind or money

        skills_idx = None
        about_idx = None
        for i, line in enumerate(lines):
            low = line.strip().lower().rstrip(":")
            if skills_idx is None and (low == "skills and expertise" or low.startswith("skills and expertise")):
                skills_idx = i
            if about_idx is None and (low == "about the client" or low.startswith("about the client")):
                about_idx = i

        if skills_idx is not None:
            heading = lines[skills_idx].strip()
            same = re.sub(r"(?i)^skills and expertise\s*:?\s*", "", heading).strip()
            parts = [same] if same else []
            for line in lines[skills_idx + 1:]:
                if _is_stop_heading(line) and not line.strip().lower().startswith("skills and expertise"):
                    break
                s = line.strip()
                if s:
                    parts.append(s)
            out["skills"] = ", ".join(parts)

        end_idx = len(lines)
        for i, line in enumerate(lines):
            if skills_idx is not None and i == skills_idx:
                end_idx = i
                break
            if about_idx is not None and i == about_idx:
                end_idx = i
                break

        start_idx = 0
        if posted_idx is not None:
            start_idx = posted_idx + 1
        elif out["title"]:
            for i, line in enumerate(lines):
                if line.strip() == out["title"]:
                    start_idx = i + 1
                    break

        def _is_meta(s):
            s = (s or "").strip()
            if not s:
                return True
            low = s.lower()
            if re.match(r"^(hourly|fixed[-\s]?price|worldwide|remote|entry level|entry|intermediate|expert)\b", s, re.I):
                return True
            if _MONEY_RE.search(s) and len(s) <= 40:
                return True
            if low.startswith("client's budget") or low.startswith("clients budget"):
                return True
            if "total price of project" in low:
                return True
            if url_idx is not None and s == lines[url_idx].strip():
                return True
            if s.lower().rstrip(":") in _CHROME_TITLES:
                return True
            if re.match(r"^(location|experience|duration|proposals)\s*:", s, re.I):
                return True
            return False

        while start_idx < end_idx and _is_meta(lines[start_idx]):
            start_idx += 1

        body_lines = lines[start_idx:end_idx]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        if body_lines and body_lines[-1].strip().lower() in ("more", "see more", "read more"):
            body_lines.pop()
        out["description"] = "\n".join(body_lines).strip()
    except Exception:
        pass
    return out


def format_job_text(draft):
    """Build the job text shown in the writer from the stored draft fields.

    Budget and skills are intentionally omitted on this page.
    """
    draft = draft or {}
    lines = []
    title = (draft.get("job_title") or "").strip()
    client = (draft.get("client") or "").strip()
    link = (draft.get("job_url") or "").strip()
    desc = (draft.get("job_text") or "").strip()
    if title:
        lines.append(title)
    if client:
        lines.append("Client: " + client)
    if link:
        lines.append("Link: " + link)
    if desc:
        if lines:
            lines.append("")
        lines.append(desc)
    return "\n".join(lines)


def _format_edited(stamp):
    """Show Last edited as '16 Nov 2026, 6:46 PM', or the raw stamp if unknown."""
    text = (stamp or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(text[:len(datetime.now().strftime(fmt))], fmt)
            return dt.strftime("%d %b %Y, %I:%M %p").lstrip("0").replace(" 0", " ")
        except ValueError:
            continue
    return text


def _ensure_styles(ui):
    """Configure Title/Sub styles only when the app has not already done so."""
    s = ttk.Style()
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    existing = ""
    try:
        existing = s.lookup("Title.TLabel", "font") or ""
    except tk.TclError:
        existing = ""
    if existing:
        return
    ui = ui or UI
    navy = "#14243A"
    muted = ui.get("muted", "#718096")
    bg = ui.get("bg", "#F5F7FB")
    s.configure("TFrame", background=bg)
    s.configure("TLabel", background=bg, foreground=ui.get("text", "#0F172A"), font=("Segoe UI", 9))
    s.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground=navy)
    s.configure("Sub.TLabel", foreground=muted, font=("Segoe UI", 9))
    s.configure("TButton", padding=(12, 7), font=("Segoe UI", 9, "bold"))
    accent = ui.get("accent", "#00866A")
    accent2 = ui.get("accent2", "#005B4B")
    s.configure("Accent.TButton", padding=(14, 8), background=accent,
                foreground="#FFFFFF", borderwidth=0, font=("Segoe UI", 9, "bold"))
    s.map("Accent.TButton", background=[("active", accent2), ("pressed", "#004739")],
          foreground=[("active", "#FFFFFF")])
    s.configure("Treeview", rowheight=38, font=("Segoe UI", 9),
                background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#343A40", borderwidth=0)
    s.configure("Treeview.Heading", background="#EEF2F7", foreground="#1E293B",
                font=("Segoe UI", 9, "bold"), padding=(10, 11), relief="flat", borderwidth=0)
    s.map("Treeview", background=[("selected", "#E0E7FF")])

# Swap point for job-text parsing (a job_text_parser module can replace this).
# parse_job_text() above is the single function to swap at merge.
_legacy_parse_job_text = parse_job_text


def parse_job_text(text):
    """Parse pasted job text. Prefer job_text_parser; fall back locally.

    Always returns title, description, budget, skills, and url, plus the
    older budget_text and job_url aliases. skills is a comma-separated
    string for the entry field. Never raises. Never fetches.
    """
    try:
        from job_text_parser import parse_job_text as _parse
        data = _parse(text) or {}
        skills = _skills_as_text(data.get("skills"))
        budget = (data.get("budget") or data.get("budget_text") or "") or ""
        url = (data.get("url") or data.get("job_url") or "") or ""
        return {
            "title": data.get("title") or "",
            "description": data.get("description") or "",
            "budget": budget,
            "skills": skills,
            "url": url,
            "budget_text": budget,
            "job_url": url,
        }
    except Exception:
        try:
            data = _legacy_parse_job_text(text) or {}
        except Exception:
            data = {}
        budget = (data.get("budget") or data.get("budget_text") or "") or ""
        url = (data.get("url") or data.get("job_url") or "") or ""
        return {
            "title": data.get("title") or "",
            "description": data.get("description") or "",
            "budget": budget,
            "skills": _skills_as_text(data.get("skills")),
            "url": url,
            "budget_text": budget,
            "job_url": url,
        }


def _skills_as_text(skills):
    if skills is None:
        return ""
    if isinstance(skills, (list, tuple)):
        return ", ".join(str(s).strip() for s in skills if str(s).strip())
    return str(skills).strip()


def _parsed_url(parsed):
    return ((parsed or {}).get("url") or (parsed or {}).get("job_url") or "").strip()


def _parsed_budget(parsed):
    return ((parsed or {}).get("budget") or (parsed or {}).get("budget_text") or "").strip()


def _parsed_skills(parsed):
    return _skills_as_text((parsed or {}).get("skills"))



PASTE_CLIP_TIP = (
    "Copy the job page in your browser with Ctrl+A and Ctrl+C, then click here."
)
MSG_PASTE_LINK = "Paste the job link from your browser's address bar."
MSG_LINK_ONLY = (
    "Now copy the job page (Ctrl+A, Ctrl+C) and click Paste from clipboard again."
)
MSG_EMPTY_CLIP = "The clipboard is empty. Copy the job page or the job link first."
MSG_NON_TEXT_CLIP = (
    "The clipboard does not have text I can paste. Copy the job page or the job link first."
)
MSG_BAD_LINK = (
    "The job link must be an Upwork job link starting with http:// or https://."
)
MSG_NEED_JOB = "Type or paste a job title or description first."
MSG_CREATE_FAILED = "The draft could not be saved. Try again."
INS_LINES = 4
DRAFT_LINES = 6
DRAFT_MIN_PX = 150
JOB_DESC_OPEN = 5
JOB_DESC_EXPANDED = 3
MSG_READING_WINDOW = "Reading the job from your Upwork window..."
MSG_WINDOW_READ_FAIL = (
    "Couldn't read the job from your Upwork window. "
    "Open the job page in your browser, or copy it (Ctrl+A, Ctrl+C) "
    "and click Paste from clipboard."
)
DRAFT_NOTE = "Review and edit the draft, then Copy it to Upwork. Use Save Draft to keep it here."
LEAVE_MESSAGE = (
    "Your draft is not saved. Copy it first or it will be lost. Leave anyway?"
)


def _legacy_validate_job_url(url):
    """Return (ok, cleaned_url_or_message). Never fetches."""
    raw = (url or "").strip()
    if not raw:
        return False, MSG_BAD_LINK
    if re.match(r"^(www\.)?upwork\.com", raw, re.I):
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except Exception:
        return False, MSG_BAD_LINK
    if (parsed.scheme or "").lower() not in ("http", "https"):
        return False, MSG_BAD_LINK
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in ("upwork.com", "www.upwork.com"):
        return False, MSG_BAD_LINK
    path = parsed.path or ""
    blob = path + " " + (parsed.query or "") + " " + raw
    if (
        path.startswith("/jobs/")
        or path.startswith("/nx/")
        or path.startswith("/freelance-jobs/")
        or "/jobs/" in path
        or re.search(r"~\w{8,}", blob)
    ):
        return True, raw
    return False, MSG_BAD_LINK


def validate_job_url(url):
    """Return (ok, cleaned_url_or_message). Never fetches.

    Uses job_text_parser when it is available. A parser failure never blocks
    typing: the local helper is used instead.
    """
    raw = (url or "").strip()
    if not raw:
        return False, MSG_BAD_LINK
    try:
        from job_text_parser import is_valid_job_url, normalize_job_url
        cleaned = normalize_job_url(raw) or raw
        if is_valid_job_url(cleaned) or is_valid_job_url(raw):
            return True, cleaned
    except Exception:
        pass
    try:
        return _legacy_validate_job_url(raw)
    except Exception:
        return False, MSG_BAD_LINK


def job_dict_to_text(job):
    """Build job_text for Generate from JobFields values."""
    job = job or {}
    return format_job_text({
        "job_title": job.get("title") or job.get("job_title") or "",
        "job_text": job.get("description") or job.get("job_text") or "",
        "job_url": job.get("url") or job.get("job_url") or "",
        "client": job.get("client") or "",
    })


def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


class _Tip:
    """Tiny tooltip. text may be a string or a callable."""

    def __init__(self, widget, text):
        self.widget = widget
        self._text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def text(self):
        return self._text() if callable(self._text) else str(self._text or "")

    def _show(self, event=None):
        if self.tip is not None:
            return
        txt = self.text()
        if not txt:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        tk.Label(tw, text=txt, bg="#111827", fg="#FFFFFF", font=("Segoe UI", 8),
                 padx=8, pady=4, wraplength=320, justify="left").pack()

    def _hide(self, event=None):
        tip, self.tip = self.tip, None
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass


class JobFields:
    """Reusable job section: link, paste, title, description.

    Budget, skills and submitted-link UI are not part of this page.
    Public API: get_values(), set_values(), validate(), paste_from_clipboard().
    """

    def __init__(self, parent, ui=None, on_change=None, parse_hook=None,
                 on_link_landed=None, on_fetch=None):
        self.ui = ui or UI
        self.on_change = on_change
        self.parse_hook = parse_hook
        self.on_link_landed = on_link_landed
        self.on_fetch = on_fetch
        self._client = ""
        self._typed = {"title": False, "description": False, "url": False}
        self._pending = None
        page_bg = self.ui.get("bg", "#FAFAF8")
        bg = self.ui.get("card", "#FFFFFF")
        fg = self.ui.get("text", "#17211F")
        muted = self.ui.get("muted", "#718078")
        line = self.ui.get("line", "#E7ECE9")
        self.outer = tk.Frame(parent, bg=page_bg)
        self.frame = tk.Frame(
            self.outer, bg=bg, highlightthickness=1, highlightbackground=line,
        )
        self.frame.pack(fill="x", padx=0, pady=0)
        inner = tk.Frame(self.frame, bg=bg)
        inner.pack(fill="x", padx=4, pady=10)
        self._inner = inner

        # Step 1: Find an Upwork Job
        tk.Label(
            inner, text=SECTION_FIND_JOB, bg=bg, fg=fg,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 6))
        row = tk.Frame(inner, bg=bg)
        row.pack(fill="x")
        tk.Label(
            row, text=LABEL_JOB_URL, bg=bg, fg=fg, font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        self.btn_paste_clip = ttk.Button(
            row, text="Paste from clipboard", command=self.paste_from_clipboard,
        )
        self.btn_paste_clip.pack(side="right")
        self._paste_tip = _Tip(self.btn_paste_clip, PASTE_CLIP_TIP)
        self.job_link_var = tk.StringVar()
        self.job_link_entry = ttk.Entry(inner, textvariable=self.job_link_var)
        self.job_link_entry.pack(fill="x", pady=(4, 6))
        self.job_link_entry.bind("<KeyRelease>", lambda e: self._mark("url"), add="+")
        self.job_link_entry.bind("<Return>", self._on_return_fetch, add="+")
        fetch_row = tk.Frame(inner, bg=bg)
        fetch_row.pack(fill="x", pady=(0, 8))
        self.btn_fetch = ttk.Button(
            fetch_row, text=BTN_FETCH, style="Accent.TButton",
            command=self._do_fetch,
        )
        self.btn_fetch.pack(side="left")
        tk.Label(
            fetch_row, text="or press Enter after pasting the URL",
            bg=bg, fg=muted, font=("Segoe UI", 8),
        ).pack(side="left", padx=(10, 0))

        # Manual paste fallback
        self.btn_fallback_toggle = ttk.Button(
            inner, text="Paste job text instead", command=self._toggle_fallback,
        )
        self.btn_fallback_toggle.pack(anchor="w", pady=(0, 4))
        self.fallback_frame = tk.Frame(inner, bg=bg)
        self.fallback_box = tk.Text(
            self.fallback_frame, height=6, wrap="word", font=("Segoe UI", 9),
            relief="solid", bd=1, padx=6, pady=4,
        )
        self.fallback_box.pack(fill="x")
        self.btn_fill_fields = ttk.Button(
            self.fallback_frame, text="Fill fields", command=self._fill_from_fallback,
        )
        self.btn_fill_fields.pack(anchor="e", pady=(4, 8))
        self._fallback_open = False

        # Job title (auto-filled or manual)
        tk.Label(inner, text="Job Title", bg=bg, fg=fg,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.job_title_var = tk.StringVar()
        self.job_title_entry = ttk.Entry(inner, textvariable=self.job_title_var,
                                         font=("Segoe UI", 10, "bold"))
        self.job_title_entry.pack(fill="x", pady=(2, 8))
        self.job_title_entry.bind("<KeyRelease>", lambda e: self._mark("title"), add="+")

        # Job description (auto-filled or manual)
        tk.Label(inner, text="Job Description", bg=bg, fg=fg,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.job_desc_box = tk.Text(
            inner, height=5, wrap="word", font=("Segoe UI", 10),
            relief="solid", bd=1, padx=8, pady=6, undo=True,
        )
        self.job_desc_box.pack(fill="both", expand=True, pady=(2, 8))
        self.job_desc_box.bind("<KeyRelease>", lambda e: self._mark("description"), add="+")

        # Budget / Skills kept as empty stubs only (no UI, never filled from fetch).
        self.optional = None
        self.budget_var = tk.StringVar(value="")
        self.skills_var = tk.StringVar(value="")
        self.budget_entry = None
        self.skills_entry = None

        # Inline message + overwrite actions
        self.message_var = tk.StringVar()
        self.message_label = tk.Label(
            inner, textvariable=self.message_var, bg=bg, fg="#DC2626",
            font=("Segoe UI", 9), wraplength=640, justify="left", anchor="w",
        )
        self.message_label.pack(fill="x", pady=(0, 2))
        self.overwrite_row = tk.Frame(inner, bg=bg)
        ttk.Button(self.overwrite_row, text="Replace", command=self._overwrite_yes).pack(side="left", padx=(0, 6))
        ttk.Button(self.overwrite_row, text="Keep", command=self._overwrite_no).pack(side="left")

        for var in (self.job_link_var, self.job_title_var):
            var.trace_add("write", lambda *a: self._fire_change())
        try:
            self.job_desc_box.bind("<<Modified>>", lambda e: self._fire_change(), add="+")
        except tk.TclError:
            pass

    def pack(self, **kw):
        """Pack the outer card so callers can treat JobFields like a Frame."""
        return self.outer.pack(**kw)

    def _do_fetch(self):
        if callable(self.on_fetch):
            try:
                self.on_fetch()
            except Exception:
                pass

    def _on_return_fetch(self, event=None):
        self._do_fetch()
        return "break"

    def _fire_change(self):
        if callable(self.on_change):
            try:
                self.on_change()
            except Exception:
                pass

    def _mark(self, key):
        self._typed[key] = True
        self._fire_change()

    def set_message(self, text, kind="error"):
        self.message_var.set(text or "")
        color = "#047857" if kind == "ok" else (
            self.ui.get("muted", "#718078") if kind == "info" else "#DC2626"
        )
        if kind == "busy":
            color = self.ui.get("accent", "#00866A")
        try:
            self.message_label.configure(fg=color)
        except tk.TclError:
            pass

    def get_values(self):
        desc = ""
        try:
            desc = self.job_desc_box.get("1.0", "end-1c")
        except tk.TclError:
            pass
        return {
            "title": self.job_title_var.get().strip(),
            "description": desc.strip(),
            "url": self.job_link_var.get().strip(),
            "budget": "",
            "skills": "",
            "client": self._client,
        }

    def set_values(self, job, mark_typed=False):
        job = job or {}
        self.job_title_var.set(job.get("title") or job.get("job_title") or "")
        self.job_link_var.set(job.get("url") or job.get("job_url") or "")
        self.budget_var.set("")
        self.skills_var.set("")
        if "client" in job:
            self._client = (job.get("client") or "").strip()
        desc = job.get("description") or job.get("job_text") or job.get("summary") or ""
        try:
            self.job_desc_box.delete("1.0", "end")
            if desc:
                self.job_desc_box.insert("1.0", desc)
        except tk.TclError:
            pass
        if not mark_typed:
            for k in self._typed:
                self._typed[k] = False
        self._fire_change()

    def clear(self):
        self._client = ""
        self.set_values({})
        self.set_message("")
        self._hide_overwrite()
        if self._fallback_open:
            self._toggle_fallback()
        try:
            self.fallback_box.delete("1.0", "end")
        except tk.TclError:
            pass

    def validate(self, require_content=True):
        vals = self.get_values()
        url = vals["url"]
        if url:
            ok, msg = validate_job_url(url)
            if not ok:
                return False, msg
            vals["url"] = msg
        if require_content and not (vals["title"] or vals["description"]):
            return False, MSG_NEED_JOB
        return True, vals

    def paste_from_clipboard(self):
        """Read Tk clipboard_get only. Never sends keystrokes or opens windows."""
        self._hide_overwrite()
        try:
            raw = self.frame.winfo_toplevel().clipboard_get()
        except tk.TclError:
            self.set_message(MSG_EMPTY_CLIP)
            return
        if not isinstance(raw, str):
            self.set_message(MSG_NON_TEXT_CLIP)
            return
        if not raw.strip():
            self.set_message(MSG_EMPTY_CLIP)
            return
        self._apply_paste(raw)
        if callable(self.on_link_landed):
            try:
                self.on_link_landed()
            except Exception:
                pass

    def _merge_parsed(self, raw):
        """Fill from parse_hook first, then job_text_parser for empty fields."""
        hook_data = {}
        hook = self.parse_hook
        if callable(hook):
            try:
                hook_data = hook(raw) or {}
            except Exception:
                hook_data = {}
        if not isinstance(hook_data, dict):
            hook_data = {}
        try:
            parsed = parse_job_text(raw) or {}
        except Exception:
            parsed = {}
        title = (hook_data.get("job") or hook_data.get("title") or "").strip() or (parsed.get("title") or "")
        desc = (hook_data.get("summary") or hook_data.get("description") or "").strip() or (parsed.get("description") or "")
        url = (hook_data.get("url") or hook_data.get("job_url") or "").strip() or _parsed_url(parsed)
        client = (hook_data.get("client") or "").strip()
        return {
            "title": title,
            "description": desc,
            "budget": "",
            "budget_text": "",
            "skills": "",
            "url": url,
            "job_url": url,
            "client": client,
        }

    def fill_from_text(self, raw, only_empty=True):
        """Parse pasted or window-read text and fill empty fields."""
        parsed = self._merge_parsed(raw)
        url = (parsed.get("url") or "").strip()
        if url:
            ok, cleaned = validate_job_url(url)
            if ok:
                url = cleaned
        if parsed.get("client") and not self._client:
            self._client = parsed["client"]
        self._fill_parsed(parsed, url=url, only_empty=only_empty)

    def _apply_paste(self, raw, force=False):
        parsed = self._merge_parsed(raw)
        url = (parsed.get("url") or parsed.get("job_url") or "").strip()
        if url:
            ok, cleaned = validate_job_url(url)
            if ok:
                url = cleaned
        if parsed.get("client") and (force or not self._client):
            self._client = parsed["client"]
        conflicts = []
        if not force:
            cur = self.get_values()
            mapping = [
                ("url", url, cur["url"]),
                ("title", parsed.get("title") or "", cur["title"]),
                ("description", parsed.get("description") or "", cur["description"]),
            ]
            for key, new, old in mapping:
                if self._typed.get(key) and old and new and old != new:
                    conflicts.append(key)
        if conflicts and not force:
            self._pending = raw
            self.set_message("Replace the text you already typed?")
            if not self.overwrite_row.winfo_manager():
                self.overwrite_row.pack(anchor="w", pady=(0, 4))
            return
        if not url:
            self.set_message(MSG_PASTE_LINK)
            try:
                self.job_link_entry.focus_set()
            except tk.TclError:
                pass
            # still fill any other parsed bits into empty fields
            self._fill_parsed(parsed, url="", only_empty=True)
            return
        only_link = not (parsed.get("title") or "").strip() and not (parsed.get("description") or "").strip()
        self._fill_parsed(parsed, url=url, only_empty=not force)
        if only_link:
            self.set_message(MSG_LINK_ONLY, "info")
        else:
            self.set_message("")
        self._fire_change()

    def _fill_parsed(self, parsed, url, only_empty=True):
        def put_var(var, value, key):
            if not value:
                return
            if only_empty and var.get().strip() and self._typed.get(key):
                return
            if only_empty and var.get().strip() and not self._typed.get(key) and key != "url":
                # fill empty only; leave a typed-or-filled value
                if var.get().strip():
                    return
            if only_empty and var.get().strip() and key != "url":
                return
            var.set(value)

        if url and (not only_empty or not self.job_link_var.get().strip() or not self._typed.get("url")):
            if not (only_empty and self.job_link_var.get().strip() and self._typed.get("url")):
                if not (only_empty and self.job_link_var.get().strip()):
                    self.job_link_var.set(url)
                elif not self._typed.get("url"):
                    self.job_link_var.set(url)
        if url and not self.job_link_var.get().strip():
            self.job_link_var.set(url)
        put_var(self.job_title_var, (parsed.get("title") or "").strip(), "title")
        desc = (parsed.get("description") or "").strip()
        if desc:
            cur = self.job_desc_box.get("1.0", "end-1c").strip()
            if not only_empty or not cur:
                self.job_desc_box.delete("1.0", "end")
                self.job_desc_box.insert("1.0", desc)
        # Never fill budget/skills on this page.
        self.budget_var.set("")
        self.skills_var.set("")

    def _overwrite_yes(self):
        raw, self._pending = self._pending, None
        self._hide_overwrite()
        if raw:
            self._apply_paste(raw, force=True)

    def _overwrite_no(self):
        raw, self._pending = self._pending, None
        self._hide_overwrite()
        if raw:
            self._apply_paste(raw, force=False)
            # force=False with conflicts would loop; fill empty only
            parsed = self._merge_parsed(raw)
            url = (parsed.get("url") or parsed.get("job_url") or "").strip()
            if url:
                ok, cleaned = validate_job_url(url)
                if ok:
                    url = cleaned
            self._fill_parsed(parsed, url=url, only_empty=True)
            self.set_message("")
            self._sync_optional()

    def _hide_overwrite(self):
        if self.overwrite_row.winfo_manager():
            self.overwrite_row.pack_forget()

    def _toggle_fallback(self):
        self._fallback_open = not self._fallback_open
        if self._fallback_open:
            self.fallback_frame.pack(fill="x", pady=(0, 6), after=self.btn_fallback_toggle)
            self.btn_fallback_toggle.configure(text="Hide paste box")
            try:
                self.fallback_box.focus_set()
            except tk.TclError:
                pass
        else:
            self.fallback_frame.pack_forget()
            self.btn_fallback_toggle.configure(text="Paste job text instead")

    def _fill_from_fallback(self):
        raw = self.fallback_box.get("1.0", "end-1c")
        if not (raw or "").strip():
            self.set_message("Paste the job text into the box first.")
            return
        self._apply_paste(raw)

    def _sync_optional(self):
        """No-op: Budget and Skills UI were removed from this page."""
        self.budget_var.set("")
        self.skills_var.set("")


def _normalize_any_url(url):
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        from job_text_parser import normalize_job_url
        cleaned = normalize_job_url(raw) or raw
    except Exception:
        cleaned = raw
    return cleaned





def _ask_leave(parent):
    """Ask whether to leave an unsaved draft. Go back is the default.

    Enter, Esc and the window close button all mean Go back (return False).
    Leave returns True. Never raises.
    """
    result = {"leave": False}
    try:
        win = tk.Toplevel(parent)
    except Exception:
        return False
    win.title("Unsaved draft")
    try:
        win.transient(parent)
    except tk.TclError:
        pass
    win.resizable(False, False)
    bg = "#F5F7FB"
    win.configure(bg=bg)
    tk.Label(
        win, text=LEAVE_MESSAGE, bg=bg, fg="#0F172A",
        font=("Segoe UI", 9), wraplength=420, justify="left", anchor="w",
    ).pack(fill="x", padx=16, pady=(16, 12))
    row = tk.Frame(win, bg=bg)
    row.pack(fill="x", padx=16, pady=(0, 14))

    def go_back(event=None):
        result["leave"] = False
        try:
            win.destroy()
        except tk.TclError:
            pass
        return "break"

    def leave(event=None):
        result["leave"] = True
        try:
            win.destroy()
        except tk.TclError:
            pass
        return "break"

    btn_leave = ttk.Button(row, text="Leave", command=leave)
    btn_leave.pack(side="right")
    btn_back = ttk.Button(row, text="Go back", command=go_back)
    btn_back.pack(side="right", padx=(0, 8))
    win.protocol("WM_DELETE_WINDOW", go_back)
    win.bind("<Return>", go_back)
    win.bind("<Escape>", go_back)
    try:
        btn_back.focus_set()
    except tk.TclError:
        pass
    try:
        win.grab_set()
    except tk.TclError:
        pass
    try:
        win.wait_window()
    except tk.TclError:
        pass
    return bool(result["leave"])


def build_page(parent, ui, get_conn, on_open_settings=None, on_submitted=None,
               parse_hook=None, window_read_hook=None, fetch_job_hook=None):
    """Build the Write a proposal page and return a WritePage.

    get_conn() must return an open sqlite3 connection the caller owns.
    This page never closes that connection and never opens the live database
    on its own. parse_hook, if given, is called with clipboard text on
    Paste from clipboard (see WritePage). window_read_hook, if given, is
    called with a job URL when the title is still empty (see WritePage).
    fetch_job_hook(url, on_done), if given, opens the job URL and reads it
    asynchronously; on_done(text, error) runs on the UI thread.
    """
    try:
        _store().ensure_table(get_conn())
    except Exception:
        pass
    return WritePage(parent, ui, get_conn, on_open_settings, on_submitted,
                     parse_hook=parse_hook, window_read_hook=window_read_hook,
                     fetch_job_hook=fetch_job_hook)


class _ScrollBody(tk.Frame):
    """Vertical scroll region so the one-screen page is never clipped."""

    def __init__(self, parent, bg):
        tk.Frame.__init__(self, parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self._bind_wheel(self)

    def _on_inner(self, event=None):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass

    def _on_canvas(self, event):
        try:
            self.canvas.itemconfigure(self._win, width=event.width)
        except tk.TclError:
            pass

    def rebind(self):
        self._walk_bind(self)

    def _bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._on_wheel, add="+")
        widget.bind("<Button-4>", self._on_wheel, add="+")
        widget.bind("<Button-5>", self._on_wheel, add="+")

    def _walk_bind(self, widget):
        self._bind_wheel(widget)
        try:
            for child in widget.winfo_children():
                self._walk_bind(child)
        except tk.TclError:
            pass

    def _on_wheel(self, event):
        try:
            if getattr(event, "num", None) == 4 or int(getattr(event, "delta", 0) or 0) > 0:
                self.canvas.yview_scroll(-1, "units")
            else:
                self.canvas.yview_scroll(1, "units")
        except tk.TclError:
            pass
        return "break"


class WritePage:
    """One-screen Write a proposal page, embedded in the CRM page frame."""

    def __init__(self, parent, ui, get_conn, on_open_settings=None,
                 on_submitted=None, parse_hook=None, window_read_hook=None,
                 fetch_job_hook=None):
        self.ui = ui or UI
        self.get_conn = get_conn
        self.on_open_settings = on_open_settings
        self.on_submitted = on_submitted
        self.parse_hook = parse_hook
        self.window_read_hook = window_read_hook
        self.fetch_job_hook = fetch_job_hook
        self._window_read_tried = set()
        self._unsaved_draft = False
        self._draft_id = None
        self._fetching = False
        self.busy = False
        self._expanded = False
        self.recorder = None
        self._timer_id = None
        self._voice_err_shown = False
        self._templates = []
        self.template_names = []
        self.client = ""
        self._q = queue.Queue()
        self._poll_id = None
        self._bg_kind = None
        self._spin_id = None
        self._spin_i = 0
        self._gen_progress_on = False
        self.voice_ok = False
        self.voice_msg = ""
        bg = self.ui.get("bg", "#FAFAF8")
        fg = self.ui.get("text", "#17211F")
        muted = self.ui.get("muted", "#718078")
        _ensure_styles(self.ui)
        self._probe_voice()

        self.frame = tk.Frame(parent, bg=bg)
        self._scroll = _ScrollBody(self.frame, bg)
        self._scroll.pack(fill="both", expand=True)
        body = self._scroll.inner
        self.body = body
        # Tk 8.6+ exposes Misc.busy as tk_busy_hold; tests read .busy as a flag.
        self.frame.busy = False
        self.body.busy = False
        self.frame.bind("<Map>", lambda e: self._on_page_mapped(), add="+")

        ttk.Label(
            body, text="Write a proposal", style="Title.TLabel", background=bg,
            anchor="w",
        ).pack(fill="x", pady=(0, 2))
        tk.Label(
            body, text=PAGE_SUBTITLE, bg=bg, fg=muted,
            font=("Segoe UI", 9), anchor="w", wraplength=720, justify="left",
        ).pack(fill="x", pady=(0, 10))

        self.job_fields = JobFields(
            body, ui=self.ui, parse_hook=self._call_parse_hook,
            on_link_landed=self._schedule_window_read,
            on_fetch=self._on_fetch_job,
            on_change=self._update_draft_btn,
        )
        self.job_fields.pack(fill="x", padx=16, pady=(0, 4))
        try:
            self.win = self.frame.winfo_toplevel()
        except tk.TclError:
            self.win = parent
        self.writer = self
        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(
            body, textvariable=self.status_var, bg=bg,
            fg="#DC2626", font=("Segoe UI", 9), wraplength=720, justify="left",
            anchor="w",
        )
        self.job_link_entry = self.job_fields.job_link_entry
        self.btn_paste_clip = self.job_fields.btn_paste_clip
        self.btn_fetch = self.job_fields.btn_fetch
        self.job_title_entry = self.job_fields.job_title_entry
        self.job_desc_box = self.job_fields.job_desc_box
        self.budget_entry = self.job_fields.budget_entry
        self.skills_entry = self.job_fields.skills_entry
        self.btn_fallback_toggle = self.job_fields.btn_fallback_toggle
        self.message_var = self.job_fields.message_var
        self.message_label = self.job_fields.message_label
        self.job_link_entry.bind("<<Paste>>", self._schedule_window_read_paste, add="+")
        # Enter is handled by JobFields → Fetch. FocusOut still tries a quiet window read.
        self.job_link_entry.bind("<FocusOut>", self._schedule_window_read, add="+")

        self.btn_create_proposal = ttk.Button(
            body, text=BTN_DRAFT, style="Accent.TButton",
            command=self._on_create_proposal,
        )
        self.btn_create_proposal.pack(anchor="w", padx=16, pady=(8, 10))
        self._update_draft_btn()

        self.writer_frame = tk.Frame(body, bg=bg)
        self._build_writer(self.writer_frame)
        self._scroll.rebind()

    def _call_parse_hook(self, text):
        hook = self.parse_hook
        if not callable(hook):
            return None
        try:
            return hook(text)
        except Exception:
            return None

    def _build_writer(self, parent):
        bg = self.ui.get("bg", "#FAFAF8")
        fg = self.ui.get("text", "#17211F")
        muted = self.ui.get("muted", "#718078")
        card = self.ui.get("card", "#FFFFFF")
        line = self.ui.get("line", "#E7ECE9")
        mint = self.ui.get("mint", "#DDF5EC")
        accent = self.ui.get("accent", "#00866A")

        # ---- Custom Instructions panel
        ins_card = tk.Frame(parent, bg=card, highlightthickness=1, highlightbackground=line)
        ins_card.pack(fill="x", pady=(0, 10))
        ins_inner = tk.Frame(ins_card, bg=card)
        ins_inner.pack(fill="x", padx=4, pady=10)
        ih = tk.Frame(ins_inner, bg=card)
        ih.pack(fill="x", pady=(0, 2))
        tk.Label(
            ih, text="Custom Instructions", bg=card, fg=fg,
            font=("Segoe UI", 12, "bold"), anchor="w",
        ).pack(side="left")
        try:
            from proposal_ui import MicButton, Tooltip
            self.btn_mic = MicButton(ih, command=self.toggle_recording, bg=card)
            self._mic_tip = Tooltip(self.btn_mic, self._mic_tip_text)
        except Exception:
            self.btn_mic = ttk.Button(ih, text="Mic", command=self.toggle_recording)
            self._mic_tip = None
        self.elapsed_var = tk.StringVar(value="")
        self.elapsed_label = tk.Label(
            ih, textvariable=self.elapsed_var, bg=card, fg=muted,
            font=("Segoe UI", 9), width=12, anchor="e",
        )
        self.stop_label = tk.Label(
            ih, text="", bg=card, fg=accent,
            font=("Segoe UI", 9, "bold"), width=5, cursor="hand2",
        )
        self.stop_label.bind("<Button-1>", lambda e: self.stop_recording())
        self.voice_note = tk.Label(
            ih, text="" if self.voice_ok else MSG_VOICE_OFF, bg=card,
            fg=muted, font=("Segoe UI", 8),
        )
        self.btn_mic.pack(side="right")
        self.stop_label.pack(side="right", padx=(0, 8))
        self.elapsed_label.pack(side="right", padx=(0, 4))
        self.voice_note.pack(side="right", padx=(0, 6))
        if not self.voice_ok:
            try:
                self.btn_mic.state(["disabled"])
            except Exception:
                pass
        tk.Label(
            ins_inner,
            text="Type or speak what this proposal should focus on for this job.",
            bg=card, fg=muted, font=("Segoe UI", 8), anchor="w",
        ).pack(fill="x", pady=(0, 4))
        self.ins_box = tk.Text(
            ins_inner, height=max(INS_LINES, 5), wrap="word", font=("Segoe UI", 10),
            relief="solid", bd=1, padx=8, pady=6, undo=True,
        )
        self.ins_box.pack(fill="x")
        self.ins_box.bind("<Escape>", self._on_escape, add="+")
        self.frame.bind("<Escape>", self._on_escape, add="+")

        self.voice_status_var = tk.StringVar(value="")
        self.voice_status_label = tk.Label(
            ins_inner, textvariable=self.voice_status_var, bg=card, fg=accent,
            font=("Segoe UI", 9), wraplength=680, justify="left", anchor="w",
        )
        self.voice_err_var = tk.StringVar(value="")
        self.voice_err_label = tk.Label(
            ins_inner, textvariable=self.voice_err_var, bg=card, fg="#DC2626",
            font=("Segoe UI", 9), wraplength=680, justify="left", anchor="w",
        )

        # ---- Proposal Templates panel
        tpl_card = tk.Frame(parent, bg=card, highlightthickness=1, highlightbackground=line)
        tpl_card.pack(fill="x", pady=(0, 10))
        tpl_inner = tk.Frame(tpl_card, bg=card)
        tpl_inner.pack(fill="x", padx=4, pady=10)
        tk.Label(
            tpl_inner, text="Proposal Templates", bg=card, fg=fg,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            tpl_inner, text="Pick a saved template. Edit templates in Settings.",
            bg=card, fg=muted, font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 6))
        trow = tk.Frame(tpl_inner, bg=mint, highlightthickness=1, highlightbackground=line)
        trow.pack(fill="x", pady=(0, 2))
        tk.Label(trow, text="Template", bg=mint, fg=fg,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(10, 0), pady=8)
        self.template_var = tk.StringVar()
        self.template_box = ttk.Combobox(
            trow, textvariable=self.template_var, state="readonly",
        )
        self.template_box.pack(side="left", fill="x", expand=True, padx=(8, 10), pady=8)
        self.template_box.bind("<<ComboboxSelected>>", self._on_template_change)
        self._reload_templates()

        # ---- Generate
        ar = tk.Frame(parent, bg=bg)
        ar.pack(fill="x", pady=(4, 0))
        self.btn_generate = ttk.Button(
            ar, text=BTN_GENERATE, style="Accent.TButton",
            command=self._on_generate,
        )
        self.btn_generate.pack(side="left")
        self.gen_spin_var = tk.StringVar(value="")
        self.gen_spin_label = tk.Label(
            ar, textvariable=self.gen_spin_var, bg=bg, fg=accent,
            font=("Segoe UI", 12, "bold"), width=2, anchor="center",
        )
        self.gen_spin_label.pack(side="left", padx=(10, 2))
        self.gen_status_var = tk.StringVar(value="")
        self.gen_status_label = tk.Label(
            ar, textvariable=self.gen_status_var, bg=bg, fg=accent,
            font=("Segoe UI", 9), anchor="w",
        )
        self.gen_status_label.pack(side="left", fill="x", expand=True)

        tk.Label(
            parent, text="Draft", bg=bg, fg=fg,
            font=("Segoe UI", 12, "bold"), anchor="w",
        ).pack(fill="x", pady=(10, 2))
        self.draft_wrap = tk.Frame(parent, bg=bg, height=DRAFT_MIN_PX)
        self.draft_box = tk.Text(
            self.draft_wrap, height=DRAFT_LINES, wrap="word", bg=card, fg=fg,
            relief="solid", bd=1, font=("Segoe UI", 10), padx=12, pady=8,
            undo=True,
        )
        self.draft_wrap.pack(fill="both", expand=True)
        self.draft_wrap.pack_propagate(False)
        self.draft_box.pack(fill="both", expand=True)
        self.draft_box.bind("<<Modified>>", self._on_draft_modified, add="+")
        self.draft_note = tk.Label(
            parent, text=DRAFT_NOTE, bg=bg, fg=muted,
            font=("Segoe UI", 8), anchor="w", justify="left",
        )
        self.draft_note.pack(fill="x", pady=(2, 0))

        self.copy_row = tk.Frame(parent, bg=bg)
        self.copy_row.pack(fill="x", pady=(6, 2))
        self.btn_copy = ttk.Button(self.copy_row, text="Copy", command=self._on_copy)
        self.btn_copy.pack(side="left")
        self.btn_revise = ttk.Button(
            self.copy_row, text=BTN_REGENERATE,
            command=lambda: self._on_generate(revise=True),
        )
        self.btn_revise.pack(side="left", padx=(6, 0))
        self.btn_save_draft = ttk.Button(
            self.copy_row, text=BTN_SAVE_DRAFT, command=self._on_save_draft,
        )
        self.btn_save_draft.pack(side="left", padx=(6, 0))
        # Same spinner/status as Generate row (shared StringVars).
        tk.Label(
            self.copy_row, textvariable=self.gen_spin_var, bg=bg, fg=accent,
            font=("Segoe UI", 12, "bold"), width=2, anchor="center",
        ).pack(side="left", padx=(10, 2))
        tk.Label(
            self.copy_row, textvariable=self.gen_status_var, bg=bg, fg=accent,
            font=("Segoe UI", 9), anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Submitted proposal link removed from this page (stubs for older callers).
        self.link_row = None
        self.url_var = tk.StringVar(value="")
        self.url_entry = None
        self.btn_save_link = None

    def _reload_templates(self):
        names = []
        default = ""
        templates = []
        try:
            import settings_store as ss
            cfg = ss.load_config() if hasattr(ss, "load_config") else None
            raw = ss.get_templates(cfg) if hasattr(ss, "get_templates") else None
            if raw:
                templates = list(raw)
            last = None
            if hasattr(ss, "get_last_template"):
                last = ss.get_last_template(cfg)
            if isinstance(last, dict):
                default = last.get("name") or ""
            elif last:
                default = str(last)
        except Exception:
            templates = []
        if not templates:
            templates = [{"name": "Standard", "text": ""}]
        self._templates = templates
        names = [t.get("name") or "" for t in templates if t.get("name")]
        self.template_names = names
        if default not in names:
            default = names[0] if names else ""
        try:
            self.template_box.configure(values=names)
        except tk.TclError:
            pass
        self.template_var.set(default)

    def set_template(self, name):
        if name and name in self.template_names:
            self.template_var.set(name)
            self._on_template_change()
            return True
        return False

    def _on_template_change(self, event=None):
        name = (self.template_var.get() or "").strip()
        if not name:
            return
        try:
            import settings_store as ss
            if hasattr(ss, "set_last_template"):
                ss.set_last_template(name)
        except Exception:
            pass

    def _current_template_text(self):
        name = (self.template_var.get() or "").strip()
        for item in self._templates:
            if (item.get("name") or "") == name:
                return item.get("text") or ""
        return ""

    def refresh(self):
        """Keep the current fields and expanded state (used on page switch)."""
        self._refresh_voice()
        self._on_page_mapped()
        if self._expanded:
            self._show_writer()

    def _on_page_mapped(self, event=None):
        sc = getattr(self, "_scroll", None)
        if sc is None:
            return
        try:
            try:
                sc.canvas.delete(sc._win)
            except Exception:
                pass
            sc._win = sc.canvas.create_window((0, 0), window=sc.inner, anchor="nw")
            sc.canvas.update_idletasks()
            width = int(sc.canvas.winfo_width() or 0)
            if width > 1:
                sc.canvas.itemconfigure(sc._win, width=width)
            sc.canvas.configure(scrollregion=sc.canvas.bbox("all"))
        except Exception:
            pass

    def _set_busy(self, on):
        flag = bool(on)
        self.busy = flag
        for obj in (getattr(self, "frame", None), getattr(self, "body", None)):
            if obj is not None:
                try:
                    obj.busy = flag
                except Exception:
                    pass
        self._refresh_action_buttons()

    def _refresh_action_buttons(self):
        """Disable Generate / Regenerate / Save while background work runs."""
        free = not self.busy
        for btn in (
            getattr(self, "btn_generate", None),
            getattr(self, "btn_revise", None),
            getattr(self, "btn_save_draft", None),
            getattr(self, "btn_copy", None),
        ):
            if btn is None:
                continue
            try:
                btn.state(["!disabled"] if free else ["disabled"])
            except Exception:
                pass
        mic = getattr(self, "btn_mic", None)
        if mic is not None and self.recorder is None:
            try:
                if free and self.voice_ok:
                    mic.state(["!disabled"])
                else:
                    mic.state(["disabled"])
            except Exception:
                pass

    def new_draft(self):
        """Reset to an empty job section. Function name stays new_draft()."""
        if not self.confirm_leave():
            return
        self._reset_page()

    def has_unsaved_draft(self):
        if self._unsaved_draft:
            try:
                if (self.draft_box.get("1.0", "end-1c") or "").strip():
                    return True
            except Exception:
                return True
        dlg = getattr(self, "_writer_dlg", None)
        fn = getattr(dlg, "has_unsaved_draft", None) if dlg is not None else None
        if callable(fn):
            try:
                if fn():
                    return True
            except Exception:
                pass
        return False

    def confirm_leave(self):
        if not self.has_unsaved_draft():
            return True
        try:
            parent = self.frame.winfo_toplevel()
        except tk.TclError:
            parent = self.frame
        return bool(_ask_leave(parent))

    def _update_draft_btn(self):
        """Refresh Fetch/Draft control states. Draft Proposal stays clickable so
        empty clicks still show the validation message; Fetch disables while busy."""
        fetch = getattr(self, "btn_fetch", None)
        if fetch is not None:
            try:
                fetch.configure(state=("disabled" if self._fetching or self.busy else "normal"))
            except tk.TclError:
                pass
        btn = getattr(self, "btn_create_proposal", None)
        if btn is not None:
            try:
                btn.configure(state=("disabled" if self._fetching else "normal"))
            except tk.TclError:
                pass

    def _on_create_proposal(self):
        ok, result = self.job_fields.validate(require_content=True)
        if not ok:
            self.job_fields.set_message(result)
            return
        self.job_fields.set_message("")
        self.client = result.get("client") or self.job_fields.get_values().get("client") or self.client
        self._show_writer()

    def _on_fetch_job(self):
        """Validate URL, then fetch via CRM hook (open browser + window read)."""
        if self._fetching or self.busy:
            return
        url = (self.job_fields.get_values().get("url") or "").strip()
        ok, cleaned = validate_job_url(url)
        if not ok:
            self.job_fields.set_message(cleaned if url else MSG_FETCH_BAD_URL)
            return
        self.job_fields.job_link_var.set(cleaned)
        self._fetching = True
        self._update_draft_btn()
        self.job_fields.set_message(MSG_FETCHING, "busy")

        def done(text, err=None):
            self._fetching = False
            self._update_draft_btn()
            if text and str(text).strip():
                self.job_fields.fill_from_text(str(text), only_empty=False)
                vals = self.job_fields.get_values()
                if (vals.get("title") or "").strip() or (vals.get("description") or "").strip():
                    self.job_fields.set_message("Job details loaded. Review them, then click Draft Proposal.", "ok")
                    self._update_draft_btn()
                    return
            self.job_fields.set_message(err or MSG_FETCH_FAIL, "error")

        if callable(self.fetch_job_hook):
            try:
                self.fetch_job_hook(cleaned, done)
                return
            except Exception:
                pass
        # Fallback: quiet window read (no navigation)
        try:
            text = self.window_read_hook(cleaned) if callable(self.window_read_hook) else None
        except Exception:
            text = None
        done(text, None if text else MSG_FETCH_FAIL)

    def _on_save_draft(self):
        """Save job + instructions + draft text into proposal_drafts."""
        vals = self.job_fields.get_values()
        draft = ""
        try:
            draft = self.draft_box.get("1.0", "end-1c")
        except tk.TclError:
            pass
        if not (vals.get("title") or vals.get("description") or draft).strip():
            self.job_fields.set_message("Add a job title, description or draft first.")
            return
        try:
            store = _store()
            conn = self.get_conn()
            store.ensure_table(conn)
            job_text = job_dict_to_text(vals)
            if self._draft_id:
                store.update_draft(
                    conn, self._draft_id,
                    job_title=vals.get("title") or "",
                    job_text=job_text,
                    client=vals.get("client") or self.client or "",
                    job_url=vals.get("url") or "",
                    budget_text=vals.get("budget") or "",
                    skills=vals.get("skills") or "",
                    template_name=(self.template_var.get() or "").strip(),
                    instructions=self.get_instructions(),
                    draft=draft,
                )
            else:
                self._draft_id = store.create_draft(
                    conn,
                    job_title=vals.get("title") or "",
                    job_text=job_text,
                    client=vals.get("client") or self.client or "",
                    job_url=vals.get("url") or "",
                    budget_text=vals.get("budget") or "",
                    skills=vals.get("skills") or "",
                )
                store.update_draft(
                    conn, self._draft_id,
                    template_name=(self.template_var.get() or "").strip(),
                    instructions=self.get_instructions(),
                    draft=draft,
                )
            self._unsaved_draft = False
            self.job_fields.set_message(MSG_DRAFT_SAVED, "ok")
        except Exception:
            self.job_fields.set_message(MSG_DRAFT_SAVE_FAIL)

    def _show_writer(self):
        if not self.writer_frame.winfo_manager():
            self.writer_frame.pack(
                fill="both", expand=True, padx=16, pady=(0, 8),
                after=self.btn_create_proposal,
            )
        try:
            self.job_desc_box.configure(height=JOB_DESC_EXPANDED)
            self.job_desc_box.pack_configure(expand=False)
        except tk.TclError:
            pass
        self._expanded = True
        self._refresh_voice()
        if not (self.ins_box.get("1.0", "end-1c") or "").strip():
            pass
        self._scroll.rebind()
        try:
            self._scroll._on_inner()
        except Exception:
            pass

    def _hide_writer(self):
        if self.writer_frame.winfo_manager():
            self.writer_frame.pack_forget()
        self._expanded = False
        try:
            self.job_desc_box.configure(height=JOB_DESC_OPEN)
            self.job_desc_box.pack_configure(expand=True, fill="both")
        except tk.TclError:
            pass

    def _reset_page(self):
        if self.recorder is not None:
            try:
                self.recorder.cancel()
            except Exception:
                pass
            self.recorder = None
        self._cancel_timer()
        self._set_busy(False)
        self._unsaved_draft = False
        self._draft_id = None
        self._fetching = False
        self.job_fields.clear()
        self.client = ""
        self._window_read_tried = set()
        self._sync_draft_note()
        self._update_draft_btn()
        dlg = getattr(self, "_writer_dlg", None)
        if dlg is not None:
            try:
                if callable(getattr(dlg, "set_draft", None)):
                    dlg.set_draft("")
                elif getattr(dlg, "draft_box", None) is not None:
                    dlg.draft_box.delete("1.0", "end")
                if hasattr(dlg, "_unsaved_draft"):
                    dlg._unsaved_draft = False
                if callable(getattr(dlg, "_sync_draft_note", None)):
                    dlg._sync_draft_note()
            except Exception:
                pass
        try:
            self.ins_box.delete("1.0", "end")
            self.draft_box.delete("1.0", "end")
        except tk.TclError:
            pass
        try:
            self.url_var.set("")
        except Exception:
            pass
        self.elapsed_var.set("")
        try:
            self.stop_label.configure(text="")
        except tk.TclError:
            pass
        self.clear_voice_error()
        self.job_fields.set_message("")
        self._hide_writer()
        self._reload_templates()

    def get_instructions(self):
        try:
            return self.ins_box.get("1.0", "end-1c")
        except tk.TclError:
            return ""

    def set_instructions(self, text):
        try:
            self.ins_box.delete("1.0", "end")
            if text:
                self.ins_box.insert("1.0", text)
        except tk.TclError:
            pass

    def _current_job_text(self):
        return job_dict_to_text(self.job_fields.get_values())

    def _on_generate(self, revise=False):
        if self.busy or self.recorder is not None:
            return
        vals = self.job_fields.get_values()
        if not (vals.get("description") or "").strip():
            self.job_fields.set_message("Type or paste a job description first.")
            return
        instructions = self.get_instructions()
        previous = ""
        if revise:
            previous = (self.draft_box.get("1.0", "end-1c") or "")
            if not previous.strip():
                self.job_fields.set_message("Generate or type a draft first.")
                return
        try:
            import ai_proposal
        except Exception:
            self.job_fields.set_message("Could not load the proposal writer. Try again.")
            return
        self.job_fields.set_message("")
        self.clear_voice_error()
        self._set_status("")
        job = self._current_job_text()
        template_text = self._current_template_text() or None
        busy_text = MSG_REVISING if revise else MSG_GENERATING
        self._gen_was_revise = bool(revise)

        def work():
            return ai_proposal.generate_proposal(
                job,
                instructions=instructions,
                previous_draft=previous or None,
                cfg=None,
                api_key=None,
                template_text=template_text,
            )

        def done(text):
            ready = MSG_REV_READY if revise else MSG_GEN_READY
            try:
                self.draft_box.delete("1.0", "end")
                if text:
                    self.draft_box.insert("1.0", text)
                self.draft_box.edit_modified(False)
            except tk.TclError:
                pass
            if text and str(text).strip():
                self._unsaved_draft = True
                self._sync_draft_note()
                self._scroll_to_draft()
                self._set_status(ready, "ok")
                self.job_fields.set_message(ready, "ok")
                self._stop_gen_progress(ready, "ok")
            else:
                self.job_fields.set_message("No draft came back. Try Generate again.")
                self._stop_gen_progress("", "info")

        def on_err(msg):
            msg = (msg or "Something went wrong. Try again.").strip()
            self.job_fields.set_message(msg)
            self._set_status(msg, "error")
            self._stop_gen_progress(msg, "error")

        self._run_bg(busy_text, work, done, on_err=on_err, progress="generate")

    def _on_copy(self):
        text = ""
        try:
            text = self.draft_box.get("1.0", "end-1c")
        except tk.TclError:
            pass
        if not (text or "").strip():
            self.job_fields.set_message("Generate or type a draft first.")
            return
        try:
            top = self.frame.winfo_toplevel()
            top.clipboard_clear()
            top.clipboard_append(text)
        except tk.TclError:
            self.job_fields.set_message("Could not copy the draft.")
            return
        self._unsaved_draft = False
        try:
            self.draft_box.edit_modified(False)
        except tk.TclError:
            pass
        self.job_fields.set_message("Copied. Paste it into Upwork.", "ok")

    def _on_submit_url(self, url):
        """Used by the writer dialog Save link button. Returns (ok, message)."""
        return self._save_submitted_link(url)

    def _on_save_link(self):
        """Submitted proposal link UI was removed from this page."""
        self.job_fields.set_message(
            "Submitted proposal link was removed from this page. Use Save Draft instead."
        )

    def _save_submitted_link(self, url):
        """Kept for the optional writer dialog; budget/skills are not stored."""
        store = _store()
        submit = getattr(store, "submit_direct", None)
        if not callable(submit):
            return False, "Saving the link is not available."
        vals = self.job_fields.get_values()
        cover = ""
        try:
            cover = self.draft_box.get("1.0", "end-1c")
        except tk.TclError:
            pass
        title = vals.get("title") or ""
        job_text = vals.get("description") or ""
        dlg = getattr(self, "_writer_dlg", None)
        if dlg is not None:
            try:
                if callable(getattr(dlg, "get_draft", None)):
                    cover = dlg.get_draft() or cover
                title = (getattr(dlg, "title", None) or title or "")
                job_text = (getattr(dlg, "job_text", None) or job_text or "")
            except Exception:
                pass
        try:
            proposal_id = submit(
                self.get_conn(),
                url,
                job_title=title,
                cover_letter=cover,
                job_text=job_text,
                budget_text="",
                skills="",
                client=vals.get("client") or self.client or "",
            )
        except Exception as exc:
            msg = getattr(exc, "message", None) or getattr(exc, "user_message", None)
            return False, (msg or "The link could not be saved.")
        if callable(self.on_submitted):
            try:
                self.on_submitted(proposal_id)
            except Exception:
                pass
        self._unsaved_draft = False
        self._reset_page()
        return True, SUBMIT_OK_MESSAGE

    # ---- mic / timer / background transcription ----------------------
    def _probe_voice(self):
        """Check whether the mic stack can open. Never raises."""
        try:
            import voice_input as vi
            result = vi.is_available() if hasattr(vi, "is_available") else (True, "")
            if isinstance(result, tuple):
                self.voice_ok = bool(result[0])
                self.voice_msg = (result[1] if len(result) > 1 else "") or ""
            else:
                self.voice_ok = bool(result)
                self.voice_msg = ""
        except Exception:
            self.voice_ok = False
            self.voice_msg = "Voice input is not available on this computer. Type your instructions instead."

    def _apply_voice_ui(self):
        """Sync mic button + note with the latest voice_ok flag."""
        note = "" if self.voice_ok else MSG_VOICE_OFF
        try:
            self.voice_note.configure(text=note)
        except Exception:
            pass
        try:
            if self.voice_ok:
                self.btn_mic.state(["!disabled"])
            else:
                self.btn_mic.state(["disabled"])
        except Exception:
            pass

    def _refresh_voice(self):
        """Re-probe the mic (page open / Draft Proposal) so a late device is usable."""
        was = self.voice_ok
        self._probe_voice()
        if getattr(self, "btn_mic", None) is not None:
            self._apply_voice_ui()
        if self.voice_ok and not was and self.recorder is None and not self.busy:
            try:
                self._set_voice_status(MSG_VOICE_READY, "info")
            except Exception:
                pass

    def _mic_tip_text(self):
        if self.busy:
            return "Please wait..."
        if not self.voice_ok:
            return self.voice_msg or "Voice input is not available on this computer. Type your instructions instead."
        if self.recorder is not None:
            return "Click to stop"
        return "Click to record your instructions"

    def _set_voice_status(self, text, kind="info"):
        text = (text or "").strip()
        self.voice_status_var.set(text)
        color = self.ui.get("accent", "#00866A")
        if kind == "error":
            color = "#DC2626"
        elif kind == "ok":
            color = "#047857"
        try:
            self.voice_status_label.configure(fg=color)
        except tk.TclError:
            pass
        if text:
            try:
                if not self.voice_status_label.winfo_manager():
                    self.voice_status_label.pack(fill="x", pady=(2, 0), after=self.ins_box)
            except tk.TclError:
                try:
                    self.voice_status_label.pack(fill="x", pady=(2, 0))
                except tk.TclError:
                    pass
        else:
            try:
                self.voice_status_label.pack_forget()
            except tk.TclError:
                pass

    def _start_gen_progress(self, text):
        """Show spinner + status next to Generate while OpenAI writes."""
        self._gen_progress_on = True
        self._spin_i = 0
        try:
            self.gen_status_var.set(text or MSG_GENERATING)
            self.gen_status_label.configure(fg=self.ui.get("accent", "#00866A"))
        except Exception:
            pass
        self._tick_gen_spin()

    def _tick_gen_spin(self):
        self._spin_id = None
        if not self._gen_progress_on:
            return
        try:
            self.gen_spin_var.set(_SPIN_FRAMES[self._spin_i % len(_SPIN_FRAMES)])
        except Exception:
            pass
        self._spin_i += 1
        try:
            self._spin_id = self.frame.after(120, self._tick_gen_spin)
        except tk.TclError:
            self._spin_id = None

    def _stop_gen_progress(self, final_text="", kind="info"):
        self._gen_progress_on = False
        if self._spin_id is not None:
            try:
                self.frame.after_cancel(self._spin_id)
            except Exception:
                pass
            self._spin_id = None
        try:
            self.gen_spin_var.set("")
        except Exception:
            pass
        text = (final_text or "").strip()
        try:
            self.gen_status_var.set(text)
            color = self.ui.get("accent", "#00866A")
            if kind == "error":
                color = "#DC2626"
            elif kind == "ok":
                color = "#047857"
            self.gen_status_label.configure(fg=color)
        except Exception:
            pass

    def _run_bg(self, busy_text, work, on_ok, on_err=None, progress="voice"):
        """Run work() off the UI thread; deliver result via after()+queue.

        progress: 'voice' (status under instructions) or 'generate' (spinner
        next to Generate / Regenerate).
        """
        self._bg_kind = progress
        self._set_busy(True)
        if progress == "generate":
            self._start_gen_progress(busy_text)
        else:
            self._set_voice_status(busy_text, "info")

        def runner():
            try:
                res = ("ok", work())
            except BaseException as e:  # noqa: B902 - shown as plain text in the UI
                try:
                    import voice_input as _vi
                except Exception:
                    _vi = None
                res = ("err", self._voice_message(e, vi=_vi))
            self._q.put((res, on_ok, on_err))

        name = "LeadPilotGenerateWorker" if progress == "generate" else "LeadPilotVoiceWorker"
        threading.Thread(target=runner, daemon=True, name=name).start()
        self._schedule_poll()

    def _schedule_poll(self):
        if self._poll_id is None:
            try:
                self._poll_id = self.frame.after(80, self._poll)
            except tk.TclError:
                self._poll_id = None

    def _poll(self):
        self._poll_id = None
        try:
            while True:
                (kind, value), on_ok, on_err = self._q.get_nowait()
                bg_kind = self._bg_kind
                self._bg_kind = None
                self._set_busy(False)
                if bg_kind == "generate":
                    # Stop the spinner; done/on_err set the final status text.
                    self._stop_gen_progress("", "info")
                if kind == "ok":
                    try:
                        on_ok(value)
                    except Exception:
                        if bg_kind == "generate":
                            self.job_fields.set_message("Something went wrong. Try again.")
                        else:
                            self.show_voice_error("Something went wrong. Try again.")
                elif on_err is not None:
                    try:
                        on_err(value)
                    except Exception:
                        if bg_kind == "generate":
                            self.job_fields.set_message(
                                value if isinstance(value, str) else "Something went wrong."
                            )
                        else:
                            self.show_voice_error(
                                value if isinstance(value, str) else "Something went wrong."
                            )
                else:
                    if bg_kind == "generate":
                        self.job_fields.set_message(
                            value if isinstance(value, str) else "Something went wrong."
                        )
                    else:
                        self.show_voice_error(
                            value if isinstance(value, str) else "Something went wrong."
                        )
        except queue.Empty:
            pass
        if self.busy:
            self._schedule_poll()

    def toggle_recording(self):
        if self.recorder is not None:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if self.busy or self.recorder is not None:
            return
        try:
            import voice_input as vi
        except Exception:
            self.voice_ok = False
            self.voice_msg = "Voice input is not available on this computer. Type your instructions instead."
            self._apply_voice_ui()
            self.show_voice_error(self.voice_msg)
            return
        # Always re-check at click time (startup probe can be stale; device may
        # have been plugged in, or QA may flip the mic mock after page build).
        try:
            result = vi.is_available() if hasattr(vi, "is_available") else (True, "")
            ok = result[0] if isinstance(result, tuple) else bool(result)
            msg = (result[1] if isinstance(result, tuple) and len(result) > 1 else "") or ""
        except Exception:
            ok, msg = False, "Voice input is not available on this computer. Type your instructions instead."
        self.voice_ok = bool(ok)
        self.voice_msg = msg
        self._apply_voice_ui()
        if not ok:
            self.show_voice_error(
                msg or "Voice input is not available on this computer. Type your instructions instead."
            )
            return
        self.clear_voice_error()
        cfg = self._load_cfg()
        try:
            rec = vi.Recorder(cfg)
            rec.start()
        except Exception as exc:
            self.show_voice_error(self._voice_message(exc, vi=vi))
            return
        self.recorder = rec
        try:
            if hasattr(self.btn_mic, "set_recording"):
                self.btn_mic.set_recording(True)
        except Exception:
            pass
        try:
            self.stop_label.configure(text="Stop")
        except tk.TclError:
            pass
        self.elapsed_var.set(self._timer_text(0))
        self._set_voice_status(MSG_RECORDING, "info")
        self._tick()

    def _tick(self):
        self._timer_id = None
        if self.recorder is None:
            return
        try:
            secs = int(self.recorder.elapsed() or 0)
        except Exception:
            secs = 0
        self.elapsed_var.set(self._timer_text(secs))
        auto = False
        try:
            auto = bool(self.recorder.auto_stopped) and not self.recorder.is_recording
        except Exception:
            auto = False
        if auto:
            self.stop_recording(auto=True)
            return
        try:
            self._timer_id = self.frame.after(200, self._tick)
        except tk.TclError:
            self._timer_id = None

    def _timer_text(self, secs):
        try:
            mx = int(getattr(self.recorder, "max_seconds", 0) or 0)
        except Exception:
            mx = 0
        if mx <= 0:
            mx = 120
        secs = max(0, min(int(secs), mx))
        return "%d:%02d of %d:%02d" % (secs // 60, secs % 60, mx // 60, mx % 60)

    def _cancel_timer(self):
        if self._timer_id is not None:
            try:
                self.frame.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None

    def _on_escape(self, event=None):
        if self.recorder is not None:
            self.stop_recording()
            return "break"
        return None

    def stop_recording(self, auto=False):
        if self.recorder is None:
            return
        rec, self.recorder = self.recorder, None
        self._cancel_timer()
        try:
            if hasattr(self.btn_mic, "set_recording"):
                self.btn_mic.set_recording(False)
        except Exception:
            pass
        self.elapsed_var.set("")
        try:
            self.stop_label.configure(text="")
        except tk.TclError:
            pass
        try:
            path = rec.stop()
        except Exception as exc:
            self._set_voice_status("")
            self.show_voice_error(self._voice_message(exc))
            return
        try:
            import voice_input as vi
        except Exception:
            self._set_voice_status("")
            self.show_voice_error("Voice input is not available. Type your instructions instead.")
            return
        empty_msg = getattr(vi, "EMPTY_MSG", None) or (
            "I could not hear anything. Try again or type your instructions."
        )
        cfg = self._load_cfg()
        prefix = "Recording reached the time limit. " if auto else ""

        def work():
            return vi.transcribe(path, cfg=cfg)

        def done(text):
            text = (text or "").strip() if isinstance(text, str) else ""
            self._set_voice_status("")
            if not text:
                self.show_voice_error(empty_msg)
                return
            self.clear_voice_error()
            cur = self.get_instructions().rstrip()
            self.set_instructions((cur + "\n" + text) if cur else text)
            self._set_voice_status("Voice added to instructions. Edit if needed, then Generate Proposal.", "ok")

        self._run_bg(prefix + MSG_TRANSCRIBING, work, done, on_err=self.show_voice_error)

    def _voice_message(self, exc, vi=None):
        """Plain English for voice errors. Prefer .user_message (NoCreditsError etc.)."""
        if isinstance(exc, str):
            return exc.strip() or "Something went wrong. Try again."
        msg = getattr(exc, "user_message", None)
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
        default = getattr(exc, "default_message", None)
        if isinstance(default, str) and default.strip():
            return default.strip()
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        if "credit" in name or "insufficient_quota" in text or "no credits" in text:
            if vi is not None:
                credits = getattr(vi, "NO_CREDITS_MSG", "") or ""
                if credits:
                    return credits
            return (
                "Your OpenAI account has no credits left. Add credits in "
                "OpenAI Billing (platform.openai.com), then try again."
            )
        return "Something went wrong. Try again. Type your instructions instead."

    def show_voice_error(self, msg):
        msg = (msg or "").strip() or "Something went wrong. Try again."
        self._set_voice_status("")
        self.voice_err_var.set(msg)
        if not self._voice_err_shown:
            try:
                self.voice_err_label.pack(fill="x", pady=(2, 0), after=self.ins_box)
            except tk.TclError:
                self.voice_err_label.pack(fill="x", pady=(2, 0))
            self._voice_err_shown = True
        try:
            self.voice_err_label.configure(fg="#DC2626")
        except tk.TclError:
            pass

    def clear_voice_error(self):
        self.voice_err_var.set("")
        if self._voice_err_shown:
            try:
                self.voice_err_label.pack_forget()
            except tk.TclError:
                pass
            self._voice_err_shown = False

    def _load_cfg(self):
        try:
            import settings_store as ss
            if hasattr(ss, "load_config"):
                return ss.load_config() or {}
        except Exception:
            pass
        return {}


    def _set_status(self, msg, kind="info"):
        msg = (msg or "").strip()
        self.status_var.set(msg)
        color = "#DC2626" if kind == "error" else ("#047857" if kind == "ok" else self.ui.get("muted", "#64748B"))
        try:
            self.status_label.configure(fg=color)
        except tk.TclError:
            pass
        if kind == "error" and "no credits" in msg.lower():
            self.show_voice_error(msg)
        elif kind != "error":
            self.clear_voice_error()


    def _scroll_widget_into_view(self, widget):
        """Scroll the page canvas so widget (and what sits just below it) is visible."""
        sc = getattr(self, "_scroll", None)
        if sc is None or widget is None:
            return
        try:
            canvas = sc.canvas
            canvas.update_idletasks()
            widget.update_idletasks()
            bbox = canvas.bbox("all") or (0, 0, 0, 1)
            total = max(float(bbox[3] - bbox[1]), 1.0)
            cy = canvas.winfo_rooty()
            ytop = canvas.canvasy(0)
            y = widget.winfo_rooty() - cy + ytop
            canvas.yview_moveto(max(0.0, (y - 12) / total))
            canvas.update_idletasks()
        except Exception:
            pass

    def _scroll_to_draft(self):
        """After Generate, bring the draft and the Copy row into view."""
        target = getattr(self, "draft_wrap", None) or getattr(self, "draft_box", None)
        self._scroll_widget_into_view(target)
        try:
            self._scroll.rebind()
        except Exception:
            pass

    def _on_draft_modified(self, event=None):

        try:
            if not self.draft_box.edit_modified():
                return
            self.draft_box.edit_modified(False)
        except tk.TclError:
            pass
        try:
            has = bool((self.draft_box.get("1.0", "end-1c") or "").strip())
        except tk.TclError:
            has = False
        if has:
            self._unsaved_draft = True
        self._sync_draft_note()

    def _sync_draft_note(self):
        note = getattr(self, "draft_note", None)
        if note is None:
            return
        try:
            has = bool((self.draft_box.get("1.0", "end-1c") or "").strip())
        except Exception:
            has = False
        try:
            mapped = bool(note.winfo_manager())
        except tk.TclError:
            mapped = False
        if has and not mapped:
            try:
                note.pack(fill="x", pady=(2, 0), after=self.draft_wrap)
            except tk.TclError:
                try:
                    note.pack(fill="x", pady=(2, 0), before=self.copy_row)
                except tk.TclError:
                    pass
        elif not has and mapped:
            try:
                note.pack_forget()
            except tk.TclError:
                pass

    def _schedule_window_read_paste(self, event=None):
        """A paste always retries the current URL (FocusOut/Return stay once-per-URL)."""
        return self._schedule_window_read(event, force_retry=True)

    def _schedule_window_read(self, event=None, force_retry=False):
        """After a job URL lands, maybe read the open Upwork window."""
        if not callable(self.window_read_hook):
            return
        try:
            # Let <<Paste>> finish inserting the URL first.
            self.frame.after(10, lambda: self._maybe_window_read(force_retry=force_retry))
        except tk.TclError:
            self._maybe_window_read(force_retry=force_retry)

    def _maybe_window_read(self, force_retry=False):
        if not callable(self.window_read_hook):
            return
        vals = self.job_fields.get_values()
        if (vals.get("title") or "").strip():
            return
        url = (vals.get("url") or "").strip()
        ok, cleaned = validate_job_url(url)
        if not ok:
            return
        key = _normalize_any_url(cleaned) or cleaned
        if key in self._window_read_tried and not force_retry:
            return
        self._window_read_tried.add(key)
        self.job_fields.set_message(MSG_READING_WINDOW, "info")
        try:
            self.frame.after(50, lambda u=cleaned: self._run_window_read(u))
        except tk.TclError:
            self._run_window_read(cleaned)

    def _run_window_read(self, url):
        text = None
        try:
            text = self.window_read_hook(url)
        except Exception:
            text = None
        if not text or not str(text).strip():
            self.job_fields.set_message(MSG_WINDOW_READ_FAIL, "info")
            return
        self.job_fields.fill_from_text(str(text), only_empty=True)
        vals = self.job_fields.get_values()
        if not (vals.get("title") or "").strip():
            self.job_fields.set_message(MSG_WINDOW_READ_FAIL, "info")
        else:
            self.job_fields.set_message("")
