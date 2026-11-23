import csv
import sqlite3
import shutil
from pathlib import Path
from datetime import date, datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# Upwork login is stored in Windows Credential Manager, never in this file.
try:
    from upwork_credentials import save_upwork_login, get_upwork_login, clear_upwork_login, keyring as _keyring
except Exception:
    _keyring = None

# AI settings and the OpenAI key. The key lives only in Windows Credential Manager (through settings_store), never in a file.
try:
    import settings_store
except Exception:
    settings_store = None
# Write a proposal window (draft only, never sends anything to Upwork)
try:
    import proposal_ui
except Exception:
    proposal_ui = None
try:
    import write_proposal_page
except Exception:
    write_proposal_page = None

APP_DIR = Path.home() / "LeadPilotCRM"
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR / "leadpilot.db"
APP_VERSION = "v1.3"   # shown in the window title and the sidebar footer

PROPOSAL_FIELDS = ["account", "member", "job", "client", "url", "proposal_date",
                   "bid", "connects", "status", "views", "notes"]
LEAD_FIELDS = ["account", "member", "name", "company", "source", "proposal_id",
               "lead_date", "status", "budget", "next_followup", "last_contact", "notes"]

PROPOSAL_STATUSES = ["Draft", "Submitted", "Viewed", "Responded", "Interview",
                     "Hired", "Lost", "Archived"]
LEAD_STATUSES = ["Qualified", "Contacted", "Follow-up", "Interview",
                 "Negotiation", "Won", "Lost", "Dead"]


import re as _re
_MONTHS = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}, \d{4}"
_SECTIONS = [("offers", "Interview"), ("active proposals", "Responded"),
             ("submitted proposals", "Submitted"), ("archived", "Archived"),
             ("referrals", "Submitted"), ("invitations to interview", None)]
_SKIP = _re.compile(r"^(initiated|submitted|received|viewed|\d+\s+(minute|hour|day|week|month|year)s? ago|today|yesterday|"
                    r"general profile|specialized profile|view|withdraw|archive|edit|messages?|\(?\d+\)?|"
                    r"my proposals|proposals|active|archived|referrals|see all|load more|show more|boost|last (week|month|year)|this (week|month)|viewed by client)\b", _re.I)

_STATUS_RANK = {"Draft": 0, "Submitted": 1, "Viewed": 2, "Responded": 3, "Interview": 4, "Hired": 5}

def _norm_title(t):
    """Title key for duplicate matching: lower case, trimmed, single spaces, no trailing punctuation."""
    return _re.sub(r"\s+", " ", (t or "")).strip().strip(" .-|").lower()

def _url_key(u):
    """Proposal/job key from an Upwork link (the long number or ~id), so different link formats still match."""
    m = _re.search(r"(?:proposals/|~)(\w{10,})", u or "")
    return m.group(1).lower() if m else (u or "").strip().rstrip("/").lower() or None

def parse_upwork_proposals(text):
    """Best-effort reader for text copied from Upwork's My Proposals page.
    Returns a list of dicts: job, proposal_date, status."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out, status = [], "Submitted"
    for i, ln in enumerate(lines):
        low = ln.lower()
        for key, st in _SECTIONS:
            if low.startswith(key):
                status = st
        if status is None:
            continue
        m = _re.search(_MONTHS, ln)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(0).replace(".", "").replace("Sept", "Sep"), "%b %d, %Y")
        except ValueError:
            try: d = datetime.strptime(m.group(0), "%B %d, %Y")
            except ValueError: continue
        title = None
        for nxt in lines[i+1:i+4]:
            if not _re.search(_MONTHS, nxt) and not _SKIP.match(nxt) and len(nxt) > 8:
                title = nxt; break
        viewed = False
        for nxt in lines[i+1:i+8]:
            if _re.search(_MONTHS, nxt): break
            if "viewed by client" in nxt.lower(): viewed = True; break
        if title:
            out.append({"job": title[:250], "proposal_date": d.date().isoformat(), "status": status, "viewed": viewed})
    seen, uniq = set(), []
    for r in out:
        k = _norm_title(r["job"])
        if k not in seen:
            seen.add(k); uniq.append(r)
    return uniq


JOB_DETAIL_COLS = [("budget_text","Budget"),("summary","Description"),("skills","Skills"),
    ("location","Client Location"),("proposals_count","Proposals"),("hire_rate","Hire Rate"),
    ("total_spent","Total Spent"),("rating","Rating"),("review_count","Reviews"),("review_name","Client Name (reviews)"),
    ("last_viewed","Last Viewed by Client"),("interviewing","Interviewing"),("invites_sent","Invites Sent"),
    ("unanswered_invites","Unanswered Invites"),("member_since","Member Since"),("payment_verified","Payment Verified"),("last_updated","Last Updated")]

# Modern UI palette (visual only)
UI = {"bg": "#F5F7FB", "card": "#FFFFFF", "line": "#E6EAF2", "text": "#0F172A", "muted": "#64748B",
      "side": "#0F172A", "side2": "#1E293B", "side_text": "#CBD5E1", "accent": "#00866A", "accent2": "#005B4B",
      "green": "#10B981", "red": "#EF4444"}
# accent aligned with Emerald Overview/sidebar so solid action buttons stay one color across pages
# Emerald & White palette for Overview + left sidebar only (other pages keep UI above).
OV = {"bg": "#FAFAF8", "card": "#FFFFFF", "line": "#E7ECE9", "text": "#17211F", "muted": "#718078",
      "emerald": "#00866A", "emerald_dark": "#005B4B", "mint": "#DDF5EC",
      "success": "#16A34A", "danger": "#EF4444",
      "side": "#FFFFFF", "side2": "#FAFAF8", "side_text": "#17211F", "side_muted": "#718078",
      "side_hover": "#F3F7F5", "side_edge": "#E7ECE9"}
STATUS_COLORS = {  # text color, soft background
    "Draft": ("#475569", "#F1F5F9"), "Submitted": ("#2563EB", "#EFF6FF"), "Viewed": ("#7C3AED", "#F5F3FF"),
    "Responded": ("#0891B2", "#ECFEFF"), "Interview": ("#B45309", "#FFFBEB"), "Hired": ("#047857", "#ECFDF5"),
    "Won": ("#047857", "#ECFDF5"), "Lost": ("#DC2626", "#FEF2F2"), "Dead": ("#991B1B", "#FEF2F2"),
    "Archived": ("#6B7280", "#F3F4F6"), "Qualified": ("#2563EB", "#EFF6FF"), "Contacted": ("#0891B2", "#ECFEFF"),
    "Follow-up": ("#7C3AED", "#F5F3FF"), "Negotiation": ("#B45309", "#FFFBEB")}

def pill(parent, text, fg, bg, size=8):
    return tk.Label(parent, text=f"  {text}  ", fg=fg, bg=bg, font=("Segoe UI", size, "bold"), padx=4, pady=2)

def parse_proposal_page(text):
    """Read the text copied (Ctrl+A, Ctrl+C) from an Upwork 'Proposal details' page."""
    import re
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]
    lines = [l for l in lines if l]
    low = [l.lower() for l in lines]
    out = {}
    def after(label):
        return low.index(label) + 1 if label in low else None
    stops = ("edit proposal", "withdraw proposal", "about the client", "messages", "\u00a9", "privacy", "terms of service")
    i = after("cover letter")
    if i is not None:
        body = []
        for l in lines[i:]:
            if l.lower().startswith(stops): break
            body.append(l)
        if body: out["cover_letter"] = "\n\n".join(body)
    i = after("job details")
    if i is not None and i < len(lines): out["job"] = lines[i]
    i = after("skills and expertise")
    if i is not None:
        sk = []
        for l in lines[i:]:
            if l.lower().startswith(("your proposed terms", "how do you want")): break
            sk.append(l)
        if sk: out["skills"] = ", ".join(sk[:12])
    m = re.search(r"posted [^\n]*\n(.+?)(?:\n(?:view job posting|skills and expertise)|\u2026)", text, re.I | re.S)
    if m: out["summary"] = re.sub(r"\s*more$", "", " ".join(m.group(1).split()))
    m = re.search(r"total price of project.*?(\$[\d,]+(?:\.\d\d)?)", text, re.I | re.S)
    if m: out["budget_text"] = m.group(1) + " fixed (your bid)"
    else:
        m = re.search(r"client.s budget:\s*(\$[\d,.]+)", text, re.I)
        if m: out["budget_text"] = m.group(1)
    if re.search(r"payment method verified", text, re.I): out["payment_verified"] = "Verified"
    elif re.search(r"payment method not verified", text, re.I): out["payment_verified"] = "Not verified"
    m = re.search(r"([\d.]+)\s+of\s+(\d+)\s+reviews", text, re.I)
    if m:
        out["rating"], out["review_count"] = m.group(1), m.group(2)
        k = next((n for n, l in enumerate(lines) if re.search(r"of\s+\d+\s+reviews", l, re.I)), None)
        if k is not None and k + 1 < len(lines): out["location"] = lines[k + 1]
    m = re.search(r"(\d+)\s+jobs? posted\s*\n?\s*(\d+%\s*hire rate[^\n]*)", text, re.I)
    if m: out["hire_rate"] = f"{m.group(2).split(',')[0]} ({m.group(1)} jobs posted)"
    m = re.search(r"(\$[\d.,]+[KkMm]?)\s+total spent\s*\n?\s*([^\n]*hires?[^\n]*)?", text, re.I)
    if m: out["total_spent"] = m.group(1) + (f" ({m.group(2).strip()})" if m.group(2) else "")
    m = re.search(r"member since\s+([^\n]+)", text, re.I)
    if m: out["member_since"] = m.group(1).strip()
    return out

# ---------- Fresh Audit helpers (Windows) ----------
import ctypes as _ct, time as _time
def _win_title(hwnd):
    u = _ct.windll.user32; n = u.GetWindowTextLengthW(hwnd)
    b = _ct.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, b, n + 1); return b.value

def find_upwork_window():
    """Return the handle of a visible browser window whose title mentions Upwork, preferring the one in front."""
    try:
        u = _ct.windll.user32
    except Exception:
        return None
    fg = u.GetForegroundWindow()
    if fg and "upwork" in _win_title(fg).lower() and "leadpilot" not in _win_title(fg).lower():
        return fg
    found = []
    @_ct.WINFUNCTYPE(_ct.c_bool, _ct.c_void_p, _ct.c_void_p)
    def cb(hwnd, _):
        t = _win_title(hwnd).lower()
        if u.IsWindowVisible(hwnd) and "upwork" in t and "leadpilot" not in t: found.append(hwnd)
        return True
    u.EnumWindows(cb, 0)
    return found[0] if found else None

_BROWSER_EXES = ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe")

def _win_process_name(hwnd):
    """Executable file name of the process that owns hwnd, e.g. 'chrome.exe', or ''."""
    try:
        u, k = _ct.windll.user32, _ct.windll.kernel32
        pid = _ct.c_ulong(0)
        u.GetWindowThreadProcessId(hwnd, _ct.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        PROCESS_QUERY_INFORMATION = 0x0400
        k.OpenProcess.restype = _ct.c_void_p
        handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            handle = k.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid.value)
        if not handle:
            return ""
        try:
            buf = _ct.create_unicode_buffer(32768)
            size = _ct.c_ulong(32768)
            q = k.QueryFullProcessImageNameW
            q.argtypes = [_ct.c_void_p, _ct.c_ulong, _ct.c_wchar_p, _ct.POINTER(_ct.c_ulong)]
            q.restype = _ct.c_int
            if not q(handle, 0, buf, _ct.byref(size)):
                return ""
            path = buf.value or ""
            return Path(path).name
        finally:
            k.CloseHandle(handle)
    except Exception:
        return ""

def find_job_browser_window():
    """Return the front-most visible top-level browser window, excluding LeadPilot.

    EnumWindows visits top-level windows in Z-order (the one in front first).
    Used by write_proposal_read_window, Fresh Audit and Import from Upwork Messages
    when no window title mentions Upwork.
    Does not send keys.
    """
    try:
        u = _ct.windll.user32
    except Exception:
        return None
    found = []
    @_ct.WINFUNCTYPE(_ct.c_bool, _ct.c_void_p, _ct.c_void_p)
    def cb(hwnd, _):
        if found:
            return False
        try:
            if not u.IsWindowVisible(hwnd):
                return True
            if u.GetWindow(hwnd, 4):  # GW_OWNER: skip owned popups
                return True
            title = _win_title(hwnd)
            if "leadpilot" in title.lower():
                return True
            name = (_win_process_name(hwnd) or "").lower()
            if name in _BROWSER_EXES:
                found.append(hwnd)
                return False
        except Exception:
            return True
        return True
    try:
        u.EnumWindows(cb, 0)
    except Exception:
        return None
    return found[0] if found else None

def _title_has(hwnd, word):
    """True if the window title contains word (lower case). Read only."""
    try:
        return bool(hwnd) and word in _win_title(hwnd).lower()
    except Exception:
        return False

_PROPOSALS_HEAD = _re.compile(r"^(my proposals|submitted proposals|active proposals|archived proposals)\b", _re.I)
_MESSAGES_MARKS = ("upwork", "search messages", "activity timeline", "local time", "find work", "deliver work", "manage finances")

def upwork_page_ok(text, kind):
    """Fallback check for text copied from a browser window whose title does not say Upwork.
    kind 'proposals': the proposals parser finds jobs AND the page has a proposals heading
    (or mentions both Upwork and proposal). kind 'messages': the Messages list parser finds chats
    AND the page has an Upwork Messages marker. Anything else is rejected."""
    text = text or ""
    low = text.lower()
    if kind == "proposals":
        if not parse_upwork_proposals(text):
            return False
        heads = any(_PROPOSALS_HEAD.match(l.strip()) for l in text.splitlines())
        return heads or ("upwork" in low and "proposal" in low)
    if kind == "messages":
        if not parse_upwork_messages_list(text):
            return False
        return any(m in low for m in _MESSAGES_MARKS)
    return False

def _clip_api():
    u, k = _ct.windll.user32, _ct.windll.kernel32
    u.GetClipboardData.restype = _ct.c_void_p; u.GetClipboardData.argtypes = [_ct.c_uint]
    k.GlobalLock.restype = _ct.c_void_p; k.GlobalLock.argtypes = [_ct.c_void_p]; k.GlobalUnlock.argtypes = [_ct.c_void_p]
    u.OpenClipboard.argtypes = [_ct.c_void_p]
    return u, k

def clear_clipboard():
    u, k = _clip_api()
    for _ in range(10):
        if u.OpenClipboard(None):
            u.EmptyClipboard(); u.CloseClipboard(); return True
        _time.sleep(0.1)
    return False

def read_clipboard_text():
    u, k = _clip_api()
    for _ in range(10):
        if u.OpenClipboard(None): break
        _time.sleep(0.1)
    else:
        return ""
    try:
        h = u.GetClipboardData(13)            # CF_UNICODETEXT
        if not h: return ""
        p = k.GlobalLock(h)
        try: return _ct.wstring_at(p) if p else ""
        finally: k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()

def copy_window_text(hwnd):
    """Bring the window forward, press Ctrl+A then Ctrl+C, the same keys you would press yourself."""
    u = _ct.windll.user32
    if u.IsIconic(hwnd): u.ShowWindow(hwnd, 9)
    if u.GetForegroundWindow() != hwnd:
        k = _ct.windll.kernel32
        ft = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None); me = k.GetCurrentThreadId()
        u.AttachThreadInput(me, ft, True); u.SetForegroundWindow(hwnd); u.BringWindowToTop(hwnd); u.AttachThreadInput(me, ft, False)
    _time.sleep(0.5)
    for key in (0x41, 0x43):                      # A, then C
        u.keybd_event(0x11, 0, 0, 0); u.keybd_event(key, 0, 0, 0)
        u.keybd_event(key, 0, 2, 0); u.keybd_event(0x11, 0, 2, 0)
        _time.sleep(0.4)
    _time.sleep(0.4)

# ---------- Follow-up cadence + Upwork Messages list reader ----------
FU_CADENCE = [24, 48, 48, 72, 72]          # hours: 1st follow-up 24h after chat start, then 48, 48, 72, 72
FU_CLOSED = ("Won", "Lost", "Dead")
_FU_DAY = _re.compile(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|yesterday|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}:\d{2}\s*[ap]\.?m\.?)$", _re.I)
_FU_PREVIEW = _re.compile(r"^([^:\n]{1,40}):\s*(.*)$")

def _fu_parse_day(tok, now=None):
    from datetime import timedelta
    now = now or datetime.now(); t = tok.strip().lower()
    if _re.match(r"^\d{1,2}:\d{2}", t):
        hm = datetime.strptime(_re.sub(r"[.\s]", "", t).upper(), "%I:%M%p")
        return now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0), True
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if t == "today": return base, False
    if t == "yesterday": return base - timedelta(days=1), False
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if t in days:
        back = (now.weekday() - days.index(t)) % 7 or 7
        return base - timedelta(days=back), False
    mo, dd, yy = t.split("/"); yy = int(yy) + (2000 if len(yy) == 2 else 0)
    return datetime(yy, int(mo), int(dd)), False

def parse_upwork_messages_list(text, now=None):
    """Read the left column of Upwork Messages: client/company, date, job title, last-message preview."""
    lines = [l.strip() for l in (text or "").splitlines()]
    lines = [l for l in lines if l and not _re.match(r"^[A-Z]{1,3}$", l)]   # drop avatar initials
    out, seen = [], set()
    for i, l in enumerate(lines):
        if not _FU_DAY.match(l) or i == 0 or i + 2 >= len(lines): continue
        who, title, prev = lines[i - 1], lines[i + 1], lines[i + 2]
        m = _FU_PREVIEW.match(prev)
        if not m or _FU_DAY.match(who) or len(who) > 80 or who.lower() in ("messages", "unread", "favorites"): continue
        sender = m.group(1).strip()
        try: when, has_time = _fu_parse_day(l, now)
        except Exception: continue
        name, _, company = who.partition(",")
        key = who.lower()
        if key in seen: continue
        seen.add(key)
        out.append({"name": name.strip(), "company": company.strip(), "title": title.rstrip(". ").replace("\u2026", ""),
                    "preview": prev[:300], "from_me": sender.lower() == "you", "sender": sender,
                    "when": when, "has_time": has_time})
    return out

SALES_STAGES = ["Chat started", "Proposal sent, awaiting response", "Meeting requested, no reply yet", "Meeting booked",
                "Contract offer, awaiting offer from client", "Offer sent, awaiting acceptance", "Contract started"]
STAGE_PAUSED = ("Meeting booked", "Contract started")     # no follow-ups are due while in these stages
_TIMELINE_STEPS = ["proposal submitted", "contract offer", "offer acceptance", "contract starts"]
_MEET_WORDS = _re.compile(r"\b(call|meeting|zoom|google meet|hop on|schedule|calendly|time (that )?works|available)\b", _re.I)

def parse_upwork_open_chat(text):
    """From the copied Messages page, read the open chat's client (the header line just before 'local time')
    and its Activity timeline stage from the right panel. Returns dict or None."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    who = None
    for i in range(1, len(lines)):
        if "local time" in lines[i].lower() and "local time" not in lines[i - 1].lower() and not _FU_DAY.match(lines[i - 1]):
            who = lines[i - 1]; break
    if not who: return None
    stage = raw = None
    low_all = [l.lower() for l in lines]
    if "activity timeline" in low_all:
        k = low_all.index("activity timeline")
        seg = lines[k + 1:k + 14]; low = [l.lower() for l in seg]
        reached = None
        for j, l in enumerate(low):
            if l in _TIMELINE_STEPS and j + 1 < len(low):
                nxt = low[j + 1]
                if nxt not in _TIMELINE_STEPS and not nxt.startswith(("search messages", "meeting recaps")):
                    reached = (seg[j], seg[j + 1])
        if reached:
            step, detail = reached; raw = f"{step}: {detail}"
            st, d = step.lower(), detail.lower()
            if st == "contract starts": stage = "Contract started"
            elif st == "offer acceptance": stage = "Offer sent, awaiting acceptance"
            elif st == "contract offer": stage = "Contract offer, awaiting offer from client" if "awaiting" in d else "Offer sent, awaiting acceptance"
            else: stage = "Proposal sent, awaiting response"
    name, _, company = who.partition(",")
    return {"who": who, "name": name.strip(), "company": company.strip(), "stage": stage, "raw": raw}

# ---------- Google Calendar (OAuth, standard library only) ----------
GCAL_SVC = "LeadPilotCRM-GoogleCalendar"      # tokens live in Windows Credential Manager, never in a file
GCAL_SCOPE = "https://www.googleapis.com/auth/calendar.events"
GCAL_API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

def gcal_secret(k, v=None, delete=False):
    if _keyring is None: return None
    try:
        if delete: _keyring.delete_password(GCAL_SVC, k); return None
        if v is not None: _keyring.set_password(GCAL_SVC, k, v); return v
        return _keyring.get_password(GCAL_SVC, k)
    except Exception:
        return None

def gcal_http(method, url, data=None, token=None, form=False):
    import urllib.request, urllib.parse, urllib.error, json
    headers, body = {}, None
    if form:
        body = urllib.parse.urlencode(data).encode(); headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode(); headers["Content-Type"] = "application/json"
    if token: headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Google returned {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Couldn't reach Google ({e.reason}). Check your internet connection.")

def gcal_client():
    import json
    raw = gcal_secret("client")
    if not raw: return None
    d = json.loads(raw)
    return d.get("installed") or d.get("web") or d

def gcal_oauth(client, timeout=300):
    """Desktop sign-in: opens Google in your browser, waits for the reply on 127.0.0.1, returns tokens (PKCE)."""
    import http.server, secrets, hashlib, base64, urllib.parse, webbrowser, time as _t
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16); result = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [None])[0] == state:
                result.update({k: v[0] for k, v in q.items()})
            ok = "code" in result
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(("<html><body style='font-family:Segoe UI;padding:40px'><h2>" +
                              ("LeadPilot is connected to Google Calendar. You can close this tab." if ok else "Waiting for Google sign-in...") +
                              "</h2></body></html>").encode())
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H); srv.timeout = 5
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = client.get("auth_uri", "https://accounts.google.com/o/oauth2/auth") + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": GCAL_SCOPE,
        "access_type": "offline", "prompt": "consent", "code_challenge": challenge, "code_challenge_method": "S256", "state": state})
    webbrowser.open(url)
    end = _t.time() + timeout
    try:
        while _t.time() < end and "code" not in result and "error" not in result:
            srv.handle_request()
    finally:
        srv.server_close()
    if "code" not in result:
        raise RuntimeError("Google sign-in was cancelled." if result.get("error") else "Timed out waiting for Google sign-in.")
    tok = gcal_http("POST", client.get("token_uri", "https://oauth2.googleapis.com/token"),
                    {"code": result["code"], "client_id": client["client_id"], "client_secret": client.get("client_secret", ""),
                     "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier}, form=True)
    if not tok.get("refresh_token"):
        raise RuntimeError("Google didn't return a refresh token. Remove LeadPilot's access in your Google account and connect again.")
    return tok

def gcal_access_token(cache={}):
    import time as _t
    if cache.get("tok") and cache.get("exp", 0) > _t.time() + 60: return cache["tok"]
    client, rt = gcal_client(), gcal_secret("refresh_token")
    if not client or not rt: raise RuntimeError("Google Calendar isn't connected.")
    tok = gcal_http("POST", client.get("token_uri", "https://oauth2.googleapis.com/token"),
                    {"client_id": client["client_id"], "client_secret": client.get("client_secret", ""),
                     "refresh_token": rt, "grant_type": "refresh_token"}, form=True)
    cache["tok"], cache["exp"] = tok["access_token"], _t.time() + int(tok.get("expires_in", 3600))
    return cache["tok"]

def gcal_list_events(days_back=7, days_ahead=60):
    import urllib.parse
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)
    params = {"timeMin": (now - timedelta(days=days_back)).isoformat(), "timeMax": (now + timedelta(days=days_ahead)).isoformat(),
              "singleEvents": "true", "orderBy": "startTime", "maxResults": "250"}
    out, page = [], None
    while True:
        if page: params["pageToken"] = page
        d = gcal_http("GET", GCAL_API + "?" + urllib.parse.urlencode(params), token=gcal_access_token())
        out += d.get("items", []); page = d.get("nextPageToken")
        if not page: return out

def gcal_event_to_meeting(e):
    """Google event -> dict for the meetings table (times in your local clock)."""
    if e.get("status") == "cancelled": return None
    def t(x):
        if "dateTime" in x:
            return datetime.fromisoformat(x["dateTime"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        return datetime.strptime(x["date"], "%Y-%m-%d")
    st, en = t(e["start"]), t(e.get("end", e["start"]))
    dur = max(5, int((en - st).total_seconds() // 60)) if en > st else 30
    others = [a.get("displayName") or a.get("email", "") for a in e.get("attendees", []) if not a.get("self")]
    loc = e.get("location") or ""
    link = e.get("hangoutLink") or (loc if loc.startswith("http") else "") or e.get("htmlLink", "")
    return {"gcal_id": e["id"], "title": e.get("summary") or "(no title)", "client": ", ".join(o for o in others if o)[:200],
            "start": st.strftime("%Y-%m-%d %H:%M"), "duration": dur, "link": link, "notes": (e.get("description") or "")[:1000]}

def gcal_meeting_body(title, start, duration, link, notes):
    from datetime import timedelta
    st = datetime.strptime(start, "%Y-%m-%d %H:%M"); en = st + timedelta(minutes=int(duration))
    body = {"summary": title, "start": {"dateTime": st.astimezone().isoformat()}, "end": {"dateTime": en.astimezone().isoformat()},
            "description": ((notes or "") + "\n\nAdded from LeadPilot CRM").strip()}
    if link: body["location"] = link
    return body

class MonthPicker:
    """Compact dropdown of saved report months. Picking a month loads that report straight away."""
    def __init__(self, parent, on_change):
        self.on_change = on_change; self.ids = []; self.labels = []; self.cur = None
        self.var = tk.StringVar()
        self.cb = ttk.Combobox(parent, textvariable=self.var, state="readonly", width=44, font=("Segoe UI", 10))
        self.cb.bind("<<ComboboxSelected>>", lambda e: self.selection_set(self.ids[self.cb.current()]))
    def delete(self, *a): self.ids, self.labels = [], []; self.cb["values"] = []
    def get_children(self): return tuple(self.ids)
    def insert(self, _p, _i, iid, label):
        self.ids.append(iid); self.labels.append(label); self.cb["values"] = self.labels
    def exists(self, iid): return iid in self.ids
    def selection(self): return (self.cur,) if self.cur in self.ids else ()
    def selection_set(self, iid):
        if iid not in self.ids: return
        self.cur = iid; self.cb.current(self.ids.index(iid)); self.cb.selection_clear(); self.on_change()
    def see(self, iid): pass

class LeadPilot:
    def __init__(self, root):
        self.root = root
        self.root.title(f"LeadPilot CRM {APP_VERSION} | Upwork Business Development")
        # Fit the window to the screen's usable area (above the taskbar) so table scrollbars are never hidden
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        try:
            rc = (_ct.c_long * 4)(); _ct.windll.user32.SystemParametersInfoW(0x30, 0, rc, 0); sh = rc[3] - rc[1]
        except Exception: sh -= 48
        self.root.geometry(f"{min(1480, sw - 20)}x{min(900, sh - 40)}+0+0")
        try: self.root.state("zoomed")
        except tk.TclError: pass
        self.root.minsize(1000, 600)
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.init_db()
        self.style()
        self.build_ui()
        self.refresh_all()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def init_db(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS proposals(
          id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, member TEXT NOT NULL,
          job TEXT NOT NULL, client TEXT, url TEXT, proposal_date TEXT, bid REAL DEFAULT 0,
          connects INTEGER DEFAULT 0, status TEXT DEFAULT 'Submitted', views INTEGER DEFAULT 0,
          notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS leads(
          id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, member TEXT NOT NULL,
          name TEXT NOT NULL, company TEXT, source TEXT DEFAULT 'Upwork', proposal_id INTEGER,
          lead_date TEXT, status TEXT DEFAULT 'Qualified', budget REAL DEFAULT 0,
          next_followup TEXT, last_contact TEXT, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(proposal_id) REFERENCES proposals(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS meetings(
          id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id INTEGER, title TEXT NOT NULL, client TEXT,
          start TEXT NOT NULL, duration INTEGER DEFAULT 30, link TEXT, notes TEXT, status TEXT DEFAULT 'Scheduled',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(proposal_id) REFERENCES proposals(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS reports(month TEXT PRIMARY KEY, generated_at TEXT, data TEXT, auto INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS fu_events(id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER, at TEXT);
        """)
        if self.setting("fu_log_started") in (None, "", "0"):
            self.db.execute("INSERT OR REPLACE INTO settings(k,v) VALUES('fu_log_started',?)", (date.today().isoformat(),)); self.db.commit()
        have = {r[1] for r in self.db.execute("PRAGMA table_info(proposals)")}
        for col, _ in JOB_DETAIL_COLS:
            if col not in have:
                self.db.execute(f"ALTER TABLE proposals ADD COLUMN {col} TEXT")
        if "cover_letter" not in have:
            self.db.execute("ALTER TABLE proposals ADD COLUMN cover_letter TEXT")
        if "category" not in have:
            self.db.execute("ALTER TABLE proposals ADD COLUMN category TEXT")
        for col in ("connects_normal", "connects_boosted"):
            if col not in have:
                self.db.execute(f"ALTER TABLE proposals ADD COLUMN {col} INTEGER")
        # Record when each job was last imported, added or refreshed
        self.db.execute("""CREATE TRIGGER IF NOT EXISTS proposals_stamp_insert AFTER INSERT ON proposals
            BEGIN UPDATE proposals SET last_updated = strftime('%Y-%m-%d %H:%M', 'now', 'localtime') WHERE id = NEW.id; END""")
        self.db.execute("""CREATE TRIGGER IF NOT EXISTS proposals_stamp_update AFTER UPDATE ON proposals
            WHEN NEW.last_updated IS OLD.last_updated
            BEGIN UPDATE proposals SET last_updated = strftime('%Y-%m-%d %H:%M', 'now', 'localtime') WHERE id = NEW.id; END""")
        self.db.commit()
        lcols = {r[1] for r in self.db.execute("PRAGMA table_info(leads)")}
        for col, typ in (("fu_count", "INTEGER DEFAULT 0"), ("fu_anchor", "TEXT"), ("chat_start", "TEXT"), ("last_client_msg", "TEXT"),
                         ("last_preview", "TEXT"), ("job_title", "TEXT"), ("closed_reason", "TEXT"), ("sales_stage", "TEXT"), ("stage_at", "TEXT")):
            if col not in lcols: self.db.execute(f"ALTER TABLE leads ADD COLUMN {col} {typ}")
        mcols = {r[1] for r in self.db.execute("PRAGMA table_info(meetings)")}
        if "source" not in mcols: self.db.execute("ALTER TABLE meetings ADD COLUMN source TEXT DEFAULT 'LeadPilot'")
        if "gcal_id" not in mcols: self.db.execute("ALTER TABLE meetings ADD COLUMN gcal_id TEXT")
        defaults = {"target":"10", "view_rate":"40", "lead_rate":"25", "close_rate":"10",
                    "perf_target":"10", "perf_view_rate":"30", "perf_lead_rate":"60", "perf_close_rate":"20", "meet_alert_minutes":"60"}
        for k, v in defaults.items():
            self.db.execute("INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)", (k,v))
        self.db.commit()

    def style(self):
        # Premium navy + teal visual system
        self.colors = {
            "navy": "#14243A", "navy2": "#1C3554", "blue": "#2F6FED",
            "teal": "#16A6A1", "bg": "#F5F7FB", "surface": "#FFFFFF",
            "text": "#17263C", "muted": "#718096", "line": "#E2E8F0",
            "success": "#138A72", "danger": "#C2414B", "soft_blue": "#EAF1FF"
        }
        c = self.colors
        s = ttk.Style()
        try: s.theme_use("clam")
        except tk.TclError: pass
        self.root.configure(bg=c["bg"])
        s.configure(".", font=("Segoe UI", 9))
        s.configure("TFrame", background=c["bg"])
        s.configure("Surface.TFrame", background=c["surface"])
        s.configure("TLabel", background=c["bg"], foreground=c["text"], font=("Segoe UI", 9))
        s.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground=c["navy"])
        s.configure("Sub.TLabel", foreground=c["muted"], font=("Segoe UI", 9))
        s.configure("Section.TLabel", font=("Segoe UI", 12, "bold"), foreground=c["navy"])
        s.configure("Hero.TLabel", background=c["navy"], foreground="#FFFFFF",
                    font=("Segoe UI", 22, "bold"))
        s.configure("HeroSub.TLabel", background=c["navy"], foreground="#C7D4E5",
                    font=("Segoe UI", 9))
        s.configure("HeroTag.TLabel", background=c["navy2"], foreground="#BFEDEA",
                    font=("Segoe UI", 8, "bold"), padding=(10, 5))
        s.configure("TButton", padding=(12, 7), background="#E8EDF5",
                    foreground=c["navy"], borderwidth=0, font=("Segoe UI", 9, "bold"))
        s.map("TButton", background=[("active", "#DCE5F1"), ("pressed", "#D1DCEB")],
              foreground=[("disabled", "#9AA6B2")])
        s.configure("Accent.TButton", padding=(14, 8), background="#00866A",
                    foreground="#FFFFFF", borderwidth=0, font=("Segoe UI", 9, "bold"))
        s.map("Accent.TButton", background=[("active", "#005B4B"), ("pressed", "#004739")],
              foreground=[("active", "#FFFFFF")])
        s.configure("Danger.TButton", padding=(11, 7), background="#FCEBED",
                    foreground=c["danger"], borderwidth=0)
        s.configure("TNotebook", background=c["bg"], borderwidth=0, tabmargins=(0, 8, 0, 0))
        s.configure("TNotebook.Tab", padding=(17, 10), background="#E8EDF5",
                    foreground="#52627A", borderwidth=0, font=("Segoe UI", 9, "bold"))
        s.map("TNotebook.Tab", background=[("selected", c["navy"])],
              foreground=[("selected", "#FFFFFF")])
        s.configure("TLabelframe", background=c["surface"], bordercolor=c["line"],
                    relief="solid", borderwidth=1)
        s.configure("TLabelframe.Label", background=c["surface"], foreground=c["muted"],
                    font=("Segoe UI", 9, "bold"))
        s.configure("Treeview", rowheight=38, font=("Segoe UI", 9),
                    background="#FFFFFF", fieldbackground="#FFFFFF",
                    foreground="#343A40", borderwidth=0)
        s.configure("Treeview.Heading", background="#EEF2F7", foreground="#1E293B",
                    font=("Segoe UI", 9, "bold"), padding=(10, 11), relief="flat", borderwidth=0)
        s.map("Treeview.Heading", background=[("active", "#E0E7FF")])
        s.map("Treeview", background=[("selected", "#E0E7FF")],
              foreground=[("selected", c["navy"])])
        s.configure("TEntry", padding=7, fieldbackground="#FFFFFF")
        s.configure("TCombobox", padding=7, fieldbackground="#FFFFFF")
        s.configure("Horizontal.TScale", background=c["surface"], troughcolor="#DCE5F0")
        s.configure("TScrollbar", background="#E4EAF2", troughcolor=c["bg"],
                    bordercolor=c["bg"], arrowsize=12)
        # Thick, high-contrast horizontal scrollbar you can grab and drag
        s.configure("Wide.Horizontal.TScrollbar", arrowsize=18, width=18, background="#94A3B8", troughcolor="#E2E8F0",
                    bordercolor="#CBD5E1", lightcolor="#94A3B8", darkcolor="#64748B", gripcount=0)
        s.map("Wide.Horizontal.TScrollbar", background=[("active", "#4F46E5"), ("pressed", "#4338CA")])
    def build_ui(self):
        self.root.configure(bg=UI["bg"])
        outer = tk.Frame(self.root, bg=UI["bg"]); outer.pack(fill="both", expand=True)
        # Left sidebar — Emerald & White (visual only; navigation keys/commands unchanged)
        sidebar = tk.Frame(outer, bg=OV["side"], width=248, highlightthickness=1,
                           highlightbackground=OV["side_edge"], highlightcolor=OV["side_edge"])
        sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
        self.sidebar = sidebar
        brand = tk.Frame(sidebar, bg=OV["side"]); brand.pack(fill="x", padx=16, pady=(12, 8))
        mark = tk.Canvas(brand, width=36, height=36, bg=OV["side"], highlightthickness=0); mark.pack(side="left", padx=(0, 10))
        mark.create_oval(1, 1, 35, 35, fill=OV["emerald"], outline="")
        mark.create_text(18, 18, text="L", fill="#FFFFFF", font=("Segoe UI", 14, "bold"))
        words = tk.Frame(brand, bg=OV["side"]); words.pack(side="left", fill="x", expand=True)
        tk.Label(words, text="LeadPilot", bg=OV["side"], fg=OV["text"], font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(words, text="Upwork Sales Workspace", bg=OV["side"], fg=OV["side_muted"], font=("Segoe UI", 8)).pack(anchor="w")
        tk.Frame(sidebar, bg=OV["line"], height=1).pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(sidebar, text="MENU", bg=OV["side"], fg=OV["side_muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(0, 4))

        main = tk.Frame(outer, bg=UI["bg"]); main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=UI["card"], height=64, highlightthickness=1, highlightbackground=UI["line"])
        header.pack(fill="x"); header.pack_propagate(False)
        self.header_title = tk.Label(header, text="Overview", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 15, "bold"))
        self.header_title.pack(side="left", padx=26)
        tk.Label(header, text=date.today().strftime("%A, %d %B %Y"), bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9)).pack(side="left")
        self.conn_badge = tk.Label(header, text="", font=("Segoe UI", 9, "bold"), padx=12, pady=4)
        self.conn_badge.pack(side="right", padx=24)
        av = tk.Canvas(header, width=34, height=34, bg=UI["card"], highlightthickness=0); av.pack(side="right")
        av.create_oval(1, 1, 33, 33, fill="#E0E7FF", outline=""); av.create_text(17, 17, text="AY", fill=UI["accent"], font=("Segoe UI", 9, "bold"))

        content = tk.Frame(main, bg=UI["bg"]); content.pack(fill="both", expand=True)
        self.content_frame = content
        self.meet_banner = tk.Frame(main, bg="#FEF3C7", highlightthickness=1, highlightbackground="#F59E0B")
        self.meet_banner_lbl = tk.Label(self.meet_banner, text="", bg="#FEF3C7", fg="#92400E", font=("Segoe UI", 10, "bold"))
        self.meet_banner_lbl.pack(side="left", padx=18, pady=8)
        self.meet_banner_join = tk.Button(self.meet_banner, text="Open meeting link", relief="flat", bd=0, bg="#F59E0B", fg="#FFFFFF",
                                          font=("Segoe UI", 9, "bold"), padx=12, pady=4, cursor="hand2")
        tk.Button(self.meet_banner, text="View meetings", relief="flat", bd=0, bg="#FFFFFF", fg="#92400E", font=("Segoe UI", 9, "bold"),
                  padx=12, pady=4, cursor="hand2", command=lambda: self.show_page("meetings")).pack(side="right", padx=(6, 14))
        self.nb = ttk.Notebook(content)
        try: ttk.Style().layout("TNotebook.Tab", [])
        except tk.TclError: pass
        self.nb.pack(fill="both", expand=True, padx=22, pady=18)
        self.tabs = {}; self.nav_buttons = {}; self.nav_labels = {}
        self._active_nav = None
        self._api_key_active = False
        icons = {"dashboard": "\u25a6", "write_proposal": "\u270d", "proposals": "\u270e", "leads": "\u25ce", "followups": "\u21bb",
                 "planner": "\u25f7", "performance": "\u2197", "meetings": "\u25f4", "upwork": "\u26ad", "data": "\u21e9", "reports": "\u2630", "settings": "\u2699"}
        for key, label in [("dashboard","Overview"),("write_proposal","Write a proposal"),("proposals","Submitted Proposals"),("leads","Leads & Pipeline"),
                           ("followups","Follow-ups"),("performance","Performance"),("meetings","Meetings"),("reports","Reporting"),("upwork","Upwork Connection"),("data","Data & Backup"),("settings","Settings")]:
            frame = ttk.Frame(self.nb, padding=4); self.nb.add(frame, text=label); self.tabs[key] = frame
            self.nav_labels[key] = label
            btn = tk.Button(sidebar, text=f"   {icons[key]}    {label}", anchor="w", relief="flat", bd=0,
                bg=OV["side"], fg=OV["side_text"], activebackground=OV["side_hover"], activeforeground=OV["text"],
                font=("Segoe UI", 10), padx=12, pady=4, cursor="hand2", command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", padx=10, pady=1)
            self._bind_side_hover(btn, key)
            self.nav_buttons[key] = btn
        # API Key: a shortcut that opens Settings at the OpenAI key section
        self.api_key_btn = tk.Button(sidebar, text="   \u25c8    API Key", anchor="w", relief="flat", bd=0,
            bg=OV["side"], fg=OV["side_text"], activebackground=OV["side_hover"], activeforeground=OV["text"],
            font=("Segoe UI", 10), padx=12, pady=4, cursor="hand2", command=self.open_api_key)
        self.api_key_btn.pack(fill="x", padx=10, pady=1)
        self._bind_side_hover(self.api_key_btn, "api_key")
        # Fresh Audit: its own section, separate from the page menu
        af = ttk.Frame(self.nb, padding=4); self.nb.add(af, text="Fresh Audit"); self.tabs["audit"] = af
        self.nav_labels["audit"] = "Fresh Audit"
        tk.Frame(sidebar, bg=OV["line"], height=1).pack(fill="x", padx=14, pady=(8, 4))
        tk.Label(sidebar, text="AUDIT", bg=OV["side"], fg=OV["side_muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(0, 4))
        self.fresh_audit_btn = tk.Button(sidebar, text="   \u21ba    Fresh Audit", anchor="w", relief="flat", bd=0,
            bg=OV["mint"], fg=OV["emerald_dark"], activebackground=OV["emerald"], activeforeground="#FFFFFF",
            font=("Segoe UI", 10, "bold"), padx=12, pady=4, cursor="hand2", command=lambda: self.show_page("audit"))
        self.fresh_audit_btn.pack(fill="x", padx=10, pady=1)
        foot = tk.Frame(sidebar, bg=OV["side2"], highlightthickness=1, highlightbackground=OV["line"])
        foot.pack(side="bottom", fill="x", padx=10, pady=8)
        tk.Label(foot, text="Local desktop edition", bg=OV["side2"], fg=OV["side_muted"],
                 font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(6, 0))
        tk.Label(foot, text=f"LeadPilot CRM {APP_VERSION}", bg=OV["side2"], fg=OV["emerald_dark"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(1, 6))

        self.make_dashboard()
        self.make_write_proposal()
        self.make_proposals()
        self.make_leads()
        self.make_followups()
        self.make_performance()
        self.make_meetings()
        self.make_reports()
        self.make_upwork()
        self.make_audit()
        self.make_data()
        self.make_settings()
        self.update_conn_badge()
        self.show_page("dashboard")
        self._meet_alerted = set()
        self.root.after(1500, self.meet_tick)
        self.root.after(3000, self.reports_auto)

    def _bind_side_hover(self, btn, key):
        """Subtle hover for inactive sidebar items (Emerald & White sidebar only)."""
        def on_enter(_e, b=btn, k=key):
            if self._api_key_active and k == "api_key":
                return
            if getattr(self, "_active_nav", None) == k:
                return
            if k == "api_key" and getattr(self, "_active_nav", None) == "settings" and self._api_key_active:
                return
            b.configure(bg=OV["side_hover"])
        def on_leave(_e, b=btn, k=key):
            if self._api_key_active and k == "api_key":
                return
            if getattr(self, "_active_nav", None) == k:
                return
            b.configure(bg=OV["side"])
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

    def _style_nav_btn(self, btn, active):
        if active:
            btn.configure(bg=OV["mint"], fg=OV["emerald_dark"], font=("Segoe UI", 10, "bold"),
                          activebackground=OV["mint"], activeforeground=OV["emerald_dark"])
        else:
            btn.configure(bg=OV["side"], fg=OV["side_text"], font=("Segoe UI", 10, "normal"),
                          activebackground=OV["side_hover"], activeforeground=OV["text"])

    def update_conn_badge(self):
        ok = False
        if _keyring is not None:
            try: e, pw = get_upwork_login(); ok = bool(e and pw)
            except Exception: ok = False
        if ok: self.conn_badge.config(text="\u25cf  Upwork connected", fg="#047857", bg="#ECFDF5")
        else:  self.conn_badge.config(text="\u25cf  Upwork disconnected", fg="#DC2626", bg="#FEF2F2")

    def show_page(self, key):
        self.nb.select(self.tabs[key])
        if key == "performance" and hasattr(self, "perf_vars"): self.perf_refresh()
        if key == "meetings" and hasattr(self, "mtree_up"): self.meet_refresh()
        if key == "reports" and hasattr(self, "rep_list"): self.report_generate("SAMPLE", quiet=True)
        if key == "settings" and getattr(self, "set_key_entry", None) is not None: self.settings_refresh_key_status()
        if key == "write_proposal" and getattr(self, "write_page", None) is not None:
            self.write_page.refresh()
        self.header_title.config(text=self.nav_labels.get(key, ""))
        self._active_nav = key
        self._api_key_active = False
        for name, btn in self.nav_buttons.items():
            self._style_nav_btn(btn, name == key)
        if getattr(self, "api_key_btn", None) is not None:
            self._style_nav_btn(self.api_key_btn, False)
        if key == "settings": self.settings_show("ai")
        if hasattr(self, "fresh_audit_btn"):
            if key == "audit":
                self.fresh_audit_btn.configure(bg=OV["emerald"], fg="#FFFFFF", relief="flat",
                                               activebackground=OV["emerald_dark"], activeforeground="#FFFFFF")
            else:
                self.fresh_audit_btn.configure(bg=OV["mint"], fg=OV["emerald_dark"], relief="flat",
                                               activebackground=OV["emerald"], activeforeground="#FFFFFF")

    def section_title(self, parent, title, subtitle=""):
        ttk.Label(parent, text=title, style="Title.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(parent, text=subtitle, style="Sub.TLabel").pack(anchor="w", pady=(4, 12))

    def make_tree(self, parent, columns, headings, widths):
        wrap = ttk.Frame(parent); wrap.pack(fill="both", expand=True, pady=8)
        tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="extended")
        sy = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        sx = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview, style="Wide.Horizontal.TScrollbar")
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tree.grid(row=0,column=0,sticky="nsew"); sy.grid(row=0,column=1,sticky="ns")
        sx.grid(row=1,column=0,sticky="ew",pady=(2,0))
        wrap.rowconfigure(0,weight=1); wrap.columnconfigure(0,weight=1)
        for i, (col, head, width) in enumerate(zip(columns, headings, widths)):
            # fixed widths (only the last column stretches) so wide tables scroll sideways instead of squeezing
            tree.heading(col, text=head); tree.column(col, width=width, minwidth=40, stretch=(i == len(columns) - 1))
        tree.tag_configure("overdue", foreground=self.colors["danger"], background="#FFF3F3")
        tree.tag_configure("odd", background="#F8FAFD")
        tree.tag_configure("even", background="#FFFFFF")
        for st, (fg, bg) in STATUS_COLORS.items():
            tree.tag_configure("st_" + st, foreground=fg, background=bg)
        self._add_grid_lines(tree, sx)
        return tree

    # Columns that hold long free text: left-aligned and capped. Everything else is centered and sized to fit.
    LONG_COLS = {"preview": 460, "job": 300, "title": 320, "notes": 360, "message": 460, "flag": 360, "description": 360, "subject": 320}
    def _autofit(self, tree):
        import tkinter.font as _tkf
        body = _tkf.Font(family="Segoe UI", size=9); head = _tkf.Font(family="Segoe UI", size=9, weight="bold")
        cols = list(tree["columns"]); kids = tree.get_children(); fit = []
        for i, c in enumerate(cols):
            texts = [str(tree.set(k, c)) for k in kids]
            data_w = max([body.measure(t) for t in texts] + [0]); head_w = head.measure(tree.heading(c, "text"))
            long_col = c in self.LONG_COLS or data_w > 200
            cap = self.LONG_COLS.get(c, 320)
            w = max(head_w + 26, min(data_w + (34 if long_col else 26), cap if long_col else 10_000), 44)
            anchor = "w" if long_col else "center"
            tree.column(c, width=w, minwidth=min(w, 40), anchor=anchor, stretch=False)  # never let Tk squeeze a column
            tree.heading(c, anchor=anchor); fit.append(w)
        tree._fit_widths = fit; tree._fit_W = None
        self._spread_cols(tree)

    def _spread_cols(self, tree):
        """If the table is narrower than the window, share the spare width across all columns so the row fills it."""
        fit = getattr(tree, "_fit_widths", None)
        if not fit: return
        try: W = tree.winfo_width()
        except tk.TclError: return
        if W <= 1 or W == getattr(tree, "_fit_W", None): return
        tree._fit_W = W
        cols = list(tree["columns"]); total = sum(fit); extra = W - total - 4
        widths = list(fit)
        if extra > 0:
            add = [int(extra * w / total) for w in fit]; add[-1] += extra - sum(add)
            widths = [w + a for w, a in zip(fit, add)]
        for c, w in zip(cols, widths): tree.column(c, width=w)

    def _add_grid_lines(self, tree, sx):
        """Thin vertical lines between columns plus a line under the header (ttk tables have none built in)."""
        lines = []; hline = tk.Frame(tree, bg="#CBD5E1", height=1); state = {"sig": None}
        def draw(*_):
            try:
                cols = list(tree["columns"]); widths = [int(tree.column(c, "width")) for c in cols]
                total = sum(widths); off = int(round(total * float(tree.xview()[0]))); W = tree.winfo_width()
                sig = (tuple(widths), off, W, tree.winfo_height())
                if sig == state["sig"]: return
                state["sig"] = sig
                while len(lines) < len(cols) - 1: lines.append(tk.Frame(tree, bg="#E2E8F0", width=1))
                x = 0
                for i, w in enumerate(widths[:-1]):
                    x += w; px = x - off
                    if 0 < px < W: lines[i].place(x=px - 1, y=0, width=1, relheight=1)
                    else: lines[i].place_forget()
                kids = tree.get_children(); b = tree.bbox(kids[0]) if kids else None
                if b: hline.place(x=0, y=b[1] - 1, relwidth=1, height=1)
            except tk.TclError: pass
        def on_x(a, b):
            sx.set(a, b); draw()
        tree.configure(xscrollcommand=on_x)
        tree.bind("<Configure>", lambda e: (self._spread_cols(tree), draw()), add="+"); tree.bind("<ButtonRelease-1>", lambda e: tree.after(10, draw), add="+")
        def loop():
            try:
                sig = tuple(tree.item(i, "values") for i in tree.get_children())
                if sig != state.get("data"): state["data"] = sig; self._autofit(tree)
            except tk.TclError: return
            draw(); tree.after(400, loop)
        tree.after(200, loop)

    def card(self, parent, **pack):
        c = tk.Frame(parent, bg=UI["card"], highlightthickness=1, highlightbackground=UI["line"])
        if pack: c.pack(**pack)
        return c

    def ov_card(self, parent, **pack):
        """Overview-only card (Emerald & White). Does not affect other pages."""
        c = tk.Frame(parent, bg=OV["card"], highlightthickness=1, highlightbackground=OV["line"])
        if pack: c.pack(**pack)
        return c

    def make_dashboard(self):
        p = self.tabs["dashboard"]
        cv = tk.Canvas(p, bg=OV["bg"], highlightthickness=0); sb = ttk.Scrollbar(p, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y"); cv.pack(side="left", fill="both", expand=True)
        page = tk.Frame(cv, bg=OV["bg"]); win = cv.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units") if self.nb.index("current") == 0 else None)

        hero = tk.Canvas(page, height=156, bg=OV["bg"], highlightthickness=0); hero.pack(fill="x", pady=(0, 18))
        def draw_hero(e=None):
            hero.delete("bg"); w = hero.winfo_width() or 1000
            steps = 60
            for i in range(steps):
                r1, g1, b1 = 0x00, 0x86, 0x6A; r2, g2, b2 = 0x00, 0x5B, 0x4B
                t = i / steps; col = "#%02x%02x%02x" % (int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))
                hero.create_rectangle(w * i / steps, 0, w * (i + 1) / steps + 1, 156, fill=col, outline="", tags="bg")
            hero.create_oval(w - 200, -70, w + 40, 180, fill="#1A9A7E", outline="", tags="bg")
            hero.create_oval(w - 100, 70, w + 50, 210, fill="#147A65", outline="", tags="bg")
            hero.create_text(30, 40, anchor="w", text="Welcome back, Ammar", fill="#FFFFFF", font=("Segoe UI", 20, "bold"), tags="bg")
            hero.create_text(30, 75, anchor="w", text="Turn Upwork opportunities into consistent client wins.", fill="#DDF5EC", font=("Segoe UI", 10), tags="bg")
            hero.tag_lower("bg")
        hero.bind("<Configure>", draw_hero)
        btns = tk.Frame(hero, bg=OV["emerald"]); hero.create_window(30, 116, anchor="w", window=btns)
        tk.Button(btns, text="+  Add New Proposal", command=self.add_new_proposal, bg="#FFFFFF", fg=OV["emerald_dark"], relief="flat", bd=0,
                  padx=14, pady=7, font=("Segoe UI", 9, "bold"), cursor="hand2",
                  activebackground=OV["mint"], activeforeground=OV["emerald_dark"]).pack(side="left", padx=(0, 8))
        tk.Button(btns, text="Write a proposal", command=self.open_write_proposal_new_draft, bg="#FFFFFF", fg=OV["emerald_dark"], relief="flat", bd=0,
                  padx=14, pady=7, font=("Segoe UI", 9, "bold"), cursor="hand2",
                  activebackground=OV["mint"], activeforeground=OV["emerald_dark"]).pack(side="left", padx=(0, 8))
        # Same solid action color as Accent.TButton / UI["accent"] (Design QA)
        tk.Button(btns, text="Follow-ups", command=lambda: self.show_page("followups"), bg=OV["emerald"], fg="#FFFFFF",
                  relief="flat", bd=0, padx=14, pady=7, font=("Segoe UI", 9, "bold"), cursor="hand2",
                  activebackground=OV["emerald_dark"], activeforeground="#FFFFFF").pack(side="left", padx=(0, 8))
        # Add Lead stays on Leads & Pipeline only (removed from Overview banner)

        kp = tk.Frame(page, bg=OV["bg"]); kp.pack(fill="x", pady=(0, 18))
        self.kpis = {}
        specs = [("Total Proposals", "submitted", "\u270e", OV["emerald"], OV["mint"]),
                 ("Proposal Views", "views", "\u25c9", OV["emerald_dark"], OV["mint"]),
                 ("Qualified Leads", "qualified", "\u25ce", OV["emerald"], "#ECF8F3"),
                 ("Clients Won", "won", "\u2605", OV["success"], OV["mint"])]
        for i, (label, key, icon, col, soft) in enumerate(specs):
            kp.grid_columnconfigure(i, weight=1, uniform="k")
            c = tk.Frame(kp, bg=OV["card"], highlightthickness=1, highlightbackground=OV["line"])
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            tk.Frame(c, bg=col, height=3).pack(fill="x")
            inner = tk.Frame(c, bg=OV["card"]); inner.pack(fill="both", expand=True, padx=18, pady=16)
            # Centered card: icon badge, big number, then label
            tk.Label(inner, text=icon, bg=soft, fg=col, font=("Segoe UI", 12, "bold"), width=3).pack(anchor="center")
            v = tk.Label(inner, text="0", bg=OV["card"], fg=OV["text"], font=("Segoe UI", 24, "bold")); v.pack(anchor="center", pady=(8, 0))
            tk.Label(inner, text=label, bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="center", pady=(2, 0))
            self.kpis[key] = v

        pc = self.ov_card(page, fill="x", pady=(0, 18))
        tk.Label(pc, text="Proposal pipeline", bg=OV["card"], fg=OV["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=18, pady=(16, 10))
        self.status_row = tk.Frame(pc, bg=OV["card"]); self.status_row.pack(fill="x", padx=18, pady=(0, 16))

        jc = self.ov_card(page, fill="x", pady=(0, 18))
        jh = tk.Frame(jc, bg=OV["card"]); jh.pack(fill="x", padx=18, pady=(16, 4))
        tk.Label(jh, text="Upwork Jobs - Details at a Glance", bg=OV["card"], fg=OV["text"], font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Button(jh, text="\u21bb  Refresh", command=self.refresh_all, bg=OV["mint"], fg=OV["emerald_dark"], relief="flat", bd=0,
                  padx=10, pady=4, font=("Segoe UI", 8, "bold"), cursor="hand2",
                  activebackground="#C8EDE0", activeforeground=OV["emerald_dark"]).pack(side="right")
        tk.Label(jc, text="Click a job to see full details. Rows are colored by status.", bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=18)
        jw = tk.Frame(jc, bg=OV["card"], height=260); jw.pack(fill="x", padx=10, pady=8); jw.pack_propagate(False)
        jcols = ("id","job","client","status","category","connects") + tuple(c for c, _ in JOB_DETAIL_COLS)
        jheads = ("ID","Job Title","Client","Status","Category","Connects") + tuple(h for _, h in JOB_DETAIL_COLS)
        jwidths = [45,260,200,95,90,75,110,240,170,150,80,80,100,70,70,160,150,90,90,120,110,120,150]
        self.jtree = self.make_tree(jw, jcols, jheads, jwidths)
        self.jtree.bind("<<TreeviewSelect>>", self.show_job_detail)

        self.detail_card = self.ov_card(page, fill="x", pady=(0, 18))
        self.job_detail = tk.Frame(self.detail_card, bg=OV["card"]); self.job_detail.pack(fill="x", padx=18, pady=16)
        tk.Label(self.job_detail, text="Select a job above to see its details here.", bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 9)).pack(anchor="w")

        lc = self.ov_card(page, fill="x")
        tk.Label(lc, text="Latest leads", bg=OV["card"], fg=OV["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
        lw = tk.Frame(lc, bg=OV["card"], height=240); lw.pack(fill="x", padx=10, pady=(0, 12)); lw.pack_propagate(False)
        self.dtree = self.make_tree(lw, ("id","name","company","source","lead_date","next_followup","status"),
            ("ID","Lead Name","Company","Source","Lead Date","Next Follow-up","Status"), [55,190,160,120,130,150,115])

    def draw_status_pills(self, proposals):
        for w in self.status_row.winfo_children(): w.destroy()
        counts = {}
        for r in proposals: counts[r["status"]] = counts.get(r["status"], 0) + 1
        for i, st in enumerate(PROPOSAL_STATUSES):
            fg, bg = STATUS_COLORS.get(st, ("#475569", "#F1F5F9"))
            self.status_row.grid_columnconfigure(i, weight=1, uniform="ps")
            box = tk.Frame(self.status_row, bg=bg, highlightthickness=1, highlightbackground=OV["line"])
            box.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            tk.Label(box, text=str(counts.get(st, 0)), bg=bg, fg=fg, font=("Segoe UI", 14, "bold")).pack(padx=14, pady=(8, 0))
            tk.Label(box, text=st, bg=bg, fg=fg, font=("Segoe UI", 8, "bold")).pack(padx=14, pady=(2, 8))

    def detail_row(self, parent, label, value, color=None):
        # Used only by Overview job details
        row = tk.Frame(parent, bg=OV["card"]); row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
        if color:
            pill(row, value or "-", color[0], color[1], 9).pack(side="left")
        else:
            tk.Label(row, text=value or "-", bg=OV["card"], fg=OV["text"], font=("Segoe UI", 10, "bold"),
                     anchor="w", justify="left", wraplength=330).pack(side="left", fill="x")
        tk.Frame(parent, bg=OV["line"], height=1).pack(fill="x")

    def panel(self, parent, title, icon, col, column):
        # Used only by Overview job details
        c = tk.Frame(parent, bg=OV["card"], highlightthickness=1, highlightbackground=OV["line"])
        c.grid(row=0, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
        tk.Frame(c, bg=col, height=3).pack(fill="x")
        h = tk.Frame(c, bg=OV["card"]); h.pack(fill="x", padx=16, pady=(12, 8))
        tk.Label(h, text=icon, bg=OV["card"], fg=col, font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 8))
        tk.Label(h, text=title, bg=OV["card"], fg=OV["text"], font=("Segoe UI", 12, "bold")).pack(side="left")
        body = tk.Frame(c, bg=OV["card"]); body.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        return body

    def show_job_detail(self, event=None):
        import re as _re, webbrowser
        sel = self.jtree.selection()
        if not sel: return
        r = self.db.execute("SELECT * FROM proposals WHERE id=?", (int(sel[0]),)).fetchone()
        if not r: return
        g = lambda k: (r[k] if k in r.keys() and r[k] not in (None, "") else "")
        num = lambda v: float(_re.search(r"[\d.]+", v.replace(",", "")).group()) if v and _re.search(r"\d", v) else None
        GREEN, AMBER, RED, GRAY = (OV["success"], OV["mint"]), ("#B45309", "#FFFBEB"), (OV["danger"], "#FEF2F2"), (OV["muted"], "#F3F7F5")
        YELLOW = ("#A16207", "#FEF9C3")
        hr_color = lambda v: GREEN if v > 50 else YELLOW if v >= 40 else AMBER if v >= 35 else RED
        for w in self.job_detail.winfo_children(): w.destroy()

        # Title bar
        top = tk.Frame(self.job_detail, bg=OV["card"]); top.pack(fill="x")
        left = tk.Frame(top, bg=OV["card"]); left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=r["job"], bg=OV["card"], fg=OV["text"], font=("Segoe UI", 14, "bold"), wraplength=780, justify="left").pack(anchor="w")
        ttk.Button(top, text="\U0001F4C5  Schedule meeting", command=lambda pid=r["id"]: self.add_meeting(pid)).pack(side="right", anchor="n", padx=(8, 0))
        tags = tk.Frame(left, bg=OV["card"]); tags.pack(anchor="w", pady=(6, 0))
        pill(tags, r["status"], *STATUS_COLORS.get(r["status"], GRAY), 9).pack(side="left", padx=(0, 6))
        if g("category") == "Boosted": pill(tags, "\u26a1 Boosted", "#C2410C", "#FFEDD5", 9).pack(side="left", padx=(0, 6))
        elif g("category") == "Normal": pill(tags, "Normal", OV["emerald"], OV["mint"], 9).pack(side="left", padx=(0, 6))
        if r["connects_normal"] and r["connects_boosted"]:
            pill(tags, f"{r['connects_normal']} normal + {r['connects_boosted']} boosted connects", OV["muted"], "#F3F7F5", 9).pack(side="left", padx=(0, 6))
        elif r["connects"]: pill(tags, f"{r['connects']} connects", OV["muted"], "#F3F7F5", 9).pack(side="left", padx=(0, 6))
        if g("budget_text"): pill(tags, g("budget_text"), OV["emerald_dark"], OV["mint"], 9).pack(side="left", padx=(0, 6))
        _nm = self.db.execute("SELECT start FROM meetings WHERE proposal_id=? AND status='Scheduled' AND start>=? ORDER BY start LIMIT 1",
                              (r["id"], datetime.now().strftime("%Y-%m-%d %H:%M"))).fetchone()
        if _nm: pill(tags, "\U0001F4C5 Meeting " + datetime.strptime(_nm["start"], "%Y-%m-%d %H:%M").strftime("%a %d %b, %I:%M %p"), OV["emerald_dark"], OV["mint"], 9).pack(side="left", padx=(0, 6))
        tk.Label(tags, text="\u23f1 Last updated: " + (g("last_updated") or "not recorded yet"), bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 9)).pack(side="right", padx=6)
        if g("client"): tk.Label(tags, text="Client: " + g("client"), bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 9)).pack(side="left", padx=6)
        if g("url"):
            tk.Button(top, text="Open on Upwork  \u2197", command=lambda u=g("url"): webbrowser.open(u), bg=OV["emerald"], fg="#FFFFFF",
                      relief="flat", bd=0, padx=14, pady=7, font=("Segoe UI", 9, "bold"), cursor="hand2",
                      activebackground=OV["emerald_dark"], activeforeground="#FFFFFF").pack(side="right", anchor="n")

        # Quick signals
        hr, props = num(g("hire_rate")), num(g("proposals_count"))
        pv = g("payment_verified").lower()
        sig = tk.Frame(self.job_detail, bg=OV["card"]); sig.pack(fill="x", pady=(12, 10))
        tk.Label(sig, text="Quick signals", bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 10))
        if pv: pill(sig, "\u2714 Payment verified" if pv.startswith(("y", "v")) else "\u2716 Payment not verified", *(GREEN if pv.startswith(("y", "v")) else RED)).pack(side="left", padx=(0, 6))
        if hr is not None: pill(sig, f"Hire rate {g('hire_rate')}", *hr_color(hr)).pack(side="left", padx=(0, 6))
        if props is not None: pill(sig, f"Competition: {g('proposals_count')} proposals", *(GREEN if props < 10 else AMBER if props < 30 else RED)).pack(side="left", padx=(0, 6))
        if g("interviewing"): pill(sig, f"Interviewing {g('interviewing')}", *GRAY).pack(side="left", padx=(0, 6))

        # Two side-by-side panels
        grid = tk.Frame(self.job_detail, bg=OV["card"]); grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="p"); grid.grid_columnconfigure(1, weight=1, uniform="p")

        cl = self.panel(grid, "Client History", "\u263a", OV["emerald"], 0)
        self.detail_row(cl, "Rating", g("rating"))
        self.detail_row(cl, "Hire rate", g("hire_rate"), hr_color(hr) if hr is not None else None)
        self.detail_row(cl, "Total spent", g("total_spent"))
        self.detail_row(cl, "Location", g("location"))
        self.detail_row(cl, "Member since", g("member_since"))
        self.detail_row(cl, "Payment verified", g("payment_verified") or "Unknown", (GREEN if pv.startswith(("y", "v")) else RED) if pv else GRAY)
        self.detail_row(cl, "Last viewed", g("last_viewed"))

        ja = self.panel(grid, "Job Activity", "\u2630", OV["emerald_dark"], 1)
        tiles = tk.Frame(ja, bg=OV["card"]); tiles.pack(fill="x", pady=(0, 8))
        for i, (lab, key, col) in enumerate([("Proposals", "proposals_count", OV["emerald"]), ("Interviewing", "interviewing", OV["emerald_dark"]),
                                             ("Invites sent", "invites_sent", "#147A65"), ("Unanswered", "unanswered_invites", "#B45309")]):
            tiles.grid_columnconfigure(i, weight=1, uniform="t")
            t = tk.Frame(tiles, bg="#F7FBF9", highlightthickness=1, highlightbackground=OV["line"])
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
            tk.Label(t, text=g(key) or "-", bg="#F7FBF9", fg=col, font=("Segoe UI", 15, "bold")).pack(pady=(8, 0))
            tk.Label(t, text=lab, bg="#F7FBF9", fg=OV["muted"], font=("Segoe UI", 8, "bold")).pack(pady=(0, 8))
        self.detail_row(ja, "Status", r["status"], STATUS_COLORS.get(r["status"], GRAY))
        self.detail_row(ja, "Budget", g("budget_text"))
        sk = tk.Frame(ja, bg=OV["card"]); sk.pack(fill="x", pady=4)
        tk.Label(sk, text="Skills", bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 9), width=18, anchor="w").pack(side="left", anchor="n")
        chips = tk.Frame(sk, bg=OV["card"]); chips.pack(side="left", fill="x")
        skills = [x.strip() for x in _re.split(r"[,;|]", g("skills")) if x.strip()] or ["-"]
        for i, x in enumerate(skills[:8]):
            pill(chips, x, OV["emerald_dark"], OV["mint"]).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 4), pady=2)
        tk.Frame(ja, bg=OV["line"], height=1).pack(fill="x")
        tk.Label(ja, text="Description", bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 2))
        tk.Label(ja, text=g("summary") or "-", bg=OV["card"], fg=OV["text"], font=("Segoe UI", 9), wraplength=470, justify="left").pack(anchor="w")

        # Proposal / cover letter section (collapsed by default, click the header to expand)
        pc = tk.Frame(self.job_detail, bg=OV["card"], highlightthickness=1, highlightbackground=OV["line"]); pc.pack(fill="x", pady=(14, 0))
        tk.Frame(pc, bg=OV["emerald"], height=3).pack(fill="x")
        ph = tk.Frame(pc, bg=OV["card"], cursor="hand2"); ph.pack(fill="x", padx=16, pady=10)
        arrow = tk.Label(ph, text="\u25b8", bg=OV["card"], fg=OV["emerald"], font=("Segoe UI", 12, "bold"), cursor="hand2"); arrow.pack(side="left", padx=(0, 8))
        title = tk.Label(ph, text="Proposal / cover letter", bg=OV["card"], fg=OV["text"], font=("Segoe UI", 12, "bold"), cursor="hand2"); title.pack(side="left")
        letter = g("cover_letter")
        hint = tk.Label(ph, text="Click to expand" if letter else "No proposal saved yet", bg=OV["card"], fg=OV["muted"], font=("Segoe UI", 8), cursor="hand2")
        hint.pack(side="left", padx=10)
        body = tk.Frame(pc, bg=OV["card"])
        if letter:
            def copy_letter(t=letter):
                self.root.clipboard_clear(); self.root.clipboard_append(t)
            tk.Button(body, text="Copy", command=copy_letter, bg=OV["mint"], fg=OV["emerald_dark"], relief="flat", bd=0, padx=10, pady=3,
                      font=("Segoe UI", 8, "bold"), cursor="hand2").pack(anchor="e", padx=16, pady=(0, 6))
            box = tk.Text(body, height=min(16, max(6, letter.count("\n") + 3)), wrap="word", bg="#F7FBF9", fg=OV["text"], relief="flat",
                          font=("Segoe UI", 10), padx=14, pady=10, highlightthickness=1, highlightbackground=OV["line"])
            box.insert("1.0", letter); box.configure(state="disabled"); box.pack(fill="x", padx=16, pady=(0, 14))
        else:
            tk.Label(body, text="No cover letter saved for this job.", bg=OV["card"],
                     fg=OV["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 14))
        state = {"open": False}
        def toggle(e=None):
            state["open"] = not state["open"]
            if state["open"]:
                body.pack(fill="x"); arrow.config(text="\u25be"); hint.config(text="Click to collapse" if letter else "No proposal saved yet")
            else:
                body.pack_forget(); arrow.config(text="\u25b8"); hint.config(text="Click to expand" if letter else "No proposal saved yet")
        for w in (ph, arrow, title, hint): w.bind("<Button-1>", toggle)
        self._toggle_proposal = toggle

        # Connects section (values from the Add New Proposal popup)
        cc = tk.Frame(self.job_detail, bg=OV["card"], highlightthickness=1, highlightbackground=OV["line"]); cc.pack(fill="x", pady=(14, 0))
        tk.Frame(cc, bg=OV["emerald_dark"], height=3).pack(fill="x")
        chd = tk.Frame(cc, bg=OV["card"]); chd.pack(fill="x", padx=16, pady=(10, 6))
        tk.Label(chd, text="\u25c8", bg=OV["mint"], fg=OV["emerald"], font=("Segoe UI", 10, "bold"), width=3).pack(side="left", padx=(0, 8))
        tk.Label(chd, text="Connects", bg=OV["card"], fg=OV["text"], font=("Segoe UI", 12, "bold")).pack(side="left")
        cn, cb, ct = r["connects_normal"], r["connects_boosted"], r["connects"]
        # Always show all three tiles; a missing value shows as 0.
        # Total is Normal + Boosted; older jobs with only a single connects number keep that number as Total.
        total = (cn or 0) + (cb or 0) if (cn or cb) else (ct or 0)
        tiles = [("Normal", cn or 0, OV["emerald"], OV["mint"]), ("Boosted", cb or 0, "#C2410C", "#FFEDD5"), ("Total", total, OV["emerald_dark"], "#ECF8F3")]
        crow = tk.Frame(cc, bg=OV["card"]); crow.pack(fill="x", padx=16, pady=(0, 14))
        for i, (lab, val, fg, soft) in enumerate(tiles):
            t = tk.Frame(crow, bg=soft); t.pack(side="left", padx=(0, 10))
            tk.Label(t, text=str(val), bg=soft, fg=fg, font=("Segoe UI", 18, "bold"), width=7).pack(padx=14, pady=(8, 0))
            tk.Label(t, text=lab, bg=soft, fg=fg, font=("Segoe UI", 9, "bold")).pack(padx=14, pady=(0, 8))

    def draw_dashboard_visuals(self, leads):
        # Dashboard follows the supplied reference: clean KPI cards and a lead table.
        return

    def make_write_proposal(self):
        p = self.tabs["write_proposal"]
        if write_proposal_page is None:
            ttk.Label(p, text="The Write a proposal page could not load.", style="Sub.TLabel").pack(anchor="w")
            return
        # Emerald & White palette for Write a proposal only (other pages keep UI).
        write_ui = {
            "bg": OV["bg"], "card": OV["card"], "line": OV["line"], "text": OV["text"],
            "muted": OV["muted"], "accent": OV["emerald"], "accent2": OV["emerald_dark"],
            "mint": OV["mint"], "green": OV["success"], "red": OV["danger"],
            "side": OV["side"], "side2": OV["side2"], "side_text": OV["side_text"],
        }
        self.write_page = write_proposal_page.build_page(
            p, write_ui, get_conn=lambda: self.db,
            on_open_settings=self.open_api_key,
            on_submitted=lambda proposal_id: self.refresh_all(),
            parse_hook=parse_proposal_page,
            window_read_hook=self.write_proposal_read_window,
            fetch_job_hook=self.write_proposal_fetch_job,
        )
        self.write_page.frame.pack(fill="both", expand=True)

    def open_write_proposal_new_draft(self):
        """Home banner: open Write a proposal and start a new draft."""
        self.show_page("write_proposal")
        if getattr(self, "write_page", None) is not None:
            self.write_page.new_draft()

    def write_proposal_read_window(self, url):
        """Read-only: reuse the Fresh Audit read (bring the open Upwork window forward, Ctrl+A, Ctrl+C) and return the copied text.
        No clicks or typing in Upwork. Returns None when no readable window is found or nothing was copied.
        If no window title mentions Upwork, falls back to the last-used browser window and keeps the text only if it mentions Upwork."""
        try:
            hwnd = find_upwork_window()
            fallback = False
            if not hwnd:
                hwnd = find_job_browser_window()
                fallback = True
            if not hwnd:
                return None
            clear_clipboard()
            copy_window_text(hwnd)
            text = read_clipboard_text() or ""
            if len(text.strip()) <= 40:
                return None
            if fallback and "upwork" not in text.lower():
                return None
            return text
        except Exception:
            return None
        finally:
            try:
                self.root.after(300, lambda: (self.root.deiconify(), self.root.lift(), self.root.focus_force()))
            except Exception:
                pass

    def write_proposal_fetch_job(self, url, on_done):
        """Open the Upwork job URL in the default browser, then poll the existing
        window-read (logged-in session) and call on_done(text, error) on the UI thread.
        Never bypasses login or automates Upwork beyond open + clipboard read."""
        import threading
        import time
        import webbrowser

        def finish(text, err):
            try:
                self.root.after(0, lambda: on_done(text, err))
            except Exception:
                try:
                    on_done(text, err)
                except Exception:
                    pass

        try:
            webbrowser.open(url)
        except Exception:
            finish(None, "Could not open the job link in your browser.")
            return

        def work():
            text = None
            for i in range(12):
                time.sleep(1.5 if i == 0 else 0.75)
                try:
                    text = self.write_proposal_read_window(url)
                except Exception:
                    text = None
                if text and str(text).strip():
                    finish(text, None)
                    return
            finish(
                None,
                "Could not read the job page. Keep Upwork open and logged in on that job, "
                "or copy the page (Ctrl+A, Ctrl+C) and use Paste from clipboard.",
            )

        threading.Thread(target=work, daemon=True).start()

    def make_proposals(self):
        p = self.tabs["proposals"]
        self.section_title(p, "Submitted Proposals", "Record each proposal and update its progress through the Upwork funnel.")
        bar = ttk.Frame(p); bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="＋  Add proposal", style="Accent.TButton", command=self.add_new_proposal).pack(side="left", padx=(0,8))
        ttk.Button(bar, text="Edit selected", command=self.edit_proposal).pack(side="left", padx=4)
        ttk.Button(bar, text="Delete selected", command=lambda:self.delete_selected(self.ptree,"proposals")).pack(side="left", padx=4)
        ttk.Button(bar, text="Export CSV", command=lambda:self.export_csv("proposals")).pack(side="right")
        self.ptree = self.make_tree(p, ("id","account","member","job","client","proposal_date","bid","connects","status","views"),
            ("ID","Upwork account","BD member","Job title","Client","Date","Bid $","Connects","Status","Views"),
            [48,130,125,240,150,100,80,75,110,70])
        self.ptree.bind("<Double-1>", lambda e:self.edit_proposal())

    def make_leads(self):
        p = self.tabs["leads"]
        self.section_title(p, "Leads & Deal Pipeline", "Track positive responses and move qualified prospects towards a contract.")
        bar = ttk.Frame(p); bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="＋  Add lead", style="Accent.TButton", command=self.add_lead).pack(side="left", padx=(0,8))
        ttk.Button(bar, text="Edit selected", command=self.edit_lead).pack(side="left", padx=4)
        ttk.Button(bar, text="\U0001F4DD Notes", command=lambda: self.lead_notes(self.ltree)).pack(side="left", padx=4)
        ttk.Button(bar, text="Delete selected", command=lambda:self.delete_selected(self.ltree,"leads")).pack(side="left", padx=4)
        ttk.Button(bar, text="Export CSV", command=lambda:self.export_csv("leads")).pack(side="right")
        self.ltree = self.make_tree(p, ("id","name","company","account","member","source","lead_date","status","budget","next_followup","proposal_id","notes"),
            ("ID","Lead name","Company","Account","BD member","Source","Lead date","Stage","Budget $","Next follow-up","Proposal ID","Notes"),
            [48,155,140,125,125,90,95,115,90,120,85,220])
        self.ltree.bind("<Double-1>", lambda e:self.edit_lead())

    def make_followups(self):
        p = self.tabs["followups"]
        # Emerald Follow-up Manager (visual only; cycle logic unchanged). Uses OV tokens.
        EM, DARK, MINT = OV["emerald"], OV["emerald_dark"], OV["mint"]
        MUTED, LINE, CARD = OV["muted"], "#B7DFCC", "#F3FBF7"
        try:
            sc = max(1.0, min(1.35, float(self.root.tk.call("tk", "scaling")) / 1.33))
        except Exception:
            sc = 1.0
        self._fu_ui_scale = sc
        self.fu_sub = ttk.Label(p, text="", style="Sub.TLabel")  # hidden text for callers/tests
        # Canvas shell = rounded outer card + mint corner washes (drawings visible in pad + under section canvases)
        shell = tk.Frame(p, bg=UI["bg"])
        shell.pack(fill="x", pady=(0, 10))
        card_h = int(200 * sc)
        self.fu_card_bg = tk.Canvas(shell, height=card_h, bg=UI["bg"], highlightthickness=0)
        self.fu_card_bg.pack(fill="x")
        self.fu_manager_card = self.fu_card_bg
        self.fu_orbit_card = self.fu_card_bg  # compat alias
        inner = tk.Frame(self.fu_card_bg, bg=CARD)
        self.fu_card_inner = inner
        self._fu_inner_win = self.fu_card_bg.create_window(10, 8, anchor="nw", window=inner)
        self.fu_card_bg.bind("<Configure>", self._fu_on_card_resize)
        # Left identity — stacked so title never clips
        left = tk.Frame(inner, bg=CARD, width=int(188 * sc))
        left.pack(side="left", fill="y", padx=(14, 6), pady=10)
        left.pack_propagate(False)
        self.fu_left_col = left
        iz = int(44 * sc)
        icon_box = tk.Canvas(left, width=iz, height=iz, bg=CARD, highlightthickness=0)
        icon_box.pack(anchor="w")
        self._fu_draw_icon_badge(icon_box, iz, EM, DARK)
        tk.Label(
            left, text="Follow-up Manager", bg=CARD, fg=DARK,
            font=("Segoe UI", int(13 * sc), "bold"), anchor="w", justify="left",
            wraplength=int(168 * sc),
        ).pack(anchor="w", pady=(8, 0))
        self.fu_cycle_kind = tk.Label(
            left, text="", bg=CARD, fg=MUTED,
            font=("Segoe UI", int(9 * sc)), anchor="w", justify="left",
            wraplength=int(168 * sc),
        )
        self.fu_cycle_kind.pack(anchor="w", pady=(2, 0))
        left_deco = tk.Canvas(left, height=int(48 * sc), bg=CARD, highlightthickness=0)
        left_deco.pack(side="bottom", fill="x", pady=(6, 0))
        self.fu_left_deco = left_deco
        # Center timeline
        center = tk.Frame(inner, bg=CARD)
        center.pack(side="left", fill="both", expand=True, padx=2, pady=6)
        self.fu_timeline_canvas = tk.Canvas(
            center, height=int(152 * sc), bg=CARD, highlightthickness=0,
        )
        self.fu_timeline_canvas.pack(fill="both", expand=True)
        self.fu_orbit_canvas = self.fu_timeline_canvas  # compat alias
        self.fu_timeline_canvas.bind("<Configure>", lambda e: self._fu_redraw_manager())
        self.fu_timeline_canvas.bind("<Motion>", self._fu_timeline_hover)
        self.fu_timeline_canvas.bind("<Leave>", lambda e: self._fu_timeline_tip(None))
        # Right column — wide enough for full summary pill text
        right = tk.Frame(inner, bg=CARD, width=int(248 * sc))
        right.pack(side="right", fill="y", padx=(8, 14), pady=8)
        right.pack_propagate(False)
        self.fu_right_col = right
        div = tk.Frame(inner, bg=LINE, width=1)
        div.place(x=0, rely=0.1, relheight=0.8)
        self.fu_right_div = div
        btn_wrap = tk.Frame(right, bg=EM, padx=1, pady=1)
        btn_wrap.pack(anchor="e")
        self.fu_set_cycle_btn = tk.Button(
            btn_wrap, text="\u2699  Set follow-up cycle", command=self.fu_set_cycle,
            bg="#FFFFFF", fg=DARK, relief="solid", bd=0,
            highlightthickness=1, highlightbackground=EM, highlightcolor=DARK,
            takefocus=1, padx=12, pady=6, font=("Segoe UI", int(9 * sc), "bold"),
            cursor="hand2", activebackground=MINT, activeforeground=DARK,
        )
        self.fu_set_cycle_btn.pack()
        ill_h, ill_w = int(54 * sc), int(84 * sc)
        ill = tk.Canvas(right, width=ill_w, height=ill_h, bg=CARD, highlightthickness=0)
        ill.pack(pady=(10, 6))
        self.fu_right_ill = ill
        self._fu_draw_cal_ill(ill, ill_w, ill_h, EM, DARK, MINT)
        right_deco = tk.Canvas(right, height=int(18 * sc), bg=CARD, highlightthickness=0)
        right_deco.pack(side="bottom", fill="x")
        self.fu_right_deco = right_deco
        # Rounded mint summary pill — full text, no overlapping icon
        self.fu_strip_canvas = tk.Canvas(right, height=int(44 * sc), bg=CARD, highlightthickness=0)
        self.fu_strip_canvas.pack(fill="x", side="bottom", pady=(2, 4))
        self.fu_strip_canvas.bind("<Configure>", lambda e: self._fu_paint_strip())
        self.fu_duration_badge = self.fu_strip_canvas
        self._fu_strip_text = ""
        class _StripProxy:
            def __init__(proxy, owner): proxy._o = owner
            def config(proxy, **kw):
                if "text" in kw:
                    proxy._o._fu_strip_text = kw["text"]
                    proxy._o._fu_paint_strip()
            def cget(proxy, key):
                return proxy._o._fu_strip_text if key == "text" else ""
        self.fu_duration_lbl = _StripProxy(self)
        self._fu_update_sub()
        self.fu_summary = tk.Label(p, text="", bg=UI["bg"], fg=UI["text"], font=("Segoe UI", 10, "bold"), anchor="w")
        self.fu_summary.pack(fill="x", pady=(0, 4))
        bar = ttk.Frame(p); bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="\U0001F4E5  Import from Upwork", style="Accent.TButton", command=self.fu_import_messages).pack(side="left")
        ttk.Button(bar, text="\u2714 Follow-up sent", command=self.fu_mark_sent).pack(side="left", padx=(10, 4))
        ttk.Button(bar, text="\u21a9 Client replied", command=self.fu_client_replied).pack(side="left", padx=4)
        ttk.Button(bar, text="\u2716 Close (Lost)", command=self.fu_close).pack(side="left", padx=4)
        ttk.Button(bar, text="\u2605 Close as Won", command=self.fu_close_won).pack(side="left", padx=4)
        ttk.Button(bar, text="Set stage", command=self.fu_set_stage).pack(side="left", padx=4)
        ttk.Button(bar, text="Reopen", command=self.fu_reopen).pack(side="left", padx=4)
        ttk.Button(bar, text="Edit lead", command=self.edit_followup_lead).pack(side="left", padx=4)
        ttk.Button(bar, text="\U0001F4DD Notes", command=lambda: self.lead_notes(self.ftree)).pack(side="left", padx=4)
        self.fu_show_closed = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Show closed", variable=self.fu_show_closed, command=self.fu_refresh, bg=UI["bg"], activebackground=UI["bg"]).pack(side="right")
        self.ftree = self.make_tree(p, ("id","name","company","job","count","stage","lastfu","due","flag","preview"),
            ("ID","Lead","Company","Job","Sequence progress","Sales stage","Last follow-up","Next due","Status","Last message"),
            [40,125,110,160,150,230,110,115,190,200])
        for t, fg, bg in (("fu_over", "#B91C1C", "#FEF2F2"), ("fu_reply", "#7C2D12", "#FFEDD5"), ("fu_soon", "#92400E", "#FFFBEB"),
                          ("fu_ok", UI["text"], "#FFFFFF"), ("fu_done", "#6D28D9", "#F5F3FF"), ("fu_closed", "#9CA3AF", "#F9FAFB")):
            self.ftree.tag_configure(t, foreground=fg, background=bg)
        self.ftree.bind("<Double-1>", lambda e: self.edit_followup_lead())
        # Message / notes / AI panels — emerald-aligned with manager card
        pnl = tk.Frame(p, bg="#FFFFFF", highlightthickness=1, highlightbackground=LINE)
        head = tk.Frame(pnl, bg=MINT); head.pack(fill="x")
        self.fu_msg_title = tk.Label(head, text="", bg=MINT, fg=DARK, font=("Segoe UI", 9, "bold"), anchor="w", padx=12, pady=6)
        self.fu_msg_title.pack(side="left", fill="x", expand=True)
        tk.Button(head, text="\u2715", command=self.fu_hide_message, relief="flat", bd=0, bg=MINT, fg=MUTED,
                  activebackground="#C8EDE0", font=("Segoe UI", 10), padx=10, cursor="hand2").pack(side="right")
        self.fu_msg_text = tk.Text(pnl, height=3, wrap="word", relief="flat", bd=0, font=("Segoe UI", 10), fg=OV["text"],
                                   bg="#FFFFFF", padx=12, pady=8, cursor="arrow")
        self.fu_msg_text.pack(fill="x"); self.fu_msg_text.configure(state="disabled")
        nh = tk.Frame(pnl, bg=MINT); nh.pack(fill="x")
        tk.Label(nh, text="\U0001F4DD  Notes", bg=MINT, fg=DARK, font=("Segoe UI", 9, "bold"), anchor="w", padx=12, pady=6).pack(side="left")
        tk.Button(nh, text="Add / edit notes", command=lambda: self.lead_notes(self.ftree), relief="flat", bd=0, bg="#FFFFFF", fg=EM,
                  activebackground="#C8EDE0", font=("Segoe UI", 9, "bold"), padx=10, cursor="hand2",
                  highlightthickness=1, highlightbackground=EM).pack(side="right", padx=8, pady=3)
        self.fu_note_text = tk.Text(pnl, height=2, wrap="word", relief="flat", bd=0, font=("Segoe UI", 10), fg=OV["text"],
                                    bg="#FFFFFF", padx=12, pady=8, cursor="arrow")
        self.fu_note_text.pack(fill="x"); self.fu_note_text.configure(state="disabled")
        ai_head = tk.Frame(pnl, bg=MINT); ai_head.pack(fill="x")
        tk.Label(
            ai_head, text="Write follow up message", bg=MINT, fg=DARK,
            font=("Segoe UI", 9, "bold"), anchor="w", padx=12, pady=6,
        ).pack(side="left")
        ai_bar = tk.Frame(pnl, bg="#FFFFFF"); ai_bar.pack(fill="x", padx=12, pady=(4, 0))
        self.fu_ai_btn = ttk.Button(
            ai_bar, text="Generate message", style="Accent.TButton",
            command=self.fu_generate_message,
        )
        self.fu_ai_btn.pack(side="left")
        self.fu_ai_copy = ttk.Button(ai_bar, text="Copy", command=self.fu_copy_ai_message)
        self.fu_ai_copy.pack(side="left", padx=(6, 0))
        self.fu_ai_spin_var = tk.StringVar(value="")
        self.fu_ai_spin = tk.Label(
            ai_bar, textvariable=self.fu_ai_spin_var, bg="#FFFFFF", fg=EM,
            font=("Segoe UI", 11, "bold"), width=2, anchor="center",
        )
        self.fu_ai_spin.pack(side="left", padx=(8, 2))
        self.fu_ai_status_var = tk.StringVar(value="")
        self.fu_ai_status = tk.Label(
            ai_bar, textvariable=self.fu_ai_status_var, bg="#FFFFFF", fg=EM,
            font=("Segoe UI", 9), anchor="w",
        )
        self.fu_ai_status.pack(side="left", fill="x", expand=True)
        self.fu_ai_draft = tk.Text(
            pnl, height=3, wrap="word", relief="flat", bd=0, font=("Segoe UI", 10),
            fg=OV["text"], bg="#FFFFFF", padx=12, pady=8,
        )
        self.fu_ai_draft.pack(fill="x", pady=(0, 4))
        self.fu_ai_draft.insert("1.0", "Select a lead, then click Generate message.")
        self.fu_ai_draft.configure(fg="#94A3B8")
        self._fu_ai_busy = False
        self._fu_ai_spin_id = None
        self._fu_ai_spin_i = 0
        self._fu_ai_lead_id = None
        self.fu_msg_panel = pnl; self.fu_msg_wrap = self.ftree.master
        self.ftree.bind("<<TreeviewSelect>>", lambda e: self.fu_show_message(), add="+")
        self.ftree.bind("<Escape>", lambda e: self.fu_hide_message(), add="+")
        self.root.after(300000, self._fu_loop)

    def fu_show_message(self):
        sel = self.ftree.selection()
        if len(sel) != 1: self.fu_hide_message(); return
        lead_id = int(sel[0][1:])
        r = self.db.execute(
            "SELECT name, company, last_preview, notes, job_title FROM leads WHERE id=?",
            (lead_id,),
        ).fetchone()
        if not r: self.fu_hide_message(); return
        who = (r["name"] or "").replace("[SAMPLE] ", "") + (f", {r['company']}" if r["company"] else "")
        self.fu_msg_title.config(text=f"Last message  \u2022  {who}")
        msg = (r["last_preview"] or "").strip() or "No message captured for this lead yet."
        t = self.fu_msg_text; t.configure(state="normal"); t.delete("1.0", "end"); t.insert("1.0", msg)
        t.configure(height=max(2, min(6, int(t.count("1.0", "end", "displaylines")[0]) if t.winfo_ismapped() else 3)))
        t.configure(state="disabled")
        n = self.fu_note_text; nt = (r["notes"] or "").strip()
        n.configure(state="normal", fg="#334155" if nt else "#94A3B8"); n.delete("1.0", "end"); n.insert("1.0", nt or "No notes yet. Click Add / edit notes to write one.")
        n.configure(height=max(1, min(6, nt.count("\n") + 1 + len(nt) // 140)), state="disabled")
        self._fu_ai_lead_id = lead_id
        if not self._fu_ai_busy:
            self._fu_ai_reset_draft("Select a lead, then click Generate message.")
        if not self.fu_msg_panel.winfo_manager():
            self.fu_msg_panel.pack(side="bottom", fill="x", pady=(0, 6), before=self.fu_msg_wrap)

    def _fu_ai_reset_draft(self, placeholder=""):
        d = getattr(self, "fu_ai_draft", None)
        if d is None:
            return
        try:
            d.delete("1.0", "end")
            if placeholder:
                d.insert("1.0", placeholder)
                d.configure(fg="#94A3B8")
            else:
                d.configure(fg="#334155")
        except tk.TclError:
            pass
        try:
            self.fu_ai_status_var.set("")
            self.fu_ai_spin_var.set("")
        except Exception:
            pass

    def _fu_ai_set_status(self, text, kind="info"):
        text = (text or "").strip()
        try:
            self.fu_ai_status_var.set(text)
            color = UI.get("accent", "#4F46E5")
            if kind == "error":
                color = "#DC2626"
            elif kind == "ok":
                color = "#047857"
            self.fu_ai_status.configure(fg=color)
        except Exception:
            pass

    def _fu_ai_start_spin(self, text):
        self._fu_ai_busy = True
        self._fu_ai_spin_i = 0
        self._fu_ai_set_status(text or "Writing a short follow-up...", "info")
        try:
            self.fu_ai_btn.state(["disabled"])
            self.fu_ai_copy.state(["disabled"])
        except Exception:
            pass
        self._fu_ai_tick_spin()

    def _fu_ai_tick_spin(self):
        self._fu_ai_spin_id = None
        if not self._fu_ai_busy:
            return
        frames = ("|", "/", "-", "\\")
        try:
            self.fu_ai_spin_var.set(frames[self._fu_ai_spin_i % 4])
        except Exception:
            pass
        self._fu_ai_spin_i += 1
        try:
            self._fu_ai_spin_id = self.root.after(120, self._fu_ai_tick_spin)
        except Exception:
            self._fu_ai_spin_id = None

    def _fu_ai_stop_spin(self):
        self._fu_ai_busy = False
        if self._fu_ai_spin_id is not None:
            try:
                self.root.after_cancel(self._fu_ai_spin_id)
            except Exception:
                pass
            self._fu_ai_spin_id = None
        try:
            self.fu_ai_spin_var.set("")
        except Exception:
            pass
        try:
            self.fu_ai_btn.state(["!disabled"])
            self.fu_ai_copy.state(["!disabled"])
        except Exception:
            pass

    def fu_generate_message(self):
        """AI draft from this lead's last message + notes. Copy-ready only."""
        if self._fu_ai_busy:
            return
        sel = self.ftree.selection()
        if len(sel) != 1:
            messagebox.showinfo("Generate message", "Select one lead in the list first.")
            return
        lead_id = int(sel[0][1:])
        try:
            r = self.db.execute(
                "SELECT name, company, last_preview, notes, job_title FROM leads WHERE id=?",
                (lead_id,),
            ).fetchone()
        except Exception:
            r = None
        if not r:
            messagebox.showinfo("Generate message", "Could not load this lead.")
            return
        last = (r["last_preview"] or "").strip()
        notes = (r["notes"] or "").strip()
        if not last and not notes:
            self._fu_ai_set_status(
                "Add a last message or notes for this lead first.", "error"
            )
            return
        try:
            import ai_proposal
        except Exception:
            self._fu_ai_set_status("Could not load the AI writer. Try again.", "error")
            return
        self._fu_ai_lead_id = lead_id
        self._fu_ai_reset_draft("Writing a short follow-up...")
        self._fu_ai_start_spin("Writing a short follow-up...")
        name = r["name"] or ""
        company = r["company"] or ""
        job = r["job_title"] or ""
        import threading

        def work():
            try:
                text = ai_proposal.generate_followup_message(
                    last_message=last,
                    notes=notes,
                    lead_name=name,
                    company=company,
                    job=job,
                )
                self.root.after(0, lambda: self._fu_ai_done(text, None, lead_id))
            except Exception as exc:
                msg = getattr(exc, "user_message", None) or getattr(exc, "default_message", None)
                msg = (msg or "Something went wrong. Try again.").strip()
                self.root.after(0, lambda: self._fu_ai_done(None, msg, lead_id))

        threading.Thread(target=work, daemon=True, name="LeadPilotFollowupAI").start()

    def _fu_ai_done(self, text, err, lead_id):
        self._fu_ai_stop_spin()
        if self._fu_ai_lead_id != lead_id:
            return
        if err:
            self._fu_ai_set_status(err, "error")
            self._fu_ai_reset_draft("Generate failed. Fix the issue, then try again.")
            return
        text = (text or "").strip()
        if not text:
            self._fu_ai_set_status("No message came back. Try again.", "error")
            return
        try:
            self.fu_ai_draft.delete("1.0", "end")
            self.fu_ai_draft.insert("1.0", text)
            self.fu_ai_draft.configure(fg="#334155")
        except tk.TclError:
            pass
        self._fu_ai_set_status("Ready. Click Copy, then paste into Upwork.", "ok")

    def fu_copy_ai_message(self):
        try:
            text = self.fu_ai_draft.get("1.0", "end-1c").strip()
        except tk.TclError:
            text = ""
        if not text or text.startswith("Select a lead") or text.startswith("Writing a short") or text.startswith("Generate failed"):
            self._fu_ai_set_status("Generate a message first, then Copy.", "error")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            self._fu_ai_set_status("Could not copy. Select the text and press Ctrl+C.", "error")
            return
        self._fu_ai_set_status("Copied. Paste it into the Upwork chat.", "ok")

    def lead_notes(self, tree, lead_id=None):
        """Free-text notes per lead: what the client said, calls, promises, next steps. Saved in leads.notes."""
        if lead_id is None:
            sel = tree.selection()
            if len(sel) != 1: return messagebox.showinfo("Notes", "Select one lead in the list first.")
            lead_id = int(tree.item(sel[0], "values")[0])
        r = self.db.execute("SELECT id, name, company, notes FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not r: return
        win = tk.Toplevel(self.root); win.configure(bg="#FFFFFF"); win.transient(self.root); win.resizable(True, True)
        who = (r["name"] or "").replace("[SAMPLE] ", "") + (f", {r['company']}" if r["company"] else "")
        win.title(f"Notes: {who}")
        tk.Frame(win, bg="#4338CA", height=4).pack(fill="x")
        tk.Label(win, text=f"Notes for {who}", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=18, pady=(14, 2))
        tk.Label(win, text="What the client said, calls, what was promised and next steps. Saved with this lead.", bg="#FFFFFF",
                 fg=UI["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(0, 8))
        txt = tk.Text(win, width=70, height=14, wrap="word", font=("Segoe UI", 10), relief="solid", bd=1, padx=8, pady=6)
        txt.pack(fill="both", expand=True, padx=18); txt.insert("1.0", r["notes"] or "")
        def stamp():
            txt.insert("end", ("\n" if txt.get("1.0", "end").strip() else "") + datetime.now().strftime("[%d %b %Y, %I:%M %p] "))
            txt.see("end"); txt.focus_set()
        def save():
            self.db.execute("UPDATE leads SET notes=? WHERE id=?", (txt.get("1.0", "end").strip(), lead_id)); self.db.commit()
            win.destroy(); self.refresh_all()
            try: self.fu_show_message()
            except Exception: pass
        b = tk.Frame(win, bg="#FFFFFF"); b.pack(fill="x", padx=18, pady=12)
        ttk.Button(b, text="\uff0b Add dated entry", command=stamp).pack(side="left")
        ttk.Button(b, text="Save notes", style="Accent.TButton", command=save).pack(side="right")
        ttk.Button(b, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        self._notes_win = (win, txt, save, stamp)
        win.update_idletasks(); win.geometry(f"+{self.root.winfo_rootx() + 220}+{self.root.winfo_rooty() + 120}")
        txt.focus_set(); txt.mark_set("insert", "end")

    def fu_hide_message(self):
        if self.fu_msg_panel.winfo_manager():
            self.fu_msg_panel.pack_forget()
        self._fu_ai_lead_id = None
        if not self._fu_ai_busy:
            self._fu_ai_reset_draft("Select a lead, then click Generate message.")

    def make_planner(self):
        p = self.tabs["planner"]
        self.section_title(p, "LeadPilot Planner", "Estimate the proposal volume required to achieve your monthly qualified-lead target.")
        box = ttk.LabelFrame(p, text="Monthly targets and conversion assumptions", padding=14); box.pack(fill="x", pady=8)
        self.plan_vars = {}
        self.plan_labels = {}
        specs = [("target","Qualified lead target",1,200),("view_rate","Proposal view rate (%)",0,100),
                 ("lead_rate","View-to-lead conversion (%)",0,100),("close_rate","Lead-to-client conversion (%)",0,100)]
        for i,(key,label,lo,hi) in enumerate(specs):
            ttk.Label(box,text=label).grid(row=i,column=0,sticky="w",pady=9)
            var = tk.IntVar(value=int(self.setting(key))); self.plan_vars[key] = var
            scale = ttk.Scale(box,from_=lo,to=hi,orient="horizontal",
                command=lambda value,k=key:self.plan_changed(k,value))
            scale.set(var.get()); scale.grid(row=i,column=1,sticky="ew",padx=14)
            out = ttk.Label(box,text=str(var.get()),font=("Segoe UI",10,"bold"),width=6)
            out.grid(row=i,column=2); self.plan_labels[key] = out
            var.trace_add("write",lambda *_:self.calculate_plan())
        box.columnconfigure(1,weight=1)
        results = ttk.Frame(p); results.pack(fill="x",pady=16)
        self.plan_results = {}
        for label,key in [("Qualified leads","leads"),("Proposal views needed","views"),
                          ("Proposals to send","proposals"),("Estimated clients","clients")]:
            card = ttk.LabelFrame(results,text=label,padding=14); card.pack(side="left",fill="both",expand=True,padx=5,pady=3)
            val = ttk.Label(card,text="-",font=("Segoe UI",22,"bold"),foreground=self.colors["blue"])
            val.pack(anchor="w"); self.plan_results[key] = val
        ttk.Button(p,text="Save planner settings",command=self.save_plan).pack(anchor="w")
        self.calculate_plan()

    # ---------- Performance ----------
    PERF_FIELDS = [("perf_target", "Monthly lead target", "leads", 1, 100),
                   ("perf_view_rate", "Proposal view rate", "%", 0, 100),
                   ("perf_lead_rate", "View to lead conversion", "%", 0, 100),
                   ("perf_close_rate", "Lead to client conversion", "%", 0, 100)]
    PERF_COLORS = {"perf_target": ("#4338CA", "#EEF2FF"), "perf_view_rate": ("#0369A1", "#E0F2FE"),
                   "perf_lead_rate": ("#047857", "#ECFDF5"), "perf_close_rate": ("#B45309", "#FFFBEB")}

    def make_performance(self):
        p = self.tabs["performance"]
        self.section_title(p, "Performance", "Set your monthly targets, see how many proposals you need, and track this month's progress.")
        top = tk.Frame(p, bg=UI["bg"]); top.pack(fill="x", pady=(8, 0))
        # Targets card
        tc = self.card(top, side="left", fill="both", padx=(0, 8))
        tk.Frame(tc, bg="#4338CA", height=4).pack(fill="x")
        tk.Label(tc, text="Monthly targets", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 6))
        form = tk.Frame(tc, bg=UI["card"]); form.pack(fill="x", padx=16)
        self.perf_vars, self.perf_scales, self.perf_vals = {}, {}, {}
        for i, (k, label, unit, lo, hi) in enumerate(self.PERF_FIELDS):
            col, light = self.PERF_COLORS[k]
            head = tk.Frame(form, bg=UI["card"]); head.grid(row=i * 2, column=0, sticky="ew", pady=(8, 0))
            tk.Label(head, text=label, bg=UI["card"], fg=UI["text"], font=("Segoe UI", 10)).pack(side="left")
            try: start = max(lo, min(hi, int(float(self.setting(k)))))
            except ValueError: start = lo
            v = tk.StringVar(value=str(start)); self.perf_vars[k] = v
            val = tk.Label(head, text="", bg=light, fg=col, font=("Segoe UI", 10, "bold"), padx=8, pady=1, width=9)
            val.pack(side="right"); self.perf_vals[k] = (val, unit)
            sc = tk.Scale(form, from_=lo, to=hi, orient="horizontal", showvalue=0, length=300, sliderlength=22, width=12,
                          troughcolor=light, bg=col, activebackground=col, highlightthickness=0, bd=0, sliderrelief="flat",
                          command=lambda x, kk=k: self.perf_vars[kk].set(str(int(float(x)))))
            sc.set(start); sc.grid(row=i * 2 + 1, column=0, sticky="ew", pady=(4, 2)); self.perf_scales[k] = sc
            v.trace_add("write", lambda *_: self.perf_refresh())
        form.columnconfigure(0, weight=1)
        bf = tk.Frame(tc, bg=UI["card"]); bf.pack(anchor="w", padx=16, pady=(8, 4))
        ttk.Button(bf, text="Save targets", style="Accent.TButton", command=self.perf_save).pack(side="left")
        self.perf_msg = tk.Label(tc, text="", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9), wraplength=300, justify="left")
        self.perf_msg.pack(anchor="w", padx=16, pady=(2, 12))
        # Plan card
        pc = self.card(top, side="left", fill="both", expand=True)
        tk.Frame(pc, bg="#047857", height=4).pack(fill="x")
        tk.Label(pc, text="What it takes", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        self.perf_explain = tk.Label(pc, text="", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9), wraplength=620, justify="left")
        self.perf_explain.pack(anchor="w", padx=16, pady=(0, 8))
        tiles = tk.Frame(pc, bg=UI["card"]); tiles.pack(fill="x", padx=12, pady=(0, 14))
        self.perf_plan = {}
        for i, (k, cap, col, bg) in enumerate([("proposals", "Proposals to send", "#4338CA", "#EEF2FF"), ("views", "Expected views", "#0369A1", "#E0F2FE"),
                                               ("leads", "Expected leads", "#047857", "#ECFDF5"), ("clients", "Expected clients", "#B45309", "#FFFBEB")]):
            t = tk.Frame(tiles, bg=bg); t.grid(row=0, column=i, sticky="nsew", padx=4); tiles.columnconfigure(i, weight=1)
            val = tk.Label(t, text="-", bg=bg, fg=col, font=("Segoe UI", 24, "bold")); val.pack(anchor="w", padx=12, pady=(10, 0))
            tk.Label(t, text=cap, bg=bg, fg=col, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(0, 10))
            self.perf_plan[k] = val
        # Progress card
        gc = self.card(p, fill="x", pady=(10, 0))
        tk.Frame(gc, bg="#B45309", height=4).pack(fill="x")
        self.perf_month = tk.Label(gc, text="", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold"))
        self.perf_month.pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(gc, text="Counted from your jobs and leads dated this month. [SAMPLE] records are left out.", bg=UI["card"], fg=UI["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 8))
        rows = tk.Frame(gc, bg=UI["card"]); rows.pack(fill="x", padx=16, pady=(0, 14)); rows.columnconfigure(1, weight=1)
        self.perf_prog = {}
        for i, (k, cap) in enumerate([("proposals", "Proposals sent"), ("views", "Viewed by client"), ("leads", "New leads"), ("clients", "Clients won")]):
            tk.Label(rows, text=cap, bg=UI["card"], fg=UI["text"], font=("Segoe UI", 10), width=16, anchor="w").grid(row=i, column=0, sticky="w", pady=5)
            bar = ttk.Progressbar(rows, orient="horizontal", mode="determinate", maximum=100); bar.grid(row=i, column=1, sticky="ew", padx=12)
            txt = tk.Label(rows, text="", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 10, "bold"), width=22, anchor="w"); txt.grid(row=i, column=2, sticky="w")
            self.perf_prog[k] = (bar, txt)
        self.perf_refresh()

    def perf_inputs(self):
        vals, bad = {}, []
        for k, label, unit, lo, hi in self.PERF_FIELDS:
            raw = self.perf_vars[k].get().strip().rstrip("%")
            try:
                n = float(raw)
                if not (lo <= n <= hi): raise ValueError
                vals[k] = n
            except ValueError:
                bad.append(f"{label} must be a number from {lo} to {hi}")
        return vals, bad

    @staticmethod
    def perf_plan_numbers(target, view, lead, close):
        import math
        views = math.ceil(round(target / (lead / 100), 6))
        proposals = math.ceil(round(views / (view / 100), 6))
        clients = target * close / 100
        return {"proposals": proposals, "views": views, "leads": int(target) if target == int(target) else target, "clients": clients}

    def perf_actuals(self):
        ym = date.today().strftime("%Y-%m")
        props = self.db.execute("SELECT id, status FROM proposals WHERE substr(proposal_date,1,7)=? AND job NOT LIKE '[SAMPLE]%'", (ym,)).fetchall()
        sent = [r for r in props if r["status"] != "Draft"]
        viewed = [r for r in sent if r["status"] in ("Viewed", "Responded", "Interview", "Hired")]
        leads = self.db.execute("SELECT status, proposal_id FROM leads WHERE substr(coalesce(nullif(lead_date,''), created_at),1,7)=? AND name NOT LIKE '[SAMPLE]%'", (ym,)).fetchall()
        won_props = {r["proposal_id"] for r in leads if r["status"] == "Won" and r["proposal_id"]}
        clients = sum(1 for r in leads if r["status"] == "Won") + sum(1 for r in sent if r["status"] == "Hired" and r["id"] not in won_props)
        return {"proposals": len(sent), "views": len(viewed), "leads": len(leads), "clients": clients}

    def perf_refresh(self):
        if not hasattr(self, "perf_prog"): return
        self.perf_month.config(text="This month: " + date.today().strftime("%B %Y"))
        for k, (lab, unit) in getattr(self, "perf_vals", {}).items():
            lab.config(text=f"{self.perf_vars[k].get()} {'%' if unit == '%' else unit}".replace(" %", "%"))
        vals, bad = self.perf_inputs()
        if not bad:
            if vals["perf_view_rate"] == 0: bad.append("Proposal view rate must be above 0%")
            if vals["perf_lead_rate"] == 0: bad.append("View to lead conversion must be above 0%")
        act = self.perf_actuals()
        fmt = lambda n: str(int(n)) if float(n).is_integer() else f"{n:.1f}"
        if bad:
            self.perf_msg.config(text="\n".join(bad), fg="#DC2626")
            for v in self.perf_plan.values(): v.config(text="-")
            for k, (bar, txt) in self.perf_prog.items(): bar["value"] = 0; txt.config(text=f"{act[k]} done")
            return
        self.perf_msg.config(text="Drag a slider and the plan updates instantly. Click Save targets to keep it.", fg=UI["muted"])
        t, vr, lr, cr = (vals[k] for k, *_ in self.PERF_FIELDS)
        plan = self.perf_plan_numbers(t, vr, lr, cr)
        for k, lab in self.perf_plan.items(): lab.config(text=fmt(plan[k]))
        self.perf_explain.config(text=f"To get {fmt(t)} leads at {fmt(lr)}% view to lead, you need {plan['views']} views. "
                                      f"At a {fmt(vr)}% view rate, that means sending {plan['proposals']} proposals. "
                                      f"At {fmt(cr)}% lead to client, expect about {fmt(plan['clients'])} clients.")
        for k, (bar, txt) in self.perf_prog.items():
            goal = plan[k]
            pct = (act[k] / goal * 100) if goal else 0
            bar["value"] = min(100, pct)
            txt.config(text=f"{act[k]} / {fmt(goal)}   ({pct:.0f}%)", fg="#047857" if pct >= 100 else UI["muted"])

    def perf_save(self):
        vals, bad = self.perf_inputs()
        if not bad and (vals["perf_view_rate"] == 0 or vals["perf_lead_rate"] == 0):
            bad.append("View rate and view to lead conversion must be above 0%")
        if bad:
            messagebox.showwarning("Check your targets", "\n".join(bad)); return
        for k, v in vals.items():
            self.db.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)", (k, str(int(v)) if v == int(v) else str(v)))
        self.db.commit(); self.perf_refresh()
        self.perf_msg.config(text="Targets saved.", fg="#047857")

    # ---------- Meetings ----------
    @staticmethod
    def _rel(delta_min):
        m = int(round(delta_min))
        if m < 1: return "now"
        if m < 60: return f"{m} minute{'s' if m != 1 else ''}"
        h, mm = divmod(m, 60)
        if h < 24: return f"{h} hour{'s' if h != 1 else ''}" + (f" {mm} min" if mm else "")
        d = round(m / 1440)
        return f"{d} day{'s' if d != 1 else ''}"

    def make_meetings(self):
        p = self.tabs["meetings"]
        self.section_title(p, "Meetings", "Schedule client meetings, see what's coming up, and get a heads-up before each one starts.")
        nc = self.card(p, fill="x", pady=(8, 10))
        tk.Frame(nc, bg="#047857", height=4).pack(fill="x")
        row = tk.Frame(nc, bg=UI["card"]); row.pack(fill="x", padx=16, pady=12)
        self.meet_next_lbl = tk.Label(row, text="", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold"), justify="left", wraplength=760)
        self.meet_next_lbl.pack(side="left", anchor="w")
        alert = tk.Frame(row, bg=UI["card"]); alert.pack(side="right")
        tk.Label(alert, text="Alert me", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        self.meet_alert_var = tk.StringVar(value={"30": "30 minutes before", "15": "15 minutes before", "120": "2 hours before"}.get(self.setting("meet_alert_minutes"), "1 hour before"))
        cb = ttk.Combobox(alert, textvariable=self.meet_alert_var, state="readonly", width=18,
                          values=["15 minutes before", "30 minutes before", "1 hour before", "2 hours before"]); cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.meet_set_alert())
        bar = ttk.Frame(p); bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="\uff0b  Schedule meeting", style="Accent.TButton", command=self.add_meeting).pack(side="left")
        ttk.Button(bar, text="Edit selected", command=self.edit_meeting).pack(side="left", padx=6)
        ttk.Button(bar, text="Open link", command=self.open_meeting_link).pack(side="left")
        ttk.Button(bar, text="Mark done", command=lambda: self.set_meeting_status("Done")).pack(side="left", padx=6)
        ttk.Button(bar, text="Cancel meeting", command=lambda: self.set_meeting_status("Cancelled")).pack(side="left")
        ttk.Button(bar, text="Delete", command=self.delete_meeting).pack(side="left", padx=6)
        self.gcal_disc_btn = ttk.Button(bar, text="Disconnect Google", command=self.gcal_disconnect)
        self.gcal_btn = ttk.Button(bar, text="", style="Accent.TButton", command=self.gcal_button)
        self.gcal_btn.pack(side="right")
        self.gcal_status = tk.Label(p, text="", bg=UI["bg"], fg=UI["muted"], font=("Segoe UI", 9), anchor="e")
        self.gcal_status.pack(fill="x")
        cols = ("id", "when", "duration", "title", "client", "job", "source", "link", "status")
        heads = ("ID", "Date & time", "Length", "Title", "With", "Related job", "Source", "Link", "Status")
        widths = (50, 170, 70, 220, 140, 200, 130, 140, 90)
        ttk.Label(p, text="Upcoming", style="Section.TLabel").pack(anchor="w", pady=(6, 0))
        self.mtree_up = self.make_tree(p, cols, heads, widths)
        self.mtree_up.configure(height=3)
        ttk.Label(p, text="History", style="Section.TLabel").pack(anchor="w", pady=(8, 0))
        self.mtree_past = self.make_tree(p, cols, heads, widths)
        self.mtree_past.configure(height=3)
        up_wrap, past_wrap = self.mtree_up.master, self.mtree_past.master
        up_wrap.pack_configure(expand=False, fill="x")   # Upcoming keeps a fixed small height; History gets the rest and scrolls
        title_lbl, sub_lbl = p.winfo_children()[0], p.winfo_children()[1]
        title_pack = {k: v for k, v in title_lbl.pack_info().items() if k != "in"}
        def meet_fit(e=None):
            h = p.winfo_height()
            if h <= 1: return
            tier = 0 if h >= 620 else (1 if h >= 520 else 2)   # 2 = very short page (small window plus an alert bar)
            small = tier > 0
            if tier == getattr(self, "_meet_tier", None): return
            self._meet_tier = tier; self._meet_small = small
            # on a very short page the big page title is hidden too; the top bar still says Meetings
            if tier == 2: title_lbl.pack_forget()
            elif not title_lbl.winfo_manager(): title_lbl.pack(**title_pack, before=nc)
            if small:
                sub_lbl.pack_forget(); nc.pack_configure(pady=(4, 6)); row.pack_configure(pady=6)
                self.mtree_up.configure(height=2); up_wrap.pack_configure(pady=4); past_wrap.pack_configure(pady=4)
            else:
                sub_lbl.pack(anchor="w", pady=(4, 12), after=title_lbl); nc.pack_configure(pady=(8, 10)); row.pack_configure(pady=12)
                self.mtree_up.configure(height=3); up_wrap.pack_configure(pady=8); past_wrap.pack_configure(pady=8)
        p.bind("<Configure>", meet_fit, add="+")
        for t in (self.mtree_up, self.mtree_past):
            t.bind("<Double-1>", lambda e: self.edit_meeting())
            t.bind("<<TreeviewSelect>>", lambda e, me=t: [o.selection_remove(*o.selection()) for o in (self.mtree_up, self.mtree_past) if o is not me and o.selection()])
            t.tag_configure("soon", background="#FEF3C7")
            t.tag_configure("done", foreground="#6B7280")
            t.tag_configure("google", foreground="#1A73E8")
        self.gcal_update_ui()
        self.meet_refresh()
        if self.gcal_connected():
            self.root.after(2500, self.gcal_sync)

    def _meet_rows(self):
        return self.db.execute("""SELECT m.*, p.job AS job FROM meetings m LEFT JOIN proposals p ON p.id = m.proposal_id
                                  ORDER BY m.start""").fetchall()

    def _meet_end(self, r):
        return datetime.strptime(r["start"], "%Y-%m-%d %H:%M") + __import__("datetime").timedelta(minutes=int(r["duration"] or 30))

    def meet_refresh(self):
        if not hasattr(self, "mtree_up"): return
        selected = None
        for t in (self.mtree_up, self.mtree_past):
            sel = t.selection()
            if sel:
                selected = sel[0]
                break
        now = datetime.now(); win = int(self.setting("meet_alert_minutes") or 60)
        for t in (self.mtree_up, self.mtree_past): t.delete(*t.get_children())
        upcoming = []
        for r in self._meet_rows():
            if r["status"] == "Removed": continue
            st = datetime.strptime(r["start"], "%Y-%m-%d %H:%M"); end = self._meet_end(r)
            live = r["status"] == "Scheduled" and end >= now
            status = r["status"] if r["status"] != "Scheduled" else ("In progress" if st <= now <= end else "Scheduled" if live else "Done")
            vals = (r["id"], st.strftime("%a %d %b %Y, %I:%M %p"), f"{r['duration']} min", r["title"], r["client"] or "",
                    (r["job"] or "")[:60], {"Google Calendar": "\u25cf Google Calendar", "LeadPilot + Google": "LeadPilot + Google"}.get(r["source"] or "", "LeadPilot"),
                    r["link"] or "", status)
            if live:
                upcoming.append((st, r))
                soon = (st - now).total_seconds() / 60 <= win
                tg = (("soon",) if soon else ()) + (("google",) if r["source"] == "Google Calendar" else ())
                self.mtree_up.insert("", "end", iid=f"m{r['id']}", values=vals, tags=tg)
            else:
                self.mtree_past.insert("", 0, iid=f"m{r['id']}", values=vals, tags=("done",))
        if upcoming:
            st, r = upcoming[0]
            who = r["client"] or r["title"]
            mins = (st - now).total_seconds() / 60
            when = "is happening now" if mins <= 0 else f"is in {self._rel(mins)}"
            if r["source"] == "Google Calendar": who += " (from Google Calendar)"
            import tkinter.font as _tkf
            fnt = _tkf.Font(font=self.meet_next_lbl.cget("font")); room = int(self.meet_next_lbl.cget("wraplength")) - 8
            def fit(txt, tail=""):
                # keep each line on one row so a long title or name never pushes the tables down
                if fnt.measure(txt + tail) <= room: return txt + tail
                while txt and fnt.measure(txt.rstrip() + "..." + tail) > room: txt = txt[:-1]
                return txt.rstrip() + "..." + tail
            line1 = fit(f"Your next meeting {when} with {who}")
            line2 = fit(str(r['title']).replace("\n", " "), f"  \u2022  {st.strftime('%A %d %B, %I:%M %p')}")
            self.meet_next_lbl.config(text=f"{line1}\n{line2}", fg=UI["text"])
        else:
            self.meet_next_lbl.config(text="No upcoming meetings. Click 'Schedule meeting' to add one.", fg=UI["muted"])
        if selected:
            for t in (self.mtree_up, self.mtree_past):
                if t.exists(selected):
                    t.selection_set(selected)
                    t.focus(selected)
                    try: t.see(selected)
                    except Exception: pass
                    break

    def meet_tick(self):
        try:
            now = datetime.now(); win = int(self.setting("meet_alert_minutes") or 60)
            nxt = None
            for r in self.db.execute("SELECT * FROM meetings WHERE status='Scheduled' ORDER BY start"):
                st = datetime.strptime(r["start"], "%Y-%m-%d %H:%M")
                if self._meet_end(r) >= now: nxt = (st, r); break
            show = nxt and (nxt[0] - now).total_seconds() / 60 <= win
            if show:
                st, r = nxt; mins = (st - now).total_seconds() / 60
                who = r["client"] or "your client"
                txt = (f"\u23f0  Meeting happening now: {r['title']} with {who}" if mins <= 0
                       else f"\u23f0  Meeting in {self._rel(mins)}: {r['title']} with {who} at {st.strftime('%I:%M %p')}")
                self.meet_banner_lbl.config(text=txt)
                if r["link"]:
                    self.meet_banner_join.config(command=lambda u=r["link"]: __import__("webbrowser").open(u))
                    self.meet_banner_join.pack(side="right", padx=(6, 0))
                else:
                    self.meet_banner_join.pack_forget()
                if not self.meet_banner.winfo_manager():
                    self.meet_banner.pack(fill="x", before=self.content_frame)
                if r["id"] not in self._meet_alerted:
                    self._meet_alerted.add(r["id"])
                    try: self.root.bell()
                    except Exception: pass
            elif self.meet_banner.winfo_manager():
                self.meet_banner.pack_forget()
            self.meet_refresh()
        finally:
            self.root.after(30000, self.meet_tick)

    def meet_set_alert(self):
        m = {"15 minutes before": "15", "30 minutes before": "30", "1 hour before": "60", "2 hours before": "120"}[self.meet_alert_var.get()]
        self.db.execute("INSERT OR REPLACE INTO settings(k,v) VALUES('meet_alert_minutes',?)", (m,)); self.db.commit()
        self._meet_alerted = set()
        self.meet_tick_now()

    def meet_tick_now(self):
        # run one check now without starting a second timer loop
        after = self.root.after
        self.root.after = lambda *a, **k: None
        try: self.meet_tick()
        finally: self.root.after = after

    def _selected_meeting(self):
        for t in (self.mtree_up, self.mtree_past):
            sel = t.selection()
            if sel: return int(sel[0][1:])
        messagebox.showinfo("Select a meeting", "Click a meeting in the list first."); return None

    def add_meeting(self, proposal_id=None, meeting=None):
        jobs = self.db.execute("SELECT id, job, client FROM proposals ORDER BY id DESC").fetchall()
        job_opts = ["(no job)"] + [f"{j['id']} - {j['job'][:70]}" for j in jobs]
        win = tk.Toplevel(self.root); win.title("Edit meeting" if meeting else "Schedule meeting"); win.configure(bg="#FFFFFF")
        win.transient(self.root); win.resizable(False, False); win.grab_set()
        tk.Frame(win, bg="#047857", height=4).pack(fill="x")
        body = tk.Frame(win, bg="#FFFFFF"); body.pack(padx=22, pady=16)
        tk.Label(body, text="Edit meeting" if meeting else "Schedule a meeting", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        pid = meeting["proposal_id"] if meeting else proposal_id
        job_row = next((j for j in jobs if j["id"] == pid), None)
        start = datetime.strptime(meeting["start"], "%Y-%m-%d %H:%M") if meeting else None
        v = {"job": tk.StringVar(value=f"{job_row['id']} - {job_row['job'][:70]}" if job_row else "(no job)"),
             "title": tk.StringVar(value=meeting["title"] if meeting else (f"Call: {job_row['job'][:50]}" if job_row else "")),
             "client": tk.StringVar(value=(meeting["client"] or "") if meeting else ((job_row["client"] or "") if job_row else "")),
             "date": tk.StringVar(value=start.strftime("%Y-%m-%d") if start else date.today().isoformat()),
             "time": tk.StringVar(value=start.strftime("%I:%M %p") if start else ""),
             "duration": tk.StringVar(value=str(meeting["duration"]) if meeting else "30"),
             "link": tk.StringVar(value=(meeting["link"] or "") if meeting else "")}
        fields = [("Related job", "job"), ("Title *", "title"), ("With (client)", "client"), ("Date * (YYYY-MM-DD)", "date"),
                  ("Time * (e.g. 3:30 PM or 15:30)", "time"), ("Length (minutes)", "duration"), ("Meeting link (Meet, Zoom, Calendly)", "link")]
        for i, (lab, k) in enumerate(fields, start=1):
            tk.Label(body, text=lab, bg="#FFFFFF", fg=UI["muted"], font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 12))
            if k == "job":
                w = ttk.Combobox(body, textvariable=v[k], values=job_opts, state="readonly", width=44)
                def on_job(e=None):
                    sel = v["job"].get()
                    if sel != "(no job)":
                        j = next((x for x in jobs if str(x["id"]) == sel.split(" - ")[0]), None)
                        if j and not v["client"].get().strip(): v["client"].set(j["client"] or "")
                        if j and not v["title"].get().strip(): v["title"].set(f"Call: {j['job'][:50]}")
                w.bind("<<ComboboxSelected>>", on_job)
            elif k == "duration":
                w = ttk.Combobox(body, textvariable=v[k], values=["15", "30", "45", "60", "90", "120"], width=10)
            else:
                w = ttk.Entry(body, textvariable=v[k], width=46)
            w.grid(row=i, column=1, sticky="w", pady=4)
        tk.Label(body, text="Notes", bg="#FFFFFF", fg=UI["muted"], font=("Segoe UI", 9)).grid(row=len(fields) + 1, column=0, sticky="nw", pady=4)
        notes = tk.Text(body, width=46, height=4, font=("Segoe UI", 10), relief="solid", bd=1)
        notes.grid(row=len(fields) + 1, column=1, sticky="w", pady=4)
        if meeting and meeting["notes"]: notes.insert("1.0", meeting["notes"])
        connected = self.gcal_connected()
        v["gcal"] = tk.BooleanVar(value=connected and (not meeting or bool(meeting["gcal_id"])))
        gtxt = ("Also update it in Google Calendar" if meeting and meeting["gcal_id"] else "Also add to my Google Calendar") if connected \
               else "Add to Google Calendar (connect Google Calendar on the Meetings page first)"
        gcb = tk.Checkbutton(body, text=gtxt, variable=v["gcal"], bg="#FFFFFF", activebackground="#FFFFFF", fg=UI["text"], font=("Segoe UI", 9))
        gcb.grid(row=len(fields) + 2, column=1, sticky="w", pady=(6, 0))
        if not connected: gcb.configure(state="disabled")

        def save(e=None):
            title = v["title"].get().strip()
            if not title: messagebox.showwarning("Missing title", "Give the meeting a title.", parent=win); return
            t = v["time"].get().strip().upper().replace(".", "")
            when = None
            for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %I:%M%p", "%Y-%m-%d %H:%M", "%Y-%m-%d %I %p", "%Y-%m-%d %I%p"):
                try: when = datetime.strptime(f"{v['date'].get().strip()} {t}", fmt); break
                except ValueError: pass
            if not when: messagebox.showwarning("Check date and time", "Use a date like 2026-11-16 and a time like 3:30 PM or 15:30.", parent=win); return
            try:
                dur = int(v["duration"].get().strip()); assert 5 <= dur <= 600
            except Exception:
                messagebox.showwarning("Check length", "Length must be minutes, between 5 and 600.", parent=win); return
            if not meeting and when < datetime.now() and not messagebox.askyesno("Time has passed", "That time is in the past. Save it to history anyway?", parent=win): return
            link = v["link"].get().strip()
            if link and not link.lower().startswith(("http://", "https://")): link = "https://" + link
            jsel = v["job"].get(); jid = int(jsel.split(" - ")[0]) if jsel != "(no job)" else None
            data = (jid, title, v["client"].get().strip(), when.strftime("%Y-%m-%d %H:%M"), dur, link, notes.get("1.0", "end").strip())
            mid = meeting["id"] if meeting else None
            if meeting:
                self.db.execute("UPDATE meetings SET proposal_id=?, title=?, client=?, start=?, duration=?, link=?, notes=?, status=CASE WHEN status='Done' AND ?>=? THEN 'Scheduled' ELSE status END WHERE id=?",
                                data + (when.strftime("%Y-%m-%d %H:%M"), datetime.now().strftime("%Y-%m-%d %H:%M"), meeting["id"]))
                self._meet_alerted.discard(meeting["id"])
            else:
                mid = self.db.execute("INSERT INTO meetings(proposal_id, title, client, start, duration, link, notes, source) VALUES(?,?,?,?,?,?,?,'LeadPilot')", data).lastrowid
            self.db.commit()
            if v["gcal"].get():
                try:
                    body = gcal_meeting_body(title, data[3], dur, link, data[6])
                    gid = meeting["gcal_id"] if meeting else None
                    if gid:
                        gcal_http("PATCH", f"{GCAL_API}/{gid}", body, token=gcal_access_token())
                    else:
                        ev = gcal_http("POST", GCAL_API, body, token=gcal_access_token())
                        self.db.execute("UPDATE meetings SET gcal_id=?, source='LeadPilot + Google' WHERE id=?", (ev["id"], mid)); self.db.commit()
                except Exception as ex:
                    messagebox.showwarning("Google Calendar", f"The meeting is saved in LeadPilot, but Google Calendar wasn't updated.\n\n{ex}", parent=win)
            win.destroy()
            self.meet_tick_now()
            if self.jtree.selection(): self.show_job_detail()
        bf = tk.Frame(body, bg="#FFFFFF"); bf.grid(row=len(fields) + 3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        tk.Button(bf, text="Cancel", command=win.destroy, relief="flat", bd=0, bg="#F1F5F9", fg=UI["text"], padx=14, pady=6).pack(side="right")
        tk.Button(bf, text="Save meeting", command=save, relief="flat", bd=0, bg="#0F766E", fg="#FFFFFF", font=("Segoe UI", 9, "bold"), padx=16, pady=6, cursor="hand2").pack(side="right", padx=8)
        win.bind("<Escape>", lambda e: win.destroy())
        self._meeting_win = (win, v, notes, save)
        return win

    def edit_meeting(self):
        mid = self._selected_meeting()
        if mid is None: return
        r = self.db.execute("SELECT * FROM meetings WHERE id=?", (mid,)).fetchone()
        if r: self.add_meeting(meeting=r)

    def open_meeting_link(self):
        mid = self._selected_meeting()
        if mid is None: return
        r = self.db.execute("SELECT link FROM meetings WHERE id=?", (mid,)).fetchone()
        if r and r["link"]: __import__("webbrowser").open(r["link"])
        else: messagebox.showinfo("No link", "This meeting has no link saved. Use Edit selected to add one.")

    def set_meeting_status(self, status):
        mid = self._selected_meeting()
        if mid is None: return
        if status == "Cancelled" and not messagebox.askyesno("Cancel meeting", "Mark this meeting as cancelled? It moves to History."): return
        self.db.execute("UPDATE meetings SET status=? WHERE id=?", (status, mid)); self.db.commit()
        if status == "Cancelled": self._gcal_offer_delete(mid)
        self.meet_tick_now()

    def _gcal_offer_delete(self, mid):
        r = self.db.execute("SELECT gcal_id FROM meetings WHERE id=?", (mid,)).fetchone()
        if not r or not r["gcal_id"] or not self.gcal_connected(): return False
        if not messagebox.askyesno("Google Calendar", "Also delete this event from your Google Calendar?"): return False
        try:
            gcal_http("DELETE", f"{GCAL_API}/{r['gcal_id']}", token=gcal_access_token()); return True
        except Exception as ex:
            messagebox.showwarning("Google Calendar", f"Couldn't delete it from Google Calendar.\n\n{ex}"); return False

    def delete_meeting(self):
        mid = self._selected_meeting()
        if mid is None: return
        if not messagebox.askyesno("Delete meeting", "Delete this meeting for good?"): return
        r = self.db.execute("SELECT source, gcal_id FROM meetings WHERE id=?", (mid,)).fetchone()
        removed = self._gcal_offer_delete(mid)
        if r and r["gcal_id"] and not removed:
            # keep a hidden marker so the next sync doesn't bring it back
            self.db.execute("UPDATE meetings SET status='Removed' WHERE id=?", (mid,))
        else:
            self.db.execute("DELETE FROM meetings WHERE id=?", (mid,))
        self.db.commit(); self.meet_tick_now()

    # ---------- Google Calendar sync ----------
    def gcal_connected(self):
        return bool(gcal_secret("refresh_token") and gcal_secret("client"))

    def gcal_update_ui(self, msg=None, color=None):
        if not hasattr(self, "gcal_btn"): return
        if self.gcal_connected():
            self.gcal_btn.config(text="\u21bb  Sync Google Calendar")
            if not self.gcal_disc_btn.winfo_manager(): self.gcal_disc_btn.pack(side="right", padx=6)
            last = self.setting("gcal_last_sync")
            self.gcal_status.config(text=msg or ("Google Calendar connected" + (f". Last synced {last}." if last and last != "0" else ".")),
                                    fg=color or "#047857")
        else:
            self.gcal_btn.config(text="\U0001F4C5  Connect Google Calendar")
            self.gcal_disc_btn.pack_forget()
            self.gcal_status.config(text=msg or "Google Calendar not connected. Your Google events will show here once you connect.", fg=color or UI["muted"])

    def gcal_button(self):
        if self.gcal_connected(): self.gcal_sync(manual=True)
        else: self.gcal_connect()

    def gcal_connect(self):
        import json, threading
        if _keyring is None:
            messagebox.showwarning("Google Calendar", "The secure password vault isn't available. Run:  python -m pip install keyring"); return
        if not gcal_secret("client"):
            if not messagebox.askokcancel("Connect Google Calendar",
                    "LeadPilot needs your own Google 'OAuth client' file (a small JSON file from Google Cloud Console, type 'Desktop app').\n\n"
                    "Click OK and choose that file. It's stored in Windows' secure vault, not in a normal file."): return
            path = filedialog.askopenfilename(title="Choose your Google OAuth client JSON", filetypes=[("JSON", "*.json")])
            if not path: return
            try:
                d = json.loads(Path(path).read_text(encoding="utf-8"))
                c = d.get("installed") or d.get("web")
                assert c and c.get("client_id")
            except Exception:
                messagebox.showwarning("Google Calendar", "That file doesn't look like a Google OAuth client file."); return
            gcal_secret("client", json.dumps({"installed": {k: c[k] for k in ("client_id", "client_secret", "auth_uri", "token_uri") if k in c}}))
        self.gcal_update_ui("Waiting for you to sign in to Google in your browser...", "#B45309")
        box = {}
        def work():
            try: box["tok"] = gcal_oauth(gcal_client())
            except Exception as ex: box["err"] = str(ex)
        threading.Thread(target=work, daemon=True).start()
        def check():
            if not box: self.root.after(500, check); return
            if "err" in box:
                self.gcal_update_ui(f"Not connected: {box['err']}", "#DC2626")
                messagebox.showwarning("Google Calendar", box["err"]); return
            gcal_secret("refresh_token", box["tok"]["refresh_token"])
            self.gcal_update_ui("Connected. Syncing your events...", "#047857")
            self.gcal_sync(manual=True)
        self.root.after(500, check)

    def gcal_disconnect(self):
        if not messagebox.askyesno("Disconnect Google", "Disconnect Google Calendar? Events pulled from Google are removed from LeadPilot. Meetings you created in LeadPilot stay."): return
        rt = gcal_secret("refresh_token")
        if rt:
            try: gcal_http("POST", "https://oauth2.googleapis.com/revoke", {"token": rt}, form=True)
            except Exception: pass
        gcal_secret("refresh_token", delete=True); gcal_secret("client", delete=True)
        self.db.execute("DELETE FROM meetings WHERE source='Google Calendar'")
        self.db.execute("UPDATE meetings SET source='LeadPilot', gcal_id=NULL WHERE source='LeadPilot + Google'")
        self.db.commit(); self.gcal_update_ui(); self.meet_tick_now()

    def gcal_sync(self, manual=False):
        import threading
        if getattr(self, "_gcal_busy", False) or not self.gcal_connected(): return
        self._gcal_busy = True
        if manual: self.gcal_update_ui("Syncing with Google Calendar...", "#B45309")
        box = {}
        def work():
            try: box["events"] = gcal_list_events()
            except Exception as ex: box["err"] = str(ex)
        threading.Thread(target=work, daemon=True).start()
        def check():
            if not box: self.root.after(400, check); return
            self._gcal_busy = False
            if "err" in box:
                self.gcal_update_ui(f"Google sync failed: {box['err']}", "#DC2626"); return
            n_new, n_upd, n_gone = self.gcal_apply(box["events"])
            self.db.execute("INSERT OR REPLACE INTO settings(k,v) VALUES('gcal_last_sync',?)", (datetime.now().strftime("%d %b %Y, %I:%M %p"),)); self.db.commit()
            self.gcal_update_ui(f"Google Calendar synced: {n_new} new, {n_upd} updated, {n_gone} removed. Last synced {self.setting('gcal_last_sync')}.")
            self.meet_tick_now()
        self.root.after(400, check)
        if not manual and not getattr(self, "_gcal_loop", False):
            self._gcal_loop = True
            def loop():
                self.gcal_sync(); self.root.after(600000, loop)
            self.root.after(600000, loop)

    def gcal_apply(self, events):
        """Merge Google events into meetings. Never duplicates (matched by Google event id)."""
        seen, n_new, n_upd = set(), 0, 0
        for e in events:
            m = gcal_event_to_meeting(e)
            if not m: continue
            seen.add(m["gcal_id"])
            hit = self.db.execute("SELECT id, source FROM meetings WHERE gcal_id=?", (m["gcal_id"],)).fetchone()
            if hit:
                cur = self.db.execute("UPDATE meetings SET title=?, start=?, duration=?, link=COALESCE(NULLIF(?,''), link) WHERE id=? AND (title IS NOT ? OR start IS NOT ? OR duration IS NOT ?)",
                                      (m["title"], m["start"], m["duration"], m["link"], hit["id"], m["title"], m["start"], m["duration"]))
                if hit["source"] == "Google Calendar":
                    self.db.execute("UPDATE meetings SET client=?, notes=? WHERE id=?", (m["client"], m["notes"], hit["id"]))
                n_upd += cur.rowcount
            else:
                self.db.execute("INSERT INTO meetings(title, client, start, duration, link, notes, source, gcal_id) VALUES(?,?,?,?,?,?,'Google Calendar',?)",
                                (m["title"], m["client"], m["start"], m["duration"], m["link"], m["notes"], m["gcal_id"]))
                n_new += 1
        # Google events deleted on Google's side disappear here too (only future ones pulled from Google)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        gone = [r["id"] for r in self.db.execute("SELECT id, gcal_id FROM meetings WHERE source='Google Calendar' AND start>=?", (now,)) if r["gcal_id"] not in seen]
        for i in gone: self.db.execute("DELETE FROM meetings WHERE id=?", (i,))
        self.db.commit()
        return n_new, n_upd, len(gone)

    # ---------- Upwork Connection ----------
    # ---------------------------------------------------------------- Monthly reports
    def report_data(self, ym):
        """All the numbers for one month (YYYY-MM), or ym='SAMPLE' for a demo built from ALL current data.
        Real months leave [SAMPLE] records out. Returns rows of (section, metric, value)."""
        sample = ym == "SAMPLE"
        q = lambda sql, a=(): self.db.execute(sql, a).fetchall()
        pct = lambda a, b: f"{(100.0 * a / b):.0f}%" if b else "-"
        pm = ("1=1", ()) if sample else ("substr(proposal_date,1,7)=? AND job NOT LIKE '[SAMPLE]%'", (ym,))
        lm = ("1=1", ()) if sample else ("substr(coalesce(nullif(lead_date,''), created_at),1,7)=? AND name NOT LIKE '[SAMPLE]%'", (ym,))
        nos = "1=1" if sample else "name NOT LIKE '[SAMPLE]%'"
        props = q(f"SELECT status, bid, connects, views FROM proposals WHERE {pm[0]}", pm[1])
        sent = [r for r in props if r["status"] != "Draft"]
        viewed = [r for r in sent if r["status"] in ("Viewed", "Responded", "Interview", "Hired")]
        resp = [r for r in sent if r["status"] in ("Responded", "Interview", "Hired")]
        inter = [r for r in sent if r["status"] in ("Interview", "Hired")]
        won = [r for r in sent if r["status"] == "Hired"]; lost = [r for r in sent if r["status"] == "Lost"]
        openp = [r for r in sent if r["status"] in ("Submitted", "Viewed", "Responded", "Interview")]
        bids = [float(r["bid"] or 0) for r in sent if float(r["bid"] or 0) > 0]
        conn = sum(int(r["connects"] or 0) for r in sent); tviews = sum(int(r["views"] or 0) for r in sent)
        leads = q(f"SELECT status, budget FROM leads WHERE {lm[0]}", lm[1])
        lw = [r for r in leads if r["status"] == "Won"]; ll = [r for r in leads if r["status"] in ("Lost", "Dead")]
        lf = [r for r in leads if r["status"] == "Follow-up"]; lo = [r for r in leads if r["status"] not in FU_CLOSED]
        won_val = sum(float(r["budget"] or 0) for r in lw)
        if sample: fu_sent = q("SELECT coalesce(SUM(coalesce(fu_count,0)),0) FROM leads")[0][0]
        else: fu_sent = q(f"SELECT COUNT(*) FROM fu_events e JOIN leads l ON l.id=e.lead_id WHERE substr(e.at,1,7)=? AND l.{nos}", (ym,))[0][0]
        now_s = datetime.now().strftime("%Y-%m-%d %H:%M"); ncad = len(self.fu_cadence())
        overdue = q(f"SELECT COUNT(*) FROM leads WHERE next_followup IS NOT NULL AND next_followup<>'' AND next_followup<? AND status NOT IN ('Won','Lost','Dead') AND {nos}", (now_s,))[0][0]
        seqs = q(f"SELECT COUNT(*) FROM leads WHERE coalesce(fu_count,0)>=? AND {nos}", (ncad,))[0][0]
        inprog = q(f"SELECT COUNT(*) FROM leads WHERE coalesce(fu_count,0)<? AND status NOT IN ('Won','Lost','Dead') AND {nos}", (ncad,))[0][0]
        stages = q(f"SELECT coalesce(nullif(sales_stage,''),'No stage set') st, COUNT(*) n FROM leads WHERE {lm[0]} GROUP BY 1 ORDER BY 2 DESC", lm[1])
        meets = q("SELECT start, duration, status FROM meetings WHERE status<>'Removed'" + ("" if sample else " AND substr(start,1,7)=?"), () if sample else (ym,))
        booked = [r for r in meets if r["status"] != "Cancelled"]
        held = [r for r in booked if r["status"] == "Done" or (r["status"] == "Scheduled" and self._meet_end(r) < datetime.now())]
        upcoming = [r for r in booked if r["status"] == "Scheduled" and self._meet_end(r) >= datetime.now()]
        try: target = float(self.setting("perf_target") or 0)
        except ValueError: target = 0
        started = self.setting("fu_log_started"); started = "" if started in (None, "0") else started
        fu_note = f" (tracked since {started})" if (not sample and started and started[:7] >= ym) else ""
        money = lambda v: f"${v:,.0f}"
        return [
            ("Proposals", "Total proposals", len(props)), ("Proposals", "Submitted", len(sent)),
            ("Proposals", "Viewed by client", len(viewed)), ("Proposals", "Total views", tviews), ("Proposals", "Client responded", len(resp)),
            ("Proposals", "Interviews", len(inter)), ("Proposals", "Won (hired)", len(won)), ("Proposals", "Lost", len(lost)),
            ("Proposals", "Still open", len(openp)), ("Proposals", "Connects used", conn), ("Proposals", "View rate", pct(len(viewed), len(sent))),
            ("Proposals", "Response rate", pct(len(resp), len(sent))), ("Proposals", "Win rate", pct(len(won), len(sent))),
            ("Leads", "New leads", len(leads)), ("Leads", "Active in follow-up", len(lf)), ("Leads", "Still open", len(lo)),
            ("Leads", "Closed", len(lw) + len(ll)), ("Leads", "Closed won", len(lw)), ("Leads", "Closed lost", len(ll)),
            ("Leads", "Lead to client conversion", pct(len(lw), len(leads))), ("Leads", "Value of won leads", money(won_val)),
            ("Follow-ups", "Follow-ups sent" + fu_note, fu_sent), ("Follow-ups", "Overdue (at report time)", overdue),
            ("Follow-ups", "Sequences completed (at report time)", seqs), ("Follow-ups", "Sequences in progress (at report time)", inprog),
            ("Follow-ups", "Average response time", "Not tracked yet"),
            ("Meetings", "Booked", len(booked)), ("Meetings", "Held", len(held)), ("Meetings", "Upcoming", len(upcoming)),
            ("Meetings", "Cancelled", len(meets) - len(booked)),
            ("Upwork", "Average bid", money(sum(bids) / len(bids)) if bids else "-"),
            ("Upwork", "Connects per lead", f"{conn / len(leads):.1f}" if leads else "-"),
            ("Upwork", "Monthly lead target", int(target) if target else "-"),
            ("Upwork", "Lead target reached", pct(len(leads), target) if target else "-"),
        ] + [("Lead stages", r["st"], r["n"]) for r in stages]

    @staticmethod
    def report_highlights(data):
        v = {}
        for sec, met, val in data: v[met.split(" (")[0]] = val
        n = lambda k: v.get(k, 0) if isinstance(v.get(k, 0), (int, float)) else 0
        pl = lambda x, w: f"{x} {w}" + ("" if x == 1 else "s")
        out = [f"{pl(n('Submitted'), 'proposal')} submitted and {n('Viewed by client')} viewed by clients ({v.get('View rate', '-')} view rate)."]
        out.append(f"{pl(n('Won (hired)'), 'proposal')} won, a {v.get('Win rate', '-')} win rate." if n("Won (hired)") else "No proposals won yet. Focus on getting views turned into replies.")
        out.append(f"{pl(n('New leads'), 'new lead')}: {n('Closed won')} won, {n('Closed lost')} lost and {n('Active in follow-up')} still in follow-up.")
        if n("Overdue"): out.append(f"{pl(n('Overdue'), 'follow-up')} overdue when this report was made. Clear these first.")
        out.append(f"{pl(n('Held'), 'meeting')} held and {n('Upcoming')} still upcoming.")
        if n("Connects used"): out.append(f"{n('Connects used')} connects used, about {v.get('Connects per lead', '-')} per lead.")
        return out

    def report_generate(self, ym=None, auto=False, quiet=False):
        import json
        ym = ym or date.today().strftime("%Y-%m")
        if ym != "SAMPLE":
            try: ok_ = bool(_re.fullmatch(r"\d{4}-\d{2}", ym)) and datetime.strptime(ym, "%Y-%m").year >= 2000
            except ValueError: ok_ = False
            if not ok_:
                if not quiet: messagebox.showwarning("Report month", f"'{ym}' is not a real month. Use year-month, for example 2026-11.")
                return None
        self.db.execute("INSERT OR REPLACE INTO reports(month, generated_at, data, auto) VALUES(?,?,?,?)",
                        (ym, datetime.now().strftime("%d %b %Y, %I:%M %p"), json.dumps(self.report_data(ym)), 1 if auto else 0))
        self.db.commit()
        if hasattr(self, "rep_list"):
            self.rep_refresh(select=None if (quiet and ym == "SAMPLE") else ym)
        if not quiet: self.rep_msg.config(text=f"{self._ym_label(ym)} report generated and saved.", fg=UI["green"])
        return ym

    @staticmethod
    def _ym_label(ym):
        if ym == "SAMPLE": return "Sample report"
        try: return datetime.strptime(ym, "%Y-%m").strftime("%B %Y")
        except ValueError: return ym

    def reports_auto(self):
        """When a new month starts, save last month's report automatically (once). Checks again every hour."""
        try:
            t = date.today(); prev = (date(t.year - 1, 12, 1) if t.month == 1 else date(t.year, t.month - 1, 1)).strftime("%Y-%m")
            have = self.db.execute("SELECT 1 FROM reports WHERE month=?", (prev,)).fetchone()
            any_data = self.db.execute("SELECT (SELECT COUNT(*) FROM proposals WHERE substr(proposal_date,1,7)=?) + (SELECT COUNT(*) FROM leads WHERE substr(coalesce(nullif(lead_date,''), created_at),1,7)=?)", (prev, prev)).fetchone()[0]
            if not have and any_data: self.report_generate(prev, auto=True, quiet=True)
        except Exception: pass
        try: self.root.after(3600 * 1000, self.reports_auto)
        except tk.TclError: pass

    def make_reports(self):
        p = self.tabs["reports"]
        self.section_title(p, "Reporting", "Monthly summaries of your proposals, leads, follow-ups and meetings. Last month's report is saved automatically when a new month starts.")
        bar = tk.Frame(p, bg=UI["bg"]); bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Generate this month's report", style="Accent.TButton", command=lambda: self.report_generate()).pack(side="left")
        ttk.Button(bar, text="Export CSV", command=self.report_export_csv).pack(side="left", padx=6)
        ttk.Button(bar, text="Print / Save as PDF", command=self.report_print).pack(side="left")
        self.rep_msg = tk.Label(bar, text="", bg=UI["bg"], fg=UI["muted"], font=("Segoe UI", 9)); self.rep_msg.pack(side="left", padx=12)
        # month picker: a compact dropdown instead of a tall list
        pick = tk.Frame(p, bg=UI["bg"]); pick.pack(fill="x", pady=(4, 10))
        tk.Label(pick, text="Report month", bg=UI["bg"], fg=UI["text"], font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 10))
        self.rep_list = MonthPicker(pick, self.rep_show); self.rep_list.cb.pack(side="left")
        self.rep_count = tk.Label(pick, text="", bg=UI["bg"], fg=UI["muted"], font=("Segoe UI", 9)); self.rep_count.pack(side="left", padx=12)
        body = tk.Frame(p, bg=UI["bg"]); body.pack(fill="both", expand=True)
        # report view: a scrollable, designed page
        right = tk.Frame(body, bg=UI["bg"]); right.pack(side="left", fill="both", expand=True)
        cv = tk.Canvas(right, bg=UI["bg"], highlightthickness=0); sb = ttk.Scrollbar(right, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y"); cv.pack(side="left", fill="both", expand=True)
        self.rep_view = tk.Frame(cv, bg=UI["bg"]); win = cv.create_window((0, 0), window=self.rep_view, anchor="nw")
        self.rep_view.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        rep_idx = self.nb.index(p)
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units") if self.nb.index("current") == rep_idx else None, add="+")
        self.rep_canvas = cv
        self.report_generate("SAMPLE", quiet=True)   # sample stays up to date with your data

    def rep_refresh(self, select=None):
        cur = self.rep_list.selection()
        select = select or (cur[0] if cur else None)
        self.rep_list.delete(*self.rep_list.get_children())
        rows = self.db.execute("SELECT month, generated_at, auto FROM reports ORDER BY (month='SAMPLE') DESC, month DESC").fetchall()
        for r in rows:
            smp = r["month"] == "SAMPLE"
            how = "demo" if smp else ("saved automatically" if r["auto"] else "saved by you")
            gen = __import__("re").sub(r" \d{4},", ",", r["generated_at"] or "")
            self.rep_list.insert("", "end", r["month"], f"{self._ym_label(r['month'])}   ({how}, {gen})")
        real = sum(1 for r in rows if r["month"] != "SAMPLE")
        self.rep_count.config(text=f"{real} saved month{'s' if real != 1 else ''} plus the sample")
        if rows:
            pick = select if select and self.rep_list.exists(select) else rows[0]["month"]
            self.rep_list.selection_set(pick)
        else: self.rep_show()

    def _rep_current(self):
        import json
        sel = self.rep_list.selection()
        if not sel: return None, None
        r = self.db.execute("SELECT * FROM reports WHERE month=?", (sel[0],)).fetchone()
        return (r, json.loads(r["data"])) if r else (None, None)

    # Reporting palette: one set of card colors used across the app
    PAL = {"indigo": ("#4338CA", "#EEF2FF"), "green": ("#047857", "#ECFDF5"), "sky": ("#0369A1", "#E0F2FE"),
           "amber": ("#B45309", "#FFFBEB"), "slate": ("#0F172A", "#F1F5F9")}
    # section, card title, palette, the 3 headline numbers shown big
    REP_CARDS = [("Proposals", "Proposals", "indigo", ("Submitted", "Won (hired)", "Lost")),
                 ("Leads", "Leads", "green", ("New leads", "Active in follow-up", "Closed won")),
                 ("Follow-ups", "Follow-up activity", "sky", ("Follow-ups sent", "Overdue", "Sequences completed")),
                 ("Meetings", "Meetings", "amber", ("Booked", "Held", "Upcoming")),
                 ("Lead stages", "Leads by stage", "indigo", ()),
                 ("Upwork", "Upwork numbers", "slate", ("Average bid", "Connects per lead", "Lead target reached"))]
    REP_TILES = [("Proposals", "Submitted", "Proposals submitted", "#4338CA", "#EEF2FF"), ("Leads", "Closed won", "Leads won", "#047857", "#ECFDF5"),
                 ("Follow-ups", "Follow-ups sent", "Follow-ups sent", "#0369A1", "#E0F2FE"), ("Meetings", "Held", "Meetings held", "#B45309", "#FFFBEB")]

    @staticmethod
    def _rep_num(x):
        try: return float(str(x).replace("%", "").replace("$", "").replace(",", ""))
        except ValueError: return None

    def rep_show(self):
        v = self.rep_view
        for w in v.winfo_children(): w.destroy()
        r, data = self._rep_current()
        self.rep_cards = {}; self.rep_shown = []
        if not r:
            tk.Label(v, text="No report yet. Click \"Generate this month's report\" to create one.", bg=UI["bg"], fg=UI["muted"], font=("Segoe UI", 10)).pack(anchor="w", pady=20)
            return
        smp = r["month"] == "SAMPLE"
        if smp:
            ban = tk.Frame(v, bg="#FFFBEB", highlightthickness=1, highlightbackground="#B45309"); ban.pack(fill="x", pady=(0, 12))
            tk.Label(ban, text="SAMPLE REPORT, NOT REAL DATA", bg="#FFFBEB", fg="#B45309", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(8, 0))
            tk.Label(ban, text="This demo uses everything currently in LeadPilot, including sample records, to show what a finished monthly report looks like.",
                     bg="#FFFBEB", fg="#B45309", font=("Segoe UI", 9), wraplength=760, justify="left").pack(anchor="w", padx=14, pady=(0, 8))
        hd = self.card(v, fill="x"); tk.Frame(hd, bg="#4338CA", height=4).pack(fill="x")
        hrow = tk.Frame(hd, bg=UI["card"]); hrow.pack(fill="x", padx=18, pady=12)
        hl = tk.Frame(hrow, bg=UI["card"]); hl.pack(side="left")
        tk.Label(hl, text="MONTHLY REPORT", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(hl, text="Sample month" if smp else self._ym_label(r["month"]), bg=UI["card"], fg=UI["text"], font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(hrow, text=f"Ammar Yasir\nGenerated {r['generated_at']}", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9), justify="right").pack(side="right")
        val = {}
        for sec, met, x in data: val[(sec, met.split(" (")[0])] = (met, x); val[(sec, met)] = (met, x)
        grid = tk.Frame(v, bg=UI["bg"]); grid.pack(fill="x", pady=(12, 0))
        grid.columnconfigure(0, weight=1, uniform="rc"); grid.columnconfigure(1, weight=1, uniform="rc")
        cards = [c for c in self.REP_CARDS if any(s_ == c[0] for s_, _, _ in data)]
        for i, (sec, title, pal, big) in enumerate(cards):
            col, soft = self.PAL[pal]
            c = self.card(grid); c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 6) if i % 2 == 0 else (6, 0), pady=(0, 12))
            tk.Frame(c, bg=col, height=4).pack(fill="x")
            tk.Label(c, text=title, bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 8))
            box = tk.Frame(c, bg=UI["card"]); box.pack(fill="x", padx=16, pady=(0, 14)); self.rep_cards[sec] = box
            used = set()
            if big:   # three headline numbers in soft tiles
                st = tk.Frame(box, bg=UI["card"]); st.pack(fill="x", pady=(0, 10))
                for j, key in enumerate(big):
                    st.columnconfigure(j, weight=1, uniform="bs")
                    met, x = val.get((sec, key), (key, "-")); used.add(met); self.rep_shown.append(met)
                    t = tk.Frame(st, bg=soft); t.grid(row=0, column=j, sticky="nsew", padx=(0 if j == 0 else 4, 0 if j == 2 else 4))
                    tk.Label(t, text=str(x), bg=soft, fg=col, font=("Segoe UI", 24, "bold")).pack(anchor="w", padx=12, pady=(6, 0))
                    tk.Label(t, text=key, bg=soft, fg=col, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(0, 8))
            rows = [(m_, x) for s_, m_, x in data if s_ == sec and m_ not in used]
            mx = max([self._rep_num(x) or 0 for m_, x in rows] + [1]) if sec == "Lead stages" else None
            lst = tk.Frame(box, bg=UI["card"]); lst.pack(fill="x"); lst.columnconfigure(0, weight=1)
            for j, (m_, x) in enumerate(rows):
                self.rep_shown.append(m_)
                muted = str(x) in ("-", "Not tracked yet")
                tk.Label(lst, text=m_, bg=UI["card"], fg=UI["muted"] if muted else UI["text"], font=("Segoe UI", 9), anchor="w").grid(row=j, column=0, sticky="ew", pady=3)
                n = self._rep_num(x)
                ratio = (n / 100.0) if (isinstance(x, str) and x.endswith("%") and n is not None) else ((n or 0) / mx if mx else None)
                if ratio is not None:   # small visual bar for rates and stage counts
                    bar = tk.Canvas(lst, width=110, height=8, bg=soft, highlightthickness=0); bar.grid(row=j, column=1, padx=(8, 10))
                    bar.create_rectangle(0, 0, max(0, min(1, ratio)) * 110, 8, fill=col, outline="")
                tk.Label(lst, text=str(x), bg=UI["card"], fg=UI["muted"] if muted else UI["text"],
                         font=("Segoe UI", 9) if muted else ("Segoe UI", 10, "bold"), anchor="e").grid(row=j, column=2, sticky="e", pady=3)
                if j < len(rows) - 1: tk.Frame(lst, bg="#F1F5F9", height=1).grid(row=j, column=0, columnspan=3, sticky="sew")
        # Highlights across the full width
        hc = self.card(grid); hc.grid(row=(len(cards) + 1) // 2, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
        tk.Frame(hc, bg="#0F172A", height=4).pack(fill="x")
        tk.Label(hc, text="Highlights", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 6))
        hb = tk.Frame(hc, bg=UI["card"]); hb.pack(fill="x", padx=16, pady=(0, 14)); self.rep_cards["Highlights"] = hb
        for j, line in enumerate(self.report_highlights(data)):
            tk.Label(hb, text="\u2022  " + line, bg=UI["card"], fg=UI["text"], font=("Segoe UI", 9), wraplength=820, justify="left").pack(anchor="w", pady=2)
        try: self.rep_canvas.yview_moveto(0)
        except Exception: pass

    def report_export_csv(self):
        r, data = self._rep_current()
        if not r: return messagebox.showinfo("Export report", "Generate or pick a report first.")
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"LeadPilot_report_{r['month']}.csv", filetypes=[("CSV files", "*.csv")])
        if not path: return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh); w.writerow(["LeadPilot monthly report", self._ym_label(r["month"]), f"Generated {r['generated_at']}"])
            if r["month"] == "SAMPLE": w.writerow(["SAMPLE REPORT, NOT REAL DATA"])
            w.writerow([]); w.writerow(["Section", "Metric", "Value"]); w.writerows(data)
            w.writerow([]); w.writerow(["Highlights"]); [w.writerow(["", h]) for h in self.report_highlights(data)]
        self.rep_msg.config(text=f"Saved {Path(path).name}", fg=UI["green"])

    def report_print(self):
        import webbrowser
        r, data = self._rep_current()
        if not r: return messagebox.showinfo("Print report", "Generate or pick a report first.")
        out = APP_DIR / "reports"; out.mkdir(exist_ok=True); fp = out / f"LeadPilot_report_{r['month']}.html"
        fp.write_text(self.report_html(r, data), encoding="utf-8")
        webbrowser.open(fp.as_uri())
        self.rep_msg.config(text="Opened in your browser. Use Print, or choose Save as PDF.", fg=UI["muted"])

    def report_html(self, r, data):
        """A4 business-style report: cover band, summary, KPI tiles, charts (inline SVG) and data tables."""
        import html
        e = html.escape; smp = r["month"] == "SAMPLE"
        val = {(s_, m_.split(" (")[0]): x for s_, m_, x in data}; val.update({(s_, m_): x for s_, m_, x in data})
        g = lambda s_, k: val.get((s_, k), "-")
        num = lambda s_, k: self._rep_num(g(s_, k)) or 0
        month = "Sample month" if smp else self._ym_label(r["month"])
        def hbars(items, color, suffix="", mx=None):   # horizontal bar chart (HTML, prints crisply)
            mx = mx or max([v_ for _, v_ in items] + [1]); rows = []
            for lab, v_ in items:
                w = max(0, min(100, 100 * v_ / mx))
                rows.append(f'<div class="hb"><span class="l" title="{e(lab)}">{e(lab)}</span><span class="tr"><i style="width:{w:.1f}%;background:{color}"></i></span><b>{v_:g}{suffix}</b></div>')
            return "".join(rows)
        def stack(parts):   # one stacked bar with a legend
            tot = sum(v_ for _, v_, _ in parts) or 1; x = 0; segs = []; leg = []
            for lab, v_, col in parts:
                w = 520 * v_ / tot
                if w > 0: segs.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="22" fill="{col}"/>')
                x += w; leg.append(f'<span><i style="background:{col}"></i>{e(lab)}: <b>{v_:g}</b></span>')
            return f'<svg viewBox="0 0 520 22" width="100%" height="22" style="border-radius:4px">{"".join(segs)}</svg><div class="leg">{"".join(leg)}</div>'
        def table(sec):
            rows = "".join(f"<tr><td>{e(m_)}</td><td class='v'>{e(str(x))}</td></tr>" for s_, m_, x in data if s_ == sec)
            return f"<table>{rows}</table>" if rows else "<p class='mut'>No data.</p>"
        tiles = "".join(f'<div class="t" style="background:{bg};color:{col}"><b>{e(str(g(s_, k)))}</b><span>{e(cap)}</span></div>' for s_, k, cap, col, bg in self.REP_TILES)
        funnel = hbars([("Submitted", num("Proposals", "Submitted")), ("Viewed", num("Proposals", "Viewed by client")),
                        ("Responded", num("Proposals", "Client responded")), ("Interviews", num("Proposals", "Interviews")),
                        ("Won", num("Proposals", "Won (hired)"))], "#4338CA")
        outcome = stack([("Won", num("Proposals", "Won (hired)"), "#047857"), ("Lost", num("Proposals", "Lost"), "#DC2626"),
                         ("Still open", num("Proposals", "Still open"), "#CBD5E1")])
        stages = [(m_, self._rep_num(x) or 0) for s_, m_, x in data if s_ == "Lead stages"]
        stage_chart = hbars(stages, "#047857") if stages else "<p class='mut'>Lead stages were not recorded in this report.</p>"
        fu = stack([("Sequences completed", num("Follow-ups", "Sequences completed"), "#0369A1"),
                    ("In progress", num("Follow-ups", "Sequences in progress"), "#7DD3FC"), ("Overdue now", num("Follow-ups", "Overdue"), "#B45309")])
        rates = hbars([(k, num(s_, k)) for s_, k in (("Proposals", "View rate"), ("Proposals", "Response rate"), ("Proposals", "Win rate"),
                                                    ("Leads", "Lead to client conversion"))], "#6366F1", "%", 100)
        hl = "".join(f"<li>{e(h)}</li>" for h in self.report_highlights(data))
        banner = '<div class="smp"><b>SAMPLE REPORT, NOT REAL DATA.</b> Built from everything currently in LeadPilot to show what a finished monthly report looks like.</div>' if smp else ""
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>LeadPilot report {e(r['month'])}</title><style>
@page{{size:A4;margin:14mm}} *{{box-sizing:border-box}}
body{{font-family:'Segoe UI',Arial,sans-serif;color:#0F172A;margin:0 auto;max-width:800px;font-size:12px;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.cover{{background:linear-gradient(90deg,#4338CA,#6366F1);color:#fff;padding:26px 28px;border-radius:6px}}
.cover small{{letter-spacing:2px;font-weight:700;opacity:.85}} .cover h1{{margin:6px 0 2px;font-size:28px}} .cover p{{margin:0;opacity:.9}}
.smp{{background:#FFFBEB;border:1px solid #B45309;color:#B45309;padding:9px 14px;margin:12px 0 0;border-radius:4px}}
h2{{font-size:15px;margin:22px 0 8px;padding-bottom:5px;border-bottom:2px solid #E6EAF2}}
.ts{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}} .t{{padding:12px 14px;border-radius:4px}} .t b{{display:block;font-size:28px}} .t span{{font-size:11px;font-weight:700}}
.g{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .box{{border:1px solid #E6EAF2;border-radius:4px;padding:12px 14px;break-inside:avoid}}
.box h3{{margin:0 0 8px;font-size:13px}} .hb{{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:11px}} .hb .l{{width:120px;color:#334155;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.hb .tr{{flex:1;height:12px;background:#F1F5F9;border-radius:3px;overflow:hidden}} .hb .tr i{{display:block;height:100%}} .hb b{{width:40px;text-align:right}} .leg{{display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;font-size:11px}} .leg i{{display:inline-block;width:10px;height:10px;margin-right:5px;border-radius:2px}}
table{{width:100%;border-collapse:collapse}} td{{padding:5px 6px;border-bottom:1px solid #F1F5F9}} td.v{{text-align:right;font-weight:700}}
ul{{margin:0;padding-left:18px}} li{{margin:4px 0}} .mut{{color:#64748B}} section{{break-inside:avoid}}
.foot{{margin-top:22px;color:#64748B;font-size:10px;border-top:1px solid #E6EAF2;padding-top:8px}}
</style></head><body onload="window.print()">
<div class="cover"><small>LEADPILOT MONTHLY BUSINESS REPORT</small><h1>{e(month)}</h1><p>Prepared for Ammar Yasir. Generated {e(r['generated_at'])}.</p></div>{banner}
<section><h2>Summary</h2><ul>{hl}</ul></section>
<section><h2>Key numbers</h2><div class="ts">{tiles}</div></section>
<section><h2>Proposals</h2><div class="g"><div class="box"><h3>Proposal funnel</h3>{funnel}</div>
<div class="box"><h3>Won vs lost</h3>{outcome}<h3 style="margin-top:16px">Rates</h3>{rates}</div></div></section>
<section><h2>Leads and follow-ups</h2><div class="g"><div class="box"><h3>Leads by stage</h3>{stage_chart}</div>
<div class="box"><h3>Follow-up sequences</h3>{fu}</div></div></section>
<section><h2>Detailed numbers</h2><div class="g"><div class="box"><h3>Proposals</h3>{table('Proposals')}</div><div class="box"><h3>Leads</h3>{table('Leads')}</div>
<div class="box"><h3>Follow-up activity</h3>{table('Follow-ups')}</div><div class="box"><h3>Meetings</h3>{table('Meetings')}</div>
<div class="box"><h3>Upwork numbers</h3>{table('Upwork')}</div></div></section>
<div class="foot">LeadPilot CRM. {'Sample data, for layout preview only.' if smp else 'Sample records are left out of these numbers.'}</div></body></html>"""

    def make_upwork(self):
        p = self.tabs["upwork"]
        self.section_title(p, "Upwork Connection",
            "Enter your Upwork login once. It is saved in Windows' secure password vault, not in any file.")
        box = ttk.Frame(p); box.pack(anchor="w", pady=10)
        self.upwork_status = tk.Label(box, text="", font=("Segoe UI", 12, "bold"), bg=UI["bg"])
        self.upwork_status.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(box, text="Upwork email").grid(row=1, column=0, sticky="w", pady=4)
        self.upwork_email = ttk.Entry(box, width=40); self.upwork_email.grid(row=1, column=1, pady=4, padx=10)
        ttk.Label(box, text="Upwork password").grid(row=2, column=0, sticky="w", pady=4)
        self.upwork_pass = ttk.Entry(box, width=40, show="*"); self.upwork_pass.grid(row=2, column=1, pady=4, padx=10)
        tk.Button(box, text="\u24d8", font=("Segoe UI", 12), relief="flat", bd=0, cursor="hand2", bg=UI["bg"],
                  command=self.upwork_peek).grid(row=2, column=2, sticky="w")
        btns = ttk.Frame(box); btns.grid(row=3, column=1, sticky="w", padx=10, pady=12)
        ttk.Button(btns, text="Save & Connect", command=self.upwork_save).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Disconnect", command=self.upwork_disconnect).pack(side="left")
        ttk.Button(btns, text="Open Upwork", command=self.upwork_open).pack(side="left", padx=(8, 0))
        ttk.Label(p, text="Tip: use this only to help you open Upwork. Do not auto-send proposals, as Upwork does not allow it.",
                  style="Sub.TLabel", wraplength=950).pack(anchor="w", pady=10)
        self.upwork_refresh_status()

    # ---------- Fresh Audit ----------
    def make_audit(self):
        p = self.tabs["audit"]
        self.section_title(p, "Fresh Audit",
            "Re-check all your submitted proposals on Upwork and update which ones the client has viewed.")
        ab = ttk.Frame(p); ab.pack(anchor="w", pady=(8, 4))
        ttk.Button(ab, text="\u25b6  Start Fresh Audit", style="Accent.TButton", command=self.upwork_scan_pages).pack(side="left")
        ttk.Label(p, text="Click 'Start Fresh Audit'. LeadPilot opens your Submitted proposals page on Upwork (if it isn't open already) and copies each page for you. Click Next on Upwork and it reads the new page by itself. Click Finish when you reach the last page to see the summary.",
                  style="Sub.TLabel", wraplength=950).pack(anchor="w", pady=(4, 0))
        ttk.Separator(p).pack(fill="x", pady=14)
        ttk.Label(p, text="Your Upwork jobs", style="Title.TLabel").pack(anchor="w")
        ttk.Label(p, text="Jobs found or updated by Fresh Audit appear here.", style="Sub.TLabel", wraplength=950).pack(anchor="w", pady=(4, 4))
        self.utree = self.make_tree(p, ("id","job","client","proposal_date","status"),
                                    ("ID","Job title","Client","Date applied","Status"), (60, 520, 160, 120, 110))
        self.upwork_refresh_jobs()

    def upwork_refresh_status(self):
        if hasattr(self, 'conn_badge'): self.update_conn_badge()
        if _keyring is None:
            self.upwork_status.config(text="Not available: run  python -m pip install keyring", fg="#B42318")
            return
        email, password = get_upwork_login()
        if email and password:
            self.upwork_status.config(text=f"\u25cf Connected as {email}", fg="#067647")
            self.upwork_email.delete(0, tk.END); self.upwork_email.insert(0, email)
        else:
            self.upwork_status.config(text="\u25cf Disconnected", fg="#B42318")

    def upwork_save(self):
        if _keyring is None:
            messagebox.showerror("Missing part", "Run: python -m pip install keyring"); return
        email = self.upwork_email.get().strip(); password = self.upwork_pass.get()
        if not email or not password:
            messagebox.showwarning("Missing info", "Please enter both your Upwork email and password."); return
        save_upwork_login(email, password)
        self.upwork_pass.delete(0, tk.END)
        self.upwork_refresh_status()
        messagebox.showinfo("Saved", "Your Upwork login is saved securely.")

    def upwork_open(self):
        import webbrowser
        email = None
        if _keyring is not None:
            email, _ = get_upwork_login()
        if email:
            self.root.clipboard_clear(); self.root.clipboard_append(email); self.root.update()
        webbrowser.open("https://www.upwork.com/ab/account-security/login")
        if email:
            messagebox.showinfo("Upwork opened",
                f"Upwork's login page is opening in your browser.\n\nYour email ({email}) is copied. "
                "Click the email box and press Ctrl+V to paste it, then type your password yourself.")

    def upwork_peek(self):
        """Show the password for 5 seconds, then hide it again."""
        typed = self.upwork_pass.get()
        from_vault = False
        if not typed and _keyring is not None:
            _, saved = get_upwork_login()
            if not saved:
                messagebox.showinfo("No password", "No Upwork password is saved yet."); return
            self.upwork_pass.insert(0, saved); from_vault = True
        self.upwork_pass.config(show="")
        def hide():
            self.upwork_pass.config(show="*")
            if from_vault: self.upwork_pass.delete(0, tk.END)
        self.root.after(5000, hide)

    def upwork_refresh_jobs(self):
        rows = self.db.execute("SELECT * FROM proposals WHERE notes LIKE 'Imported from Upwork%' ORDER BY proposal_date DESC").fetchall()
        self.utree.delete(*self.utree.get_children())
        for i, r in enumerate(rows):
            self.utree.insert("", "end", values=(r["id"], r["job"], r["client"] or "", r["proposal_date"] or "", r["status"]),
                              tags=("odd" if i % 2 else "even",))

    def _plan_import(self, jobs):
        """Decide what each scanned job means: ('new', j) or ('update', j, id, new_status_or_None, fill_date).
        Matches by proposal URL when the job has one, otherwise by title (case-insensitive, trimmed).
        Never adds a second row for a job already in the CRM, and never downgrades a status."""
        rows = self.db.execute("SELECT id, job, url, status, proposal_date FROM proposals ORDER BY id DESC").fetchall()
        by_title, by_url = {}, {}
        for r in rows:
            by_title.setdefault(_norm_title(r["job"]), r)
            k = _url_key(r["url"])
            if k: by_url.setdefault(k, r)
        plan, planned_new = [], set()
        for j in jobs:
            key = _norm_title(j["job"])
            hit = (by_url.get(_url_key(j.get("url"))) if j.get("url") else None) or by_title.get(key)
            target = "Viewed" if j.get("viewed") and j["status"] == "Submitted" else j["status"]
            if not hit:
                if key in planned_new: continue          # same job twice in one copy: add it once
                planned_new.add(key); plan.append(("new", j, target)); continue
            cur = hit["status"]
            up = target if (target in _STATUS_RANK and cur in _STATUS_RANK and _STATUS_RANK[target] > _STATUS_RANK[cur]) else None
            fill = j["proposal_date"] if not hit["proposal_date"] and j.get("proposal_date") else None
            plan.append(("update", j, hit["id"], up, fill))
        return plan

    def _commit_import(self, plan, note):
        email = None
        if _keyring is not None:
            email, _ = get_upwork_login()
        added = viewed = other = 0
        for item in plan:
            if item[0] == "new":
                _, j, st = item
                self.db.execute("INSERT INTO proposals(account, member, job, proposal_date, status, notes) VALUES(?,?,?,?,?,?)",
                                ("Upwork", email or "Me", j["job"], j["proposal_date"], st, note))
                added += 1
            else:
                _, j, pid, up, fill = item
                if fill: self.db.execute("UPDATE proposals SET proposal_date=? WHERE id=? AND (proposal_date IS NULL OR proposal_date='')", (fill, pid))
                if up:
                    self.db.execute("UPDATE proposals SET status=? WHERE id=?", (up, pid))
                    if up == "Viewed": viewed += 1
                    else: other += 1
        self.db.commit()
        return added, viewed, other

    def upwork_import_clipboard(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Nothing copied", "Copy your Upwork Proposals page first (Ctrl+A, then Ctrl+C)."); return
        jobs = parse_upwork_proposals(text)
        if not jobs:
            messagebox.showwarning("No jobs found",
                "I couldn't find any jobs in what you copied.\nMake sure you copied the My Proposals page on Upwork.")
            return
        plan = self._plan_import(jobs)
        new = [x for x in plan if x[0] == "new"]
        ups = [x for x in plan if x[0] == "update" and x[3]]
        if not new and not ups:
            messagebox.showinfo("Up to date", f"Found {len(jobs)} jobs. All are already in your CRM and nothing changed."); return
        msg = ""
        if new:
            preview = "\n".join(f"- {j['proposal_date']}  {j['job'][:60]}  ({st})" for _, j, st in new[:15])
            more = f"\n...and {len(new)-15} more" if len(new) > 15 else ""
            msg += f"New jobs to add ({len(new)}):\n{preview}{more}\n\n"
        if ups:
            msg += f"Existing jobs to update ({len(ups)}):\n" + "\n".join(f"- {x[1]['job'][:55]}  ->  {x[3]}" for x in ups[:15]) + "\n\n"
        if not messagebox.askyesno("Save these changes?", msg + "Save to your CRM?"):
            return
        added, viewed, other = self._commit_import(plan, "Imported from Upwork")
        self.refresh_all(); self.upwork_refresh_jobs()
        messagebox.showinfo("Saved", f"Added {added} new jobs, marked {viewed} as Viewed and updated {other} other statuses.\nNo duplicates were created.")

    def add_new_proposal(self):
        STYLE = {"Normal": ("#1D4ED8", "#DBEAFE", "\u25c6  Normal", [10, 15, 20]),
                 "Boosted": ("#C2410C", "#FFEDD5", "\u26a1  Boosted", [5, 10, 15, 20])}
        win = tk.Toplevel(self.root); win.title("Add new proposal"); win.configure(bg="#FFFFFF")
        win.transient(self.root); win.resizable(False, False); win.grab_set()
        body = tk.Frame(win, bg="#FFFFFF"); body.pack(padx=28, pady=22)
        tk.Label(body, text="Add new proposal", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(body, text="Saved with status Submitted.", bg="#FFFFFF", fg=UI["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 14))
        tk.Label(body, text="1.  Proposal URL", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        url_var = tk.StringVar()
        try:
            clip = self.root.clipboard_get().strip()
            if clip.startswith("http") and "upwork.com" in clip and "\n" not in clip: url_var.set(clip)
        except tk.TclError:
            pass
        ent = tk.Entry(body, textvariable=url_var, width=62, font=("Segoe UI", 10), relief="solid", bd=1)
        ent.pack(anchor="w", fill="x", pady=(4, 16), ipady=5); ent.focus_set()
        tk.Label(body, text="2.  Connects", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        con_row = tk.Frame(body, bg="#FFFFFF"); con_row.pack(anchor="w", pady=(4, 6))
        con_vars = {}
        for name in ("Normal", "Boosted"):
            fg, soft, label, _ = STYLE[name]
            col = tk.Frame(con_row, bg="#FFFFFF"); col.pack(side="left", padx=(0, 18))
            v = tk.StringVar(); con_vars[name] = v
            tk.Entry(col, textvariable=v, width=10, justify="center", font=("Segoe UI", 13, "bold"), fg=fg, relief="solid", bd=1,
                     highlightthickness=2, highlightbackground=soft, highlightcolor=fg).pack(ipady=6)
            tk.Label(col, text=name, bg="#FFFFFF", fg=fg, font=("Segoe UI", 9, "bold")).pack(pady=(4, 0))

        def save(event=None):
            url = url_var.get().strip()
            if not url.lower().startswith("http"):
                messagebox.showwarning("Missing URL", "Paste the proposal URL first.", parent=win); return
            vals = {}
            for name, v in con_vars.items():
                t = v.get().strip()
                if not t: vals[name] = None; continue
                if not t.isdigit():
                    messagebox.showwarning("Connects must be a number", f"The {name} box must be a whole number, like 12.", parent=win); return
                vals[name] = int(t)
            if vals["Normal"] is None and vals["Boosted"] is None:
                messagebox.showwarning("Connects missing", "Type your connects in the Normal box, the Boosted box, or both.", parent=win); return
            total = (vals["Normal"] or 0) + (vals["Boosted"] or 0)
            cat = "Boosted" if vals["Boosted"] is not None else "Normal"   # both filled counts as Boosted
            if self.db.execute("SELECT 1 FROM proposals WHERE url=?", (url,)).fetchone():
                if not messagebox.askyesno("Already saved", "This URL is already in LeadPilot. Add it again anyway?", parent=win): return
            m = _re.search(r"/proposals/(\d+)", url) or _re.search(r"~0?(\w+)", url)
            title = f"New proposal ({m.group(1)})" if m else "New proposal"
            email = None
            if _keyring is not None:
                email, _ = get_upwork_login()
            self.db.execute("INSERT INTO proposals(account, member, job, url, proposal_date, connects, connects_normal, connects_boosted, category, status, notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            ("Upwork", email or "Me", title, url, date.today().isoformat(), total, vals["Normal"], vals["Boosted"], cat, "Submitted",
                             "Added with Add new proposal."))
            self.db.commit(); win.destroy(); self.refresh_all()
            messagebox.showinfo("Saved", f"Saved as {cat}, {total} connects, status Submitted.")

        btns = tk.Frame(body, bg="#FFFFFF"); btns.pack(fill="x", pady=(18, 0))
        tk.Button(btns, text="Save proposal", command=save, bg=UI["accent"], fg="#FFFFFF", relief="flat", bd=0, padx=18, pady=8,
                  font=("Segoe UI", 10, "bold"), cursor="hand2", activebackground="#4F46E5", activeforeground="#FFFFFF").pack(side="right")
        tk.Button(btns, text="Cancel", command=win.destroy, bg="#F1F5F9", fg=UI["text"], relief="flat", bd=0, padx=14, pady=8,
                  font=("Segoe UI", 10), cursor="hand2").pack(side="right", padx=8)
        win.bind("<Return>", save); win.bind("<Escape>", lambda e: win.destroy())
        self._new_proposal_win = (win, url_var, con_vars, save)

    def upwork_scan_pages(self):
        if getattr(self, "_scan", None) and self._scan["win"].winfo_exists():
            self._scan["win"].lift(); return
        opened = False
        if find_upwork_window() is None and not _title_has(find_job_browser_window(), "proposal"):
            # One click: open the Submitted proposals page in your normal browser (your own Upwork session handles login)
            try:
                __import__("webbrowser").open("https://www.upwork.com/nx/proposals/")
                opened = True
            except Exception:
                messagebox.showwarning("Upwork not found",
                    "I couldn't open your browser.\n\nOpen your Submitted proposals page on Upwork, make sure you're logged in, then click Start Fresh Audit again.")
                return
        win = tk.Toplevel(self.root); win.title("Fresh Audit"); win.configure(bg="#FFFFFF"); win.attributes("-topmost", True); win.resizable(False, False)
        sw = self.root.winfo_screenwidth(); win.geometry(f"360x300+{sw - 390}+80")
        tk.Frame(win, bg="#4338CA", height=4).pack(fill="x")
        body = tk.Frame(win, bg="#FFFFFF"); body.pack(fill="both", expand=True, padx=18, pady=12)
        tk.Label(body, text="Fresh Audit", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        status = tk.Label(body, text="Starting...", bg="#FFFFFF", fg=UI["muted"], font=("Segoe UI", 9), wraplength=320, justify="left"); status.pack(anchor="w", pady=(4, 10))
        nums = tk.Frame(body, bg="#FFFFFF"); nums.pack(fill="x")
        labels = {}
        for i, (k, cap, col) in enumerate([("pages", "Pages", "#475569"), ("scanned", "Scanned", "#4338CA"), ("viewed", "New Viewed", "#047857"), ("added", "Added", "#0369A1")]):
            t = tk.Frame(nums, bg="#F8FAFC"); t.grid(row=0, column=i, padx=(0, 6), sticky="nsew")
            v = tk.Label(t, text="0", bg="#F8FAFC", fg=col, font=("Segoe UI", 15, "bold"), width=4); v.pack(pady=(6, 0))
            tk.Label(t, text=cap, bg="#F8FAFC", fg=UI["muted"], font=("Segoe UI", 8)).pack(pady=(0, 6)); labels[k] = v
        tk.Label(body, text="Click Next on Upwork after each page. LeadPilot reads the new page by itself every few seconds.",
                 bg="#FFFFFF", fg=UI["muted"], font=("Segoe UI", 8), wraplength=320, justify="left").pack(anchor="w", pady=(10, 0))
        btns = tk.Frame(body, bg="#FFFFFF"); btns.pack(fill="x", side="bottom", pady=(8, 0))
        S = self._scan = {"win": win, "status": status, "labels": labels, "seen": set(), "last_sig": None, "pages": 0,
                          "scanned": 0, "viewed": 0, "added": 0, "unchanged": 0, "job": None, "busy": False}
        tk.Button(btns, text="Finish", command=self._scan_finish, bg=UI["accent"], fg="#FFFFFF", relief="flat", bd=0, padx=16, pady=6,
                  font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="right")
        tk.Button(btns, text="Read this page now", command=lambda: self._scan_capture(manual=True), bg="#EEF2FF", fg=UI["accent"], relief="flat", bd=0,
                  padx=12, pady=6, font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="right", padx=8)
        win.protocol("WM_DELETE_WINDOW", self._scan_finish)
        if opened:
            status.config(text="Opening your Submitted proposals page on Upwork... If Upwork asks you to log in, log in there. I'll start reading as soon as the page is in front.", fg=UI["muted"])
            S["job"] = self.root.after(6000, self._scan_capture)
        else:
            S["job"] = self.root.after(800, lambda: self._scan_capture(manual=True))

    def _scan_capture(self, manual=False):
        S = getattr(self, "_scan", None)
        if not S or not S["win"].winfo_exists() or S["busy"]: return
        S["busy"] = True
        try:
            hwnd = find_upwork_window()
            fallback = False
            if hwnd is None:
                # Tab titles may not say Upwork (e.g. "Proposals and offers"): use the browser window in front, checked below
                hwnd = find_job_browser_window(); fallback = True
            if hwnd is None:
                S["status"].config(text="Upwork window not found. Open the Submitted proposals page in your browser.", fg="#DC2626")
                return
            # In auto mode only read when Upwork is the window in front, so nothing jumps around while you work elsewhere
            if not manual and (_ct.windll.user32.GetForegroundWindow() != hwnd or (fallback and not _title_has(hwnd, "proposal"))):
                S["status"].config(text="Waiting. Bring the Upwork page to the front, or click 'Read this page now'.", fg=UI["muted"])
                return
            clear_clipboard()
            copy_window_text(hwnd)
            text = read_clipboard_text() or ""
            if fallback and not upwork_page_ok(text, "proposals"):
                S["status"].config(text="Upwork window not found. Open the Submitted proposals page in your browser.", fg="#DC2626")
                return
            jobs = parse_upwork_proposals(text)
            if not jobs:
                low = text.lower()
                if ("log in" in low or "sign up" in low) and "proposal" not in low:
                    S["status"].config(text="Upwork looks logged out. Log in on Upwork, open Submitted proposals, then click 'Read this page now'.", fg="#DC2626")
                elif not text.strip():
                    S["status"].config(text="Nothing was copied. Click on the Upwork page once, then click 'Read this page now'.", fg="#B45309")
                else:
                    S["status"].config(text="This doesn't look like the Submitted proposals list. Open that page on Upwork.", fg="#B45309")
                return
            sig = tuple(j["job"] for j in jobs)
            if sig == S["last_sig"]:
                S["status"].config(text=f"Page {S['pages']} done. Click Next on Upwork for the next page.", fg=UI["muted"]); return
            S["last_sig"] = sig
            fresh = [j for j in jobs if _norm_title(j["job"]) not in S["seen"]]
            for j in fresh: S["seen"].add(_norm_title(j["job"]))
            added, viewed, other = self._scan_apply(fresh)
            S["pages"] += 1; S["scanned"] += len(fresh); S["added"] += added; S["viewed"] += viewed
            S["other"] = S.get("other", 0) + other; S["unchanged"] += len(fresh) - added - viewed - other
            for k in ("pages", "scanned", "viewed", "added"): S["labels"][k].config(text=str(S[k]))
            S["status"].config(text=f"Page {S['pages']} read: {len(fresh)} proposals, {viewed} newly Viewed, {added} added. Click Next on Upwork.", fg="#047857")
        finally:
            S["busy"] = False
            if S["win"].winfo_exists():
                S["job"] = self.root.after(4000, self._scan_capture)

    def _scan_apply(self, jobs):
        """Same rules as Import from clipboard (shared _plan_import): no duplicates, upgrades only."""
        added, viewed, other = self._commit_import(self._plan_import(jobs), "Imported from Upwork (Fresh Audit)")
        if added or viewed or other:
            self.refresh_all(); self.upwork_refresh_jobs()
        return added, viewed, other

    def _scan_finish(self):
        S = getattr(self, "_scan", None)
        if not S: return
        if S["job"]:
            try: self.root.after_cancel(S["job"])
            except Exception: pass
        if S["win"].winfo_exists(): S["win"].destroy()
        self._scan = None
        self.refresh_all(); self.upwork_refresh_jobs()
        messagebox.showinfo("Fresh Audit finished",
            f"Pages read: {S['pages']}\nTotal proposals scanned: {S['scanned']}\nNewly marked Viewed: {S['viewed']}\n"
            f"Other status updates: {S.get('other', 0)}\nNew jobs added: {S['added']}\nUnchanged: {S['unchanged']}\n\nNo duplicate jobs were created.")

    def upwork_import_proposal_page(self):
        import re
        try: text = self.root.clipboard_get()
        except tk.TclError: text = ""
        data = parse_proposal_page(text) if text else {}
        if not data.get("cover_letter"):
            messagebox.showwarning("No proposal found", "Open the proposal on Upwork, press Ctrl+A then Ctrl+C, and try again.\nI couldn't find a Cover letter section in what you copied."); return
        url = (simpledialog.askstring("Proposal link", "Paste the proposal link from your browser (optional):", parent=self.root) or "").strip()
        m = re.search(r"/proposals/(\d+)", url); pid_key = m.group(1) if m else None
        row = None
        if pid_key: row = self.db.execute("SELECT * FROM proposals WHERE url LIKE ?", (f"%/proposals/{pid_key}%",)).fetchone()
        if not row and data.get("job"): row = self.db.execute("SELECT * FROM proposals WHERE job=?", (data["job"],)).fetchone()
        where = f"update job #{row['id']}" if row else "add it as a new job"
        if not messagebox.askyesno("Save proposal?", f"Job: {data.get('job', '(title not found)')}\nBid: {data.get('budget_text', '-')}\nCover letter: {len(data['cover_letter'])} characters\n\nI'll {where}. Save?"):
            return
        if row:
            sets = {k: v for k, v in data.items() if v}
            if pid_key and not row["url"]: sets["url"] = url
            self.db.execute("UPDATE proposals SET " + ",".join(f"{k}=?" for k in sets) + " WHERE id=?", (*sets.values(), row["id"]))
        else:
            email = None
            if _keyring is not None: email, _ = get_upwork_login()
            base = {"account": "Upwork", "member": email or "Me", "job": data.get("job", "Upwork proposal"), "proposal_date": date.today().isoformat(),
                    "status": "Submitted", "notes": "Imported from Upwork proposal page", "url": url}
            base.update({k: v for k, v in data.items() if v})
            self.db.execute("INSERT INTO proposals(" + ",".join(base) + ") VALUES(" + ",".join("?" for _ in base) + ")", tuple(base.values()))
        self.db.commit(); self.refresh_all()
        if hasattr(self, "upwork_refresh_jobs"): self.upwork_refresh_jobs()
        messagebox.showinfo("Saved", "Proposal saved. Click the job on the Overview page to read the cover letter.")

    def upwork_disconnect(self):
        if _keyring is None: return
        if messagebox.askyesno("Disconnect", "Remove your saved Upwork login from this computer?"):
            clear_upwork_login()
            self.upwork_email.delete(0, tk.END); self.upwork_pass.delete(0, tk.END)
            self.upwork_refresh_status()

    def make_data(self):
        p = self.tabs["data"]
        self.section_title(p, "Import, Export & Backup", "Use CSV templates to bulk-load existing records. Back up your database regularly.")
        actions = [
            ("Download proposals CSV template",lambda:self.template_csv("proposals")),
            ("Import proposals CSV",lambda:self.import_csv("proposals")),
            ("Export proposals CSV",lambda:self.export_csv("proposals")),
            ("Download leads CSV template",lambda:self.template_csv("leads")),
            ("Import leads CSV",lambda:self.import_csv("leads")),
            ("Export leads CSV",lambda:self.export_csv("leads")),
            ("Create database backup",self.backup),
            ("Restore from backup",self.restore_backup)
        ]
        for label,cmd in actions: ttk.Button(p,text=label,command=cmd).pack(anchor="w",pady=5)
        ttk.Label(p,text=f"Database location: {DB_PATH}",wraplength=950).pack(anchor="w",pady=14)
        ttk.Label(p,text="Your data is stored only on this computer. It does not sync between team computers.",
                  style="Sub.TLabel",wraplength=950).pack(anchor="w")

    # ---------- Settings (AI settings and the OpenAI API key) ----------
    # Only the new AI feature settings live here for now. The older app values stay where they are (planned step P2).
    AI_FIELDS = [("openai_model", "OpenAI model", "text"), ("transcription_model", "Transcription model", "text"),
                 ("temperature", "Temperature (0 to 2)", "float"), ("max_tokens", "Max tokens (50 to 4000)", "int"),
                 ("request_timeout", "Request timeout (5 to 300 seconds)", "int")]
    AI_TEXTS = [("proposal_system_prompt", "Proposal system prompt")]   # the proposal template is edited in Proposal templates below
    KEYRING_MISSING = "Not available: run  python -m pip install keyring"

    def make_settings(self):
        p = self.tabs["settings"]
        # Two views share this tab: the API Key page (key only) and the Settings page (everything else)
        kv = ttk.Frame(p); av = ttk.Frame(p); self.set_views = {"key": kv, "ai": av}
        self.section_title(kv, "API Key", "Your OpenAI key for the AI proposal writer. It is kept in Windows' secure password vault, never in a file.")
        self.section_title(av, "Settings", "Settings for the AI proposal writer. Your OpenAI key is on the API Key page.")
        av.pack(fill="both", expand=True)
        self.set_key_entry = None; self.set_ai_vars = {}; self.set_ai_texts = {}
        if settings_store is None:
            for v in (kv, av):
                tk.Label(v, text="Settings are not available: the file settings_store.py is missing from the LeadPilot folder.",
                         bg=UI["bg"], fg="#DC2626", font=("Segoe UI", 10, "bold"), wraplength=900, justify="left").pack(anchor="w", pady=10)
            return
        # scrollable page body (the page title stays fixed above it, like the other pages)
        body = tk.Frame(av, bg=UI["bg"]); body.pack(fill="both", expand=True)
        cv = tk.Canvas(body, bg=UI["bg"], highlightthickness=0); sb = ttk.Scrollbar(body, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y"); cv.pack(side="left", fill="both", expand=True)
        page = tk.Frame(cv, bg=UI["bg"]); win = cv.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        set_idx = self.nb.index(p)
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units") if self.nb.index("current") == set_idx and cv.winfo_ismapped() else None, add="+")
        self.set_canvas = cv

        # OpenAI API key
        kc = self.card(kv, fill="x", pady=(0, 12)); self.set_key_card = kc
        tk.Frame(kc, bg="#4338CA", height=4).pack(fill="x")
        tk.Label(kc, text="OpenAI API key", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(kc, text="Paste your own key from your OpenAI account. It is saved only in Windows' secure password vault, "
                          "never in a file, the database, a backup or a log. Only the start and end of the key are ever shown.",
                 bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9), wraplength=820, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        row = tk.Frame(kc, bg=UI["card"]); row.pack(fill="x", padx=16)
        tk.Label(row, text="API key", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 10)).pack(side="left", padx=(0, 10))
        self.set_key_entry = ttk.Entry(row, width=52, show="*"); self.set_key_entry.pack(side="left")
        self.set_key_entry.bind("<Return>", lambda e: self.settings_save_key())
        kb = tk.Frame(kc, bg=UI["card"]); kb.pack(anchor="w", padx=16, pady=(10, 4))
        self.set_key_btns = [ttk.Button(kb, text="Save key", style="Accent.TButton", command=self.settings_save_key),
                             ttk.Button(kb, text="Test key", command=self.settings_test_key),
                             ttk.Button(kb, text="Remove key", command=self.settings_remove_key)]
        for i, b in enumerate(self.set_key_btns): b.pack(side="left", padx=(0 if i == 0 else 8, 0))
        self.set_key_status = tk.Label(kc, text="", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9, "bold"), wraplength=820, justify="left")
        self.set_key_status.pack(anchor="w", padx=16, pady=(2, 14))

        # AI settings (non-secret, saved in the settings file)
        ac = self.card(page, fill="x", pady=(0, 12))
        tk.Frame(ac, bg="#047857", height=4).pack(fill="x")
        tk.Label(ac, text="AI settings", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(ac, text="These settings control how proposal drafts are written. They are saved in the settings file below, never with your key.",
                 bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9), wraplength=820, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        grid = tk.Frame(ac, bg=UI["card"]); grid.pack(fill="x", padx=16)
        for i, (k, label, _t) in enumerate(self.AI_FIELDS):
            tk.Label(grid, text=label, bg=UI["card"], fg=UI["text"], font=("Segoe UI", 10)).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 12))
            v = tk.StringVar(); self.set_ai_vars[k] = v
            ttk.Entry(grid, textvariable=v, width=40).grid(row=i, column=1, sticky="w", pady=4)
        for k, label in self.AI_TEXTS:
            tk.Label(ac, text=label, bg=UI["card"], fg=UI["text"], font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(10, 2))
            t = tk.Text(ac, height=6, wrap="word", font=("Segoe UI", 10), bg="#F8FAFC", fg=UI["text"], relief="flat",
                        highlightthickness=1, highlightbackground=UI["line"], padx=10, pady=6)
            t.pack(fill="x", padx=16); self.set_ai_texts[k] = t
        ab = tk.Frame(ac, bg=UI["card"]); ab.pack(anchor="w", padx=16, pady=(10, 4))
        ttk.Button(ab, text="Save settings", style="Accent.TButton", command=self.settings_save_ai).pack(side="left")
        ttk.Button(ab, text="Reset to default", command=self.settings_reset_ai).pack(side="left", padx=8)
        self.set_ai_msg = tk.Label(ac, text="", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9, "bold"), wraplength=820, justify="left")
        self.set_ai_msg.pack(anchor="w", padx=16, pady=(2, 4))
        tk.Label(ac, text=f"Settings file: {settings_store.CONFIG_PATH}", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9),
                 wraplength=820, justify="left").pack(anchor="w", padx=16, pady=(0, 2))
        tk.Label(ac, text="Other LeadPilot settings will move to this page in a later update.", bg=UI["card"], fg=UI["muted"],
                 font=("Segoe UI", 9), wraplength=820, justify="left").pack(anchor="w", padx=16, pady=(0, 14))

        # Proposal templates (up to 5 slots; empty slots are not saved)
        tc = self.card(page, fill="x", pady=(0, 12))
        tk.Frame(tc, bg="#0369A1", height=4).pack(fill="x")
        tk.Label(tc, text="Proposal templates", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(tc, text="Each template needs a name and its text. Empty slots are not saved. "
                          "Keep the words in curly brackets, such as {job_post} and {instructions}. LeadPilot fills them in.",
                 bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9), wraplength=820, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        sr = tk.Frame(tc, bg=UI["card"]); sr.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(sr, text="Number of templates (1 to 10)", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 10)).pack(side="left", padx=(0, 10))
        self.set_tpl_slots_var = tk.StringVar(value=str(self.settings_slot_count()))
        ttk.Spinbox(sr, from_=1, to=10, increment=1, width=5, textvariable=self.set_tpl_slots_var).pack(side="left")
        ttk.Button(sr, text="Set number of templates", command=self.settings_save_slots).pack(side="left", padx=8)
        self.set_tpl_box = tk.Frame(tc, bg=UI["card"]); self.set_tpl_box.pack(fill="x")
        self.set_tpl_names = []; self.set_tpl_texts = []
        self.settings_build_slots(self.settings_slot_count())
        tb = tk.Frame(tc, bg=UI["card"]); tb.pack(anchor="w", padx=16, pady=(10, 4))
        ttk.Button(tb, text="Save templates", style="Accent.TButton", command=self.settings_save_templates).pack(side="left")
        self.set_tpl_msg = tk.Label(tc, text="", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9, "bold"), wraplength=820, justify="left")
        self.set_tpl_msg.pack(anchor="w", padx=16, pady=(2, 14))
        self.settings_load_ai()
        self.settings_load_templates()
        self.settings_refresh_key_status()

    def _set_key_ok(self):
        try: return bool(settings_store.keyring_available())
        except Exception: return False

    def _set_status(self, label, text, color=None):
        label.config(text=text, fg=color or UI["muted"])

    def settings_refresh_key_status(self, msg=None, color=None):
        """Status line under the key box. Shows only the masked hint, never the key."""
        if settings_store is None or not getattr(self, "set_key_entry", None): return
        if not self._set_key_ok():
            for b in self.set_key_btns: b.state(["disabled"])
            self._set_status(self.set_key_status, self.KEYRING_MISSING, "#DC2626"); return
        for b in self.set_key_btns: b.state(["!disabled"])
        try: hint = settings_store.masked_hint()
        except Exception: hint = "No key saved"
        text = hint if hint in ("No key saved", "Secure storage not available") else f"Key saved: {hint}"
        if msg: text = f"{text}. {msg}"
        self._set_status(self.set_key_status, text, color or ("#047857" if text.startswith("Key saved") else UI["muted"]))

    def settings_save_key(self):
        if settings_store is None or not self.set_key_entry: return
        if not self._set_key_ok():
            return messagebox.showwarning("OpenAI API key", self.KEYRING_MISSING)
        key = self.set_key_entry.get().strip()
        if not key:
            return messagebox.showwarning("OpenAI API key", "Paste your OpenAI API key in the box first.")
        try:
            settings_store.set_api_key(key)
        except Exception as ex:
            text = settings_store.redact(getattr(ex, "message", None) or "Could not save the API key in secure storage.", key)
            key = None
            return messagebox.showwarning("OpenAI API key", text)
        key = None
        self.set_key_entry.delete(0, tk.END)
        self.settings_refresh_key_status("Saved in the Windows password vault.", "#047857")

    def settings_test_key(self):
        """Tests the typed key, or the saved key when the box is empty. Runs in the background so the app never freezes."""
        if settings_store is None or not self.set_key_entry: return
        if getattr(self, "_set_testing", False): return
        typed = self.set_key_entry.get().strip() or None
        self._set_testing = True
        self._set_status(self.set_key_status, "Testing the key with OpenAI...", "#B45309")
        box = {}
        def work():
            try: box["res"] = settings_store.test_api_key(typed)
            except Exception: box["res"] = (False, "The key test did not finish. Please try again.")
        import threading
        threading.Thread(target=work, daemon=True).start()
        def check():
            if not box: self.root.after(300, check); return
            self._set_testing = False
            ok_, msg = box["res"]
            msg = settings_store.redact(str(msg or ""), typed)
            self.settings_refresh_key_status(msg, "#047857" if ok_ else "#DC2626")
        self.root.after(300, check)

    def settings_remove_key(self):
        if settings_store is None or not self.set_key_entry: return
        if not self._set_key_ok():
            return messagebox.showwarning("OpenAI API key", self.KEYRING_MISSING)
        if not messagebox.askyesno("Remove API key", "Remove your OpenAI API key from this computer? AI proposal writing stops until you add a key again."): return
        try:
            removed = settings_store.remove_api_key()
        except Exception as ex:
            return messagebox.showwarning("OpenAI API key", getattr(ex, "message", None) or "Could not remove the API key from secure storage.")
        self.set_key_entry.delete(0, tk.END)
        self.settings_refresh_key_status("Key removed." if removed else "There was no key to remove.")

    def settings_show(self, view):
        """Show one view of the Settings tab: 'key' (API Key page) or 'ai' (Settings page)."""
        views = getattr(self, "set_views", None)
        if not views or views[view].winfo_ismapped(): return
        for name, frame in views.items():
            if name == view: frame.pack(fill="both", expand=True)
            else: frame.pack_forget()

    def open_api_key(self):
        """Left-menu 'API Key': opens the API Key page (key section only) and puts the cursor in the key box."""
        self.show_page("settings")
        self.settings_show("key")
        self.header_title.config(text="API Key")
        self._api_key_active = True
        self._active_nav = "api_key"
        self._style_nav_btn(self.nav_buttons["settings"], False)
        self.api_key_btn.configure(bg=OV["mint"], fg=OV["emerald_dark"], font=("Segoe UI", 10, "bold"),
                                   activebackground=OV["mint"], activeforeground=OV["emerald_dark"])
        if getattr(self, "set_key_entry", None) is not None: self.root.after(50, self.set_key_entry.focus_set)

    def settings_load_ai(self, cfg=None):
        if settings_store is None or not self.set_ai_vars: return
        try: cfg = cfg if cfg is not None else settings_store.load_config()
        except Exception: cfg = dict(settings_store.DEFAULTS)
        for k, v in self.set_ai_vars.items(): v.set(str(cfg.get(k, settings_store.DEFAULTS.get(k, ""))))
        for k, t in self.set_ai_texts.items():
            t.delete("1.0", "end"); t.insert("1.0", str(cfg.get(k, settings_store.DEFAULTS.get(k, ""))))

    def settings_ai_values(self):
        """Read and check the AI settings boxes. Returns (values, problems)."""
        vals, bad = {}, []
        limits = {"temperature": (0, 2), "max_tokens": (50, 4000), "request_timeout": (5, 300)}
        for k, label, typ in self.AI_FIELDS:
            raw = self.set_ai_vars[k].get().strip()
            if typ == "text":
                if not raw: bad.append(f"{label} cannot be empty."); continue
                vals[k] = raw; continue
            try:
                n = float(raw) if typ == "float" else int(raw)
                lo, hi = limits[k]
                if not (lo <= n <= hi): raise ValueError
                vals[k] = n
            except ValueError:
                bad.append(f"{label.split(' (')[0]} must be a {'number' if typ == 'float' else 'whole number'} from {limits[k][0]} to {limits[k][1]}.")
        for k, label in self.AI_TEXTS:
            txt = self.set_ai_texts[k].get("1.0", "end").strip()
            if not txt: bad.append(f"{label} cannot be empty."); continue
            vals[k] = txt
        return vals, bad

    def settings_save_ai(self):
        if settings_store is None or not self.set_ai_vars: return
        vals, bad = self.settings_ai_values()
        if bad:
            self._set_status(self.set_ai_msg, " ".join(bad), "#DC2626"); return
        try:
            cfg = dict(settings_store.load_config()); cfg.update(vals); settings_store.save_config(cfg)
        except Exception as ex:
            self._set_status(self.set_ai_msg, getattr(ex, "message", None) or "Could not save the settings file.", "#DC2626"); return
        self.settings_load_ai()
        self._set_status(self.set_ai_msg, "AI settings saved.", "#047857")

    def settings_reset_ai(self):
        if settings_store is None or not self.set_ai_vars: return
        if not messagebox.askyesno("Reset AI settings", "Put all AI settings on this page back to their default values?"): return
        d = settings_store.DEFAULTS
        for k, v in self.set_ai_vars.items(): v.set(str(d.get(k, "")))
        for k, t in self.set_ai_texts.items(): t.delete("1.0", "end"); t.insert("1.0", str(d.get(k, "")))
        self.settings_save_ai()
        if self.set_ai_msg.cget("text") != "AI settings saved.": return
        # The default template goes back into slot 1 only; templates 2 to 5 are kept
        try:
            tpls = settings_store.get_templates()
            tpls[0]["text"] = d.get("proposal_user_template", tpls[0]["text"]); settings_store.save_templates(tpls)
            if getattr(self, "set_tpl_texts", None):
                self.set_tpl_texts[0].delete("1.0", "end"); self.set_tpl_texts[0].insert("1.0", tpls[0]["text"])
                if not self.set_tpl_names[0].get().strip(): self.set_tpl_names[0].set(tpls[0]["name"])
        except Exception as ex:
            return self._set_status(self.set_ai_msg, getattr(ex, "message", None) or "Could not reset Template 1.", "#DC2626")
        self._set_status(self.set_ai_msg, "AI settings reset to default and saved.", "#047857")

    def settings_slot_count(self):
        try: return int(settings_store.get_max_templates())
        except Exception: return 3

    def settings_build_slots(self, n):
        """(Re)build the template slots. Text typed in slots that stay is kept on screen."""
        keep = [(v.get(), t.get("1.0", "end-1c")) for v, t in zip(self.set_tpl_names, self.set_tpl_texts)]
        for w in self.set_tpl_box.winfo_children(): w.destroy()
        self.set_tpl_names = []; self.set_tpl_texts = []
        for i in range(n):
            nr = tk.Frame(self.set_tpl_box, bg=UI["card"]); nr.pack(fill="x", padx=16, pady=(8, 2))
            tk.Label(nr, text=f"Template {i + 1}", bg=UI["card"], fg=UI["text"], font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 12))
            tk.Label(nr, text="Name", bg=UI["card"], fg=UI["muted"], font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
            nv = tk.StringVar(); ttk.Entry(nr, textvariable=nv, width=40).pack(side="left")
            t = tk.Text(self.set_tpl_box, height=5, wrap="word", font=("Segoe UI", 10), bg="#F8FAFC", fg=UI["text"], relief="flat",
                        highlightthickness=1, highlightbackground=UI["line"], padx=10, pady=6)
            t.pack(fill="x", padx=16)
            if i < len(keep): nv.set(keep[i][0]); t.insert("1.0", keep[i][1])
            self.set_tpl_names.append(nv); self.set_tpl_texts.append(t)

    def settings_save_slots(self):
        """Save the number of template slots. Asks first if lowering it would delete templates."""
        if settings_store is None or not hasattr(self, "set_tpl_box"): return
        old = len(self.set_tpl_texts)
        try: n = settings_store.parse_template_slots(self.set_tpl_slots_var.get())
        except Exception as ex:
            self.set_tpl_slots_var.set(str(old))
            return self._set_status(self.set_tpl_msg, getattr(ex, "message", None) or "Number of templates must be a whole number from 1 to 10.", "#DC2626")
        try: stored = settings_store.load_config().get("proposal_templates") or []
        except Exception: stored = []
        lost = sorted({i + 1 for i in range(n, len(stored))} |
                      {i + 1 for i in range(n, old) if self.set_tpl_names[i].get().strip() or self.set_tpl_texts[i].get("1.0", "end").strip()})
        if lost:
            if len(lost) == 1: what = f"Template {lost[0]} contains"
            elif lost == list(range(lost[0], lost[-1] + 1)): what = f"Templates {lost[0]}-{lost[-1]} contain"
            else: what = "Templates " + ", ".join(str(x) for x in lost) + " contain"
            if not messagebox.askyesno("Number of templates", f"{what} text and will be permanently deleted. Continue?"):
                self.set_tpl_slots_var.set(str(old)); return
        try: settings_store.set_template_slots(n)
        except Exception as ex:
            self.set_tpl_slots_var.set(str(old))
            return self._set_status(self.set_tpl_msg, getattr(ex, "message", None) or "Could not save the number of templates.", "#DC2626")
        self.set_tpl_slots_var.set(str(n))
        self.settings_build_slots(n)
        self._set_status(self.set_tpl_msg, f"Number of templates saved: {n}.", "#047857")

    def settings_load_templates(self):
        """Fill the 5 template slots from the settings file. Slots without a saved template stay empty."""
        if settings_store is None or not getattr(self, "set_tpl_texts", None): return
        try: tpls = settings_store.get_templates()
        except Exception: tpls = []
        for i, (nv, t) in enumerate(zip(self.set_tpl_names, self.set_tpl_texts)):
            tp = tpls[i] if i < len(tpls) else {}
            nv.set(str(tp.get("name", ""))); t.delete("1.0", "end"); t.insert("1.0", str(tp.get("text", "")))

    def settings_save_templates(self):
        if settings_store is None or not getattr(self, "set_tpl_texts", None): return
        tpls, half = [], []
        for i, (nv, t) in enumerate(zip(self.set_tpl_names, self.set_tpl_texts), 1):
            name, text = nv.get().strip(), t.get("1.0", "end").strip()
            if name and text: tpls.append({"name": name, "text": text})
            elif name or text: half.append(f"Template {i}")
        if half:
            return messagebox.showwarning("Proposal templates", f"{', '.join(half)}: add both a name and the text, or clear both. Nothing was saved.")
        try:
            settings_store.save_templates(tpls)
        except Exception as ex:
            return messagebox.showwarning("Proposal templates", getattr(ex, "message", None) or "Could not save the templates.")
        self.settings_load_templates()
        self._set_status(self.set_tpl_msg, "Templates saved.", "#047857")
        messagebox.showinfo("Proposal templates", "Templates saved.")

    def dialog(self, title, fields, values=None, choices=None):
        values = values or {}; choices = choices or {}
        win = tk.Toplevel(self.root); win.title(title); win.transient(self.root); win.grab_set()
        win.geometry("650x600"); win.minsize(560,480)
        outer = ttk.Frame(win,padding=16); outer.pack(fill="both",expand=True)
        canvas = tk.Canvas(outer,highlightthickness=0); sb=ttk.Scrollbar(outer,orient="vertical",command=canvas.yview)
        inner=ttk.Frame(canvas); inner.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=inner,anchor="nw"); canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        vars={}
        for i,(key,label) in enumerate(fields):
            ttk.Label(inner,text=label).grid(row=i,column=0,sticky="w",pady=5,padx=(0,12))
            var=tk.StringVar(value=str(values.get(key,"") if values.get(key) is not None else "")); vars[key]=var
            if key in choices:
                widget=ttk.Combobox(inner,textvariable=var,values=choices[key],state="readonly",width=48)
            else:
                widget=ttk.Entry(inner,textvariable=var,width=52)
            widget.grid(row=i,column=1,sticky="ew",pady=5)
        inner.columnconfigure(1,weight=1)
        result={"saved":False}
        btns=ttk.Frame(outer); btns.pack(fill="x",pady=(12,0))
        def save():
            result["data"]={k:v.get().strip() for k,v in vars.items()}
            result["saved"]=True; win.destroy()
        ttk.Button(btns,text="Cancel",command=win.destroy).pack(side="right",padx=5)
        ttk.Button(btns,text="Save record",style="Accent.TButton",command=save).pack(side="right")
        win.wait_window()
        return result["data"] if result["saved"] else None

    def proposal_form(self, row=None):
        fields=[("account","Upwork account *"),("member","BD member *"),("job","Job title *"),
                ("client","Client name"),("url","Job URL"),("proposal_date","Proposal date (YYYY-MM-DD)"),
                ("bid","Bid amount (USD)"),("connects","Connects used"),("status","Proposal status"),
                ("views","Proposal views (0/1)"),("notes","Notes")]
        defaults={"proposal_date":date.today().isoformat(),"status":"Submitted","views":"0"}
        if row: defaults.update(dict(row))
        return self.dialog("Proposal record",fields,defaults,{"status":PROPOSAL_STATUSES})

    def lead_form(self,row=None):
        fields=[("account","Upwork account *"),("member","BD member *"),("name","Lead name *"),
                ("company","Company"),("source","Source"),("proposal_id","Related proposal ID"),
                ("lead_date","Lead date (YYYY-MM-DD)"),("status","Pipeline stage"),
                ("budget","Potential budget (USD)"),("next_followup","Next follow-up (YYYY-MM-DD)"),
                ("last_contact","Last contact (YYYY-MM-DD)"),("notes","Notes")]
        defaults={"source":"Upwork","lead_date":date.today().isoformat(),"status":"Qualified"}
        if row: defaults.update(dict(row))
        return self.dialog("Lead record",fields,defaults,{"status":LEAD_STATUSES})

    def add_proposal(self):
        data=self.proposal_form()
        if not data:return
        self.save_proposal(data)

    def edit_proposal(self):
        row=self.selected_row(self.ptree,"proposals")
        if not row:return
        data=self.proposal_form(row)
        if data:self.save_proposal(data,row["id"])

    def write_proposal_selected(self):
        """Proposals page: open Write a proposal for the selected row."""
        sel = self.ptree.selection()
        if not sel: return messagebox.showinfo("Write a proposal", "Click a proposal in the list first.")
        self.write_proposal_for(int(self.ptree.item(sel[0], "values")[0]))

    def write_proposal_for(self, pid):
        """Open the Write a proposal window for one job. Draft only: nothing is sent to Upwork."""
        if proposal_ui is None:
            return messagebox.showerror("Write a proposal", "The Write a proposal window (proposal_ui.py) is missing or could not load.")
        r = self.db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        if not r: return messagebox.showinfo("Write a proposal", "This job was not found. It may have been deleted.")
        g = lambda k: (str(r[k]).strip() if k in r.keys() and r[k] not in (None, "") else "")
        parts = [f"{lab}: {g(k)}" for k, lab in (("job", "Job title"), ("client", "Client"), ("budget_text", "Budget"),
                                                  ("skills", "Skills"), ("location", "Client location"), ("url", "Job link")) if g(k)]
        if g("summary"): parts.append("Description:\n" + g("summary"))
        def save_letter(text, pid=pid):
            old = self.db.execute("SELECT cover_letter FROM proposals WHERE id=?", (pid,)).fetchone()
            if old and (old["cover_letter"] or "").strip() and not messagebox.askyesno("Replace cover letter?", "Replace the saved cover letter?"):
                return False
            self.db.execute("UPDATE proposals SET cover_letter=? WHERE id=?", (text, pid)); self.db.commit()
            if getattr(self, "jtree", None) is not None and self.jtree.selection() == (str(pid),): self.show_job_detail()
        return proposal_ui.open_write_proposal(self.root, "\n".join(parts), title=g("job"), on_save_cover_letter=save_letter,
                                               on_open_settings=self.open_api_key, ui=UI)

    @staticmethod
    def _bad_date(v, allow_time=False):
        """True if v is filled in but is not a real date (YYYY-MM-DD, or YYYY-MM-DD HH:MM when allow_time)."""
        v = (v or "").strip()
        if not v: return False
        for fmt in (("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S") if allow_time else ("%Y-%m-%d",)):
            try: datetime.strptime(v, fmt); return False
            except ValueError: pass
        return True

    @staticmethod
    def _norm_date(v, allow_time=False):
        """Returns the date in the standard form (2026-1-5 becomes 2026-01-05, with HH:MM when a time is given),
        '' for an empty box, or None when it is not a real date."""
        v = (v or "").strip()
        if not v: return ""
        for fmt in (("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S") if allow_time else ("%Y-%m-%d",)):
            try: dt = datetime.strptime(v, fmt)
            except ValueError: continue
            return dt.strftime("%Y-%m-%d") if fmt == "%Y-%m-%d" else dt.strftime("%Y-%m-%d %H:%M")
        return None

    def save_proposal(self,d,record_id=None):
        if not d["account"] or not d["member"] or not d["job"]:
            return messagebox.showwarning("Required fields","Upwork account, BD member and job title are required.")
        nd = self._norm_date(d.get("proposal_date"))
        if nd is None:
            return messagebox.showwarning("Check the date", f"Proposal date '{d['proposal_date']}' is not a real date. Use year-month-day, for example 2026-11-14.")
        d = dict(d); d["proposal_date"] = nd
        try:
            bid=float(d["bid"] or 0); connects=int(d["connects"] or 0); views=int(d["views"] or 0)
            if bid<0 or connects<0 or views<0: raise ValueError()
            values=[d[k] for k in PROPOSAL_FIELDS]
            values[6]=bid; values[7]=connects; values[9]=views
            if record_id:
                self.db.execute("UPDATE proposals SET account=?,member=?,job=?,client=?,url=?,proposal_date=?,bid=?,connects=?,status=?,views=?,notes=? WHERE id=?",
                    (*values,record_id))
            else:
                self.db.execute("INSERT INTO proposals("+",".join(PROPOSAL_FIELDS)+") VALUES("+",".join("?" for _ in PROPOSAL_FIELDS)+")",values)
            self.db.commit();self.refresh_all()
        except ValueError:
            messagebox.showerror("Invalid values","Bid, Connects and Views must be valid non-negative numbers.")

    def add_lead(self):
        data=self.lead_form()
        if data:self.save_lead(data)

    def edit_lead(self):
        row=self.selected_row(self.ltree,"leads")
        if not row:return
        data=self.lead_form(row)
        if data:self.save_lead(data,row["id"])

    def edit_followup_lead(self):
        row=self.selected_row(self.ftree,"leads")
        if not row:return
        data=self.lead_form(row)
        if data:self.save_lead(data,row["id"])

    def save_lead(self,d,record_id=None):
        if not d["account"] or not d["member"] or not d["name"]:
            return messagebox.showwarning("Required fields","Upwork account, BD member and lead name are required.")
        d = dict(d)
        for k, lab, t in (("lead_date", "Lead date", False), ("next_followup", "Next follow-up", True), ("last_contact", "Last contact", True)):
            nd = self._norm_date(d.get(k), t)
            if nd is None:
                return messagebox.showwarning("Check the date", f"{lab} '{d[k]}' is not a real date. Use year-month-day, for example 2026-11-14" + (" or 2026-11-14 15:30." if t else "."))
            d[k] = nd
        try:
            budget=float(d["budget"] or 0)
            proposal_id=int(d["proposal_id"]) if d["proposal_id"] else None
            if budget<0:raise ValueError()
            values=[d[k] for k in LEAD_FIELDS]
            values[5]=proposal_id;values[8]=budget
            if record_id:
                self.db.execute("UPDATE leads SET account=?,member=?,name=?,company=?,source=?,proposal_id=?,lead_date=?,status=?,budget=?,next_followup=?,last_contact=?,notes=? WHERE id=?",
                    (*values,record_id))
                if not values[9] and values[7] not in FU_CLOSED:
                    self._fu_save(record_id)   # box cleared: work the next follow-up out from the cycle again
            else:
                self.db.execute("INSERT INTO leads("+",".join(LEAD_FIELDS)+") VALUES("+",".join("?" for _ in LEAD_FIELDS)+")",values)
            self.db.commit();self.refresh_all()
        except (ValueError,sqlite3.IntegrityError):
            messagebox.showerror("Invalid values","Check the budget and related proposal ID. The proposal ID must exist.")

    # ---------- Follow-up cadence ----------
    @staticmethod
    def _fu_fmt(dt): return dt.strftime("%Y-%m-%d %H:%M") if dt else None
    @staticmethod
    def _fu_dt(s):
        if not s: return None
        for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try: return datetime.strptime(s[:19] if f.endswith("%S") else s[:16] if "%M" in f else s[:10], f)
            except ValueError: pass
        return None

    def _fu_next(self, anchor, count):
        from datetime import timedelta
        cad = self.fu_cadence()
        if anchor is None or count >= len(cad): return None
        return anchor + timedelta(hours=cad[count])

    def fu_cadence(self):
        """The user's follow-up cycle in hours (Settings key fu_cadence). Falls back to the default 24, 48, 48, 72, 72."""
        try:
            row = self.db.execute("SELECT v FROM settings WHERE k='fu_cadence'").fetchone()
            vals = [int(x) for x in (row[0] if row else "").replace(" ", "").split(",") if x]
            if vals and all(0 < v <= 720 for v in vals): return vals
        except Exception: pass
        return list(FU_CADENCE)

    def _fu_duration_text(self, total_hours):
        """Human label for total cycle length, e.g. '11 Days' or '3 days 6 hr'."""
        try:
            tot = int(total_hours or 0)
        except (TypeError, ValueError):
            tot = 0
        if tot <= 0:
            return "—"
        d, h = divmod(tot, 24)
        if d and not h:
            return f"{d} Day{'s' if d != 1 else ''}"
        if d and h:
            return f"{d} day{'s' if d != 1 else ''} {h} hr"
        return f"{h} hr"

    def _fu_draw_icon_badge(self, cnv, size, em, dark):
        cnv.delete("all")
        s = size - 1
        r = max(6, size // 5)
        self._fu_round_rect(cnv, 1, 1, s, s, r=r, fill=em, outline=dark, width=1)
        m = size / 44.0
        cnv.create_rectangle(12 * m, 14 * m, 32 * m, 33 * m, outline="#FFFFFF", width=2)
        cnv.create_line(12 * m, 20 * m, 32 * m, 20 * m, fill="#FFFFFF", width=2)
        cnv.create_line(17 * m, 11 * m, 17 * m, 17 * m, fill="#FFFFFF", width=2)
        cnv.create_line(27 * m, 11 * m, 27 * m, 17 * m, fill="#FFFFFF", width=2)
        cnv.create_oval(23 * m, 25 * m, 33 * m, 35 * m, outline="#FFFFFF", width=1.5)
        cnv.create_line(28 * m, 27 * m, 28 * m, 30 * m, fill="#FFFFFF", width=1.5)
        cnv.create_line(28 * m, 30 * m, 30 * m, 31 * m, fill="#FFFFFF", width=1.5)

    def _fu_draw_cal_ill(self, ill, w, h, em, dark, mint):
        ill.delete("all")
        sx, sy = w / 88.0, h / 58.0
        ill.create_rectangle(18 * sx, 10 * sy, 58 * sx, 48 * sy, fill="#FFFFFF", outline=em, width=2)
        ill.create_rectangle(18 * sx, 10 * sy, 58 * sx, 22 * sy, fill=em, outline=em)
        ill.create_line(26 * sx, 6 * sy, 26 * sx, 16 * sy, fill=dark, width=2)
        ill.create_line(50 * sx, 6 * sy, 50 * sx, 16 * sy, fill=dark, width=2)
        ill.create_oval(48 * sx, 26 * sy, 82 * sx, 56 * sy, fill=mint, outline="")
        ill.create_oval(52 * sx, 30 * sy, 78 * sx, 54 * sy, fill="#FFFFFF", outline=em, width=2)
        ill.create_oval(63 * sx, 40 * sy, 67 * sx, 44 * sy, fill=em, outline=em)
        ill.create_line(65 * sx, 42 * sy, 65 * sx, 34 * sy, fill=dark, width=2)
        ill.create_line(65 * sx, 42 * sy, 72 * sx, 45 * sy, fill=dark, width=2)

    def _fu_on_card_resize(self, event=None):
        self._fu_paint_card_bg()
        self._fu_paint_side_decor()
        self._fu_paint_strip()
        try:
            cnv = self.fu_card_bg
            w = max(int(cnv.winfo_width()), 400)
            h = max(int(cnv.winfo_height()), 180)
            pad_x, pad_y = 10, 8
            if getattr(self, "_fu_inner_win", None):
                cnv.coords(self._fu_inner_win, pad_x, pad_y)
                cnv.itemconfigure(self._fu_inner_win, width=max(100, w - 2 * pad_x), height=max(100, h - 2 * pad_y))
            self.fu_card_inner.update_idletasks()
            if hasattr(self, "fu_right_col") and hasattr(self, "fu_right_div"):
                rx = self.fu_right_col.winfo_x()
                self.fu_right_div.place_configure(x=max(40, rx - 6), rely=0.1, relheight=0.8)
        except Exception:
            pass

    def _fu_round_rect(self, cnv, x1, y1, x2, y2, r=10, **kw):
        """Rounded rectangle via smooth polygon (Tkinter has no native round-rect)."""
        r = max(2, min(r, int((x2 - x1) / 2), int((y2 - y1) / 2)))
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return cnv.create_polygon(pts, smooth=True, splinesteps=16, **kw)

    def _fu_paint_card_bg(self):
        """Rounded outer card + mint corner washes on the shell canvas."""
        cnv = getattr(self, "fu_card_bg", None)
        if cnv is None:
            return
        EM, MINT, CARD = OV["emerald"], OV["mint"], "#F3FBF7"
        LINE = "#B7DFCC"
        try:
            cnv.delete("bg")
            w = max(int(cnv.winfo_width()), 400)
            h = max(int(cnv.winfo_height()), 180)
            cnv.create_rectangle(0, 0, w, h, fill=UI["bg"], outline="", tags="bg")
            self._fu_round_rect(cnv, 1, 1, w - 2, h - 2, r=16, fill=CARD, outline=LINE, width=1, tags="bg")
            cnv.create_oval(-70, h - 90, 150, h + 80, fill=MINT, outline="", tags="bg")
            cnv.create_oval(w - 170, h - 80, w + 90, h + 100, fill="#E4F7EE", outline="", tags="bg")
            cnv.create_oval(w * 0.35, h - 40, w * 0.65, h + 70, fill="#EEF9F3", outline="", tags="bg")
            # soft emerald edge accent
            cnv.create_line(18, 3, w - 18, 3, fill=EM, width=1, tags="bg")
            cnv.tag_lower("bg")
        except Exception:
            pass

    def _fu_paint_side_decor(self):
        MINT = OV["mint"]
        for attr, ovals in (
            ("fu_left_deco", [(-36, -8, 130, 100, MINT), (-8, 14, 100, 110, "#E8F8F0")]),
            ("fu_right_deco", [(-20, -30, 160, 80, "#E4F7EE"), (40, -10, 200, 90, MINT)]),
        ):
            cnv = getattr(self, attr, None)
            if cnv is None:
                continue
            try:
                cnv.delete("all")
                for x1, y1, x2, y2, fill in ovals:
                    cnv.create_oval(x1, y1, x2, y2, fill=fill, outline="")
            except Exception:
                pass

    def _fu_paint_strip(self):
        cnv = getattr(self, "fu_strip_canvas", None)
        if cnv is None:
            return
        DARK, MINT = OV["emerald_dark"], OV["mint"]
        text = getattr(self, "_fu_strip_text", "") or ""
        try:
            cnv.delete("all")
            cnv.update_idletasks()
            w = max(int(cnv.winfo_width()), 160)
            h = max(int(cnv.winfo_height()), 40)
            pad = 10
            self._fu_round_rect(cnv, 1, 2, w - 2, h - 2, r=min(14, h // 2), fill=MINT, outline="#B7DFCC", width=1)
            # Two-line friendly layout so nothing clips
            sc = getattr(self, "_fu_ui_scale", 1.0)
            fnt = ("Segoe UI", max(8, int(8 * sc)), "bold")
            import tkinter.font as _tkf
            measure = _tkf.Font(family=fnt[0], size=fnt[1], weight="bold")
            max_tw = max(60, w - pad * 2)
            if "\u00b7" in text and measure.measure(text) > max_tw:
                left, right = [x.strip() for x in text.split("\u00b7", 1)]
                cnv.create_text(w // 2, h // 2 - 7, text=left, fill=DARK, font=fnt, width=max_tw, justify="center")
                cnv.create_text(w // 2, h // 2 + 8, text=right, fill=DARK, font=fnt, width=max_tw, justify="center")
            else:
                cnv.create_text(
                    w // 2, h // 2, text=text, fill=DARK, font=fnt,
                    width=max_tw, justify="center",
                )
        except Exception:
            pass

    def _fu_redraw_manager(self, event=None):
        cad = getattr(self, "_fu_cad_cache", None)
        if cad is None:
            try:
                cad = self.fu_cadence()
            except Exception:
                cad = list(FU_CADENCE)
        self._fu_draw_timeline(cad)

    def _fu_timeline_tip(self, text):
        tip = getattr(self, "_fu_tip", None)
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
            self._fu_tip = None
        if not text:
            return
        tip = tk.Toplevel(self.root)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        tk.Label(
            tip, text=text, bg=OV["emerald_dark"], fg="#FFFFFF",
            font=("Segoe UI", 8), padx=8, pady=4,
        ).pack()
        self._fu_tip = tip

    def _fu_timeline_hover(self, event):
        hits = getattr(self, "_fu_hit_zones", None) or []
        x, y = event.x, event.y
        msg = None
        for x1, y1, x2, y2, lab in hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                msg = lab
                break
        if msg:
            tip = getattr(self, "_fu_tip", None)
            if tip is None:
                self._fu_timeline_tip(msg)
            else:
                try:
                    for ch in tip.winfo_children():
                        ch.config(text=msg)
                except Exception:
                    pass
            try:
                self._fu_tip.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
            except Exception:
                pass
        else:
            self._fu_timeline_tip(None)

    def _fu_draw_timeline(self, cad):
        """Draw connected FU cards with connector line (reference timeline)."""
        cnv = getattr(self, "fu_timeline_canvas", None) or getattr(self, "fu_orbit_canvas", None)
        if cnv is None:
            return
        EM, DARK = OV["emerald"], OV["emerald_dark"]
        MINT, LINE, SHADOW = OV["mint"], "#A8D9C4", "#C5E8D6"
        sc = getattr(self, "_fu_ui_scale", 1.0)
        try:
            cnv.delete("all")
        except Exception:
            return
        try:
            w = max(int(cnv.winfo_width()), 280)
            h = max(int(cnv.winfo_height()), 120)
        except Exception:
            w, h = 560, 152
        cad = list(cad or [24])
        n = max(1, len(cad))
        # Decorative mint wash (visible — this IS the center surface)
        cnv.create_oval(-40, h - 55, 120, h + 70, fill=MINT, outline="")
        cnv.create_oval(w - 130, h - 50, w + 50, h + 80, fill="#E4F7EE", outline="")
        cnv.create_oval(w * 0.2, h - 40, w * 0.8, h + 60, fill="#EAF8F1", outline="")
        pad_x = 6
        compact = n > 6
        gap = 12 if compact else 18
        max_cw = 78 if compact else 96
        min_cw = 48 if compact else 64
        usable = max(120, w - pad_x * 2)
        card_w = max(min_cw, min(max_cw, (usable - gap * max(0, n - 1)) // n))
        # If still overflowing, enable scrollregion (horizontal pan via shift+wheel / drag not required — shrink gap)
        total = n * card_w + max(0, n - 1) * gap
        if total > usable and n > 1:
            gap = max(6, (usable - n * min_cw) // max(1, n - 1))
            card_w = max(min_cw, (usable - gap * (n - 1)) // n)
            total = n * card_w + (n - 1) * gap
        card_h = int((88 if compact else 104) * sc)
        pill_pt = 8 if compact else 9
        day_pt = 8 if compact else 9
        int_pt = 12 if compact else 15
        x0 = max(pad_x, (w - total) // 2)
        y0 = max(8, (h - card_h) // 2 - 2)
        cy = y0 + card_h // 2
        if n > 1:
            cnv.create_line(
                x0 + card_w // 2, cy, x0 + total - card_w // 2, cy,
                fill=EM, width=2,
            )
        hits = []
        cum = 0
        for i, hours in enumerate(cad):
            try:
                hours = int(hours)
            except (TypeError, ValueError):
                hours = 0
            cum += hours
            day_n = max(1, (cum + 23) // 24)
            x = x0 + i * (card_w + gap)
            self._fu_round_rect(
                cnv, x + 2, y0 + 4, x + card_w + 2, y0 + card_h + 4,
                r=12, fill=SHADOW, outline="",
            )
            fill = "#F1FAF5" if i < max(1, n - 2) else "#FFFFFF"
            self._fu_round_rect(
                cnv, x, y0, x + card_w, y0 + card_h,
                r=12, fill=fill, outline=LINE, width=1,
            )
            pw, ph = min(48, card_w - 10), 18
            px = x + (card_w - pw) // 2
            py = y0 + 8
            cnv.create_oval(px, py, px + ph, py + ph, fill=EM, outline=EM)
            cnv.create_oval(px + pw - ph, py, px + pw, py + ph, fill=EM, outline=EM)
            cnv.create_rectangle(px + ph // 2, py, px + pw - ph // 2, py + ph, fill=EM, outline=EM)
            cnv.create_text(
                x + card_w // 2, py + ph // 2, text=f"FU {i + 1}",
                fill="#FFFFFF", font=("Segoe UI", pill_pt, "bold"),
            )
            cnv.create_text(
                x + card_w // 2, y0 + int(card_h * 0.48), text=f"{hours}h",
                fill=DARK, font=("Segoe UI", int_pt, "bold"),
            )
            day_txt = f"Day {day_n}"
            group_w = 12 + 4 + max(28, len(day_txt) * 6)
            gx = x + (card_w - group_w) // 2
            gy = y0 + card_h - 20
            cnv.create_rectangle(gx, gy, gx + 10, gy + 10, outline=EM, width=1)
            cnv.create_line(gx, gy + 3, gx + 10, gy + 3, fill=EM)
            cnv.create_text(
                gx + 14, gy + 5, text=day_txt, anchor="w",
                fill=EM, font=("Segoe UI", day_pt),
            )
            hits.append((x, y0, x + card_w, y0 + card_h, f"FU {i + 1}: {hours}h · Day {day_n}"))
            if i < n - 1:
                dx = x + card_w + gap // 2
                cnv.create_oval(dx - 4, cy - 4, dx + 4, cy + 4, fill="#FFFFFF", outline=EM, width=2)
        self._fu_hit_zones = hits
        try:
            cnv.configure(scrollregion=(0, 0, max(w, total + pad_x * 2), h))
        except Exception:
            pass

    def _fu_update_sub(self):
        cad = self.fu_cadence()
        self._fu_cad_cache = list(cad)
        default = cad == list(FU_CADENCE)
        txt = ", then ".join(f"{h}h" for h in cad[:1]) + (
            "" if len(cad) == 1 else ", then " + ", ".join(f"{h}h" for h in cad[1:])
        )
        kind = "Default" if default else "Your custom"
        sentence = (
            f"{kind} cycle, {len(cad)} follow-ups: {txt}. A client reply restarts it."
        )
        if hasattr(self, "fu_sub"):
            try:
                self.fu_sub.config(text=sentence)
            except Exception:
                pass
        try:
            self.fu_cycle_kind.config(
                text=f"{kind} cycle  \u00b7  {len(cad)} follow-up{'s' if len(cad) != 1 else ''}"
            )
        except Exception:
            pass
        try:
            n = len(cad)
            self.fu_duration_lbl.config(
                text=f"{n} follow-up{'s' if n != 1 else ''}  \u00b7  Automatic reset on client reply"
            )
        except Exception:
            pass
        self._fu_paint_card_bg()
        self._fu_paint_side_decor()
        self._fu_paint_strip()
        self._fu_draw_timeline(cad)

    def fu_set_cycle(self):
        ORD = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth"]
        win = tk.Toplevel(self.root); win.title("Set follow-up cycle"); win.configure(bg="#FFFFFF"); win.transient(self.root); win.resizable(False, False); win.grab_set()
        body = tk.Frame(win, bg="#FFFFFF"); body.pack(padx=26, pady=20)
        tk.Label(body, text="Your follow-up cycle", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(body, text="Set how many hours to wait before each follow-up. Up to 10 follow-ups, each 1 to 720 hours.",
                 bg="#FFFFFF", fg=UI["muted"], font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(4, 12))
        grid = tk.Frame(body, bg="#FFFFFF"); grid.pack(anchor="w", fill="x")
        rows = []   # (frame, StringVar)
        prev = tk.Label(body, text="", bg="#FFFFFF", fg=UI["accent"], font=("Segoe UI", 9, "bold"), justify="left"); 
        ctl = tk.Frame(body, bg="#FFFFFF")
        def parse():
            out = []
            for _, v in rows:
                t = v.get().strip()
                if not t.isdigit() or not 0 < int(t) <= 720: return None
                out.append(int(t))
            return out if 0 < len(out) <= 10 else None
        def preview(*_):
            c = parse()
            if c:
                tot = sum(c); d, h = divmod(tot, 24)
                span = (f"{d} day{'s' if d != 1 else ''}" + (f" {h} hr" if h else "")) if d else f"{h} hr"
                prev.config(text=f"{len(c)} follow-up{'s' if len(c) != 1 else ''}, total cycle {tot} hr ({span})", fg=UI["accent"])
            else:
                prev.config(text="Fill every box with whole hours from 1 to 720", fg="#B91C1C")
            add_btn.config(state="normal" if len(rows) < 10 else "disabled")
            rem_btn.config(state="normal" if len(rows) > 1 else "disabled")
        def add_row(val=""):
            if len(rows) >= 10: return
            i = len(rows); fr = tk.Frame(grid, bg="#FFFFFF"); fr.pack(anchor="w", pady=3)
            tk.Label(fr, text=f"{ORD[i]} follow-up", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 10), width=16, anchor="w").pack(side="left")
            v = tk.StringVar(value=str(val))
            e = tk.Entry(fr, textvariable=v, width=7, font=("Segoe UI", 11), relief="solid", bd=1, justify="center"); e.pack(side="left", ipady=3)
            tk.Label(fr, text="hr", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 10, "bold")).pack(side="left", padx=(6, 10))
            tk.Label(fr, text="after the chat starts" if i == 0 else "after the previous follow-up", bg="#FFFFFF", fg=UI["muted"], font=("Segoe UI", 9)).pack(side="left")
            v.trace_add("write", preview); rows.append((fr, v)); return e
        def remove_row():
            if len(rows) > 1: fr, _ = rows.pop(); fr.destroy(); preview()
        def set_values(vals):
            while rows: rows.pop()[0].destroy()
            for h in vals[:10]: add_row(h)
            preview()
        add_btn = tk.Button(ctl, text="+  Add follow-up", command=lambda: (add_row(), preview()), bg=OV["mint"], fg=OV["emerald_dark"], relief="flat", bd=0,
                            padx=10, pady=4, font=("Segoe UI", 9, "bold"), cursor="hand2", activebackground="#C8EDE0")
        rem_btn = tk.Button(ctl, text="Remove last", command=remove_row, bg="#F3F7F5", fg=OV["text"], relief="flat", bd=0,
                            padx=10, pady=4, font=("Segoe UI", 9), cursor="hand2")
        add_btn.pack(side="left"); rem_btn.pack(side="left", padx=8)
        ctl.pack(anchor="w", pady=(8, 0)); prev.pack(anchor="w", pady=(10, 0))
        def apply(cad):
            self.db.execute("INSERT OR REPLACE INTO settings(k,v) VALUES('fu_cadence',?)", (",".join(str(h) for h in cad),))
            for r in self.db.execute("SELECT id, fu_count FROM leads").fetchall():
                self._fu_save(r["id"], fu_count=min(r["fu_count"] or 0, len(cad)))
            self.db.commit(); self._fu_update_sub(); self.fu_refresh()
        def save(event=None):
            c = parse()
            if not c: messagebox.showwarning("Check the cycle", "Fill every follow-up box with whole hours from 1 to 720.", parent=win); return
            apply(c); win.destroy()
        def reset():
            apply(list(FU_CADENCE)); win.destroy()
        btns = tk.Frame(body, bg="#FFFFFF"); btns.pack(fill="x", pady=(16, 0))
        tk.Button(btns, text="Save cycle", command=save, bg=OV["emerald"], fg="#FFFFFF", relief="flat", bd=0, padx=18, pady=8, font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground=OV["emerald_dark"]).pack(side="right")
        tk.Button(btns, text="Cancel", command=win.destroy, bg="#F3F7F5", fg=OV["text"], relief="flat", bd=0, padx=14, pady=8, font=("Segoe UI", 10), cursor="hand2").pack(side="right", padx=8)
        tk.Button(btns, text="Reset to default (24, 48, 48, 72, 72)", command=reset, bg="#FFFFFF", fg=OV["muted"], relief="flat", bd=0, font=("Segoe UI", 9, "underline"), cursor="hand2").pack(side="left")
        set_values(self.fu_cadence())
        if rows: win.after(50, lambda: rows[0][0].winfo_children()[1].focus_set())
        win.bind("<Return>", save); win.bind("<Escape>", lambda e: win.destroy())
        class _Fields:   # lets tests fill the boxes: .set("12, 36") or .set([12, 36]); .get() returns "12, 36"
            def set(_, v): set_values([x.strip() for x in v.split(",")] if isinstance(v, str) else list(v))
            def get(_): return ", ".join(v.get() for _f, v in rows)
        self._cycle_win = (win, _Fields(), save, reset); self._cycle_rows = rows; self._cycle_add = add_row

    def _fu_save(self, lid, **kv):
        r = self.db.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
        if "fu_count" in kv and (kv["fu_count"] or 0) > (r["fu_count"] or 0):
            self.db.execute("INSERT INTO fu_events(lead_id, at) VALUES(?,?)", (lid, datetime.now().strftime("%Y-%m-%d %H:%M")))
        d = dict(r); d.update(kv)
        if d["status"] in FU_CLOSED or d.get("sales_stage") in STAGE_PAUSED: d["next_followup"] = None
        else: d["next_followup"] = self._fu_fmt(self._fu_next(self._fu_dt(d["fu_anchor"]), d["fu_count"] or 0))
        keys = list(kv) + ["next_followup"]
        self.db.execute("UPDATE leads SET " + ",".join(f"{k}=?" for k in dict.fromkeys(keys)) + " WHERE id=?",
                        [d[k] for k in dict.fromkeys(keys)] + [lid])

    def _fu_init_missing(self):
        for r in self.db.execute("SELECT * FROM leads WHERE fu_anchor IS NULL AND status NOT IN ('Won','Lost','Dead')").fetchall():
            start = self._fu_dt(r["chat_start"]) or self._fu_dt(r["lead_date"]) or self._fu_dt(r["created_at"]) or datetime.now()
            typed = self._norm_date(r["next_followup"], True)   # a date typed in the lead form wins over the cycle
            self._fu_save(r["id"], fu_anchor=self._fu_fmt(start), chat_start=r["chat_start"] or self._fu_fmt(start), fu_count=r["fu_count"] or 0)
            if typed: self.db.execute("UPDATE leads SET next_followup=? WHERE id=?", (typed, r["id"]))
        self.db.commit()

    def _fu_flag(self, r, now):
        if r["status"] in FU_CLOSED: return f"Closed ({r['status']})" + (f": {r['closed_reason']}" if r["closed_reason"] else ""), "fu_closed", 9e9
        lc = self._fu_dt(r["last_client_msg"])
        due = self._fu_dt(r["next_followup"])
        n = r["fu_count"] or 0
        if r["sales_stage"] in STAGE_PAUSED: return f"Paused: {r['sales_stage'].lower()}", "fu_ok", 7e9
        if due is None: return f"Sequence done ({n} sent). Close or keep?", "fu_done", 8e9
        mins = int((due - now).total_seconds() // 60)
        client_last = r["last_preview"] and not r["last_preview"].lower().startswith("you:") and n == 0 and lc is not None
        lab = f"Follow-up {n + 1}"
        if mins < 0: return ("Client replied: " if client_last else "") + f"{lab} OVERDUE by {self._rel(-mins)}", ("fu_reply" if client_last else "fu_over"), mins
        if mins <= 360: return f"{lab} due in {self._rel(mins)}", "fu_soon", mins
        return f"{lab} due in {self._rel(mins)}", "fu_ok", mins

    def _fu_stage(self, r):
        """Segmented progress bar: filled segment = follow-up sent, outline = still to send."""
        total = len(self.fu_cadence()); n = min(r["fu_count"] or 0, total)
        bar = "\u25b0" * n + "\u25b1" * (total - n)
        if r["status"] in FU_CLOSED: return f"{bar}  {n}/{total} Closed"
        if r["sales_stage"] in STAGE_PAUSED: return f"{bar}  {n}/{total} Paused"
        if n >= total: return f"{bar}  {total}/{total} Done"
        return f"{bar}  {n}/{total}"

    def fu_refresh(self):
        if not hasattr(self, "ftree"): return
        self._fu_init_missing()
        now = datetime.now(); rows = []
        for r in self.db.execute("SELECT * FROM leads").fetchall():
            if r["status"] in FU_CLOSED and not self.fu_show_closed.get(): continue
            flag, tag, key = self._fu_flag(r, now)
            n = r["fu_count"] or 0
            rows.append((key, r, flag, tag, n))
        rows.sort(key=lambda x: x[0])
        self.ftree.delete(*self.ftree.get_children())
        over = soon = 0
        for key, r, flag, tag, n in rows:
            over += tag in ("fu_over", "fu_reply"); soon += tag == "fu_soon"
            self.ftree.insert("", "end", iid=f"l{r['id']}", tags=(tag,), values=(
                r["id"], r["name"], r["company"] or "", (r["job_title"] or "")[:60], self._fu_stage(r), r["sales_stage"] or "Chat started",
                (r["last_contact"] or "")[:16] if n else "", (r["next_followup"] or "")[:16], flag, self._fu_fit_msg(r["last_preview"] or "")))
        self._autofit(self.ftree)
        txt = (f"\u26a0  {over} follow-up(s) overdue" if over else "\u2714  Nothing overdue") + (f"   \u2022   {soon} due in the next 6 hours" if soon else "")
        self.fu_summary.config(text=txt, fg="#B91C1C" if over else "#047857")

    FU_MSG_MAX = 460
    def _fu_fit_msg(self, text):
        """Shorten a message so it fits the capped column, ending with ... ."""
        import tkinter.font as _tkf
        text = " ".join(text.split()); fnt = _tkf.Font(family="Segoe UI", size=9); lim = self.FU_MSG_MAX - 28
        if fnt.measure(text) <= lim: return text
        while text and fnt.measure(text + "…") > lim: text = text[:-1]
        return text.rstrip() + "…"

    def _fu_loop(self):
        try: self.fu_refresh()
        finally: self.root.after(300000, self._fu_loop)

    def _fu_selected(self):
        sel = self.ftree.selection()
        if not sel: messagebox.showinfo("Select a lead", "Select a lead in the list first."); return None
        return self.db.execute("SELECT * FROM leads WHERE id=?", (int(self.ftree.item(sel[0], "values")[0]),)).fetchone()

    def fu_mark_sent(self, lead=None, when=None):
        r = lead or self._fu_selected()
        if not r: return
        if r["status"] in FU_CLOSED: return messagebox.showinfo("Closed lead", "This lead is closed. Reopen it first.")
        n = min((r["fu_count"] or 0) + 1, len(self.fu_cadence())); t = self._fu_fmt(when or datetime.now())
        self._fu_save(r["id"], fu_count=n, fu_anchor=t, last_contact=t, status="Follow-up" if r["status"] in ("Qualified", "Contacted") else r["status"])
        self.db.commit(); self.refresh_all()

    def fu_client_replied(self, lead=None, when=None):
        r = lead or self._fu_selected()
        if not r: return
        t = self._fu_fmt(when or datetime.now())
        self._fu_save(r["id"], fu_count=0, fu_anchor=t, last_client_msg=t)
        self.db.commit(); self.refresh_all()

    def fu_change_stage(self, lid, stage, when=None, raw=None):
        """A new stage restarts the follow-up clock from the stage time (follow-up 1 due 24h after it)."""
        r = self.db.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
        if not r or (r["sales_stage"] or "Chat started") == stage: return False
        t = self._fu_fmt(when or datetime.now())
        kv = dict(sales_stage=stage, stage_at=t, fu_count=0, fu_anchor=t)
        if stage == "Contract started": kv["status"] = "Won"
        elif stage == "Meeting booked" and r["status"] in ("Qualified", "Contacted", "Follow-up"): kv["status"] = "Interview"
        if raw: kv["notes"] = ((r["notes"] or "") + f"\n[{t}] Upwork timeline: {raw}").strip()
        self._fu_save(lid, **kv); return True

    def fu_set_stage(self):
        r = self._fu_selected()
        if not r: return
        win = tk.Toplevel(self.root); win.title("Set sales stage"); win.configure(bg="#FFFFFF"); win.transient(self.root)
        tk.Label(win, text=f"Stage for {r['name']}", bg="#FFFFFF", fg=UI["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(win, text="Changing the stage restarts the follow-ups: follow-up 1 is due 24 hours later.", bg="#FFFFFF", fg=UI["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        v = tk.StringVar(value=r["sales_stage"] or "Chat started")
        ttk.Combobox(win, textvariable=v, values=SALES_STAGES, state="readonly", width=44).pack(padx=16, pady=10)
        def ok():
            if self.fu_change_stage(r["id"], v.get()): self.db.commit(); self.refresh_all()
            win.destroy()
        bf = tk.Frame(win, bg="#FFFFFF"); bf.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(bf, text="Save", style="Accent.TButton", command=ok).pack(side="right")
        ttk.Button(bf, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        try: win.grab_set()
        except tk.TclError: pass
        self._stage_win = (win, v, ok)

    def fu_close(self):
        r = self._fu_selected()
        if not r: return
        reason = simpledialog.askstring("Close lead", f"Why is {r['name']} closed?\n(for example: went with someone else, no budget, no reply)",
                                        initialvalue="Went with someone else", parent=self.root)
        if reason is None: return
        self._fu_save(r["id"], status="Lost", closed_reason=reason.strip()[:200])
        self.db.commit(); self.refresh_all()

    def fu_reopen(self):
        r = self._fu_selected()
        if not r: return
        if r["status"] not in FU_CLOSED: return messagebox.showinfo("Reopen", "This lead is already open.")
        t = self._fu_fmt(datetime.now())
        kv = dict(status="Contacted", closed_reason=None, fu_count=0, fu_anchor=t)
        if (r["sales_stage"] or "") in STAGE_PAUSED: kv.update(sales_stage="Chat started", stage_at=t)   # otherwise follow-ups would stay paused
        self._fu_save(r["id"], **kv)
        self.db.commit(); self.refresh_all()

    def fu_close_won(self):
        r = self._fu_selected()
        if not r: return
        if r["status"] == "Won": return messagebox.showinfo("Close as Won", "This lead is already marked as Won.")
        if not messagebox.askyesno("Close as Won", f"Mark {r['name']} as Won?\n\nFollow-ups stop and the lead counts as won in your reports."): return
        t = self._fu_fmt(datetime.now())
        self._fu_save(r["id"], status="Won", closed_reason="Won", sales_stage="Contract started", stage_at=t)
        self.db.commit(); self.refresh_all()

    def fu_apply_messages(self, rows):
        """Create or update leads from the Upwork Messages list. Returns (new, replies, followups)."""
        from datetime import timedelta
        acct = self.db.execute("SELECT account, member FROM proposals WHERE account<>'' ORDER BY id DESC LIMIT 1").fetchone()
        account, member = (acct["account"], acct["member"]) if acct else ("Upwork", "Ammar")
        props = self.db.execute("SELECT id, job FROM proposals").fetchall()
        new = replies = fus = 0
        for m in rows:
            when = self._fu_fmt(m["when"])
            r = self.db.execute("SELECT * FROM leads WHERE lower(name)=lower(?) AND lower(COALESCE(company,''))=lower(?)", (m["name"], m["company"])).fetchone()
            if not r:
                tkey = _norm_title(m["title"]); pid = None
                for pr in props:
                    if tkey and len(tkey) >= 8 and _norm_title(pr["job"]).startswith(tkey[:40]): pid = pr["id"]; break
                cur = self.db.execute("INSERT INTO leads(account, member, name, company, source, proposal_id, lead_date, status, job_title, last_preview, chat_start, fu_anchor, fu_count, last_client_msg, last_contact) "
                                      "VALUES(?,?,?,?,'Upwork Messages',?,?,'Contacted',?,?,?,?,0,?,?)",
                                      (account, member, m["name"], m["company"], pid, m["when"].strftime("%Y-%m-%d"), m["title"], m["preview"], when, when,
                                       None if m["from_me"] else when, when if m["from_me"] else None))
                self._fu_save(cur.lastrowid, sales_stage="Meeting requested, no reply yet" if m["from_me"] and _MEET_WORDS.search(m["preview"]) else "Chat started", stage_at=when); new += 1
                continue
            upd = {"last_preview": m["preview"]}
            if not r["job_title"]: upd["job_title"] = m["title"]
            if r["status"] not in FU_CLOSED:
                anc = self._fu_dt(r["fu_anchor"]) or datetime.min
                newer = (m["when"] > anc + timedelta(minutes=30)) if m["has_time"] else (m["when"].date() > anc.date())
                if newer and not m["from_me"]:
                    upd.update(fu_count=0, fu_anchor=when, last_client_msg=when); replies += 1
                    if r["sales_stage"] == "Meeting requested, no reply yet": upd.update(sales_stage="Chat started", stage_at=when)
                elif newer and m["from_me"] and _MEET_WORDS.search(m["preview"]) and (r["sales_stage"] or "Chat started") in ("Chat started", "Proposal sent, awaiting response"):
                    upd.update(sales_stage="Meeting requested, no reply yet", stage_at=when, fu_count=0, fu_anchor=when, last_contact=when)
                elif newer and m["from_me"]:
                    upd.update(fu_count=min((r["fu_count"] or 0) + 1, len(self.fu_cadence())), fu_anchor=when, last_contact=when); fus += 1
            self._fu_save(r["id"], **upd)
        self.db.commit()
        return new, replies, fus

    def fu_import_messages(self):
        hwnd = find_upwork_window()
        fallback = False
        if hwnd is None:
            # Tab title may be just "Messages": use the browser window in front if its title says so, checked below
            fb = find_job_browser_window()
            if _title_has(fb, "messages"):
                hwnd, fallback = fb, True
        if hwnd is None:
            try: __import__("webbrowser").open("https://www.upwork.com/ab/messages/")
            except Exception: pass
            return messagebox.showinfo("Import from Upwork Messages", "I opened Upwork Messages in your browser.\n\nLog in if asked, wait for your chat list to load, then click Import again.")
        clear_clipboard(); copy_window_text(hwnd); text = read_clipboard_text()
        try: self.root.deiconify(); self.root.lift(); self.root.focus_force()
        except Exception: pass
        rows = parse_upwork_messages_list(text)
        if fallback and not upwork_page_ok(text, "messages"):
            rows = []
        if not rows:
            low = (text or "").lower()
            msg = ("Nothing was copied. Click once on the Upwork page, then click Import again." if not low.strip() else
                   "Upwork looks logged out. Log in, open Messages, then try again." if "log in" in low and "messages" not in low else
                   "I couldn't find the chat list. Make sure the Upwork Messages page (with the list of chats on the left) is the tab in front.")
            return messagebox.showwarning("Import from Upwork Messages", msg)
        new, replies, fus = self.fu_apply_messages(rows)
        stage_note = self.fu_apply_open_chat(parse_upwork_open_chat(text))
        self.refresh_all(); self.show_page("followups")
        messagebox.showinfo("Import from Upwork Messages",
            f"Read {len(rows)} chats from Upwork Messages.\n\nNew leads: {new}\nClient replies found (timeline restarted): {replies}\n"
            f"Your new follow-ups found: {fus}\n{stage_note}\n\nNo duplicate leads were created. Nothing was sent or changed on Upwork.")

    def fu_apply_open_chat(self, oc):
        if not oc: return "Open chat: none detected (open a chat to also read its stage)."
        r = self.db.execute("SELECT * FROM leads WHERE lower(name)=lower(?) AND lower(COALESCE(company,''))=lower(?)", (oc["name"], oc["company"])).fetchone()
        if not r: return f"Open chat: {oc['who']} (not in your list yet)."
        if not oc["stage"]: return f"Open chat: {oc['who']}, no timeline stage found."
        changed = self.fu_change_stage(r["id"], oc["stage"], raw=oc["raw"]); self.db.commit()
        return f"Stage for {oc['name']}: {oc['stage']}" + (" (updated, follow-ups restarted)" if changed else " (no change)")

    def selected_row(self,tree,table):
        selection=tree.selection()
        if not selection:return messagebox.showinfo("Select a record","Please select a record first.")
        record_id=int(tree.item(selection[0],"values")[0])
        return self.db.execute(f"SELECT * FROM {table} WHERE id=?",(record_id,)).fetchone()

    def delete_selected(self,tree,table):
        selection=tree.selection()
        if not selection:return messagebox.showinfo("Select a record","Please select one or more records first.")
        if not messagebox.askyesno("Confirm delete",f"Delete {len(selection)} selected record(s)?"):return
        for item in selection:
            self.db.execute(f"DELETE FROM {table} WHERE id=?",(int(tree.item(item,"values")[0]),))
        self.db.commit();self.refresh_all()

    def setting(self,key):
        row=self.db.execute("SELECT v FROM settings WHERE k=?",(key,)).fetchone()
        return row["v"] if row else "0"

    def plan_changed(self, key, value):
        # ttk.Scale may invoke its callback during initial setup before the
        # matching value label has been registered. Update only when ready.
        n = round(float(value))
        if key in self.plan_vars and self.plan_vars[key].get() != n:
            self.plan_vars[key].set(n)
        label = getattr(self, "plan_labels", {}).get(key)
        if label is not None:
            label.configure(text=str(n))

    def calculate_plan(self):
        if not hasattr(self,"plan_vars"):return
        target=self.plan_vars["target"].get()
        view=self.plan_vars["view_rate"].get()
        lead=self.plan_vars["lead_rate"].get()
        close=self.plan_vars["close_rate"].get()
        views=(target*100+lead-1)//lead if lead else None
        proposals=(views*100+view-1)//view if views is not None and view else None
        clients=(target*close)//100
        outputs={"leads":str(target),"views":str(views) if views is not None else "-",
                 "proposals":str(proposals) if proposals is not None else "-","clients":str(clients)}
        for key,value in outputs.items():self.plan_results[key].configure(text=value)

    def save_plan(self):
        for key,var in self.plan_vars.items():
            self.db.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)",(key,str(var.get())))
        self.db.commit();messagebox.showinfo("Saved","Planner assumptions saved.")

    def populate_tree(self,tree,rows,keys,followup_highlight=False):
        tree.delete(*tree.get_children())
        today=date.today().isoformat()
        for index, row in enumerate(rows):
            vals=[row[k] if row[k] is not None else "" for k in keys]
            overdue = followup_highlight and row["next_followup"] and row["next_followup"] < today
            st = row["status"] if "status" in row.keys() else None
            tags = ("overdue",) if overdue else (("st_" + st,) if st in STATUS_COLORS else (("odd",) if index % 2 else ("even",)))
            tree.insert("","end",values=vals,tags=tags)

    def refresh_all(self):
        proposals=self.db.execute("SELECT * FROM proposals ORDER BY id DESC").fetchall()
        leads=self.db.execute("SELECT *, trim(replace(replace(coalesce(notes,''), char(13), ''), char(10), '  ')) AS notes_pv FROM leads ORDER BY id DESC").fetchall()
        self.populate_tree(self.ptree,proposals,["id","account","member","job","client","proposal_date","bid","connects","status","views"])
        self.populate_tree(self.ltree,leads,["id","name","company","account","member","source","lead_date","status","budget","next_followup","proposal_id","notes_pv"])
        self.fu_refresh()
        self.populate_tree(self.dtree,leads[:100],["id","name","company","source","lead_date","next_followup","status"],True)
        self.jtree.delete(*self.jtree.get_children())
        for i, r in enumerate(proposals):
            cat = r["category"] or ""
            vals = [r["id"], r["job"], r["client"] or "", r["status"], ("\u26a1 Boosted" if cat == "Boosted" else cat), (f'{r["connects_normal"]} + {r["connects_boosted"]}\u26a1' if r["connects_normal"] and r["connects_boosted"] else (r["connects"] or ""))]
            for c, _ in JOB_DETAIL_COLS:
                v = r[c] or ""
                vals.append((v[:60] + "...") if c == "summary" and len(v) > 60 else v)
            self.jtree.insert("", "end", iid=str(r["id"]), values=vals, tags=(("st_" + r["status"]) if r["status"] in STATUS_COLORS else ("odd" if i % 2 else "even"),))
        self.draw_status_pills(proposals)
        self.perf_refresh()
        counts={
            "submitted":sum(1 for r in proposals if r["status"] not in ("Draft","Archived")),
            "views":sum(int(r["views"] or 0) for r in proposals),
            "qualified":sum(1 for r in leads if r["status"] in ("Qualified","Contacted","Follow-up","Interview","Negotiation","Won")),
            "interviews":sum(1 for r in proposals if r["status"]=="Interview")+sum(1 for r in leads if r["status"]=="Interview"),
            "won":sum(1 for r in leads if r["status"]=="Won")}
        # Dashboard cards are configurable; update only metrics represented
        # by cards in the current dashboard layout.
        for key, value in counts.items():
            widget = self.kpis.get(key)
            if widget is not None:
                widget.configure(text=str(value))
        self.draw_dashboard_visuals(leads)
        self.calculate_plan()

    def template_csv(self,table):
        fields=PROPOSAL_FIELDS if table=="proposals" else LEAD_FIELDS
        path=filedialog.asksaveasfilename(defaultextension=".csv",initialfile=f"{table}_template.csv",filetypes=[("CSV","*.csv")])
        if not path:return
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f);w.writerow(fields)
        messagebox.showinfo("Template created",f"CSV template saved:\n{path}")

    def import_csv(self,table):
        path=filedialog.askopenfilename(filetypes=[("CSV files","*.csv")])
        if not path:return
        fields=PROPOSAL_FIELDS if table=="proposals" else LEAD_FIELDS
        required=["account","member","job"] if table=="proposals" else ["account","member","name"]
        try:
            count=0
            with open(path,newline="",encoding="utf-8-sig") as f:
                reader=csv.DictReader(f)
                if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
                    raise ValueError("Required headers: "+", ".join(required))
                columns=[x for x in fields if x in reader.fieldnames]
                key = lambda n, c: (" ".join((n or "").split()).lower(), " ".join((c or "").split()).lower())
                have = {key(x["name"], x["company"]) for x in self.db.execute("SELECT name, company FROM leads")} if table == "leads" else set()
                dates = [("proposal_date", False)] if table == "proposals" else [("lead_date", False), ("next_followup", True), ("last_contact", True)]
                dup = []; bad = []
                for line_no, row in enumerate(reader, start=2):
                    for k, allow_t in dates:
                        if k in columns:
                            nd = self._norm_date(row.get(k), allow_t)
                            if nd is None: bad.append(f"row {line_no} ({k.replace('_', ' ')} '{row.get(k)}')"); break
                            row[k] = nd
                    else:
                        if table == "leads":
                            kk = key(row.get("name"), row.get("company"))
                            if kk in have: dup.append(line_no); continue
                            have.add(kk)
                    if bad and bad[-1].startswith(f"row {line_no} "): continue
                    vals=[row.get(k,"") or None for k in columns]
                    if table=="proposals":
                        for col_name,default in [("bid","0"),("connects","0"),("views","0")]:
                            if col_name in columns:
                                idx=columns.index(col_name);vals[idx]=float(vals[idx] or default) if col_name=="bid" else int(vals[idx] or default)
                    else:
                        if "budget" in columns:
                            idx=columns.index("budget");vals[idx]=float(vals[idx] or 0)
                        if "proposal_id" in columns:
                            idx=columns.index("proposal_id");vals[idx]=int(vals[idx]) if vals[idx] else None
                    self.db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",vals)
                    count+=1
            self.db.commit();self.refresh_all()
            msg = f"Imported {count} {table} records."
            if table == "leads": msg += f"\nSkipped {len(dup)} lead(s) already in LeadPilot (same name and company)."
            if bad: msg += f"\nSkipped {len(bad)} row(s) with a date that is not real: " + ", ".join(bad[:8]) + (" ..." if len(bad) > 8 else "")
            messagebox.showinfo("Import complete", msg)
        except Exception as exc:
            self.db.rollback();messagebox.showerror("Import failed",str(exc))

    def export_csv(self,table):
        path=filedialog.asksaveasfilename(defaultextension=".csv",initialfile=f"{table}_export.csv",filetypes=[("CSV files","*.csv")])
        if not path:return
        rows=self.db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        fields=[x for x in (PROPOSAL_FIELDS if table=="proposals" else LEAD_FIELDS)]
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            writer=csv.DictWriter(f,fieldnames=["id"]+fields);writer.writeheader()
            for row in rows:writer.writerow({k:row[k] for k in ["id"]+fields})
        messagebox.showinfo("Export complete",f"Exported {len(rows)} records.")

    def backup(self):
        path=filedialog.asksaveasfilename(defaultextension=".db",initialfile="LeadPilot_backup.db",filetypes=[("SQLite database","*.db")])
        if path:
            self.db.commit();shutil.copy2(DB_PATH,path)
            messagebox.showinfo("Backup created",f"Backup saved:\n{path}")

    def restore_backup(self):
        """Replace all data with a backup file. The current data is saved first as a safety copy, then LeadPilot reloads."""
        path = filedialog.askopenfilename(title="Choose a LeadPilot backup to restore", filetypes=[("LeadPilot backup", "*.db"), ("All files", "*.*")])
        if not path: return
        src = Path(path)
        if not src.is_file(): return messagebox.showwarning("Restore from backup", "That file could not be found. Nothing was changed.")
        try:
            if src.resolve() == Path(DB_PATH).resolve():
                return messagebox.showwarning("Restore from backup", "That is the database LeadPilot is using now. Choose a backup file instead.")
            con = sqlite3.connect(str(src))
            try:
                okc = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                tabs = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not okc or not {"proposals", "leads"} <= tabs: raise ValueError("not a LeadPilot backup")
                n_p = con.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]; n_l = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            except Exception:
                con.close(); return messagebox.showwarning("Restore from backup", "That file is not a LeadPilot backup, or it is damaged. Nothing was changed.")
        except sqlite3.Error:
            return messagebox.showwarning("Restore from backup", "That file is not a LeadPilot backup, or it is damaged. Nothing was changed.")
        if not messagebox.askyesno("Restore from backup", f"Replace ALL current data with this backup?\n\n{src.name}\n{n_p} proposals, {n_l} leads\n\n"
                                   "Your current data is saved first as a safety copy, so you can undo this."):
            con.close(); return
        safe_dir = APP_DIR / "backups"; safe_dir.mkdir(parents=True, exist_ok=True)
        safe = safe_dir / f"before_restore_{datetime.now():%Y-%m-%d_%H%M%S}.db"
        try:
            self.db.commit(); out = sqlite3.connect(str(safe)); self.db.backup(out); out.close()
            con.backup(self.db); con.close()
        except Exception as exc:
            try: con.close()
            except Exception: pass
            return messagebox.showerror("Restore from backup", f"The restore did not finish, and your data was not replaced.\n\n{exc}")
        self.init_db(); self._fu_update_sub(); self.refresh_all(); self.meet_tick_now()
        if hasattr(self, "rep_list"): self.rep_refresh()
        messagebox.showinfo("Restore from backup", f"Restored {n_p} proposals and {n_l} leads from {src.name}.\n\nYour data from before the restore is saved here:\n{safe}")

    def close(self):
        page = getattr(self, "write_page", None)
        if page is not None and callable(getattr(page, "confirm_leave", None)):
            try:
                if not page.confirm_leave():
                    return
            except Exception:
                pass
        self.db.close();self.root.destroy()

if __name__=="__main__":
    root=tk.Tk()
    app=LeadPilot(root)
    root.mainloop()
