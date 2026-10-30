"""
charts.py

Two small chart widgets for the Results tab, drawn on a plain tkinter
Canvas (matplotlib would bloat the PyInstaller bundle):

  GradeChart   students per letter-grade band, one bar per series
  ChoiceBars   one question's answer distribution, horizontal bars

The layout math (nice_ticks, bar_slots, choice_rows, ...) is in plain
functions that never touch Tk, so it tests without a display. Colors
come from a small per-mode palette picked at draw time, and the canvas
background follows the CTkFrame color so it blends into the tab.
"""
from __future__ import annotations

import math
import os
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

import customtkinter as ctk

UNADJUSTED_COLOR = '#B4B2AC'
ADJUSTED_COLOR = '#2A78D6'
KEY_COLOR = '#2E8B57'
OTHER_COLOR = '#B4B2AC'

PALETTES = {
    'Light': {'text': '#222222', 'muted': '#666666', 'grid': '#D0D0D0',
              'axis': '#8A8A8A', 'tip_bg': '#FFFFE0', 'tip_fg': '#222222'},
    'Dark': {'text': '#E6E6E6', 'muted': '#A0A0A0', 'grid': '#444444',
             'axis': '#777777', 'tip_bg': '#3A3A3A', 'tip_fg': '#F0F0F0'},
}
FALLBACK_BG = ('#F2F2F2', '#2B2B2B')


# ---- theme -------------------------------------------------------------

def mode() -> str:
    """'Light' or 'Dark'."""
    return 'Dark' if str(ctk.get_appearance_mode()) == 'Dark' else 'Light'


def frame_background(appearance: str) -> str:
    """The CTkFrame fill for the mode. The theme stores a [light, dark]
    pair, possibly of Tk color names such as 'gray86' (Tk accepts those)."""
    try:
        pair = ctk.ThemeManager.theme['CTkFrame']['fg_color']
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            return str(pair[1 if appearance == 'Dark' else 0])
        if isinstance(pair, str) and pair != 'transparent':
            return pair
    except (KeyError, TypeError, AttributeError):
        pass
    return FALLBACK_BG[1 if appearance == 'Dark' else 0]


# ---- pure layout math --------------------------------------------------

def nice_ticks(max_value: int) -> list[int]:
    """Integer y ticks from 0 up to a round top at or above max_value, at
    most 6 of them (0 included)."""
    top = max(int(max_value), 1)
    magnitude = 1
    while True:
        for mult in (1, 2, 5):
            step = mult * magnitude
            if math.ceil(top / step) <= 5:
                return list(range(0, math.ceil(top / step) * step + 1, step))
        magnitude *= 10


def show_legend(n_series: int) -> bool:
    """A legend only helps when there is more than one series."""
    return n_series >= 2


def bar_slots(left: float, right: float, n_cats: int, n_series: int,
              group_gap: float = 0.25) -> list[list[tuple[float, float]]]:
    """x-extents (x0, x1) of every bar: [category][series]. Each category
    owns an equal slot; the bars sit side by side in the middle of it,
    leaving group_gap of the slot empty so groups do not touch."""
    if n_cats <= 0 or n_series <= 0:
        return []
    slot = (right - left) / n_cats
    inner = slot * (1 - group_gap)
    bar_w = inner / n_series
    slots = []
    for c in range(n_cats):
        start = left + c * slot + (slot - inner) / 2
        slots.append([(start + s * bar_w, start + (s + 1) * bar_w)
                      for s in range(n_series)])
    return slots


def bar_top(value: int, axis_top: int, plot_top: float, plot_bottom: float
            ) -> float:
    """y of a bar's top edge (the baseline itself when value is 0)."""
    if axis_top <= 0:
        return plot_bottom
    return plot_bottom - (plot_bottom - plot_top) * value / axis_top


def fit_font_size(measure: Callable[[str, int], float], texts: list[str],
                  slot_width: float, sizes: tuple[int, ...] = (10, 9, 8, 7)
                  ) -> int | None:
    """The largest size at which every text fits in slot_width, or None.
    measure(text, size) returns the pixel width."""
    for size in sizes:
        if all(measure(t, size) <= slot_width for t in texts):
            return size
    return None


def hit_bar(x: float, y: float, slots: list[list[tuple[float, float]]],
            plot_top: float, plot_bottom: float) -> tuple[int, int] | None:
    """(category, series) under the pointer, or None."""
    if not plot_top <= y <= plot_bottom:
        return None
    for c, group in enumerate(slots):
        for s, (x0, x1) in enumerate(group):
            if x0 <= x < x1:
                return c, s
    return None


def choice_rows(width: float, height: float, n_rows: int, label_w: float,
                text_w: float, pad: float = 6, max_row_h: float = 30
                ) -> dict:
    """Geometry for horizontal bars: where the bars start, how long a
    full-scale bar may be, each row's pitch and the bar thickness."""
    n = max(n_rows, 1)
    row_h = min(max_row_h, (height - 2 * pad) / n)
    x0 = pad + label_w + 6
    full = max(width - x0 - text_w - pad, 1)
    total_h = row_h * n
    return {'x0': x0, 'full': full, 'row_h': row_h,
            'bar_h': max(row_h * 0.62, 1), 'y0': (height - total_h) / 2}


def choice_label(count: int, total: int) -> str:
    """'7 · 35%' (percent of everyone who answered or left it blank)."""
    pct = round(100 * count / total) if total else 0
    return f'{count} · {pct}%'


# ---- widgets -----------------------------------------------------------

def _font(size: int, bold: bool = False) -> tuple:
    return ('Helvetica', size, 'bold') if bold else ('Helvetica', size)


_FONTS: dict = {}


def _measuring_font(size: int, bold: bool) -> tkfont.Font:
    """One Font per size and weight: each new Font is a named Tk font that
    lives as long as the app."""
    if (size, bold) not in _FONTS:
        _FONTS[size, bold] = tkfont.Font(family='Helvetica', size=size,
                                         weight='bold' if bold else 'normal')
    return _FONTS[size, bold]


def _set_background(canvas: tk.Canvas, color: str) -> None:
    """Only when it changes: configuring a canvas sends it <Configure>,
    which redraws, which would configure it again without end."""
    if canvas.cget('bg') != color:
        canvas.configure(bg=color)


class GradeChart(tk.Canvas):
    """Students per letter-grade band, one bar per series in each band."""

    def __init__(self, master, width: int = 560, height: int = 240, **kw):
        self._appearance = mode()
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0,
                         bg=frame_background(self._appearance), **kw)
        self._cats: list[str] = []
        self._series: list[tuple[str, list[int], str]] = []
        self._slots: list[list[tuple[float, float]]] = []
        self._plot = (0.0, 0.0)  # plot_top, plot_bottom
        self.bind('<Configure>', lambda _e: self.redraw())
        self.bind('<Motion>', self._on_motion)
        self.bind('<Leave>', lambda _e: self.delete('tip'))

    def set_data(self, categories: list[str],
                 series: list[tuple[str, list[int], str]]) -> None:
        self._cats = list(categories)
        self._series = [(n, list(c), col) for n, c, col in series]
        self.redraw()

    def _measure(self, text: str, size: int) -> float:
        return _measuring_font(size, False).measure(text)

    def redraw(self) -> None:
        self._appearance = mode()
        pal = PALETTES[self._appearance]
        _set_background(self, frame_background(self._appearance))
        self.delete('all')
        self._slots = []
        w, h = self.winfo_width(), self.winfo_height()
        if w < 60 or h < 60 or not self._cats or not self._series:
            return
        n_cats, n_ser = len(self._cats), len(self._series)
        peak = max((max(c, default=0) for _, c, _ in self._series), default=0)
        ticks = nice_ticks(peak)
        axis_top = ticks[-1]

        tick_size = 8
        left = max(self._measure(str(t), tick_size) for t in ticks) + 12
        right = w - 8
        top = 22 if show_legend(n_ser) else 14
        # Category labels: shrink to fit the slot, else stagger on two rows.
        slot_w = (right - left) / n_cats - 2
        cat_size = fit_font_size(lambda t, s: self._measure(t, s),
                                 self._cats, slot_w)
        stagger = cat_size is None
        if stagger:
            cat_size = 7
        bottom = h - (34 if stagger else 20)
        if bottom - top < 30:
            return

        # Gridlines and y labels.
        for t in ticks:
            y = bar_top(t, axis_top, top, bottom)
            if t:
                self.create_line(left, y, right, y, fill=pal['grid'])
            self.create_text(left - 5, y, text=str(t), anchor='e',
                             fill=pal['muted'], font=_font(tick_size))
        self.create_line(left, top, left, bottom, fill=pal['axis'])
        self.create_line(left, bottom, right, bottom, fill=pal['axis'])

        # Bars, count labels, category labels.
        self._slots = bar_slots(left, right, n_cats, n_ser)
        self._plot = (top, bottom)
        pitch = ((right - left) / n_cats * 0.75) / n_ser
        count_size = 8 if pitch >= self._measure('88', 8) else 7
        show_counts = pitch >= self._measure('88', count_size) - 1
        for c, group in enumerate(self._slots):
            for s, (x0, x1) in enumerate(group):
                value = self._series[s][1][c] if c < len(self._series[s][1]) else 0
                if value > 0:
                    y = bar_top(value, axis_top, top, bottom)
                    self.create_rectangle(x0, y, x1, bottom, width=0,
                                          fill=self._series[s][2])
                    if show_counts:
                        self.create_text((x0 + x1) / 2, y - 2, text=str(value),
                                         anchor='s', fill=pal['text'],
                                         font=_font(count_size))
            cx = (group[0][0] + group[-1][1]) / 2
            row = c % 2 if stagger else 0
            self.create_text(cx, bottom + 4 + row * 12, text=self._cats[c],
                             anchor='n', fill=pal['text'],
                             font=_font(cat_size))

        if show_legend(n_ser):
            x = right
            for name, _counts, color in reversed(self._series):
                tw = self._measure(name, 8)
                x -= tw
                self.create_text(x, 8, text=name, anchor='w',
                                 fill=pal['text'], font=_font(8))
                x -= 14
                self.create_rectangle(x, 3, x + 10, 13, width=0, fill=color)
                x -= 12

    def _on_motion(self, event) -> None:
        self.delete('tip')
        hit = hit_bar(event.x, event.y, self._slots, *self._plot)
        if hit is None:
            return
        c, s = hit
        name, counts, _col = self._series[s]
        n = counts[c] if c < len(counts) else 0
        text = f'{name}: {n} student{"" if n == 1 else "s"}'
        pal = PALETTES[self._appearance]
        x = min(event.x + 10, max(self.winfo_width() - 4, 0))
        y = max(event.y - 14, 10)
        item = self.create_text(x, y, text=text, anchor='w', tags='tip',
                                fill=pal['tip_fg'], font=_font(9))
        x0, y0, x1, y1 = self.bbox(item)
        # Keep the tip inside the canvas, then give it a backing box.
        shift = min(0, self.winfo_width() - 4 - x1)
        if shift:
            self.move(item, shift, 0)
            x0, y0, x1, y1 = self.bbox(item)
        box = self.create_rectangle(x0 - 3, y0 - 2, x1 + 3, y1 + 2, tags='tip',
                                    fill=pal['tip_bg'], outline=pal['axis'])
        self.tag_lower(box, item)


class ChoiceBars(tk.Canvas):
    """One question's answer distribution as horizontal bars."""

    def __init__(self, master, width: int = 420, height: int = 160, **kw):
        self._appearance = mode()
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0,
                         bg=frame_background(self._appearance), **kw)
        self._rows: list[tuple[str, int, str]] = []
        self._highlight: set[str] = set()
        self.bind('<Configure>', lambda _e: self.redraw())

    def set_data(self, rows, highlight: set[str]) -> None:
        """Rows are (label, count), or (label, count, text) to name the choice
        beside its letter. highlight holds labels, the letters, either way."""
        self._rows = [(r[0], r[1], r[2] if len(r) > 2 else '') for r in rows]
        self._highlight = set(highlight)
        self.redraw()

    def _measure(self, text: str, size: int, bold: bool = False) -> float:
        return _measuring_font(size, bold).measure(text)

    def _fit(self, text: str, size: int, bold: bool, max_w: float) -> str:
        """text cut to max_w, with an ellipsis when it had to be cut."""
        if self._measure(text, size, bold) <= max_w:
            return text
        kept = text
        while kept and self._measure(kept + '…', size, bold) > max_w:
            kept = kept[:-1]
        return kept.rstrip() + '…' if kept else ''

    def redraw(self) -> None:
        self._appearance = mode()
        pal = PALETTES[self._appearance]
        _set_background(self, frame_background(self._appearance))
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w < 40 or h < 20:
            return
        if not self._rows or not any(c for _, c, _ in self._rows):
            self.create_text(w / 2, h / 2, text='No answers',
                             fill=pal['muted'], font=_font(11))
            return
        total = sum(c for _, c, _ in self._rows)
        peak = max(c for _, c, _ in self._rows)
        size = 10
        # A choice named as well as lettered takes the room a letter alone
        # does not, so the names are cut to a share of the width and the bars
        # keep the rest
        shown = {}
        for label, _, text in self._rows:
            shown[label] = self._fit(f'{label}  {text}' if text else label,
                                     size, True, w * 0.45)
        label_w = max(self._measure(s, size, True) for s in shown.values())
        text_w = max(self._measure(choice_label(c, total), size)
                     for _, c, _ in self._rows)
        g = choice_rows(w, h, len(self._rows), label_w, text_w)
        for i, (label, count, _) in enumerate(self._rows):
            yc = g['y0'] + (i + 0.5) * g['row_h']
            key = label in self._highlight
            self.create_text(g['x0'] - 6, yc, text=shown[label], anchor='e',
                             fill=pal['text'],
                             font=_font(size, bold=key))
            length = g['full'] * count / peak if peak else 0
            if count:
                self.create_rectangle(g['x0'], yc - g['bar_h'] / 2,
                                      g['x0'] + length, yc + g['bar_h'] / 2,
                                      width=0,
                                      fill=KEY_COLOR if key else OTHER_COLOR)
            self.create_text(g['x0'] + length + 6, yc, anchor='w',
                             text=choice_label(count, total),
                             fill=pal['text'], font=_font(size))
        self.create_line(g['x0'], g['y0'], g['x0'], g['y0'] + g['row_h'] * len(self._rows),
                         fill=pal['axis'])


# ---- demo --------------------------------------------------------------

def _demo(auto_close_ms: int | None = None) -> None:
    import analysis
    root = ctk.CTk()
    root.title('charts demo')
    root.geometry('720x520')
    frame = ctk.CTkFrame(root)
    frame.pack(fill='both', expand=True, padx=12, pady=12)
    cats = [b[0] for b in analysis.BANDS]
    unadj = [1, 2, 1, 2, 3, 5, 7, 6, 8, 9, 5, 4, 3]
    adj = [0, 1, 1, 2, 2, 4, 6, 7, 9, 10, 6, 5, 4]
    gc = GradeChart(frame)
    gc.pack(fill='both', expand=True, padx=8, pady=8)
    gc.set_data(cats, [('Unadjusted', unadj, UNADJUSTED_COLOR),
                       ('Adjusted', adj, ADJUSTED_COLOR)])
    cb = ChoiceBars(frame, height=150)
    cb.pack(fill='x', padx=8, pady=8)
    cb.set_data([('A', 3, 'the T tubule'), ('B', 7, 'the sarcoplasmic reticulum'),
                 ('C', 6, 'the sarcolemma'), ('D', 2, 'the myofibril'), ('Blank', 2)], {'B'})
    ctk.CTkSwitch(root, text='Dark', command=lambda: ctk.set_appearance_mode(
        'Dark' if ctk.get_appearance_mode() == 'Light' else 'Light')
    ).pack(pady=(0, 8))
    if auto_close_ms:
        root.after(auto_close_ms, root.destroy)
    root.mainloop()


if __name__ == '__main__':
    _demo(int(os.environ.get('CHARTS_DEMO_MS', '0')) or None)
