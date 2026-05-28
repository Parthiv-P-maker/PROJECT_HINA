import customtkinter as ctk


def create_section_frame(parent, **kwargs):
    """Create a reusable section frame for a modern UI panel."""
    return ctk.CTkFrame(parent, **kwargs)


def create_icon_button(parent, text, command, width=28, height=28, **kwargs):
    """Create a small icon-style button for window controls."""
    return ctk.CTkButton(parent, text=text, width=width, height=height, command=command, **kwargs)
