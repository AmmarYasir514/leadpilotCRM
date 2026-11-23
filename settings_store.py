"""LeadPilot CRM settings store.

Non-secret settings live in an external JSON file in the LeadPilotCRM data
folder (leadpilot_config.json). The OpenAI API key lives only in the system
key store (Windows Credential Manager through the keyring package). The key is
never written to the config file, a log, the database or the code, and it is
never included in any message or exception text from this module.

The data folder is Path.home()/"LeadPilotCRM", or the folder named in the
LEADPILOT_DATA_DIR environment variable when that is set (used by tests).
"""

import copy
import json
import os
import re
import socket
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

__all__ = [
    "DATA_DIR", "CONFIG_PATH", "DEFAULTS",
    "SettingsError", "KeyringUnavailable",
    "load_config", "save_config", "get", "MAX_TEMPLATES",
    "SLOTS_MIN", "SLOTS_MAX", "get_max_templates", "parse_template_slots",
    "set_template_slots", "get_templates", "get_template", "save_templates",
    "set_last_template", "get_last_template",
    "keyring_available", "get_api_key", "set_api_key", "remove_api_key",
    "has_api_key", "masked_hint", "test_api_key", "redact",
]

# ---------------------------------------------------------------- paths
_env_dir = os.environ.get("LEADPILOT_DATA_DIR", "").strip()
DATA_DIR = Path(_env_dir) if _env_dir else Path.home() / "LeadPilotCRM"
CONFIG_PATH = DATA_DIR / "leadpilot_config.json"

# ---------------------------------------------------------------- defaults
# Non-secret values only. Never put a key, token or password in here.
DEFAULTS = {
    "openai_base_url": "https://api.openai.com/v1",
    "openai_model": "gpt-4o-mini",
    "transcription_model": "whisper-1",
    "temperature": 0.7,
    "max_tokens": 900,
    "max_job_post_chars": 12000,
    "request_timeout": 60,
    "keyring_service": "LeadPilotCRM-OpenAI",
    "keyring_username": "openai_api_key",
    "proposal_system_prompt": (
        "You are an expert Upwork proposal writer. You write cover letters for "
        "Ammar Yasir, a freelancer, in his own voice (first person). "
        "Rules: use plain, simple English and short sentences. Never use em "
        "dashes or en dashes; use commas, full stops or the word 'and' instead. "
        "Never invent facts, past clients, numbers, results, tools or "
        "experience that are not in the job post or the instructions. If a "
        "detail is unknown, leave it out or ask about it. Open with the "
        "client's problem, not with a greeting about yourself. Show how Ammar "
        "would approach the work in a few clear steps. Keep it concise, about "
        "120 to 200 words unless the instructions say otherwise. The "
        "freelancer's instructions are mandatory: follow them closely, and "
        "if they conflict with these style rules or the template, prefer the "
        "instructions. End with a short question or a clear call to action. "
        "Return only the proposal text, with no title and no notes."
    ),
    "proposal_user_template": (
        "Write an Upwork proposal for this job post.\n\n"
        "JOB POST:\n{job_post}\n\n"
        "INSTRUCTIONS FROM AMMAR (follow these closely):\n{instructions}\n\n"
        "PREVIOUS DRAFT (if any, use it as a starting point):\n{previous_draft}\n"
    ),
    "revision_template": (
        "Revise the proposal below for the same job post. Apply the new "
        "instructions and keep everything else that still fits. Follow all "
        "the writing rules.\n\n"
        "JOB POST:\n{job_post}\n\n"
        "CURRENT DRAFT:\n{previous_draft}\n\n"
        "NEW INSTRUCTIONS FROM AMMAR:\n{instructions}\n"
    ),
    "record_max_seconds": 120,
    "sample_rate": 16000,
    "channels": 1,
}

# Proposal templates (P6). Each template is {"name": str, "text": str} and
# uses the same placeholders as proposal_user_template.
# The number of template slots is a setting (template_slots, 1 to 10, default 3).
MAX_TEMPLATES = 3          # default number of slots
SLOTS_MIN, SLOTS_MAX = 1, 10
SLOTS_MESSAGE = "Number of templates must be a whole number from %d to %d." % (SLOTS_MIN, SLOTS_MAX)
DEFAULT_TEMPLATE_NAME = "Template 1"
DEFAULTS["template_slots"] = MAX_TEMPLATES
DEFAULTS["proposal_templates"] = [
    {"name": DEFAULT_TEMPLATE_NAME, "text": DEFAULTS["proposal_user_template"]}]
DEFAULTS["last_template"] = DEFAULT_TEMPLATE_NAME
_TEMPLATE_KEYS = ("proposal_templates", "last_template")

# Field names that must never be stored in the config file.
_SECRET_NAME_RE = re.compile(
    r"(api[_\- ]?key|apikey|secret|password|passwd|access[_\- ]?token|"
    r"auth[_\- ]?token|bearer|credential)", re.IGNORECASE)
# Values that look like an OpenAI style key.
_SECRET_VALUE_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}")


# ---------------------------------------------------------------- errors
class SettingsError(Exception):
    """An error with a short, user friendly message (safe to show in the UI)."""

    def __init__(self, message="Something went wrong with the settings."):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message


class KeyringUnavailable(SettingsError):
    """The secure key store (keyring / Windows Credential Manager) is not usable."""

    def __init__(self, message=(
            "Secure key storage is not available on this computer. "
            "Install the keyring package (pip install keyring) and restart LeadPilot.")):
        super().__init__(message)


# ---------------------------------------------------------------- helpers
def redact(text, key=None):
    """Return text with any key-like value (and the given key) replaced by '***'."""
    if text is None:
        return ""
    text = str(text)
    if key:
        text = text.replace(key, "***")
    return _SECRET_VALUE_RE.sub("***", text)


def _is_secret_field(name, value):
    if isinstance(name, str) and _SECRET_NAME_RE.search(name):
        return True
    if isinstance(value, str) and _SECRET_VALUE_RE.search(value):
        return True
    return False


def _strip_secrets(obj):
    """Return a copy of obj without any key-like fields or values."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _is_secret_field(k, v):
                continue
            out[k] = _strip_secrets(v)
        return out
    if isinstance(obj, list):
        return [_strip_secrets(v) for v in obj
                if not (isinstance(v, str) and _SECRET_VALUE_RE.search(v))]
    return obj


def _coerce(name, value):
    """Keep a file value only if it has a sensible type for that default."""
    default = DEFAULTS.get(name)
    if default is None:
        return value
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, int):
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return default
    if isinstance(default, float):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return default
    if isinstance(default, str):
        return value if isinstance(value, str) and value.strip() else default
    return value


def _config_path():
    # Read the module value at call time so callers and tests can point it elsewhere.
    return Path(CONFIG_PATH)


def _write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _keep_broken_copy(path):
    """Keep a copy of a broken config file as <name>.broken (once per content)."""
    try:
        raw = Path(path).read_bytes()
        broken = Path(str(path) + ".broken")
        if not broken.exists() or broken.read_bytes() != raw:
            broken.write_bytes(raw)
    except OSError:
        pass


# ---------------------------------------------------------------- config
def load_config():
    """Return DEFAULTS merged with the config file.

    Creates the file with DEFAULTS on first run. A missing, unreadable or
    broken file never crashes the app: defaults are returned, and a broken
    file is left in place (a copy is kept as leadpilot_config.json.broken).
    Secret-looking fields in the file are ignored.

    If a valid file has no valid proposal_templates, slot 1 ("Template 1") is
    built from the file's proposal_user_template (or the default) and saved
    once. proposal_user_template stays in the file for older code.
    """
    cfg = copy.deepcopy(DEFAULTS)
    path = _config_path()
    if not path.exists():
        try:
            _write_json_atomic(path, _strip_secrets(DEFAULTS))
        except OSError:
            pass
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        _keep_broken_copy(path)
        return cfg
    if not isinstance(data, dict):
        _keep_broken_copy(path)
        return cfg
    data = _strip_secrets(data)
    for k, v in data.items():
        if k in _TEMPLATE_KEYS:
            continue
        cfg[k] = _coerce(k, v)

    templates = _clean_templates(data.get("proposal_templates"))
    if templates:
        cfg["proposal_templates"] = templates
        cfg["last_template"] = _valid_last(data.get("last_template"), templates)
    else:
        # One-time migration from the single proposal_user_template.
        cfg["proposal_templates"] = [
            {"name": DEFAULT_TEMPLATE_NAME, "text": cfg["proposal_user_template"]}]
        cfg["last_template"] = DEFAULT_TEMPLATE_NAME
        migrated = dict(data)
        migrated["proposal_templates"] = copy.deepcopy(cfg["proposal_templates"])
        migrated["last_template"] = DEFAULT_TEMPLATE_NAME
        try:
            _write_json_atomic(path, migrated)
        except OSError:
            pass
    return cfg


def save_config(cfg):
    """Write cfg to the config file atomically, without any secrets."""
    if not isinstance(cfg, dict):
        raise SettingsError("Settings must be a set of names and values.")
    clean = _strip_secrets(cfg)
    try:
        _write_json_atomic(_config_path(), clean)
    except (OSError, TypeError, ValueError):
        raise SettingsError("Could not save the settings file. Check that the "
                            "LeadPilotCRM folder can be written to.") from None
    return clean


def get(key, default=None):
    """Return one setting (file value, else the built-in default, else default)."""
    cfg = load_config()
    if key in cfg:
        return cfg[key]
    return DEFAULTS.get(key, default)


# ---------------------------------------------------------------- templates
def _clean_templates(value):
    """Lenient read: keep valid entries (trimmed, unique names), at most SLOTS_MAX."""
    out, seen = [], set()
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        name, text = item.get("name"), item.get("text")
        if not isinstance(name, str) or not isinstance(text, str):
            continue
        name = name.strip()
        if not name or not text.strip() or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "text": text})
        if len(out) >= SLOTS_MAX:
            break
    return out


def _valid_last(name, templates):
    if isinstance(name, str):
        for t in templates:
            if t["name"] == name.strip():
                return t["name"]
        for t in templates:
            if t["name"].lower() == name.strip().lower():
                return t["name"]
    return templates[0]["name"] if templates else DEFAULT_TEMPLATE_NAME


def get_max_templates(cfg=None):
    """Number of template slots: template_slots from the config, 1 to 10, else 3."""
    cfg = cfg if isinstance(cfg, dict) else load_config()
    n = cfg.get("template_slots")
    if not isinstance(n, int) or isinstance(n, bool):
        return MAX_TEMPLATES
    return max(SLOTS_MIN, min(SLOTS_MAX, n))


def parse_template_slots(value):
    """Strict check of a typed number of slots. Returns an int or raises SettingsError."""
    if isinstance(value, bool):
        raise SettingsError(SLOTS_MESSAGE)
    if isinstance(value, str):
        value = value.strip()
        if not re.fullmatch(r"[0-9]{1,3}", value):
            raise SettingsError(SLOTS_MESSAGE)
        value = int(value)
    if not isinstance(value, int) or not SLOTS_MIN <= value <= SLOTS_MAX:
        raise SettingsError(SLOTS_MESSAGE)
    return value


def set_template_slots(value, cfg=None):
    """Save the number of template slots. Lowering it deletes the templates
    after the new last slot (the app asks the user first). Returns the number."""
    n = parse_template_slots(value)
    base = cfg if isinstance(cfg, dict) else load_config()
    new = copy.deepcopy(base)
    new["template_slots"] = n
    stored = _clean_templates(base.get("proposal_templates"))
    if len(stored) > n:
        new["proposal_templates"] = stored[:n]
        new["last_template"] = _valid_last(base.get("last_template"), stored[:n])
    save_config(new)
    if isinstance(cfg, dict):
        cfg.update(copy.deepcopy(new))
    return n


def _validate_templates(templates, limit=None):
    """Strict check for saving. Returns a clean list or raises SettingsError."""
    limit = MAX_TEMPLATES if limit is None else limit
    if not isinstance(templates, (list, tuple)):
        raise SettingsError("Templates must be a list.")
    if len(templates) < 1:
        raise SettingsError("Keep at least one template.")
    if len(templates) > limit:
        raise SettingsError("You can save up to %d templates." % limit)
    out, seen = [], set()
    for i, item in enumerate(templates, 1):
        if not isinstance(item, dict):
            raise SettingsError("Template %d is not valid." % i)
        name = item.get("name")
        text = item.get("text")
        name = name.strip() if isinstance(name, str) else ""
        text = text.strip() if isinstance(text, str) else ""
        if not name:
            raise SettingsError("Each template needs a name.")
        if len(name) > 60:
            raise SettingsError("Template names can be up to 60 characters.")
        if not text:
            raise SettingsError('The template "%s" has no text.' % name)
        if _SECRET_VALUE_RE.search(text) or _SECRET_VALUE_RE.search(name):
            raise SettingsError('The template "%s" seems to contain an API key. '
                                "Please remove it." % name)
        if name.lower() in seen:
            raise SettingsError('Two templates have the same name: "%s". '
                                "Please use different names." % name)
        seen.add(name.lower())
        out.append({"name": name, "text": text})
    return out


def _cfg_templates(cfg):
    templates = _clean_templates(cfg.get("proposal_templates"))
    if not templates:
        text = cfg.get("proposal_user_template")
        if not isinstance(text, str) or not text.strip():
            text = DEFAULTS["proposal_user_template"]
        templates = [{"name": DEFAULT_TEMPLATE_NAME, "text": text}]
    return templates


def get_templates(cfg=None):
    """Return the templates in the first N slots (copies), always at least one."""
    cfg = cfg if isinstance(cfg, dict) else load_config()
    return copy.deepcopy(_cfg_templates(cfg)[:get_max_templates(cfg)])


def get_template(name, cfg=None):
    """Return a copy of the template with this name, or None."""
    if not isinstance(name, str) or not name.strip():
        return None
    templates = get_templates(cfg)
    want = name.strip()
    for t in templates:
        if t["name"] == want:
            return t
    for t in templates:
        if t["name"].lower() == want.lower():
            return t
    return None


def save_templates(templates, cfg=None):
    """Check and save the templates (1 to N slots, unique names).

    Entries already in the file after slot N (an older file with more
    templates than slots) are kept as they are, never dropped here.
    Keeps last_template if it still exists, otherwise uses the first one.
    Updates cfg in place when given. Returns the saved list (copies).
    Raises SettingsError with a plain message on problems.
    """
    base = cfg if isinstance(cfg, dict) else load_config()
    limit = get_max_templates(base)
    clean = _validate_templates(templates, limit)
    extra = _clean_templates(base.get("proposal_templates"))[limit:]
    names = {t["name"].lower() for t in clean}
    for t in extra:
        if t["name"].lower() in names:
            raise SettingsError('A template after slot %d already uses the name "%s". '
                                "Please use a different name." % (limit, t["name"]))
    new = copy.deepcopy(base)
    new["proposal_templates"] = clean + extra
    new["last_template"] = _valid_last(base.get("last_template"), clean)
    save_config(new)
    if isinstance(cfg, dict):
        cfg["proposal_templates"] = copy.deepcopy(clean + extra)
        cfg["last_template"] = new["last_template"]
    return copy.deepcopy(clean)


def set_last_template(name, cfg=None):
    """Remember the template used last. Raises SettingsError if it does not exist."""
    base = cfg if isinstance(cfg, dict) else load_config()
    t = get_template(name, base)
    if t is None:
        raise SettingsError("There is no template with that name.")
    new = copy.deepcopy(base)
    new["proposal_templates"] = _cfg_templates(base)
    new["last_template"] = t["name"]
    save_config(new)
    if isinstance(cfg, dict):
        cfg["last_template"] = t["name"]
    return t["name"]


def get_last_template(cfg=None):
    """Return a copy of the last used template, or the first one."""
    cfg = cfg if isinstance(cfg, dict) else load_config()
    templates = _cfg_templates(cfg)[:get_max_templates(cfg)]
    name = _valid_last(cfg.get("last_template"), templates)
    for t in templates:
        if t["name"] == name:
            return copy.deepcopy(t)
    return copy.deepcopy(templates[0])


# ---------------------------------------------------------------- keyring
def _load_keyring():
    """Lazy import of keyring. Returns the module or raises KeyringUnavailable."""
    try:
        import keyring  # noqa: WPS433 (lazy on purpose)
    except Exception:
        raise KeyringUnavailable() from None
    return keyring


def _backend_ok(kr):
    try:
        backend = kr.get_keyring()
    except Exception:
        return False
    name = type(backend).__module__ + "." + type(backend).__name__
    if "keyring.backends.fail" in name or "null" in name.lower():
        return False
    try:
        return float(getattr(backend, "priority", 1)) > 0
    except Exception:
        return True


def keyring_available():
    """True when the keyring package is installed and has a working backend."""
    try:
        kr = _load_keyring()
    except KeyringUnavailable:
        return False
    return _backend_ok(kr)


def _names(cfg):
    cfg = cfg if isinstance(cfg, dict) else load_config()
    service = cfg.get("keyring_service") or DEFAULTS["keyring_service"]
    user = cfg.get("keyring_username") or DEFAULTS["keyring_username"]
    return service, user


def _kr_or_raise():
    kr = _load_keyring()
    if not _backend_ok(kr):
        raise KeyringUnavailable()
    return kr


def get_api_key(cfg=None):
    """Return the saved key, or None if no key is saved.

    Raises KeyringUnavailable if secure storage cannot be used.
    """
    kr = _kr_or_raise()
    service, user = _names(cfg)
    try:
        key = kr.get_password(service, user)
    except Exception:
        raise SettingsError("Could not read the API key from secure storage.") from None
    key = (key or "").strip()
    return key or None


def _validate_key(key):
    if not isinstance(key, str):
        raise SettingsError("Please paste your OpenAI API key.")
    key = key.strip()
    if not key:
        raise SettingsError("Please paste your OpenAI API key.")
    if any(c.isspace() for c in key):
        raise SettingsError("The key should not contain spaces or line breaks. "
                            "Please paste it again.")
    if len(key) < 20:
        raise SettingsError("This key looks too short. Please paste the full key.")
    if not all(33 <= ord(c) < 127 for c in key):
        raise SettingsError("The key contains characters that are not allowed. "
                            "Please paste it again.")
    return key


def set_api_key(key, cfg=None):
    """Check and save the key in secure storage. Raises SettingsError on problems."""
    key = _validate_key(key)
    kr = _kr_or_raise()
    service, user = _names(cfg)
    try:
        kr.set_password(service, user, key)
    except Exception:
        raise SettingsError("Could not save the API key in secure storage.") from None
    return True


def remove_api_key(cfg=None):
    """Remove the saved key. No error if there is no key."""
    kr = _kr_or_raise()
    service, user = _names(cfg)
    try:
        if kr.get_password(service, user) is None:
            return False
        kr.delete_password(service, user)
        return True
    except Exception as exc:
        errors = getattr(kr, "errors", None)
        pde = getattr(errors, "PasswordDeleteError", None) if errors else None
        if pde is not None and isinstance(exc, pde):
            return False
        raise SettingsError("Could not remove the API key from secure storage.") from None


def has_api_key(cfg=None):
    """True if a key is saved. Never raises."""
    try:
        return bool(get_api_key(cfg))
    except SettingsError:
        return False


def masked_hint(key=None, cfg=None):
    """Return a safe hint such as 'sk-...ab12', or 'No key saved'."""
    if key is None:
        try:
            key = get_api_key(cfg)
        except KeyringUnavailable:
            return "Secure storage not available"
        except SettingsError:
            return "No key saved"
    key = (key or "").strip()
    if not key:
        return "No key saved"
    if len(key) < 12:
        return "..." + key[-2:]
    return key[:3] + "..." + key[-4:]


# ---------------------------------------------------------------- key test
def test_api_key(key=None, cfg=None):
    """Check the key against OpenAI (GET {base_url}/models).

    Returns (ok, message). The message is plain English, safe to show, and
    never contains the key. Never raises.
    """
    cfg = cfg if isinstance(cfg, dict) else load_config()
    if key is None:
        try:
            key = get_api_key(cfg)
        except SettingsError as exc:
            return False, exc.message
        if not key:
            return False, "No API key saved. Paste your key in Settings first."
    else:
        try:
            key = _validate_key(key)
        except SettingsError as exc:
            return False, exc.message

    base = str(cfg.get("openai_base_url") or DEFAULTS["openai_base_url"]).rstrip("/")
    try:
        timeout = float(cfg.get("request_timeout") or DEFAULTS["request_timeout"])
    except (TypeError, ValueError):
        timeout = float(DEFAULTS["request_timeout"])
    try:
        req = urllib.request.Request(
            base + "/models",
            headers={"Authorization": "Bearer " + key, "User-Agent": "LeadPilotCRM"},
            method="GET")
    except ValueError:
        return False, "The OpenAI address in the settings file is not valid."

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        try:
            code = getattr(resp, "status", None) or resp.getcode()
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except urllib.error.HTTPError as exc:
        code = exc.code
        try:
            exc.close()
        except Exception:
            pass
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError):
        return False, "Could not reach OpenAI. Check your internet connection."
    except OSError:
        return False, "Could not reach OpenAI. Check your internet connection."
    except Exception:
        return False, "The key test did not finish. Please try again."

    if code == 200:
        return True, "Key works."
    if code in (401, 403):
        return False, "OpenAI rejected this key."
    if code == 429:
        return False, ("OpenAI says the rate limit or quota was reached. "
                       "Check your plan and billing, then try again.")
    if isinstance(code, int) and code >= 500:
        return False, "OpenAI is having problems right now. Please try again later."
    return False, "OpenAI returned an unexpected answer (code %s). Please try again." % code
