import customtkinter as ctk
import keyboard
import queue
import threading

from core.assistant import hina_reply
from core.ambient import AmbientThoughtManager
from core.command_router import route_command
from core.dispatcher import DispatchResult, dispatch_command
from core.startup import build_startup_message
from core.stt import SpeechInput, SttError
from memory import get_name
from ui.animations import start_petal_animation, start_status_blink
from ui.effects import _on_entry_blur, _on_entry_focus
from ui.theme import (
    C_WARM_GOLD,
    C_TEXT_MAIN,
    C_SAKURA,
    C_BG_PANEL,
    C_TEXT_SUB,
    C_BORDER,
    C_BG_CARD,
    C_ENTRY_FG,
    C_ENTRY_PH,
    C_SAKURA_DIM,
    C_BG_DEEP,
)
from utils.logger import get_logger
from ui.window import toggle_window, start_drag, do_drag
logger = get_logger(__name__)


# =========================
# STATUS DOT BLINK


_busy = False
_listening = False
_results = queue.Queue()

_STATE_LABELS = {
    "waiting": "waiting for me to finish...",
    "listening": "listening... 🎤",
    "transcribing": "transcribing...",
}


class _Heard:
    """Worker -> Tk thread: what the microphone made of the user's speech."""

    def __init__(self, text="", error=None, cancelled=False):
        self.text, self.error, self.cancelled = text, error, cancelled


class _State:
    """Worker -> Tk thread: the voice pipeline moved to a new stage."""

    def __init__(self, name):
        self.name = name


def _speaking_now():
    import voice
    return voice.is_speaking()


speech = SpeechInput(is_speaking=_speaking_now, on_state=lambda name: _results.put(_State(name)))


def _set_busy(busy, label="thinking..."):
    global _busy
    _busy = busy
    sub_label.configure(text=label if busy else "your ambient companion")
    mic_btn.configure(text="■" if _listening else "🎤")


def _show_confirm_buttons(show):
    """Yes/No buttons live in the title bar so the fixed-size window doesn't change."""
    if show:
        no_btn.pack(side="right", padx=(0, 6))
        yes_btn.pack(side="right", padx=(0, 4))
    else:
        yes_btn.pack_forget()
        no_btn.pack_forget()


def _answer(text):
    if not _busy:
        _start_command(text)


def _finish_command(result):
    """Runs on the Tk thread: show the reply and clear the busy state."""
    _set_busy(False)
    _show_confirm_buttons(getattr(result, "needs_confirmation", False))

    if result.reply:
        hina_reply(result.reply, output_var, output_label, app)

    if result.should_exit:
        app.after(result.exit_delay_ms or 1800, app.destroy)


def _run_command(raw_command):
    """Runs in a worker thread so slow work (AI, file search) never freezes the window."""
    try:
        command = route_command(raw_command)
        result = dispatch_command(
            command,
            output_var=output_var,
            output_label=output_label,
            app=app,
        )
    except Exception:
        logger.exception("Command failed: %s", raw_command)
        result = DispatchResult(reply="Something went wrong with that one 🌸")

    # Hand the result to the Tk thread through a queue; Tk widgets and
    # after() must only be touched from the main thread.
    _results.put(result)


def _run_listen():
    """Worker thread: record + transcribe, then report back through the queue."""
    try:
        text = speech.listen()
        _results.put(_Heard(text=text, cancelled=speech.cancel.is_set()))
    except SttError as exc:
        _results.put(_Heard(error=str(exc)))
    except Exception:
        logger.exception("Voice input failed")
        _results.put(_Heard(error="Voice input hit a snag 🌸"))


def _finish_listening(heard):
    """Runs on the Tk thread once the mic is done."""
    global _listening
    _listening = False
    _set_busy(False)

    if heard.cancelled:
        return
    if heard.error:
        output_var.set(heard.error)
    elif not heard.text:
        output_var.set("I didn't catch that - try again? 🎤")
    else:
        _start_command(heard.text)


def toggle_listening(event=None):
    """Mic button / hotkey: start listening, or stop if already listening."""
    global _listening
    if _listening:
        speech.cancel.set()
        return
    if _busy:
        return

    _listening = True
    output_var.set("Listening... 🎤")
    _set_busy(True, _STATE_LABELS["listening"])
    threading.Thread(target=_run_listen, daemon=True).start()


def _hotkey_listen():
    """keyboard calls hotkeys on its own thread; hop to Tk before touching widgets."""
    def go():
        if app.state() == "withdrawn":
            toggle_window(app, entry)
        toggle_listening()
    app.after(0, go)


def _handle_result(item):
    if isinstance(item, _Heard):
        _finish_listening(item)
    elif isinstance(item, _State):
        if _listening:
            sub_label.configure(text=_STATE_LABELS.get(item.name, item.name))
    else:
        _finish_command(item)


def _poll_results():
    try:
        while True:
            _handle_result(_results.get_nowait())
    except queue.Empty:
        pass
    app.after(50, _poll_results)


# =========================
# COMMAND EXECUTION
# =========================

def execute_command(event=None):
    if _busy:
        return

    raw_command = entry.get().strip()
    if not raw_command:
        return

    entry.delete(0, "end")
    _start_command(raw_command)


def _start_command(raw_command):
    """Shared by typed and spoken input: same router, same dispatcher."""
    output_var.set(f"> {raw_command}")
    _set_busy(True)
    threading.Thread(target=_run_command, args=(raw_command,), daemon=True).start()


# =========================
# TOGGLE WINDOW
# =========================




# =========================
# WINDOW DRAG
# =========================




# =========================
# APP WINDOW
# =========================

app = ctk.CTk()
app.geometry("520x300")
app.title("Project Hina")
app.attributes("-topmost", True)
app.resizable(False, False)
app.configure(fg_color=C_BG_DEEP)

# Remove native title bar decorations feel via overrideredirect (borderless)
app.overrideredirect(True)

# Center on screen
app.update_idletasks()
sw = app.winfo_screenwidth()
sh = app.winfo_screenheight()
x = (sw - 520) // 2
y = sh - 360
app.geometry(f"520x300+{x}+{y}")


# =========================
# OUTER BORDER FRAME
# =========================

outer = ctk.CTkFrame(
    app,
    corner_radius=24,
    fg_color=C_BG_PANEL,
    border_color=C_BORDER,
    border_width=1
)
outer.pack(fill="both", expand=True, padx=2, pady=2)
outer.bind("<ButtonPress-1>", lambda e: start_drag(app, e))
outer.bind("<B1-Motion>", lambda e: do_drag(app, e))


# =========================
# PETAL CANVAS (behind content)
# =========================

petal_canvas = ctk.CTkCanvas(
    outer,
    width=516, height=296,
    bg=C_BG_PANEL,
    highlightthickness=0
)
petal_canvas.place(x=0, y=0, relwidth=1, relheight=1)
petal_canvas.place(
    x=0,
    y=0,
    relwidth=1,
    relheight=1
)

petal_canvas.bind(
    "<ButtonPress-1>",
    lambda e: start_drag(app, e)
)

petal_canvas.bind(
    "<B1-Motion>",
    lambda e: do_drag(app, e)
)
# Subtle horizontal rule lines for texture
for yy in range(0, 300, 28):
    petal_canvas.create_line(0, yy, 520, yy, fill="#2e1e2c", width=1)


# =========================
# TITLE BAR ROW
# =========================

title_bar = ctk.CTkFrame(outer, fg_color="transparent", height=44)
title_bar.pack(fill="x", padx=18, pady=(14, 0))
title_bar.pack_propagate(False)


# Status dot
status_dot = ctk.CTkLabel(
    title_bar,
    text="●",
    font=("Segoe UI", 11),
    text_color=C_SAKURA
)
status_dot.pack(side="left", padx=(0, 6))

# Title
title_label = ctk.CTkLabel(
    title_bar,
    text="Hina  🌸",
    font=("Yu Gothic UI", 22, "bold"),
    text_color=C_SAKURA
)
title_label.pack(side="left")

# Subtitle
sub_label = ctk.CTkLabel(
    title_bar,
    text="your ambient companion",
    font=("Segoe UI", 11),
    text_color=C_TEXT_SUB
)
sub_label.pack(side="left", padx=(10, 0))

# Close button
close_btn = ctk.CTkButton(
    title_bar,
    text="✕",
    width=28, height=28,
    corner_radius=8,
    fg_color="transparent",
    hover_color="#4a2040",
    text_color=C_TEXT_SUB,
    font=("Segoe UI", 13),
    command=lambda: toggle_window(app, entry)
)
close_btn.pack(side="right")

# Yes / No for "Should I?" questions (hidden until one is pending)
yes_btn = ctk.CTkButton(
    title_bar, text="Yes", width=46, height=28, corner_radius=8,
    fg_color=C_SAKURA_DIM, hover_color=C_SAKURA, text_color=C_BG_DEEP,
    font=("Segoe UI", 12), command=lambda: _answer("yes")
)
no_btn = ctk.CTkButton(
    title_bar, text="No", width=46, height=28, corner_radius=8,
    fg_color=C_BG_CARD, hover_color="#4a2040", text_color=C_TEXT_SUB,
    font=("Segoe UI", 12), command=lambda: _answer("no")
)

title_bar.bind("<ButtonPress-1>", lambda e: start_drag(app, e))
title_bar.bind("<B1-Motion>", lambda e: do_drag(app, e))


# =========================
# DIVIDER
# =========================

divider = ctk.CTkFrame(outer, height=1, fg_color=C_BORDER)
divider.pack(fill="x", padx=18, pady=(8, 0))


# =========================
# OUTPUT AREA
# =========================

output_var = ctk.StringVar(value="Hina is ready 🌸")

output_frame = ctk.CTkFrame(
    outer,
    fg_color=C_BG_CARD,
    corner_radius=14,
    border_color=C_BORDER,
    border_width=1
)
output_frame.pack(fill="x", padx=18, pady=(14, 0))

output_label = ctk.CTkLabel(
    output_frame,
    textvariable=output_var,
    wraplength=440,
    justify="center",
    font=("Segoe UI", 15),
    text_color=C_TEXT_MAIN,
    pady=14,
    padx=16
)
output_label.pack(fill="x")

ambient_manager = AmbientThoughtManager(app, output_var, output_label)
ambient_manager.start()


# =========================
# ENTRY ROW
# =========================

entry_frame = ctk.CTkFrame(outer, fg_color="transparent")
entry_frame.pack(fill="x", padx=18, pady=(12, 16))

entry = ctk.CTkEntry(
    entry_frame,
    height=44,
    corner_radius=14,
    font=("Segoe UI", 15),
    placeholder_text="Talk to Hina...",
    fg_color=C_BG_CARD,
    border_color=C_BORDER,
    border_width=1,
    text_color=C_ENTRY_FG,
    placeholder_text_color=C_ENTRY_PH
)
entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

mic_btn = ctk.CTkButton(
    entry_frame,
    text="🎤",
    width=44, height=44,
    corner_radius=14,
    fg_color=C_BG_CARD,
    border_color=C_BORDER,
    border_width=1,
    hover_color=C_SAKURA_DIM,
    text_color=C_SAKURA,
    font=("Segoe UI Emoji", 16),
    command=toggle_listening
)
send_btn = ctk.CTkButton(
    entry_frame,
    text="→",
    width=44, height=44,
    corner_radius=14,
    fg_color=C_SAKURA_DIM,
    hover_color=C_SAKURA,
    text_color=C_BG_DEEP,
    font=("Segoe UI", 18, "bold"),
    command=execute_command
)
send_btn.pack(side="right")
mic_btn.pack(side="right", padx=(0, 10))

entry.bind("<Return>", execute_command)
entry.bind("<FocusIn>", _on_entry_focus)
entry.bind("<FocusOut>", _on_entry_blur)
entry.bind("<KeyRelease>", ambient_manager.reset_timer)
entry.bind("<FocusIn>", ambient_manager.reset_timer)
entry.bind("<FocusOut>", ambient_manager.reset_timer)


app.after(50, _poll_results)


# =========================
# SPAWN PETALS
# =========================

start_petal_animation(petal_canvas, app)


# =========================
# BLINK STATUS DOT
# =========================

start_status_blink(status_dot, app)


# =========================
# HOTKEY
# =========================

keyboard.add_hotkey(
    "ctrl+h",
    lambda: toggle_window(app, entry)
)

keyboard.add_hotkey("ctrl+m", _hotkey_listen)


# =========================
# STARTUP GREETING
# =========================

# Display greeting immediately in UI (non-blocking)
saved_name = get_name()
startup_message = build_startup_message(saved_name)
output_var.set(startup_message)

# Speak the greeting in a background thread to avoid blocking UI
def _speak_startup():
    from voice import speak
    speak(startup_message, blocking=False)

greeting_thread = threading.Thread(target=_speak_startup, daemon=True)
greeting_thread.start()

app.after(2500, app.withdraw)

app.mainloop()