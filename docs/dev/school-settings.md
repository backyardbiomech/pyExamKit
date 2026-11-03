# School settings: logo, ID label, prefix, ID length

## Goal

Let someone outside Longwood print and scan answer sheets for their own school: their logo, their name for the student ID, their ID prefix (or none), and their ID length. Longwood's values stay the defaults, so nothing changes for anyone who never opens the settings.

## Where the settings live

A new module, `school.py`, reads and writes four keys in the existing per-user config (`~/.pyexamkit_config.json`, through `ai_ocr.load_config`/`save_config`):

| Key | Default | Used by |
|---|---|---|
| `sheet_logo` | `images/longwood_logo.pdf` | every sheet's header; `""` means no logo |
| `id_label` | `Longwood ID number` | the heading over the ID boxes |
| `canvas_id_prefix` | `L` | the letter printed before the ID boxes, the Canvas upload, and roster parsing |
| `id_digits` | `8` | how many ID columns a sheet prints, and how roster IDs are padded |

`canvas_id_prefix` keeps its old key so a prefix already set on the Scan tab carries over. The printed letter and the Canvas prefix are the same fact (how the school writes an ID), so one setting drives both and they cannot disagree.

## The sheet carries its own ID length

The scanner must know how many ID columns a sheet has, and it cannot trust its own setting: a sheet may have been printed before the setting changed, or on someone else's machine. So the length is printed on the sheet, the way the layout already is.

Three new code squares sit in the bottom margin at x = 1040, 1068, 1096 (y = 1532), clear of the layout code (152–252), the exam's "Form X" note (300), the practical's form squares (292–392) and its page note (440), and the bottom-right registration circle (left edge 1132). They hold a 3-bit value:

| Value | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| Digits | 8 | 9 | 10 | 7 | 6 | 5 | 4 |

Blank squares mean 8, so every sheet printed before this change still reads as 8 digits. The classic Illustrator sheet never has these squares read (its layout is fixed at 8). Lengths run 4 to 10; letters inside an ID are out of scope.

The ID block is right-aligned: its last column stays at x = 1100, so an 8-digit sheet's columns sit exactly where they always have (first at 890), and a 10-digit sheet starts at 830, clear of the marking guide (which ends near 690).

`sheet_layout.detect_layout` still returns the shared layout objects (callers compare them by identity). `bubbles.read_sheet` reads the length squares on any generated sheet and swaps in that many ID rows before reading, so the exam, keyed, and practical paths all get it without each knowing about it.

## Roster

`roster.normalize_id` pads to the configured length and strips the configured prefix rather than a hard-coded `L`. `match_id` reports a clear note when a sheet's ID length differs from the roster's, instead of a misleading "not on the roster".

## GUI

A **Sheet settings…** button in the tab row's left corner (Help has the right) opens one dialog (`school_dialog.py`) with the four settings: a logo file picker (PDF, PNG, or JPG; with a Longwood default and a no-logo choice), the label, the prefix, and the digit count. The Standard Sheet dialog's "Longwood logo" checkbox becomes "Logo", meaning the logo set there. The Scan tab's prefix field stays and edits the same setting.

## Logo drawing

The header fits the logo in a box (x 60–420, y 42–115) keeping its aspect ratio, so a square logo does not run into the title at y = 132. PDF logos go through `show_pdf_page`; images through `insert_image`. A logo file that has gone missing prints no logo rather than failing the build.

## Verification

Unit tests: the code squares round-trip for every length; blank squares read as 8; an 8-digit sheet's ID bubbles match the old positions exactly; a rendered 6- and 10-digit sheet, filled synthetically, reads back its ID; the roster pads and strips by the settings. What remains after merge is a real print-and-scan of a non-8-digit sheet.
