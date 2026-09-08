<img src="images/AppIcon.png" width="96" alt="pyExamKit icon">

# pyExamKit

A desktop app for building bubble-sheet exams from question banks, then scanning and grading them. Both halves — building and grading — share one file format and one download; there is nothing else to install.

Written by Brandon E. Jackson, Ph.D. Licensed under [GPLv3](LICENSE).

---

## What it does

The app opens to one window with four tabs, sharing a single log at the bottom.

**Build Exam** turns one or more plain-text question banks into a printable exam — multiple choice, multiple answer, true/false, short answer, multiple dropdown, ordering, and matching — in up to six scrambled versions, with an answer key CSV the scanner grades against. It can also import a Canvas QTI export, so a quiz that already exists in Canvas becomes a paper exam without being retyped.

**Build Key** produces that same key CSV from a scanned answer sheet, either by reading the bubbles you filled in by hand or by letting you mark where the handwritten answers sit on the page.

**Scan Exams** reads a stack of completed answer sheets, grades them against the key, and writes out a results spreadsheet, a per-question breakdown, a Canvas-ready upload file, and a marked copy of every student's sheet.

**Re-grade** re-runs the open-ended grading against transcriptions already on disk, so a key that turns out to have been too strict can be loosened without rescanning anything.

## Documentation

1. [Installation](docs/installation.md) — download a packaged app, or run from source
2. [Question bank format](docs/question-bank-format.md) — how to write the plain-text file the exam is built from
3. [Building an exam](docs/building-exams.md) — the Build Exam tab: pools, versions, shuffling, and what it writes out
4. [Importing a Canvas quiz](docs/importing-canvas-quizzes.md) — turning a QTI export into a question bank
5. [Answer sheets](docs/answer-sheets.md) — the printable sheets, and how far you can modify them
6. [Building a key](docs/building-keys.md) — the Build Key tab, plus the key CSV format
7. [Scanning and grading](docs/scanning-and-grading.md) — the Scan Exams tab and how each score is calculated
8. [Open-ended questions](docs/open-ended-questions.md) — handwriting transcription, on-screen grading, and re-grading
9. [Outputs](docs/outputs.md) — every file the app writes and what to do with it
10. [FAQ and troubleshooting](docs/faq.md)

Design notes and implementation history live in [docs/dev/](docs/dev/). They document why parts of the app are built the way they are, and are aimed at anyone modifying the code rather than at anyone using it.

## Related

The question bank format is shared with [qtiConverter](https://github.com/backyardbiomech/qtiConverter), which converts the same plain-text file into a Canvas QTI package. One bank file can feed both a paper exam and a Canvas quiz.
