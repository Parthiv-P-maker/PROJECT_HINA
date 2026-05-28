from ui.theme import C_BORDER, C_SAKURA, C_TEXT_MAIN, C_WARM_GOLD

_pulse_after_id = None


def _fade_to_normal(output_label, app, step):
    """Transition the output label color back to the normal text color."""
    global _pulse_after_id
    total = 18
    if step >= total:
        output_label.configure(text_color=C_TEXT_MAIN)
        return

    t = step / total
    r1, g1, b1 = 0xf7, 0xc9, 0x7e
    r2, g2, b2 = 0xf5, 0xdc, 0xe8
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    output_label.configure(text_color=f"#{r:02x}{g:02x}{b:02x}")
    _pulse_after_id = app.after(30, _fade_to_normal, output_label, app, step + 1)


def _pulse_output(output_label, app):
    """Pulse the output label color for assistant responses."""
    global _pulse_after_id
    if _pulse_after_id:
        app.after_cancel(_pulse_after_id)

    output_label.configure(text_color=C_WARM_GOLD)
    _fade_to_normal(output_label, app, 0)


def _on_entry_focus(event=None):
    """Apply focus styling when the entry receives focus."""
    widget = getattr(event, "widget", None)
    if widget is not None:
        widget.configure(border_color=C_SAKURA)


def _on_entry_blur(event=None):
    """Restore entry styling when the entry loses focus."""
    widget = getattr(event, "widget", None)
    if widget is not None:
        widget.configure(border_color=C_BORDER)
