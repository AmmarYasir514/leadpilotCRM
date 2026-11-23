"""Voice input for LeadPilot CRM.

Records a short spoken instruction from the microphone and turns it into
text with OpenAI transcription. Used by the "Write a proposal" flow.

Public interface (called by the UI):
    is_available() -> (bool, message)
    Recorder(cfg=None): start(), stop() -> wav path, cancel(),
                        is_recording, auto_stopped, elapsed()
    transcribe(wav_path, cfg=None, api_key=None, delete_after=True) -> str
    VoiceError and its subclasses, each with .user_message

Notes:
    - sounddevice (and optionally numpy) are imported lazily, so this
      module always imports cleanly even when they are not installed.
      If numpy is missing or blocked, recording uses sd.RawInputStream.
    - The API key is never logged, printed, or put in any error text.
    - transcribe() does network I/O; call it from a background thread.
"""

import io
import json
import os
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave

__all__ = [
    "VoiceError", "MicUnavailable", "NoKeyError", "AuthError",
    "OfflineError", "RateLimitError", "NoCreditsError", "TranscribeError",
    "is_available", "Recorder", "transcribe", "delete_file",
]

MIC_UNAVAILABLE_MSG = ("Voice input is not available on this computer. "
                       "Type your instructions instead.")
NO_KEY_MSG = ("No OpenAI API key is saved. Add your key on the Settings "
              "screen, or type your instructions instead.")
AUTH_MSG = ("OpenAI did not accept the saved API key. Check the key on the "
            "Settings screen.")
AUDIO_SCOPE_MSG = (
    "Your OpenAI API key works for writing proposals, but it is not allowed "
    "to use voice (Whisper). On platform.openai.com/api-keys, edit this "
    "project key and turn on Audio permissions (or create a new key with "
    "All permissions), then paste it on the Settings screen."
)
OFFLINE_MSG = ("Could not reach OpenAI. Check your internet connection and "
               "try again.")
RATE_MSG = ("OpenAI says there are too many requests or your credit has run "
            "out. Wait a minute and try again, or check your OpenAI billing.")
TIMEOUT_MSG = ("OpenAI took too long to answer. Try again, or type your "
               "instructions instead.")
NO_CREDITS_MSG = ("Your OpenAI account has no credits left. Add credits in "
                  "OpenAI Billing (platform.openai.com), then try again.")
EMPTY_MSG = "I could not hear anything. Try again or type your instructions."
NOTHING_RECORDED_MSG = ("No sound was recorded. Check your microphone and "
                        "try again, or type your instructions instead.")
GENERIC_MSG = ("Something went wrong while turning your voice into text. "
               "Try again, or type your instructions instead.")

_DEFAULTS = {
    "openai_base_url": "https://api.openai.com/v1",
    "transcription_model": "whisper-1",
    "request_timeout": 60,
    "record_max_seconds": 120,
    "sample_rate": 16000,
    "channels": 1,
}


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class VoiceError(Exception):
    """Base error. user_message is plain English, safe to show in the UI."""

    default_message = GENERIC_MSG

    def __init__(self, user_message=None):
        self.user_message = user_message or self.default_message
        super().__init__(self.user_message)


class MicUnavailable(VoiceError):
    default_message = MIC_UNAVAILABLE_MSG


class NoKeyError(VoiceError):
    default_message = NO_KEY_MSG


class AuthError(VoiceError):
    default_message = AUTH_MSG


class OfflineError(VoiceError):
    default_message = OFFLINE_MSG


class RateLimitError(VoiceError):
    default_message = RATE_MSG


class NoCreditsError(RateLimitError):
    """HTTP 429 with error code or type 'insufficient_quota'. A RateLimitError
    subclass, so code that catches RateLimitError still works."""
    default_message = NO_CREDITS_MSG


def _read_http_error(http_err):
    """Return (code, type, message) from an HTTPError body. Never raises.
    Body is read once; fields are plain text for matching only, never logged."""
    code = typ = msg = ""
    try:
        raw = http_err.read(65536)
    except Exception:
        return code, typ, msg
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            code = str(err.get("code") or "").strip().lower()
            typ = str(err.get("type") or "").strip().lower()
            msg = str(err.get("message") or "").strip().lower()
    except Exception:
        pass
    return code, typ, msg


def _is_no_credits(http_err):
    """True if an HTTPError body says insufficient_quota. Never raises."""
    code, typ, _msg = _read_http_error(http_err)
    return code == "insufficient_quota" or typ == "insufficient_quota"


def _auth_user_message(http_err):
    """Pick a clear AuthError message from a 401/403 body. Never raises."""
    code, typ, msg = _read_http_error(http_err)
    blob = " ".join((code, typ, msg))
    if (
        "missing_scope" in blob
        or "api.model.audio" in blob
        or ("audio" in blob and "permission" in blob)
        or ("insufficient permissions" in blob and "audio" in blob)
    ):
        return AUDIO_SCOPE_MSG
    return AUTH_MSG


class TranscribeError(VoiceError):
    default_message = GENERIC_MSG


# --------------------------------------------------------------------------
# Config helpers
# --------------------------------------------------------------------------
def _load_cfg(cfg=None):
    """Return a config dict with defaults filled in. Never raises."""
    data = {}
    if cfg is None:
        try:
            import settings_store
            data = dict(settings_store.load_config() or {})
        except Exception:
            data = {}
    else:
        data = dict(cfg)
    out = dict(_DEFAULTS)
    for k, v in data.items():
        if v is not None and v != "":
            out[k] = v
    return out


def _num(value, default, cast):
    try:
        n = cast(value)
        return n if n > 0 else default
    except (TypeError, ValueError):
        return default


def _get_key(cfg, api_key):
    if api_key:
        return api_key
    try:
        import settings_store
        return settings_store.get_api_key(cfg)
    except Exception:
        return None


def delete_file(path):
    """Delete a file if it exists. Never raises."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------
def _import_audio():
    """Import sounddevice. Raises MicUnavailable if it cannot load.

    numpy is optional: if it loads, sd.InputStream is used; if it is missing
    or blocked, sd.RawInputStream is used instead (plain int16 bytes).
    Returns (sd, use_numpy).
    """
    try:
        import sounddevice as sd
    except Exception:
        raise MicUnavailable() from None
    try:
        import numpy  # noqa: F401
        use_numpy = hasattr(sd, "InputStream")
    except Exception:
        use_numpy = False
    if not use_numpy and not hasattr(sd, "RawInputStream"):
        raise MicUnavailable()
    return sd, use_numpy


def _has_input_device(sd):
    devices = sd.query_devices()
    try:
        items = list(devices)
    except TypeError:
        items = [devices]
    for dev in items:
        try:
            if int(dev.get("max_input_channels", 0) or 0) > 0:
                return True
        except Exception:
            continue
    return False


def is_available():
    """Return (True, message) if a microphone can be used, else (False, message).

    Read-only: lists devices, never records. Never raises.
    """
    try:
        sd, _ = _import_audio()
        if not _has_input_device(sd):
            return False, MIC_UNAVAILABLE_MSG
        return True, "Voice input is ready."
    except Exception:
        return False, MIC_UNAVAILABLE_MSG


# --------------------------------------------------------------------------
# Recorder
# --------------------------------------------------------------------------
class Recorder:
    """Non-blocking microphone recorder.

    start() opens an input stream; audio arrives on a sounddevice thread and
    is kept in memory. Recording stops taking audio at record_max_seconds
    (auto_stopped becomes True, is_recording becomes False). The UI should
    then call stop() to get the WAV path, or cancel() to throw it away.
    """

    def __init__(self, cfg=None):
        c = _load_cfg(cfg)
        self.sample_rate = _num(c.get("sample_rate"), 16000, int)
        self.channels = _num(c.get("channels"), 1, int)
        self.max_seconds = _num(c.get("record_max_seconds"), 120, float)
        self._max_frames = int(self.max_seconds * self.sample_rate)
        self._frame_bytes = 2 * self.channels  # int16
        self._lock = threading.Lock()
        self._chunks = []
        self._frames = 0
        self._stream = None
        self._recording = False
        self._auto_stopped = False
        self._started_at = None
        self._stopped_at = None

    # ----- state -----
    @property
    def is_recording(self):
        with self._lock:
            return self._recording and not self._auto_stopped

    @property
    def auto_stopped(self):
        with self._lock:
            return self._auto_stopped

    def elapsed(self):
        """Seconds recorded so far (capped at record_max_seconds)."""
        with self._lock:
            if self._started_at is None:
                return 0.0
            end = self._stopped_at if self._stopped_at is not None else time.monotonic()
            return min(max(0.0, end - self._started_at), self.max_seconds)

    # ----- audio thread -----
    def _callback(self, indata, frames, time_info, status):
        # Runs on the sounddevice audio thread. Keep it short.
        with self._lock:
            if not self._recording or self._auto_stopped:
                return
            room = self._max_frames - self._frames
            if room <= 0:
                self._auto_stopped = True
                self._stopped_at = time.monotonic()
                return
            try:
                data = indata.tobytes() if hasattr(indata, "tobytes") else bytes(indata)
            except Exception:
                return
            n = int(frames)
            if n > room:
                data = data[:room * self._frame_bytes]
                n = room
            self._chunks.append(data)
            self._frames += n
            if self._frames >= self._max_frames:
                self._auto_stopped = True
                self._stopped_at = time.monotonic()

    # ----- controls -----
    def start(self):
        """Begin recording. Raises MicUnavailable if the mic cannot be opened."""
        with self._lock:
            if self._recording:
                return
        sd, use_numpy = _import_audio()
        with self._lock:
            self._chunks = []
            self._frames = 0
            self._auto_stopped = False
            self._stopped_at = None
        try:
            stream_cls = sd.InputStream if use_numpy else sd.RawInputStream
            stream = stream_cls(samplerate=self.sample_rate,
                                    channels=self.channels,
                                    dtype="int16",
                                    callback=self._callback)
            with self._lock:
                self._recording = True
                self._started_at = time.monotonic()
            stream.start()
        except Exception:
            with self._lock:
                self._recording = False
                self._started_at = None
            raise MicUnavailable() from None
        with self._lock:
            self._stream = stream

    def _close_stream(self):
        with self._lock:
            stream, self._stream = self._stream, None
            self._recording = False
            if self._started_at is not None and self._stopped_at is None:
                self._stopped_at = time.monotonic()
        if stream is not None:
            for fn in ("stop", "close"):
                try:
                    getattr(stream, fn)()
                except Exception:
                    pass

    def stop(self):
        """Stop and save to a temp WAV file. Returns its path.

        Raises VoiceError if nothing was recorded. The caller (or
        transcribe with delete_after=True) is responsible for the file.
        """
        self._close_stream()
        with self._lock:
            chunks, self._chunks = self._chunks, []
            frames = self._frames
        if not chunks or frames <= 0:
            raise VoiceError(NOTHING_RECORDED_MSG)
        fd, path = tempfile.mkstemp(prefix="leadpilot_voice_", suffix=".wav")
        os.close(fd)
        try:
            with wave.open(path, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # int16
                wf.setframerate(self.sample_rate)
                wf.writeframes(b"".join(chunks))
        except Exception:
            delete_file(path)
            raise VoiceError(GENERIC_MSG) from None
        return path

    def cancel(self):
        """Stop and throw away anything recorded. Never raises."""
        try:
            self._close_stream()
        finally:
            with self._lock:
                self._chunks = []
                self._frames = 0


# --------------------------------------------------------------------------
# Transcription
# --------------------------------------------------------------------------
def _multipart(fields, file_field, filename, file_bytes, content_type):
    boundary = "----LeadPilot" + uuid.uuid4().hex
    buf = io.BytesIO()
    for name, value in fields.items():
        buf.write(("--%s\r\n" % boundary).encode())
        buf.write(('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode())
        buf.write(str(value).encode("utf-8"))
        buf.write(b"\r\n")
    buf.write(("--%s\r\n" % boundary).encode())
    buf.write(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
               % (file_field, filename)).encode())
    buf.write(("Content-Type: %s\r\n\r\n" % content_type).encode())
    buf.write(file_bytes)
    buf.write(b"\r\n")
    buf.write(("--%s--\r\n" % boundary).encode())
    return buf.getvalue(), "multipart/form-data; boundary=%s" % boundary


def _is_timeout(exc):
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, (socket.timeout, TimeoutError))


def transcribe(wav_path, cfg=None, api_key=None, delete_after=True):
    """Send a WAV file to OpenAI transcription and return the text.

    Blocking network call: run it in a background thread.
    Raises NoKeyError, AuthError, OfflineError, RateLimitError or
    TranscribeError. Deletes wav_path afterwards when delete_after is True,
    whatever happens.
    """
    try:
        c = _load_cfg(cfg)
        key = _get_key(c, api_key)
        if not key or not str(key).strip():
            raise NoKeyError()
        key = str(key).strip()

        try:
            with open(wav_path, "rb") as f:
                audio = f.read()
        except (OSError, TypeError):
            raise TranscribeError(NOTHING_RECORDED_MSG) from None
        if not audio:
            raise TranscribeError(NOTHING_RECORDED_MSG)

        fields = {"model": c.get("transcription_model") or _DEFAULTS["transcription_model"],
                  "response_format": "json"}
        lang = c.get("transcription_language")
        if lang:
            fields["language"] = lang
        body, ctype = _multipart(fields, "file", "instruction.wav", audio, "audio/wav")
        url = str(c.get("openai_base_url") or _DEFAULTS["openai_base_url"]).rstrip("/") \
            + "/audio/transcriptions"
        timeout = _num(c.get("request_timeout"), 60, float)
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": "Bearer " + key,
            "Content-Type": ctype,
            "Accept": "application/json",
            "User-Agent": "LeadPilotCRM",
        })

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            code = getattr(e, "code", None)
            if code in (401, 403):
                auth_msg = _auth_user_message(e)
                try:
                    e.close()
                except Exception:
                    pass
                raise AuthError(auth_msg) from None
            no_credits = code == 429 and _is_no_credits(e)
            try:
                e.close()
            except Exception:
                pass
            if code == 429:
                if no_credits:
                    raise NoCreditsError() from None
                raise RateLimitError() from None
            if code == 413:
                raise TranscribeError("The recording is too long. Record a "
                                      "shorter instruction and try again.") from None
            raise TranscribeError("OpenAI could not turn the recording into text "
                                  "(error %s). Try again, or type your "
                                  "instructions instead." % code) from None
        except urllib.error.URLError as e:
            if _is_timeout(e):
                raise TranscribeError(TIMEOUT_MSG) from None
            raise OfflineError() from None
        except (socket.timeout, TimeoutError):
            raise TranscribeError(TIMEOUT_MSG) from None
        except OSError:
            raise OfflineError() from None

        try:
            data = json.loads(raw.decode("utf-8"))
            text = data.get("text", "") if isinstance(data, dict) else ""
        except Exception:
            raise TranscribeError(GENERIC_MSG) from None
        text = (text or "").strip()
        if not text:
            raise TranscribeError(EMPTY_MSG)
        return text
    except VoiceError:
        raise
    except Exception:
        raise TranscribeError(GENERIC_MSG) from None
    finally:
        if delete_after:
            delete_file(wav_path)
