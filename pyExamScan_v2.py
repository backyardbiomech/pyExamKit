#!/usr/bin/env python3

import customtkinter as ctk
from gui import pyScanUI


if __name__ == "__main__":
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    pyScanUI(root)
    root.mainloop()
