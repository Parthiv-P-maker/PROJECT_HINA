import customtkinter as ctk
import keyboard
import random
import threading
import time
import math

from parser import normalize_command
from actions import (
    open_app,
    search_and_open_file,
    find_folder,
    close_app,
    restart_app,
    tell_time,
    tell_date,
    battery_status,
    disk_usage,
    calculate,
    set_timer,
    cancel_timer,
)
from voice import speak
from memory import (
    set_name,
    get_name,
    add_recent_app,
    add_recent_file,
    set_favorite_app,
    get_favorite_app,
    get_recent_apps,
    get_recent_files
)
from ui.window import toggle_window, start_drag, do_drag

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


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


# =========================
# HINA REPLY
# =========================

def hina_reply(message):
    output_var.set(f"{message}")
    _pulse_output()
    speak(message)


# =========================
# OUTPUT PULSE ANIMATION
# =========================

_pulse_after_id = None

def _pulse_output():
    global _pulse_after_id
    if _pulse_after_id:
        app.after_cancel(_pulse_after_id)
    output_label.configure(text_color=C_WARM_GOLD)
    _fade_to_normal(0)

def _fade_to_normal(step):
    global _pulse_after_id
    total = 18
    if step >= total:
        output_label.configure(text_color=C_TEXT_MAIN)
        return
    t = step / total
    r1, g1, b1 = 0xf7, 0xc9, 0x7e   # gold
    r2, g2, b2 = 0xf5, 0xdc, 0xe8   # text main
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    output_label.configure(text_color=f"#{r:02x}{g:02x}{b:02x}")
    _pulse_after_id = app.after(30, _fade_to_normal, step + 1)


# =========================
# PETAL PARTICLE ANIMATION
# =========================

class Petal:
    def __init__(self, canvas, w, h):
        self.canvas = canvas
        self.w = w
        self.h = h
        self.reset(initial=True)

    def reset(self, initial=False):
        self.x = random.uniform(0, self.w)
        self.y = random.uniform(-60, -10) if not initial else random.uniform(0, self.h)
        self.size = random.uniform(3, 7)
        self.speed_y = random.uniform(0.4, 1.1)
        self.speed_x = random.uniform(-0.3, 0.3)
        self.sway_amp = random.uniform(0.4, 1.2)
        self.sway_freq = random.uniform(0.01, 0.03)
        self.sway_offset = random.uniform(0, math.tau)
        self.alpha_idx = random.randint(0, 5)
        self.tick = 0
        colors = ["#f2a7c3", "#f7b8cf", "#fddde8", "#e891b2", "#f5cad8", "#f9d2e3"]
        self.color = colors[self.alpha_idx % len(colors)]
        self.oval_id = self.canvas.create_oval(
            self.x, self.y,
            self.x + self.size, self.y + self.size,
            fill=self.color, outline=""
        )

    def step(self):
        self.tick += 1
        sway = math.sin(self.tick * self.sway_freq + self.sway_offset) * self.sway_amp
        self.x += self.speed_x + sway * 0.15
        self.y += self.speed_y
        self.canvas.coords(
            self.oval_id,
            self.x, self.y,
            self.x + self.size, self.y + self.size
        )
        if self.y > self.h + 10:
            self.canvas.delete(self.oval_id)
            self.reset()
            self.oval_id = self.canvas.create_oval(
                self.x, self.y,
                self.x + self.size, self.y + self.size,
                fill=self.color, outline=""
            )


_petals = []
_petal_running = True

def _animate_petals():
    for p in _petals:
        p.step()
    if _petal_running:
        app.after(35, _animate_petals)


# =========================
# ENTRY GLOW ON FOCUS
# =========================

def _on_entry_focus(event=None):
    entry.configure(border_color=C_SAKURA)

def _on_entry_blur(event=None):
    entry.configure(border_color=C_BORDER)


# =========================
# COUNTDOWN WITH VOICE
# =========================

def voiced_countdown(seconds):
    cute_lines = [
        "Ready?", "Steady...", "Almost there...",
        "Just a little more...", "Don't blink...",
        "Hina is counting...", "Nearly done..."
    ]
    for i in range(seconds, 0, -1):
        msg = f"{i}... {random.choice(cute_lines)}"
        app.after(0, lambda m=msg: output_var.set(m))
        app.after(0, _pulse_output)
        speak(msg)
        time.sleep(1)
    app.after(0, lambda: hina_reply("Done!"))


# =========================
# STATUS DOT BLINK
# =========================

_dot_state = True

def _blink_dot():
    global _dot_state
    _dot_state = not _dot_state
    status_dot.configure(text_color=C_SAKURA if _dot_state else C_BG_PANEL)
    app.after(900, _blink_dot)


# =========================
# COMMAND EXECUTION
# =========================

def execute_command(event=None):
    
    raw_command = entry.get().strip()
    if not raw_command:
        return
    command = normalize_command(raw_command)
    entry.delete(0, "end")

    # Show user's message briefly
    output_var.set(f"> {raw_command}")
    app.after(300, lambda: _dispatch(command))

def _dispatch(command):

    # MEMORY
    if command.startswith("set name "):
        name = command.replace("set name ", "").strip()
        hina_reply(set_name(name))


    # EXIT
    if command in ["bye", "exit"]:
        hina_reply(random.choice([
            "Bye bye! Take care 🌸",
            "Hina is going to sleep now 🎀",
            "See you soon! 🌷",
            "Good work today! ✨",
            "Until next time 🌸"
        ]))
        app.after(1800, app.destroy)
        return

    # FILES
    elif command.startswith("open "):
        app_name = command.replace("open ", "").strip()

        favorite_app = get_favorite_app(app_name)

        if favorite_app:
            app_name = favorite_app

        add_recent_app(app_name)

        hina_reply(open_app(app_name))

    elif command.startswith("open file "):
        file_name = command.replace("open file ", "").strip()

        add_recent_file(file_name)

        hina_reply(search_and_open_file(file_name))

    elif command.startswith("find folder "):
        hina_reply(find_folder(command.replace("find folder ", "")))

    elif command.startswith("favorite app "):
        data = command.replace("favorite app ", "").split(" as ")

        if len(data) == 2:
            app_name = data[0].strip()
            label = data[1].strip()

            hina_reply(set_favorite_app(label, app_name))
        else:
            hina_reply("Use: favorite app chrome as browser 🌸")
    # APPS
    elif command.startswith("close "):
        hina_reply(close_app(command.replace("close ", "")))
    elif command.startswith("restart "):
        hina_reply(restart_app(command.replace("restart ", "")))

    # SYSTEM
    elif command == "tell time":
        hina_reply(tell_time())
    elif command == "tell date":
        hina_reply(tell_date())
    elif command == "battery":
        hina_reply(battery_status())
    elif command == "disk usage":
        hina_reply(disk_usage())

    # CALCULATOR
    elif command.startswith("calculate "):
        hina_reply(calculate(command.replace("calculate ", "")))

    # TIMER
    elif command.startswith("timer "):
        hina_reply(set_timer(int(command.replace("timer ", ""))))
    elif command == "cancel timer":
        hina_reply(cancel_timer())

    # COUNTDOWN
    elif command.startswith("countdown "):
        seconds = int(command.replace("countdown ", ""))
        threading.Thread(target=voiced_countdown, args=(seconds,), daemon=True).start()

    # CONVERSATION
    elif command in ["hello", "hi"]:
        hina_reply(random.choice([
            "Hello! 🌸", "Hi there! 🎀", "Welcome back! 🌷", "Hina is listening ✨"
        ]))
    elif command == "how are you":
        hina_reply(random.choice([
            "I'm doing great 🌸", "Feeling cheerful as always 🎀", "All systems happy ✨"
        ]))
    elif command == "who are you":
        hina_reply(random.choice([
            "I'm Hina, your desktop assistant 🌸",
            "Project Hina at your service 🎀",
            "Your cheerful anime companion ✨"
        ]))
    elif command == "thanks":
        hina_reply(random.choice([
            "You're welcome 🌸", "Happy to help 🎀", "Anytime ✨"
        ]))
    elif command == "what can you do":
        hina_reply("Open apps, manage files, tell time, calculate, set timers, and more 🌸")
    else:
        hina_reply(random.choice([
            "Hmm, I don't know that one yet 🌸",
            "Hina is still learning! 🎀",
            "That's a new one for me ✨"
        ]))


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


# =========================
# SPAWN PETALS
# =========================

for _ in range(14):
    _petals.append(Petal(petal_canvas, 520, 300))

app.after(200, _animate_petals)


# =========================
# BLINK STATUS DOT
# =========================

app.after(500, _blink_dot)


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

if saved_name:
    startup_message = random.choice([
        f"Welcome back, {saved_name} 🌸",
        f"Good to see you again, {saved_name} 🎀",
        f"Hina is ready for another day with you, {saved_name} ✨"
    ])
else:
    startup_message = random.choice([
        "Hina is awake and ready to help 🌸",
        "Welcome back! What shall we do today? 🎀",
        "Yay, Hina is here 🌷",
        "Ready for another productive day ✨",
        "Hina reporting in 🌸"
    ])

hina_reply(startup_message)

app.after(2500, app.withdraw)

app.mainloop()