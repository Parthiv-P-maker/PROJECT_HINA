import math
import random

from ui.theme import C_BG_PANEL, C_SAKURA
from utils.constants import PETAL_CANVAS_WIDTH, PETAL_CANVAS_HEIGHT, DEFAULT_PETAL_COUNT

_dot_state = True


class Petal:
    """Simple sakura petal particle for the floating assistant background."""

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
        self.tick = 0
        colors = ["#f2a7c3", "#f7b8cf", "#fddde8", "#e891b2", "#f5cad8", "#f9d2e3"]
        self.color = random.choice(colors)
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


def animate_petals(petals, app):
    """Animate petals continuously using the main app scheduler."""
    for petal in petals:
        petal.step()
    app.after(35, animate_petals, petals, app)


def start_petal_animation(canvas, app, count=DEFAULT_PETAL_COUNT):
    """Create and start the sakura petal animation loop."""
    petals = [Petal(canvas, PETAL_CANVAS_WIDTH, PETAL_CANVAS_HEIGHT) for _ in range(count)]
    app.after(200, animate_petals, petals, app)
    return petals


def start_status_blink(status_dot, app, initial_delay=500):
    """Begin the status dot blink animation."""
    def _blink_dot():
        global _dot_state
        _dot_state = not _dot_state
        status_dot.configure(text_color=C_SAKURA if _dot_state else C_BG_PANEL)
        app.after(900, _blink_dot)

    app.after(initial_delay, _blink_dot)
