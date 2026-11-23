"""Store for Write a proposal drafts.

Drafts live in the proposal_drafts table, separate from submitted
proposals, until a submitted Upwork proposal URL is saved. This module
never opens a network connection and never touches Upwork.

Callers pass an open sqlite3 connection (the same one the app uses).
Write functions commit on success. submit_draft does its work in one
transaction and rolls back if anything fails.
"""

from datetime import date, datetime
from urllib.parse import urlparse, urlunparse

__all__ = [
    "DraftError",
    "ensure_table",
    "list_drafts",
    "get_draft",
    "create_draft",
    "update_draft",
    "delete_draft",
    "validate_proposal_url",
    "submit_draft",
    "submit_direct",
]

# Friendly message for a rejected submitted-proposal URL.
INVALID_URL_MESSAGE = (
    "Please paste the link of your submitted proposal from Upwork "
    "(it starts with https://www.upwork.com/)."
)

# Fields the UI may change with update_draft. status, submitted_url and
# proposal_id are only set by submit_draft.
UPDATE_FIELDS = (
    "job_title",
    "client",
    "job_url",
    "budget_text",
    "skills",
    "location",
    "job_text",
    "template_name",
    "instructions",
    "draft",
)

# Defaults used by the Add proposal form when connects and bid are left blank.
# account and member match Add proposal when no Upwork login is stored.
DEFAULT_ACCOUNT = "Upwork"
DEFAULT_MEMBER = "Me"
SUBMITTED_STATUS = "Submitted"
SUBMIT_NOTES = "Added from Write a proposal."

_DRAFT_COLUMNS = (
    "id", "job_title", "client", "job_url", "budget_text", "skills",
    "location", "job_text", "template_name", "instructions", "draft",
    "created_at", "updated_at", "status", "submitted_url", "proposal_id",
)


class DraftError(Exception):
    """Friendly, user-facing error. Read the message attribute."""

    def __init__(self, message):
        self.message = message
        super().__init__(message)


def _now():
    """Same minute-precision local stamp the app writes (YYYY-MM-DD HH:MM)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _dicts(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _title_from_text(job_text):
    for line in (job_text or "").splitlines():
        line = line.strip()
        if line:
            return line[:250]
    return ""


def _resolve_title(job_title, job_text):
    title = (job_title or "").strip()
    if title:
        return title
    return _title_from_text(job_text) or "Untitled job"


def ensure_table(conn):
    """Create proposal_drafts if needed. Safe to call on an existing database."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_drafts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_title TEXT,
          client TEXT,
          job_url TEXT,
          budget_text TEXT,
          skills TEXT,
          location TEXT,
          job_text TEXT,
          template_name TEXT,
          instructions TEXT,
          draft TEXT,
          created_at TEXT,
          updated_at TEXT,
          status TEXT NOT NULL DEFAULT 'draft',
          submitted_url TEXT,
          proposal_id INTEGER
        )
        """
    )
    have = {row[1] for row in conn.execute("PRAGMA table_info(proposal_drafts)")}
    for col in _DRAFT_COLUMNS:
        if col == "id":
            continue
        if col not in have:
            typ = "INTEGER" if col == "proposal_id" else "TEXT"
            if col == "status":
                typ = "TEXT NOT NULL DEFAULT 'draft'"
            conn.execute(f"ALTER TABLE proposal_drafts ADD COLUMN {col} {typ}")
    conn.commit()


def list_drafts(conn):
    """Open drafts only (status='draft'), newest updated_at first."""
    cur = conn.execute(
        "SELECT * FROM proposal_drafts WHERE status='draft' "
        "ORDER BY updated_at DESC, id DESC"
    )
    return _dicts(cur)


def get_draft(conn, draft_id):
    """Return one draft as a dict, or None if it is not there."""
    cur = conn.execute(
        "SELECT * FROM proposal_drafts WHERE id=?", (draft_id,)
    )
    rows = _dicts(cur)
    return rows[0] if rows else None


def create_draft(conn, job_title, job_text, client="", job_url="",
                 budget_text="", skills="", location=""):
    """Insert a new open draft and return its id."""
    title = _resolve_title(job_title, job_text)
    stamp = _now()
    cur = conn.execute(
        """
        INSERT INTO proposal_drafts (
          job_title, client, job_url, budget_text, skills, location,
          job_text, template_name, instructions, draft,
          created_at, updated_at, status, submitted_url, proposal_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', '', ?, ?, 'draft', NULL, NULL)
        """,
        (title, client or "", job_url or "", budget_text or "",
         skills or "", location or "", job_text or "", stamp, stamp),
    )
    conn.commit()
    return cur.lastrowid


def update_draft(conn, draft_id, **fields):
    """Update allowed fields and bump updated_at. Unknown keys are ignored."""
    updates = {k: fields[k] for k in UPDATE_FIELDS if k in fields}
    if not updates:
        return
    sets = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values())
    values.append(_now())
    values.append(draft_id)
    conn.execute(
        f"UPDATE proposal_drafts SET {sets}, updated_at=? WHERE id=?",
        values,
    )
    conn.commit()


def delete_draft(conn, draft_id):
    """Delete a draft by id. Returns True if a row was removed."""
    cur = conn.execute(
        "DELETE FROM proposal_drafts WHERE id=?", (draft_id,)
    )
    conn.commit()
    return cur.rowcount > 0


def _host_ok(host):
    host = (host or "").lower().rstrip(".")
    return host in ("upwork.com", "www.upwork.com")


def _path_ok(path):
    path = (path or "").lower()
    if not path.startswith("/"):
        path = "/" + path
    exact = (
        "/jobs",
    )
    prefixes = (
        "/nx/proposals",
        "/ab/proposals",
        "/freelance-jobs/apply",
        "/proposals",
    )
    if path in exact or path.rstrip("/") in exact:
        return True
    if path.startswith("/jobs/"):
        return True
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def validate_proposal_url(url):
    """Return (True, cleaned_url) or (False, friendly_message). Never fetches."""
    cleaned = (url or "").strip()
    if not cleaned or any(ch.isspace() for ch in cleaned):
        return False, INVALID_URL_MESSAGE
    try:
        parsed = urlparse(cleaned)
    except Exception:
        return False, INVALID_URL_MESSAGE
    if (parsed.scheme or "").lower() not in ("http", "https"):
        return False, INVALID_URL_MESSAGE
    if parsed.username is not None or parsed.password is not None:
        return False, INVALID_URL_MESSAGE
    if not _host_ok(parsed.hostname):
        return False, INVALID_URL_MESSAGE
    if not _path_ok(parsed.path or ""):
        return False, INVALID_URL_MESSAGE
    return True, cleaned


def submit_draft(conn, draft_id, url):
    """Move a draft into proposals after a valid submitted Upwork URL is given.

    Returns the new proposals.id. Raises DraftError with a friendly message
    when the draft cannot be submitted. On any failure the transaction is
    rolled back, so neither table is left half-updated.
    """
    ok, cleaned = validate_proposal_url(url)
    if not ok:
        raise DraftError(cleaned)

    conn.execute("SAVEPOINT lp_submit_draft")
    try:
        cur = conn.execute(
            "SELECT * FROM proposal_drafts WHERE id=?", (draft_id,)
        )
        rows = _dicts(cur)
        if not rows:
            raise DraftError(
                "This draft was not found. It may have been deleted."
            )
        draft = rows[0]
        if (draft.get("status") or "") == "submitted":
            raise DraftError("This draft has already been submitted.")
        text = (draft.get("draft") or "").strip()
        if not text:
            raise DraftError(
                "This draft has no proposal text yet. "
                "Generate or write a draft first."
            )

        if _url_already_saved(conn, cleaned):
            raise DraftError(
                "This Upwork link is already saved in Submitted Proposals."
            )

        job = _resolve_title(draft.get("job_title"), draft.get("job_text"))
        cur = conn.execute(
            """
            INSERT INTO proposals (
              account, member, job, client, url, proposal_date,
              bid, connects, status, views, notes,
              cover_letter, budget_text, skills, location, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_ACCOUNT,
                DEFAULT_MEMBER,
                job,
                draft.get("client") or "",
                cleaned,
                date.today().isoformat(),
                0,
                0,
                SUBMITTED_STATUS,
                0,
                SUBMIT_NOTES,
                text,
                draft.get("budget_text") or "",
                draft.get("skills") or "",
                draft.get("location") or "",
                draft.get("job_text") or "",
            ),
        )
        proposal_id = cur.lastrowid
        conn.execute(
            """
            UPDATE proposal_drafts
               SET status='submitted',
                   submitted_url=?,
                   proposal_id=?,
                   updated_at=?
             WHERE id=?
            """,
            (cleaned, proposal_id, _now(), draft_id),
        )
        conn.execute("RELEASE SAVEPOINT lp_submit_draft")
        conn.commit()
        return proposal_id
    except Exception:
        try:
            conn.execute("ROLLBACK TO SAVEPOINT lp_submit_draft")
            conn.execute("RELEASE SAVEPOINT lp_submit_draft")
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        raise




def _normalize_stored_url(url):
    """Clean a proposal or job URL for storage and duplicate checks.

    Uses job_text_parser.normalize_job_url when available, then drops a
    trailing slash and the query string so those do not create a second row.
    Never fetches. Never imports tkinter.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        from job_text_parser import normalize_job_url
        raw = normalize_job_url(raw) or raw
    except Exception:
        pass
    try:
        parsed = urlparse(raw)
        path = (parsed.path or "").rstrip("/")
        return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, "", ""))
    except Exception:
        return raw.rstrip("/")


def _url_key(url):
    cleaned = _normalize_stored_url(url)
    try:
        parsed = urlparse(cleaned)
        return (
            (parsed.scheme or "https").lower(),
            (parsed.netloc or "").lower().rstrip("."),
            (parsed.path or "").rstrip("/"),
        )
    except Exception:
        return ("", "", (cleaned or "").lower())


def _url_already_saved(conn, url):
    key = _url_key(url)
    if key == ("", "", ""):
        return False
    for row in conn.execute("SELECT url FROM proposals"):
        existing = row["url"] if hasattr(row, "keys") else row[0]
        if _url_key(existing) == key:
            return True
    return False


def submit_direct(conn, url, job_title="", cover_letter="", job_text="",
                  budget_text="", skills="", location="", client="",
                  **kwargs):
    """Insert one proposals row for a submitted Upwork URL, with no draft row.

    Returns the new proposals.id. Raises DraftError with a friendly message
    when the URL is invalid or already saved. Commits on success.
    """
    ok, cleaned = validate_proposal_url(url)
    if not ok:
        raise DraftError(cleaned)
    stored = _normalize_stored_url(cleaned) or cleaned
    if _url_already_saved(conn, stored) or _url_already_saved(conn, cleaned):
        raise DraftError(
            "This Upwork link is already saved in Submitted Proposals."
        )
    if isinstance(skills, (list, tuple)):
        skills_text = ", ".join(str(s).strip() for s in skills if str(s).strip())
    else:
        skills_text = (skills or "").strip()
    job = (job_title or "").strip()
    if not job:
        for line in (job_text or "").splitlines():
            if line.strip():
                job = line.strip()
                break
    cur = conn.execute(
        """
        INSERT INTO proposals (
          account, member, job, client, url, proposal_date,
          bid, connects, status, views, notes,
          cover_letter, budget_text, skills, location, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            DEFAULT_ACCOUNT,
            DEFAULT_MEMBER,
            job,
            client or "",
            stored,
            date.today().isoformat(),
            0,
            0,
            SUBMITTED_STATUS,
            0,
            SUBMIT_NOTES,
            cover_letter or "",
            budget_text or "",
            skills_text,
            location or "",
            job_text or "",
        ),
    )
    proposal_id = cur.lastrowid
    conn.commit()
    return proposal_id
