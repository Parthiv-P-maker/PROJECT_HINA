_drag_x = 0
_drag_y = 0


def toggle_window(app, entry):
    if app.state() == "withdrawn":
        app.deiconify()
        app.focus_force()
        entry.focus()
    else:
        app.withdraw()


def start_drag(app, event):
    global _drag_x, _drag_y

    _drag_x = event.x_root - app.winfo_x()
    _drag_y = event.y_root - app.winfo_y()


def do_drag(app, event):
    app.geometry(
        f"+{event.x_root - _drag_x}+{event.y_root - _drag_y}"
    )