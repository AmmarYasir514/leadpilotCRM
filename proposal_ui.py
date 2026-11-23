"""Write a proposal dialog for LeadPilot CRM.

DRAFT ONLY. This window never sends, submits or clicks anything on Upwork.
It writes a draft with OpenAI, the user reviews and edits it, then copies it
(or saves it as the job's cover letter, only when they click that button).

Public API:
    open_write_proposal(parent, job_text, title='', on_save_cover_letter=None,
                        on_open_settings=None, ui=None, initial_draft='',
                        initial_instructions='', initial_template=None,
                        on_draft_changed=None, on_submit_url=None) -> WriteProposalDialog

Flow (one screen, opens with the cursor in the Instructions box):
    job post preview, Template dropdown (P6, hidden if templates cannot load),
    Instructions box (always typeable) with a mic icon at the right end of its
    header (click to record, click again to stop; greyed out with a note and
    tooltip when voice is not available), Generate proposal, editable Draft,
       Revise with these instructions, Copy, Save as cover letter, Close.

Threading: all network work (OpenAI chat, OpenAI transcription) runs in a
threading.Thread. Worker threads never touch Tk. They put results on a
queue.Queue, and the Tk main loop polls that queue with widget.after().

The API key is never read, shown or logged here. ai_proposal and voice_input
fetch it themselves from settings_store (Windows Credential Manager).
"""

import importlib
import queue
import threading
import tkinter as tk
from tkinter import ttk

__all__ = ["open_write_proposal", "WriteProposalDialog"]

# Same palette as leadpilot_crm.UI (copied so this module never imports the app).
DEFAULT_UI = {"bg": "#F5F7FB", "card": "#FFFFFF", "line": "#E6EAF2", "text": "#0F172A",
              "muted": "#64748B", "side": "#0F172A", "side2": "#1E293B", "side_text": "#CBD5E1",
              "accent": "#6366F1", "accent2": "#8B5CF6", "green": "#10B981", "red": "#EF4444"}
FONT = "Segoe UI"

# Tests set this to True so the window never shows on screen.
_START_HIDDEN = False

# Window size and text box heights (lines). Chosen so that at the minimum
# size the draft box keeps about 6 lines and the Copy / Save row stays fully
# visible, even with the Template row and the No key banner showing.
DEFAULT_W, DEFAULT_H = 900, 760
MIN_W, MIN_H = 640, 660
JOB_LINES = 5
INS_LINES = 3
DRAFT_LINES = 6

TIMER_WIDTH = 12   # characters, fits "10:00 of 10:00"
STOP_WIDTH = 5

POLL_MS = 50
DEBOUNCE_MS = 1500        # on_draft_changed after typing stops
SUBMIT_CLOSE_MS = 1200    # close after a link is saved
LINK_TIP = "After you submit on Upwork, paste the proposal link here."
TIMER_MS = 200

MSG_NO_KEY = "No OpenAI API key saved."
MSG_NO_KEY_HINT = "Add your key on the Settings page, then come back and press Generate."
MSG_NO_JOB = "There is no job post text. Import or paste a job post first."
MSG_NO_DRAFT = "There is no draft yet. Press Generate proposal first."
MSG_NO_REVISE_INS = "Type or speak what you want to change, then press Revise."
DRAFT_NOTE = "Drafts are not saved. Copy before closing."
MSG_GENERIC = "Something went wrong. Try again."
MSG_EMPTY_TRANSCRIPT = "I could not hear anything. Try again or type your instructions."
MSG_SAVED = "Saved as the cover letter for this job."
MSG_SAVE_KEPT = "Not saved. The old cover letter was kept."
MSG_SAVE_FAILED = "Could not save the cover letter. Copy the draft instead."
MSG_TYPE_FALLBACK = "You can type your instructions instead."
MSG_MISSING = {
    "ai_proposal": "The proposal writer (ai_proposal.py) is missing or could not load.",
    "voice_input": "Voice input (voice_input.py) is missing or could not load. Type your instructions instead.",
    "settings_store": "Settings (settings_store.py) is missing or could not load.",
}


def _load(name):
    """Import a helper module lazily. Returns (module or None, message)."""
    try:
        return importlib.import_module(name), ""
    except Exception:
        return None, MSG_MISSING.get(name, "A part of LeadPilot could not load.")


def _safe_message(exc):
    """Plain English text for an error. Only uses .user_message, never str(exc)."""
    msg = getattr(exc, "user_message", None)
    if isinstance(msg, str) and msg.strip():
        return msg
    return MSG_GENERIC


class MicButton(tk.Canvas):
    """Small mic icon button drawn on a Canvas (looks the same with any
    Windows font). Idle: grey mic. Recording: red circle, white mic.
    Disabled: light grey. Supports invoke(), state() and instate() like ttk."""

    SIZE = 28

    def __init__(self, parent, command=None, bg="#F5F7FB"):
        super().__init__(parent, width=self.SIZE, height=self.SIZE, bg=bg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self._command = command
        self._disabled = False
        self.recording = False
        self._hover = False
        # Button-1 and ButtonRelease-1: some nested scroll canvases eat one of them.
        self.bind("<Button-1>", lambda e: self.invoke())
        self.bind("<ButtonRelease-1>", lambda e: "break")
        self.bind("<space>", lambda e: self.invoke())
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<Enter>", lambda e: self._set_hover(True), add="+")
        self.bind("<Leave>", lambda e: self._set_hover(False), add="+")
        self.configure(takefocus=1)
        self._draw()

    def _set_hover(self, on):
        self._hover = on
        self._draw()

    def colors(self):
        if self._disabled:
            return "#EEF1F5", "#B8C2CF"
        if self.recording:
            return "#DC2626", "#FFFFFF"
        return ("#DCE5F1" if self._hover else "#E8EDF5"), "#334155"

    def _draw(self):
        self.delete("all")
        n = self.SIZE
        back, fore = self.colors()
        self.create_oval(1, 1, n - 1, n - 1, fill=back, outline=back, tags="back")
        cx = n / 2
        self.create_oval(cx - 4, 6, cx + 4, 14, fill=fore, outline=fore)
        self.create_rectangle(cx - 4, 10, cx + 4, 16, fill=fore, outline=fore)
        self.create_oval(cx - 4, 12, cx + 4, 20, fill=fore, outline=fore)
        self.create_arc(cx - 7, 9, cx + 7, 21, start=180, extent=180, style="arc", outline=fore, width=1.6)
        self.create_line(cx, 21, cx, 24, fill=fore, width=1.6)
        self.create_line(cx - 3.5, 24, cx + 3.5, 24, fill=fore, width=1.6)
        self.configure(cursor="arrow" if self._disabled else "hand2")

    def set_recording(self, on):
        self.recording = bool(on)
        self._draw()

    def invoke(self):
        if not self._disabled and callable(self._command):
            return self._command()
        return None

    def state(self, spec=None):
        if spec:
            for flag in spec:
                if flag == "disabled":
                    self._disabled = True
                elif flag == "!disabled":
                    self._disabled = False
            self._draw()
        return ("disabled",) if self._disabled else ()

    def instate(self, spec):
        for flag in spec:
            if flag == "disabled" and not self._disabled:
                return False
            if flag == "!disabled" and self._disabled:
                return False
        return True


class Tooltip:
    """Plain hover tooltip. text_fn is called each time, so the text can change."""

    def __init__(self, widget, text_fn, delay_ms=400):
        self.widget = widget
        self.text_fn = text_fn
        self.delay_ms = delay_ms
        self.tip = None
        self._after = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")
        widget.bind("<Button-1>", lambda e: self.hide(), add="+")

    def text(self):
        try:
            return str(self.text_fn() or "")
        except Exception:
            return ""

    def _schedule(self, event=None):
        self._cancel()
        try:
            self._after = self.widget.after(self.delay_ms, self.show)
        except Exception:
            self._after = None

    def _cancel(self):
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def show(self):
        self._after = None
        text = self.text()
        if not text or self.tip is not None:
            return
        try:
            x = self.widget.winfo_rootx() - 180
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry("+%d+%d" % (max(0, x), y))
            tk.Label(tip, text=text, bg="#0F172A", fg="#FFFFFF", font=(FONT, 8), padx=8, pady=4,
                     wraplength=260, justify="left").pack()
            self.tip = tip
        except Exception:
            self.tip = None

    def hide(self):
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


def _with_type_hint(msg):
    """Add the typing hint only if the message does not already mention typing."""
    msg = (msg or "").strip()
    low = msg.lower()
    if "type your instructions" in low or "type the instructions" in low or "typing" in low:
        return msg
    return (msg + " " + MSG_TYPE_FALLBACK).strip()


class WriteProposalDialog:
    """The Write a proposal window. Create it with open_write_proposal()."""

    def __init__(self, parent, job_text, title="", on_save_cover_letter=None,
                 on_open_settings=None, ui=None, initial_draft="", initial_instructions="",
                 initial_template=None, on_draft_changed=None, on_submit_url=None,
                 editable_job=False, initial_job=None, start_expanded=False,
                 on_create_proposal=None):
        self.ui = dict(DEFAULT_UI)
        if isinstance(ui, dict):
            self.ui.update(ui)
        self.job_text = str(job_text or "")
        self.title = str(title or "")
        self.on_save_cover_letter = on_save_cover_letter
        self.on_open_settings = on_open_settings
        self.initial_template = initial_template
        self.on_draft_changed = on_draft_changed if callable(on_draft_changed) else None
        self.on_submit_url = on_submit_url if callable(on_submit_url) else None
        self.editable_job = bool(editable_job)
        self.initial_job = dict(initial_job or {})
        self.start_expanded = bool(start_expanded)
        self.on_create_proposal = on_create_proposal if callable(on_create_proposal) else None
        self.job_fields = None
        self.btn_create_proposal = None
        self.writer_parts = None
        self.result_parts = None
        self.draft_note = None
        self._unsaved_draft = False
        self._submitted = False
        self._expanded = False
        self.url_entry = None
        self.job_link_entry = None
        self.btn_paste_clip = None
        self.job_title_entry = None
        self.job_desc_box = None
        self._initial_draft = str(initial_draft or "")
        self._initial_instructions = str(initial_instructions or "")
        self.btn_save_link = None
        self.link_row = None
        self._debounce_id = None
        self._submit_close_id = None
        self._last_sent = None
        self._final_saved = False

        self.mode = None            # None, "text" or "voice"
        self.closed = False
        self.busy = False
        self.recorder = None
        self.no_key_shown = False
        self._q = queue.Queue()
        self._poll_id = None
        self._timer_id = None
        self._job_open = True
        self.min_height = MIN_H
        self.templates = []          # list of {"name", "text"} from settings_store
        self.template_names = []
        self.template_var = None
        self.template_box = None     # None when templates are not available

        c = self.ui
        self.win = tk.Toplevel(parent)
        if _START_HIDDEN:
            self.win.withdraw()
        self.win.title("Write a proposal" + (" - " + self.title if self.title else ""))
        self.win.configure(bg=c["bg"])
        try:
            sh = int(self.win.winfo_screenheight())
        except Exception:
            sh = 0
        default_h = 820 if self.editable_job else DEFAULT_H
        h = default_h if sh <= 0 else max(MIN_H, min(default_h, sh - 80))
        if self.editable_job and not self.start_expanded:
            h = min(h, 620)
        self.win.geometry("%dx%d" % (DEFAULT_W, h))
        self.win.minsize(MIN_W, MIN_H)
        try:
            self.win.transient(parent.winfo_toplevel())
        except Exception:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", self._on_escape, add="+")   # Esc stops a recording

        self.status_var = tk.StringVar(master=self.win, value="")

        # Header
        head = tk.Frame(self.win, bg=c["card"], highlightthickness=1, highlightbackground=c["line"])
        head.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(head, text="Write a proposal", bg=c["card"], fg=c["text"],
                 font=(FONT, 15, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(head, text=(self.title or "Job post") + "   |   Draft only. Nothing is sent to Upwork.",
                 bg=c["card"], fg=c["muted"], font=(FONT, 9), wraplength=820,
                 justify="left").pack(anchor="w", padx=16, pady=(2, 12))

        # No-key banner (shown only when no key is saved)
        self.no_key_frame = tk.Frame(self.win, bg="#FEF3C7")
        self.no_key_label = tk.Label(self.no_key_frame, text=MSG_NO_KEY + " " + MSG_NO_KEY_HINT,
                                     bg="#FEF3C7", fg="#92400E", font=(FONT, 9, "bold"),
                                     wraplength=640, justify="left")
        self.no_key_label.pack(side="left", padx=12, pady=8)
        self.btn_open_settings = None
        if callable(self.on_open_settings):
            self.btn_open_settings = ttk.Button(self.no_key_frame, text="Open Settings",
                                                command=self.open_settings)
            self.btn_open_settings.pack(side="right", padx=12, pady=6)

        # Status line (bottom)
        bottom = tk.Frame(self.win, bg=c["bg"])
        bottom.pack(side="bottom", fill="x", padx=16, pady=(4, 12))
        # Close first, so a long status message can never push it out.
        self.btn_close = ttk.Button(bottom, text="Close", command=self.close)
        self.btn_close.pack(side="right")
        self.status_label = tk.Label(bottom, textvariable=self.status_var, bg=c["bg"], fg=c["muted"],
                                     font=(FONT, 9, "bold"), anchor="w", justify="left", wraplength=480)
        self.status_label.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.status_label.bind("<Configure>", self._wrap_status, add="+")

        self.body = tk.Frame(self.win, bg=c["bg"])
        self.body.pack(fill="both", expand=True, padx=16)

        self.check_key()
        self.voice_ok, self.voice_msg = self._voice_available()
        self._open_main()

    # ------------------------------------------------------------ helpers
    def _alive(self):
        if self.closed:
            return False
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def set_status(self, text, kind="info"):
        if not self._alive():
            return
        colors = {"info": self.ui["muted"], "error": "#DC2626", "ok": "#047857", "busy": self.ui["accent"]}
        self.status_var.set(text or "")
        try:
            self.status_label.configure(fg=colors.get(kind, self.ui["muted"]))
        except Exception:
            pass

    def check_key(self):
        """Show or hide the No OpenAI API key banner. Returns True if a key is saved."""
        ss, _msg = _load("settings_store")
        has = False
        if ss is not None:
            try:
                has = bool(ss.has_api_key())
            except Exception:
                has = False
        if not self._alive():
            return has
        if has and self.no_key_shown:
            self.no_key_frame.pack_forget()
            self.no_key_shown = False
            self._fit_min_size()
        elif not has and not self.no_key_shown:
            self.no_key_frame.pack(fill="x", padx=16, pady=(0, 8), after=self._first_child())
            self.no_key_shown = True
            if self.mode is not None:
                self._fit_min_size()
        return has

    def _fit_min_size(self):
        """Raise the minimum window height to what the content needs, so the
        draft box and the Copy / Save row never get squeezed. This also covers
        Windows display scaling (125%, 150%), where everything is taller.
        Never larger than the screen."""
        if not self._alive():
            return
        try:
            self.win.update_idletasks()
            need = int(self.win.winfo_reqheight()) + 8
            sh = int(self.win.winfo_screenheight())
            h = max(MIN_H, need)
            if sh > 0:
                h = min(h, max(MIN_H, sh - 60))
            self.win.minsize(MIN_W, h)
            self.min_height = h
        except Exception:
            pass

    def _first_child(self):
        return self.win.winfo_children()[0]

    def open_settings(self):
        if callable(self.on_open_settings):
            try:
                self.on_open_settings()
            except Exception:
                self.set_status("Could not open Settings. Use the Settings item in the left menu.", "error")

    def _load_cfg(self):
        ss, _ = _load("settings_store")
        if ss is None:
            return None
        try:
            return ss.load_config()
        except Exception:
            return None

    def _voice_available(self):
        vi, msg = _load("voice_input")
        if vi is None:
            return False, msg
        try:
            ok, m = vi.is_available()
            return bool(ok), str(m or "")
        except Exception:
            return False, "Voice input is not available on this computer. Type your instructions instead."

    # Kept for older callers and QA scripts. The window now opens straight on
    # the main screen, so these do nothing.
    def choose_text(self):
        return None

    def choose_voice(self):
        return None

    # ------------------------------------------------------------ main screen
    def _open_main(self):
        if not self._alive() or self.mode is not None:
            return
        self.mode = "main"
        c = self.ui
        b = self.body

        # Layout note (screen fit): Tk's pack gives space in packing order, and
        # the last packed widget is squeezed first when the window is small.
        # So the important parts are packed first from the bottom up:
        #   Copy / Save row, Draft box (min DRAFT_LINES lines), Draft label,
        #   Generate row, Instructions, Template.
        # The job post preview is packed last, so it is the part that shrinks.
        # Visual order (top to bottom) stays: job post, template, instructions,
        # generate, draft, copy / save.

        # Widgets are created in visual order ...
        self.btn_job_toggle = None
        self.job_box = None
        self._job_header = None
        if self.editable_job:
            self._build_editable_job(b, c)
        else:
            jh = tk.Frame(b, bg=c["bg"])
            tk.Label(jh, text="Job post", bg=c["bg"], fg=c["text"], font=(FONT, 10, "bold")).pack(side="left")
            self.btn_job_toggle = ttk.Button(jh, text="Hide job post", command=self.toggle_job)
            self.btn_job_toggle.pack(side="right")
            self.job_box = tk.Text(b, height=JOB_LINES, wrap="word", bg="#F8FAFC", fg=c["text"], relief="flat",
                                   font=(FONT, 9), padx=10, pady=6, highlightthickness=1, highlightbackground=c["line"])
            self.job_box.insert("1.0", self.job_text or "(No job post text.)")
            self.job_box.configure(state="disabled")
            self._job_header = jh

        # Template dropdown (P6). Hidden if templates cannot be loaded.
        trow = self._build_template_row(b)

        ih = tk.Frame(b, bg=c["bg"])
        # Right side first: Tk squeezes the last packed widgets first, so the
        # mic, Stop label and timer are packed before the left labels and keep
        # a fixed width. The long example text is the part that gets cut.
        self.elapsed_var = tk.StringVar(master=self.win, value="")
        self.btn_mic = MicButton(ih, command=self.toggle_recording, bg=c["bg"])
        self.btn_mic.pack(side="right")
        self.stop_label = tk.Label(ih, text="", width=STOP_WIDTH, anchor="e", bg=c["bg"], fg="#DC2626",
                                   font=(FONT, 9, "bold"), cursor="hand2")
        self.stop_label.bind("<Button-1>", lambda e: self.stop_recording() if self.recorder is not None else None)
        self.stop_label.pack(side="right", padx=(0, 4))
        self.elapsed_label = tk.Label(ih, textvariable=self.elapsed_var, width=TIMER_WIDTH, anchor="e",
                                      bg=c["bg"], fg="#DC2626", font=(FONT, 9, "bold"))
        self.elapsed_label.pack(side="right", padx=(0, 4))
        self.voice_note = tk.Label(ih, text="" if self.voice_ok else "Voice not available", bg=c["bg"],
                                   fg=c["muted"], font=(FONT, 8))
        self.voice_note.pack(side="right", padx=(0, 6))
        tk.Label(ih, text="Instructions", bg=c["bg"], fg=c["text"], font=(FONT, 10, "bold")).pack(side="left")
        tk.Label(ih, text="For example: keep it short, focus on my Shopify experience.", bg=c["bg"],
                 fg=c["muted"], font=(FONT, 8), anchor="w").pack(side="left", padx=8, fill="x", expand=True)
        self.mic_tip = Tooltip(self.btn_mic, self._mic_tip_text)
        if not self.voice_ok:
            self.btn_mic.state(["disabled"])
        # Voice error note (red, wraps), shown under the Instructions header only
        # when recording or transcribing fails.
        self.voice_err_var = tk.StringVar(master=self.win, value="")
        self.voice_err_label = tk.Label(b, textvariable=self.voice_err_var, bg=c["bg"], fg="#DC2626",
                                        font=(FONT, 9, "bold"), anchor="w", justify="left", wraplength=560)
        self.voice_err_label.bind("<Configure>", self._wrap_voice_err, add="+")
        self.voice_err_shown = False
        self.ins_box = tk.Text(b, height=INS_LINES, wrap="word", bg=c["card"], fg=c["text"], relief="flat",
                               font=(FONT, 10), padx=10, pady=6, highlightthickness=1,
                               highlightbackground=c["line"], undo=True)

        ar = tk.Frame(b, bg=c["bg"])
        self.btn_generate = ttk.Button(ar, text="Generate proposal", style="Accent.TButton", command=self.generate)
        self.btn_generate.pack(side="left", padx=(0, 8))
        self.btn_revise = ttk.Button(ar, text="Revise with these instructions", command=self.revise)
        self.btn_revise.pack(side="left", padx=(0, 8))

        dh = tk.Frame(b, bg=c["bg"])
        tk.Label(dh, text="Draft", bg=c["bg"], fg=c["text"], font=(FONT, 10, "bold")).pack(side="left")
        tk.Label(dh, text="You can edit the draft here before you copy it.", bg=c["bg"], fg=c["muted"],
                 font=(FONT, 8)).pack(side="left", padx=8)
        self.draft_box = tk.Text(b, height=DRAFT_LINES, wrap="word", bg=c["card"], fg=c["text"], relief="flat",
                                 font=(FONT, 10), padx=12, pady=8, highlightthickness=1,
                                 highlightbackground=c["line"], undo=True)

        self.copy_row = tk.Frame(b, bg=c["bg"])
        self.btn_save = None
        if callable(self.on_save_cover_letter):
            self.btn_save = ttk.Button(self.copy_row, text="Save as cover letter", command=self.save_cover_letter)
            self.btn_save.pack(side="right", padx=(8, 0))
        self.btn_copy = ttk.Button(self.copy_row, text="Copy", command=self.copy_draft)
        self.btn_copy.pack(side="right")
        self.draft_note = tk.Label(
            b, text=DRAFT_NOTE, bg=c["bg"], fg=c["muted"],
            font=(FONT, 8), anchor="w", justify="left",
        )

        # Submitted proposal link row (P8), only when the caller wants it.
        if self.on_submit_url is not None:
            self.link_row = tk.Frame(b, bg=c["bg"])
            link_label = tk.Label(self.link_row, text="Submitted proposal link", bg=c["bg"], fg=c["text"],
                                  font=(FONT, 9, "bold"))
            link_label.pack(side="left")
            self.btn_save_link = ttk.Button(self.link_row, text="Save link", command=self.save_link)
            self.btn_save_link.pack(side="right")
            self.url_entry = ttk.Entry(self.link_row, font=(FONT, 9))
            self.url_entry.pack(side="left", fill="x", expand=True, padx=8)
            self.url_entry.bind("<Return>", lambda e: self.save_link())
            self.link_tips = [Tooltip(w, lambda: LINK_TIP) for w in (link_label, self.url_entry)]

        # ... and packed in priority order (bottom up, then the job post).
        if self.link_row is not None:
            self.link_row.pack(side="bottom", fill="x", pady=(2, 2))
        self.copy_row.pack(side="bottom", fill="x", pady=(4, 2))
        self.draft_box.pack(side="bottom", fill="both", expand=True)
        dh.pack(side="bottom", fill="x", pady=(8, 2))
        ar.pack(side="bottom", fill="x", pady=(6, 0))
        self.ins_box.pack(side="bottom", fill="x")
        ih.pack(side="bottom", fill="x", pady=(8, 2))
        if trow is not None:
            trow.pack(side="bottom", fill="x", pady=(8, 0))
        if self.editable_job:
            self._pack_editable_job()
        else:
            self._job_header.pack(side="top", fill="x", pady=(8, 2))
            self.job_box.pack(side="top", fill="x")

        # Prefill (P8) and watch for edits.
        if self._initial_instructions:
            self.ins_box.insert("1.0", self._initial_instructions)
        if self._initial_draft:
            self.draft_box.insert("1.0", self._initial_draft)
        self._sync_draft_note()
        self._last_sent = self._snapshot()
        for box in (self.ins_box, self.draft_box):
            box.edit_modified(False)
            box.bind("<<Modified>>", self._on_text_modified, add="+")

        self._fit_min_size()
        self.set_status("Type or speak your instructions, then press Generate proposal." if self.voice_ok
                        else "Type your instructions, then press Generate proposal.")
        self._refresh_buttons()
        self._focus_instructions()
        # Put the cursor in Instructions again when the window first appears.
        self._map_bind = self.win.bind("<Map>", self._on_first_map, add="+")

    def _focus_instructions(self):
        try:
            if self.editable_job and not self._expanded and self.job_link_entry is not None:
                self.job_link_entry.focus_set()
            else:
                self.ins_box.focus_set()
        except Exception:
            pass

    def _on_first_map(self, event=None):
        if event is not None and event.widget is not self.win:
            return
        try:
            self.win.unbind("<Map>", self._map_bind)
        except Exception:
            pass
        if self._alive():
            self.win.after_idle(self._focus_instructions)

    # ------------------------------------------------------------ templates (P6)
    def _load_templates(self):
        """Return (templates, default_name), or ([], None) if not available."""
        ss, _ = _load("settings_store")
        if ss is None:
            return [], None
        try:
            cfg = ss.load_config()
            raw = ss.get_templates(cfg)
            out = []
            for t in raw or []:
                name = str((t or {}).get("name") or "").strip()
                if name and name not in [x["name"] for x in out]:
                    out.append({"name": name, "text": str((t or {}).get("text") or "")})
            if not out:
                return [], None
        except Exception:
            return [], None
        default = out[0]["name"]
        want = str(self.initial_template or "").strip()
        if want in [x["name"] for x in out]:
            return out, want          # caller asked for this template
        try:
            last = ss.get_last_template(cfg)
            last_name = str((last or {}).get("name") or "").strip()
            if last_name in [x["name"] for x in out]:
                default = last_name
        except Exception:
            pass
        return out, default

    def _build_template_row(self, parent):
        self.templates, default = self._load_templates()
        self.template_names = [t["name"] for t in self.templates]
        if not self.templates:
            self.template_box = None
            return None
        c = self.ui
        row = tk.Frame(parent, bg=c["bg"])   # packed by _open_main
        tk.Label(row, text="Template", bg=c["bg"], fg=c["text"], font=(FONT, 10, "bold")).pack(side="left")
        self.template_var = tk.StringVar(master=self.win, value=default)
        self.template_box = ttk.Combobox(row, textvariable=self.template_var, values=self.template_names,
                                         state="readonly", width=40, font=(FONT, 10))
        self.template_box.pack(side="left", padx=8)
        self.template_box.bind("<<ComboboxSelected>>", self._on_template_change)
        return row

    def get_template_name(self):
        """Name of the selected template, or None when the dropdown is hidden."""
        if self.template_box is None or self.template_var is None:
            return None
        name = self.template_var.get().strip()
        return name or None

    def get_template_text(self):
        """Text of the selected template, or None (use the default prompt)."""
        name = self.get_template_name()
        for t in self.templates:
            if t["name"] == name:
                return t["text"] if t["text"].strip() else None
        return None

    def set_template(self, name):
        """Select a template by name (as if picked in the dropdown). Returns True if found."""
        if self.template_box is None or name not in self.template_names:
            return False
        self.template_var.set(name)
        self._on_template_change()
        return True

    def _on_template_change(self, event=None):
        name = self.get_template_name()
        if not name:
            return
        ss, _ = _load("settings_store")
        if ss is None:
            self.set_status("Could not remember this template choice. It will still be used for this draft.", "error")
            return
        try:
            ss.set_last_template(name)
        except Exception as e:
            msg = None
            se = getattr(ss, "SettingsError", None)
            if isinstance(se, type) and isinstance(e, se):
                msg = getattr(e, "message", None)   # short, user friendly by design
            if not isinstance(msg, str) or not msg.strip():
                msg = "Could not remember this template choice."
            self.set_status(msg + " It will still be used for this draft.", "error")
            return
        self.set_status('Template "%s" selected.' % name, "info")
        self._schedule_notify()

    def toggle_job(self):
        if not self._alive() or self.mode is None:
            return
        self._job_open = not self._job_open
        if self._job_open:
            self.job_box.pack(side="top", fill="x", after=self._job_header)
            self.btn_job_toggle.configure(text="Hide job post")
        else:
            self.job_box.pack_forget()
            self.btn_job_toggle.configure(text="Show job post")

    def _set_state(self, btn, enabled):
        if btn is None:
            return
        try:
            btn.state(["!disabled"] if enabled else ["disabled"])
        except Exception:
            pass

    def _refresh_buttons(self):
        if not self._alive() or self.mode is None:
            return
        recording = self.is_recording()
        free = not self.busy and not recording
        self._set_state(self.btn_generate, free)
        self._set_state(self.btn_revise, free)
        self._set_state(self.btn_copy, not self.busy)
        self._set_state(self.btn_save, not self.busy)
        self._set_state(self.btn_mic, bool(self.voice_ok) and not self.busy)
        if self.template_box is not None:
            try:
                self.template_box.configure(state="disabled" if self.busy else "readonly")
            except Exception:
                pass

    # ------------------------------------------------------------ text access (QA friendly)
    def get_instructions(self):
        if self.mode is None or not self._alive():
            return ""
        return self.ins_box.get("1.0", "end-1c")

    def set_instructions(self, text):
        if self.mode is None:
            self.choose_text()
        if not self._alive():
            return
        self.ins_box.delete("1.0", "end")
        self.ins_box.insert("1.0", text or "")

    def get_draft(self):
        if self.mode is None or not self._alive():
            return ""
        return self.draft_box.get("1.0", "end-1c")

    def set_draft(self, text):
        if self.mode is None or not self._alive():
            return
        self.draft_box.delete("1.0", "end")
        self.draft_box.insert("1.0", text or "")

    def is_busy(self):
        return self.busy

    # ------------------------------------------------------------ background work
    def _run_bg(self, busy_text, work, on_ok, on_err=None):
        """Run work() in a thread. on_ok(result) or on_err(message) runs later
        on the Tk thread. Without on_err the message goes to the status line."""
        self.busy = True
        self._refresh_buttons()
        self.set_status(busy_text, "busy")

        def runner():
            try:
                res = ("ok", work())
            except BaseException as e:  # noqa: B902 - reported to the UI as plain text
                res = ("err", _safe_message(e))
            self._q.put((res, on_ok, on_err))   # queue only, never touch Tk here

        threading.Thread(target=runner, daemon=True, name="LeadPilotProposalWorker").start()
        self._schedule_poll()

    def _schedule_poll(self):
        if self._alive() and self._poll_id is None:
            self._poll_id = self.win.after(POLL_MS, self._poll)

    def _poll(self):
        self._poll_id = None
        if not self._alive():
            return
        try:
            while True:
                (kind, value), on_ok, on_err = self._q.get_nowait()
                self.busy = False
                if kind == "ok":
                    try:
                        on_ok(value)
                    except Exception:
                        self.set_status(MSG_GENERIC, "error")
                elif on_err is not None:
                    try:
                        on_err(value)
                    except Exception:
                        self.set_status(value, "error")
                else:
                    self.set_status(value, "error")
                self._refresh_buttons()
        except queue.Empty:
            pass
        if self.busy:
            self._schedule_poll()

    # ------------------------------------------------------------ generate / revise
    def generate(self):
        self._start_ai(revise=False)

    def revise(self):
        self._start_ai(revise=True)

    def _start_ai(self, revise):
        if not self._alive():
            return
        if self.mode is None:
            self.choose_text()
        if self.busy or self.is_recording():
            return
        job_text = self.get_current_job_text()
        if not job_text.strip():
            msg = "Type or paste a job description first." if self.editable_job else MSG_NO_JOB
            self.set_status(msg, "error")
            if self.job_fields is not None:
                self.job_fields.set_message(msg)
            return
        ai, msg = _load("ai_proposal")
        if ai is None:
            self.set_status(msg, "error")
            return
        if not self.check_key():
            self.set_status(MSG_NO_KEY + " " + MSG_NO_KEY_HINT, "error")
            return
        instructions = self.get_instructions().strip()
        previous = None
        if revise:
            previous = self.get_draft().strip()
            if not previous:
                self.set_status(MSG_NO_DRAFT, "error")
                return
            if not instructions:
                self.set_status(MSG_NO_REVISE_INS, "error")
                return
        cfg = self._load_cfg()
        job = self.get_current_job_text()
        template_text = self.get_template_text()

        def work():
            return ai.generate_proposal(job, instructions=instructions, previous_draft=previous, cfg=cfg,
                                        template_text=template_text)

        def done(text):
            self.set_draft(text)
            self._unsaved_draft = True
            self._submitted = False
            try:
                self.draft_box.edit_modified(False)
            except Exception:
                pass
            self.show_result_parts()
            self._sync_draft_note()
            self.notify_draft_changed(force=True)
            self.set_status("Draft revised. Review it, then press Copy." if revise
                            else "Draft ready. Review and edit it, then press Copy.", "ok")

        self._run_bg("Revising..." if revise else "Generating...", work, done)

    # ------------------------------------------------------------ P8 hooks
    def _snapshot(self):
        base = (self.get_draft(), self.get_instructions(), self.get_template_name())
        if self.job_fields is not None:
            return base + (self.job_fields.get_values(),)
        return base

    def notify_draft_changed(self, force=False):
        """Call on_draft_changed(draft, instructions, template_name[, job_dict]). Never raises.
        Without force, it only calls when something changed since the last call.
        Callers that only accept three arguments still work."""
        if self.on_draft_changed is None or self.mode is None:
            return False
        try:
            snap = self._snapshot()
        except Exception:
            return False
        if not force and snap == self._last_sent:
            return False
        self._last_sent = snap
        try:
            self.on_draft_changed(*snap)
        except TypeError:
            try:
                self.on_draft_changed(*snap[:3])
            except Exception:
                pass
        except Exception:
            pass
        return True

    def _schedule_notify(self):
        if self.on_draft_changed is None or not self._alive():
            return
        if self._debounce_id is not None:
            try:
                self.win.after_cancel(self._debounce_id)
            except Exception:
                pass
        self._debounce_id = self.win.after(DEBOUNCE_MS, self._debounce_fire)

    def _debounce_fire(self):
        self._debounce_id = None
        if self._alive():
            self.notify_draft_changed()

    def _on_text_modified(self, event=None):
        w = getattr(event, "widget", None)
        try:
            if w is not None and not w.edit_modified():
                return
            if w is not None:
                w.edit_modified(False)
        except Exception:
            pass
        if w is self.draft_box or w is None:
            try:
                if (self.get_draft() or "").strip():
                    self._unsaved_draft = True
            except Exception:
                self._unsaved_draft = True
            self._sync_draft_note()
        self._schedule_notify()

    def save_link(self):
        """Save link button: pass the pasted URL to on_submit_url. Never opens it."""
        if not self._alive() or self.on_submit_url is None or self.url_entry is None:
            return
        if self._submit_close_id is not None:
            return
        url = self.url_entry.get().strip()
        if not url:
            self.set_status("Paste the proposal link first.", "error")
            return
        try:
            result = self.on_submit_url(url)
            if isinstance(result, (tuple, list)) and len(result) >= 2:
                ok, msg = bool(result[0]), str(result[1] or "")
            else:
                ok, msg = bool(result), ""
        except Exception:
            ok, msg = False, "Could not save the link. Try again."
        if not ok:
            self.set_status(msg or "Could not save the link. Check it and try again.", "error")
            return
        self.set_status(msg or "Link saved.", "ok")
        self.mark_submitted()
        try:
            self.url_entry.state(["disabled"])
            self.btn_save_link.state(["disabled"])
        except Exception:
            pass
        self._submit_close_id = self.win.after(SUBMIT_CLOSE_MS, self._close_after_submit)

    def _close_after_submit(self):
        self._submit_close_id = None
        if not self._alive():
            return
        self.notify_draft_changed(force=True)   # final save
        self._final_saved = True
        self.close()

    # ------------------------------------------------------------ copy / save
    def copy_draft(self):
        if not self._alive():
            return
        text = self.get_draft().strip()
        if not text:
            self.set_status(MSG_NO_DRAFT, "error")
            return
        self._unsaved_draft = False
        try:
            self.draft_box.edit_modified(False)
        except Exception:
            pass
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(text)
            self.win.update_idletasks()
        except Exception:
            self.set_status("Could not copy to the clipboard. Select the text and press Ctrl+C.", "error")
            return
        self.set_status("Copied.", "ok")

    def save_cover_letter(self):
        if not self._alive() or not callable(self.on_save_cover_letter):
            return
        text = self.get_draft().strip()
        if not text:
            self.set_status(MSG_NO_DRAFT, "error")
            return
        try:
            result = self.on_save_cover_letter(text)
        except Exception:
            self.set_status(MSG_SAVE_FAILED, "error")
            return
        if result is False:   # the user said No to replacing the old letter
            self.set_status(MSG_SAVE_KEPT, "info")
            return
        self.set_status(MSG_SAVED, "ok")   # True or None mean saved

    # ------------------------------------------------------------ voice
    def is_recording(self):
        r = self.recorder
        try:
            return bool(r is not None and r.is_recording)
        except Exception:
            return False

    def _mic_tip_text(self):
        if not self.voice_ok:
            return self.voice_msg or "Voice input is not available on this computer."
        if self.recorder is not None:
            return "Click to stop"
        if self.busy:
            return "Please wait..."
        return "Click to record your instructions"

    def toggle_recording(self):
        if self.recorder is not None:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if not self._alive() or self.mode is None or self.busy or self.recorder is not None:
            return
        if not self.voice_ok:
            self.set_status(self.voice_msg or "Voice input is not available.", "error")
            return
        vi, msg = _load("voice_input")
        if vi is None:
            self.set_status(msg, "error")
            return
        self.clear_voice_error()
        try:
            rec = vi.Recorder(self._load_cfg())
            rec.start()
        except Exception as e:
            self.show_voice_error(_with_type_hint(_safe_message(e)))
            return
        self.recorder = rec
        self.btn_mic.set_recording(True)
        self.stop_label.configure(text="Stop")
        self.elapsed_var.set(self._timer_text(0))
        self.set_status("Recording... Click the mic again to stop.", "busy")
        self._refresh_buttons()
        self._tick()

    def _tick(self):
        self._timer_id = None
        if not self._alive() or self.recorder is None:
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
        self._timer_id = self.win.after(TIMER_MS, self._tick)

    def _on_escape(self, event=None):
        if self.recorder is not None:
            self.stop_recording()
            return "break"
        return None

    def show_voice_error(self, msg):
        """Show a voice error in red under the Instructions header (and on the status line)."""
        msg = (msg or "").strip() or MSG_GENERIC
        self.set_status(msg, "error")
        if not self._alive() or self.mode is None:
            return
        self.voice_err_var.set(msg)
        if not self.voice_err_shown:
            self.voice_err_label.pack(side="bottom", fill="x", pady=(0, 2), after=self.ins_box)
            self.voice_err_shown = True
            self._fit_min_size()

    def clear_voice_error(self):
        if not self._alive() or self.mode is None:
            return
        self.voice_err_var.set("")
        if self.voice_err_shown:
            self.voice_err_label.pack_forget()
            self.voice_err_shown = False

    def _wrap_status(self, event=None):
        try:
            w = int(self.status_label.winfo_width())
            if w > 50 and abs(int(float(self.status_label.cget("wraplength"))) - (w - 8)) > 4:
                self.status_label.configure(wraplength=w - 8)
        except Exception:
            pass

    def _wrap_voice_err(self, event=None):
        try:
            w = int(self.voice_err_label.winfo_width())
            if w > 50 and abs(int(float(self.voice_err_label.cget("wraplength"))) - (w - 8)) > 4:
                self.voice_err_label.configure(wraplength=w - 8)
        except Exception:
            pass

    def _timer_text(self, secs):
        """For example '1:50 of 2:00'. The max comes from recorder.max_seconds."""
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
                self.win.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None

    def stop_recording(self, auto=False):
        if not self._alive() or self.recorder is None:
            return
        rec, self.recorder = self.recorder, None
        self._cancel_timer()
        self.btn_mic.set_recording(False)
        self.elapsed_var.set("")
        self.stop_label.configure(text="")
        try:
            path = rec.stop()
        except Exception as e:
            self.show_voice_error(_safe_message(e))
            self._refresh_buttons()
            return
        vi, msg = _load("voice_input")
        if vi is None:
            self.show_voice_error(msg)
            self._refresh_buttons()
            return
        empty_msg = getattr(vi, "EMPTY_MSG", None) or MSG_EMPTY_TRANSCRIPT
        cfg = self._load_cfg()

        def work():
            return vi.transcribe(path, cfg=cfg)

        def done(text):
            text = (text or "").strip() if isinstance(text, str) else ""
            if not text:                      # never fail silently
                self.show_voice_error(empty_msg)
                return
            self.clear_voice_error()
            cur = self.get_instructions().rstrip()
            self.set_instructions((cur + "\n" + text) if cur else text)
            self.set_status("Check the instructions and fix anything, then press Generate proposal.", "ok")

        self._run_bg(("Recording reached the time limit. " if auto else "") + "Transcribing...",
                     work, done, on_err=self.show_voice_error)

    # ------------------------------------------------------------ close
    def close(self):
        if self.closed:
            return
        rec, self.recorder = self.recorder, None
        if rec is not None:
            try:
                rec.cancel()
            except Exception:
                pass
        self._cancel_timer()
        if self._poll_id is not None:
            try:
                self.win.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        try:
            self.mic_tip.hide()
        except Exception:
            pass
        for attr in ("_debounce_id", "_submit_close_id"):
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.win.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        if not self._final_saved and self._alive():
            self._final_saved = True
            self.notify_draft_changed(force=True)   # once on Close
        self.closed = True   # any thread still running is ignored when it ends
        try:
            self.win.destroy()
        except Exception:
            pass


    def get_current_job_text(self):
        """Job text for Generate, from JobFields when present, else the job box."""
        if self.job_fields is not None:
            try:
                import write_proposal_page as wpp
                return wpp.job_dict_to_text(self.job_fields.get_values())
            except Exception:
                try:
                    return (self.job_fields.get_values().get("description") or "")
                except Exception:
                    return ""
        try:
            return self.job_box.get("1.0", "end-1c")
        except Exception:
            return self.job_text or ""

    def show_result_parts(self):
        for item in (self.result_parts or []):
            try:
                widget, opts = item[0], item[1]
                if not widget.winfo_manager():
                    widget.pack(**opts)
            except Exception:
                pass

    def _sync_draft_note(self):
        """Grey one-line note under the draft, only once a draft exists."""
        note = getattr(self, "draft_note", None)
        if note is None or not self._alive():
            return
        try:
            has = bool((self.get_draft() or "").strip())
        except Exception:
            has = bool(getattr(self, "_initial_draft", ""))
        try:
            mapped = bool(note.winfo_manager())
        except Exception:
            mapped = False
        if has and not mapped:
            try:
                note.pack(side="bottom", fill="x", pady=(2, 0), before=self.draft_box)
            except Exception:
                try:
                    note.pack(side="bottom", fill="x", pady=(2, 0))
                except Exception:
                    pass
        elif not has and mapped:
            try:
                note.pack_forget()
            except Exception:
                pass

    def has_unsaved_draft(self):
        if getattr(self, "_submitted", False):
            return False
        try:
            has_text = bool((self.get_draft() or "").strip())
        except Exception:
            has_text = False
        return bool(self._unsaved_draft) and has_text

    def mark_submitted(self):
        self._submitted = True
        self._unsaved_draft = False
        self._sync_draft_note()

    def _build_editable_job(self, parent, c):
        """Job section used only when editable_job=True (one-screen)."""
        try:
            import write_proposal_page as wpp
            self.job_fields = wpp.JobFields(parent, ui=self.ui)
            if self.initial_job:
                self.job_fields.set_values(self.initial_job)
            jf = self.job_fields
            self.job_link_entry = jf.job_link_entry
            self.btn_paste_clip = getattr(jf, "btn_paste_clip", None)
            self.job_title_entry = jf.job_title_entry
            self.job_desc_box = jf.job_desc_box
        except Exception:
            self.job_fields = None
        self.create_row = tk.Frame(parent, bg=c["bg"])
        self.btn_create_proposal = ttk.Button(
            self.create_row, text="Create proposal", style="Accent.TButton",
            command=self._on_create_clicked if hasattr(self, "_on_create_clicked") else None,
        )
        self.btn_create_proposal.pack(side="left")

    def _pack_editable_job(self):
        if self.job_fields is not None:
            try:
                self.job_fields.frame.pack(side="top", fill="x")
            except Exception:
                pass
        if getattr(self, "create_row", None) is not None:
            try:
                self.create_row.pack(side="top", fill="x", pady=(8, 0))
            except Exception:
                pass
        if getattr(self, "start_expanded", False) or getattr(self, "_expanded", False):
            for item in (self.writer_parts or []):
                try:
                    item[0].pack(**item[1])
                except Exception:
                    pass
            for item in (self.result_parts or []):
                try:
                    item[0].pack(**item[1])
                except Exception:
                    pass

    def _on_create_clicked(self):
        if self.job_fields is not None:
            ok, result = self.job_fields.validate(require_content=True)
            if not ok:
                try:
                    self.job_fields.set_message(result)
                except Exception:
                    self.set_status(result, "error")
                return
        self._expanded = True
        if callable(self.on_create_proposal):
            try:
                self.on_create_proposal()
            except Exception:
                pass
        for item in (self.writer_parts or []):
            try:
                item[0].pack(**item[1])
            except Exception:
                pass


def open_write_proposal(parent, job_text, title="", on_save_cover_letter=None,
                        on_open_settings=None, ui=None, initial_draft="", initial_instructions="",
                        initial_template=None, on_draft_changed=None, on_submit_url=None,
                        editable_job=False, initial_job=None, start_expanded=False,
                        on_create_proposal=None):
    """Open the Write a proposal window and return the dialog object.

    parent: any Tk widget (the app root is fine).
    job_text: the job post text the draft is based on.
    title: job title shown in the window title.
    on_save_cover_letter: optional callable(draft_text). Called only when the
        user clicks Save as cover letter. Return False if nothing was saved
        (for example the user said No to replacing the old letter); True or
        None mean saved. An exception shows a friendly error.
    on_open_settings: optional callable(). Called by the Open Settings button
        shown when no API key is saved.
    ui: optional colour dict (same keys as leadpilot_crm.UI).
    initial_draft, initial_instructions: optional text to prefill the boxes.
    initial_template: optional template name to preselect (if it exists).
    on_draft_changed: optional callable(draft_text, instructions_text,
        template_name). Called after Generate or Revise succeeds, about 1.5 s
        after edits stop, and once on Close. Errors in it are ignored.
    on_submit_url: optional callable(url) -> (ok, message). Shows a
        "Submitted proposal link" row with a Save link button. On ok the row
        is disabled and the window closes after about 1.2 s (final
        on_draft_changed first). The URL is never opened.
    """
    return WriteProposalDialog(parent, job_text, title=title, on_save_cover_letter=on_save_cover_letter,
                               on_open_settings=on_open_settings, ui=ui, initial_draft=initial_draft,
                               initial_instructions=initial_instructions, initial_template=initial_template,
                               on_draft_changed=on_draft_changed, on_submit_url=on_submit_url,
                               editable_job=editable_job, initial_job=initial_job,
                               start_expanded=start_expanded, on_create_proposal=on_create_proposal)
