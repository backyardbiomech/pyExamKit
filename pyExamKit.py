#!/usr/bin/env python3

import sys
import traceback
from tkinter import messagebox

import customtkinter as ctk
from gui import pyScanUI


def report_error(exc_type, exc, tb):
    """Show an error from any button. Tk prints these only to the terminal
    that launched the app, which the built app does not have, so a failed
    button otherwise looks like one that did nothing."""
    text = ''.join(traceback.format_exception(exc_type, exc, tb))
    print(text, file=sys.stderr)
    messagebox.showerror('pyExamKit error',
                         f'{exc}\n\nDetails:\n{text[-1500:]}')


if __name__ == "__main__":
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    root.report_callback_exception = report_error
    pyScanUI(root)
    root.mainloop()
