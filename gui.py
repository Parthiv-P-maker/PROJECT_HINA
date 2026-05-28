import customtkinter as ctk
import keyboard

from core.assistant import hina_reply
from core.ambient import AmbientThoughtManager
from core.command_router import route_command
from core.dispatcher import dispatch_command
from core.startup import build_startup_message
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


def _handle_command(command):
    result = dispatch_command(
        command,
        output_var=output_var,
        output_label=output_label,
        app=app,
    )

    if result.reply:
        hina_reply(result.reply, output_var, output_label, app)

    if result.should_exit:
        app.after(result.exit_delay_ms or 1800, app.destroy)


# =========================
# COMMAND EXECUTION
# =========================

def execute_command(event=None):
    raw_command = entry.get().strip()
    if not raw_command:
        return

    command = route_command(raw_command)
    entry.delete(0, "end")

    output_var.set(f"> {raw_command}")
    app.after(300, lambda: _handle_command(command))


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

entry.bind("<Return>", execute_command)
entry.bind("<FocusIn>", _on_entry_focus)
entry.bind("<FocusOut>", _on_entry_blur)
entry.bind("<KeyRelease>", ambient_manager.reset_timer)
entry.bind("<FocusIn>", ambient_manager.reset_timer)
entry.bind("<FocusOut>", ambient_manager.reset_timer)


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


# =========================
# STARTUP GREETING
# =========================

# =========================
# STARTUP GREETING
# =========================

saved_name = get_name()
startup_message = build_startup_message(saved_name)

hina_reply(
    startup_message,
    output_var,
    output_label,
    app
)

app.after(2500, app.withdraw)

app.mainloop()