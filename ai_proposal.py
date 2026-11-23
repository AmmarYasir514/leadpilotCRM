"""AI proposal generator for LeadPilot CRM.

Builds a proposal DRAFT from a job post plus the user's instructions by
calling the OpenAI chat completions API. DRAFT ONLY: this module never talks
to Upwork, never clicks, submits or sends anything. The user always reviews,
edits and copies the draft by hand.

Uses only the Python standard library (urllib), so no new dependency.
Config (model, base URL, templates, limits) comes from settings_store.load_config().
The API key comes from settings_store.get_api_key() (Windows Credential Manager).
The key is never logged, printed, or placed in any exception or message.

The UI should call generate_proposal() from a background thread and show
AIError.user_message to the user on failure.
"""

import json
import socket
import urllib.error
import urllib.request

# Fallbacks used only if a config key is missing. The real values live in the
# external config file managed by settings_store.
_DEFAULTS = {
    "openai_base_url": "https://api.openai.com/v1",
    "openai_model": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 900,
    "request_timeout": 60,
    "max_job_post_chars": 12000,
    "proposal_system_prompt": (
        "You write short, clear Upwork proposals in plain, simple English. "
        "Do not use em dashes or en dashes. "
        "When the freelancer gives instructions, treat them as mandatory: "
        "follow them closely. If they conflict with general style rules or "
        "the template, prefer the freelancer's instructions."
    ),
    "proposal_user_template": (
        "Job post:\n{job_post}\n\n"
        "Instructions from the freelancer (follow these closely):\n"
        "{instructions}\n\nWrite a proposal draft."
    ),
    "revision_template": (
        "Job post:\n{job_post}\n\nCurrent draft:\n{previous_draft}\n\n"
        "Revise the draft using these instructions (follow them closely):\n"
        "{instructions}\n\n"
        "Return only the revised draft."
    ),
}

NO_INSTRUCTIONS = "No extra instructions."
TRUNCATION_NOTE = "\n\n[Note: the job post was very long and has been shortened.]"


# ---------------------------------------------------------------- errors

class AIError(Exception):
    """Base error. user_message is plain English, safe to show in the UI."""

    default_message = "Something went wrong while writing the proposal. Try again."

    def __init__(self, user_message=None):
        self.user_message = user_message or self.default_message
        super().__init__(self.user_message)


class NoKeyError(AIError):
    default_message = "No OpenAI API key saved. Add it on the Settings page."


class AuthError(AIError):
    default_message = ("OpenAI rejected the API key. Check the key on the "
                       "Settings page and try again.")


class OfflineError(AIError):
    default_message = ("Could not reach OpenAI. Check your internet "
                       "connection and try again.")


class RateLimitError(AIError):
    default_message = ("OpenAI is getting too many requests right now. "
                       "Wait a minute and try again.")


class AITimeoutError(AIError):
    default_message = "OpenAI took too long to answer. Try again."


NO_CREDITS_MESSAGE = ("Your OpenAI account has no credits left. Add credits in OpenAI "
                      "Billing (platform.openai.com), then try again.")
QUOTA_MESSAGE = NO_CREDITS_MESSAGE   # old name, kept for callers


class NoCreditsError(RateLimitError):
    """HTTP 429 with error code or type 'insufficient_quota'. A RateLimitError
    subclass, so code that catches RateLimitError still works."""
    default_message = NO_CREDITS_MESSAGE


# ---------------------------------------------------------------- helpers

def _load_cfg(cfg):
    if cfg is None:
        import settings_store
        cfg = settings_store.load_config() or {}
    merged = dict(_DEFAULTS)
    for k, v in (cfg or {}).items():
        if v is not None and v != "":
            merged[k] = v
    return merged


def _num(value, cast, default):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def _fill(template, job_post, instructions, previous_draft):
    """Safe placeholder fill. Uses str.replace, never str.format, so braces in
    the job post or instructions cannot break anything. User text is put in
    last-to-first order through unique markers so a user typing
    '{instructions}' in a job post is not expanded."""
    markers = {
        "{job_post}": "\x00JOB\x00",
        "{instructions}": "\x00INS\x00",
        "{previous_draft}": "\x00PREV\x00",
    }
    out = str(template)
    for ph, mk in markers.items():
        out = out.replace(ph, mk)
    out = out.replace("\x00JOB\x00", job_post)
    out = out.replace("\x00INS\x00", instructions)
    out = out.replace("\x00PREV\x00", previous_draft or "")
    return out


def _clean_dashes(text):
    # Ammar's style rule: no em dashes or en dashes in proposals.
    # Em dash becomes a comma, en dash becomes a plain hyphen.
    text = text.replace(" \u2014 ", ", ").replace("\u2014", ", ")
    text = text.replace("\u2013", "-")
    return text


def trim_job_post(job_post, cfg=None):
    """Return (text, was_trimmed). Trims very long posts to max_job_post_chars."""
    c = _load_cfg(cfg)
    limit = _num(c.get("max_job_post_chars"), int, 12000)
    if limit > 0 and len(job_post) > limit:
        return job_post[:limit] + TRUNCATION_NOTE, True
    return job_post, False


# ---------------------------------------------------------------- public API

def build_messages(job_post, instructions="", previous_draft=None, cfg=None,
                   template_text=None):
    """Build the chat messages list for OpenAI.

    template_text (optional, P6 proposal templates): a user-chosen template
    used instead of cfg['proposal_user_template'] for a first draft. Same
    placeholders. Ignored for revisions (previous_draft given), which always
    use revision_template."""
    c = _load_cfg(cfg)
    job = (job_post or "").strip()
    job, _ = trim_job_post(job, c)
    ins = (instructions or "").strip() or NO_INSTRUCTIONS
    use_custom = (not previous_draft and template_text is not None
                  and bool(str(template_text).strip()))
    if previous_draft:
        template = c.get("revision_template") or _DEFAULTS["revision_template"]
    elif use_custom:
        template = str(template_text)
    else:
        template = c.get("proposal_user_template") or _DEFAULTS["proposal_user_template"]
    user_text = _fill(template, job, ins, previous_draft)
    if use_custom and "{job_post}" not in template:
        # Custom template has no {job_post} placeholder: append the job post
        # so the model always sees it. Config templates are left as before.
        user_text = user_text.rstrip() + "\n\nJob post:\n" + job
    if use_custom and "{instructions}" not in template and ins != NO_INSTRUCTIONS:
        # Same idea for instructions: a template without {instructions}
        # used to drop Custom Instructions entirely.
        user_text = (
            user_text.rstrip()
            + "\n\nInstructions from the freelancer (follow these closely):\n"
            + ins
        )
    if previous_draft and "{previous_draft}" not in str(template):
        user_text += "\n\nCurrent draft:\n" + previous_draft
    if ins != NO_INSTRUCTIONS:
        user_text = (
            user_text.rstrip()
            + "\n\nImportant: Follow the freelancer's instructions closely. "
            "They override the template style when they conflict."
        )
    system = str(c.get("proposal_system_prompt") or "")
    if ins != NO_INSTRUCTIONS:
        system = (
            system.rstrip()
            + " The freelancer's instructions are mandatory for this draft. "
            "Follow them closely; if they conflict with general style rules "
            "or the template, prefer the instructions."
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]


def _error_detail(http_err):
    """Read the error body of an HTTPError without ever exposing the key."""
    try:
        body = http_err.read().decode("utf-8", "replace")
    except Exception:
        return "", ""
    code, msg = "", ""
    try:
        err = json.loads(body).get("error") or {}
        # Both fields: OpenAI may put 'insufficient_quota' in either one.
        code = " ".join(str(x) for x in (err.get("code"), err.get("type")) if x)
        msg = str(err.get("message") or "")
    except Exception:
        msg = body
    return code, msg


def _resolve_key(cfg, api_key=None):
    key = api_key
    if not key:
        try:
            import settings_store
            key = settings_store.get_api_key(cfg)
        except Exception:
            key = None
    if not key or not str(key).strip():
        raise NoKeyError()
    return str(key).strip()


def _complete_chat(messages, cfg=None, api_key=None, max_tokens=None,
                   temperature=None):
    """POST chat/completions. Returns plain text. Raises AIError subclasses."""
    c = _load_cfg(cfg)
    key = _resolve_key(c, api_key)
    payload = {
        "model": str(c.get("openai_model")),
        "messages": messages,
        "temperature": _num(
            temperature if temperature is not None else c.get("temperature"),
            float, 0.7,
        ),
        "max_tokens": _num(
            max_tokens if max_tokens is not None else c.get("max_tokens"),
            int, 900,
        ),
    }
    url = str(c.get("openai_base_url")).rstrip("/") + "/chat/completions"
    timeout = _num(c.get("request_timeout"), float, 60.0)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key},
        method="POST",
    )

    # Errors are raised "from None" so no traceback chain carries the request
    # (and its Authorization header) along with the exception.
    err = None
    raw = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        code, msg = _error_detail(e)
        if status in (401, 403):
            err = AuthError()
        elif status == 429:
            if "insufficient_quota" in code.lower() or "insufficient_quota" in msg.lower():
                err = NoCreditsError()
            else:
                err = RateLimitError()
        elif 500 <= status < 600:
            err = AIError("OpenAI is having problems. Try again in a minute.")
        elif status == 404:
            err = AIError("OpenAI could not find the model or address in settings. "
                          "Check the model name on the Settings page.")
        else:
            err = AIError("OpenAI could not handle the request (error %d). "
                          "Try again or check the settings." % status)
    except (socket.timeout, TimeoutError):
        err = AITimeoutError()
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            err = AITimeoutError()
        else:
            err = OfflineError()
    except (ConnectionError, OSError):
        err = OfflineError()
    finally:
        del req
    if err is not None:
        key = None
        raise err from None
    key = None

    try:
        data = json.loads(raw.decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
    except Exception:
        raise AIError("OpenAI sent back an answer LeadPilot could not read. "
                      "Try again.") from None
    if not isinstance(content, str) or not content.strip():
        raise AIError("OpenAI sent back an empty draft. Try again.")
    return _clean_dashes(content.strip())


def generate_proposal(job_post, instructions="", previous_draft=None,
                      cfg=None, api_key=None, template_text=None):
    """Return a proposal draft (str). Raises AIError subclasses on failure.
    Draft only: nothing is sent anywhere except the OpenAI API request."""
    if not job_post or not str(job_post).strip():
        raise AIError("There is no job post text. Import or paste a job post first.")
    c = _load_cfg(cfg)
    messages = build_messages(job_post, instructions, previous_draft, c,
                              template_text=template_text)
    return _complete_chat(messages, cfg=c, api_key=api_key)


FOLLOWUP_SYSTEM = (
    "You write short Upwork chat follow-up messages for Ammar Yasir, a "
    "freelancer, in first person. Use plain, simple English and short "
    "sentences. Never use em dashes or en dashes. Do not invent facts, "
    "dates, prices or promises that are not in the last message or notes. "
    "Return only the message text, ready to paste into Upwork. Keep it "
    "under about 80 words unless the notes clearly ask for more."
)


def generate_followup_message(last_message="", notes="", lead_name="",
                              company="", job="", cfg=None, api_key=None):
    """Return a short follow-up chat message from last message + notes.

    Draft only: never sends anything to Upwork. Raises AIError subclasses.
    """
    last_message = (last_message or "").strip()
    notes = (notes or "").strip()
    if not last_message and not notes:
        raise AIError(
            "Add a last message or notes for this lead first, then Generate message."
        )
    who = (lead_name or "").replace("[SAMPLE] ", "").strip()
    company = (company or "").strip()
    job = (job or "").strip()
    parts = []
    if who:
        parts.append("Lead name: " + who)
    if company:
        parts.append("Company: " + company)
    if job:
        parts.append("Job: " + job)
    parts.append(
        "Last message (chat preview):\n"
        + (last_message or "(none captured yet)")
    )
    parts.append("Notes:\n" + (notes or "(no notes)"))
    parts.append(
        "Write one short follow-up message Ammar can paste into Upwork chat now."
    )
    messages = [
        {"role": "system", "content": FOLLOWUP_SYSTEM},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
    return _complete_chat(
        messages, cfg=cfg, api_key=api_key, max_tokens=220, temperature=0.5,
    )
