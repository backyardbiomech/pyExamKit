# Importing a Canvas quiz

**Import QTI…**, beside **Add Pool File…** on the Build Exam tab, turns a quiz you already built in Canvas into a [question bank file](question-bank-format.md) without retyping it.

## Getting the export out of Canvas

In Canvas, export the quiz or the item bank as QTI and download the `.zip`. Both quiz engines produce a file this reads: Canvas wraps New Quizzes and classic quizzes in the same QTI 1.2 format, so it does not matter which one the quiz was built in.

An item bank export can hold several assessments. They are folded into one bank file, since pyExamKit draws a pool per file and splitting them would only mean adding each one separately.

## Doing the import

Click **Import QTI…** and pick the `.zip`. The app reads the quiz title out of the export and suggests it as the bank filename; choose where to save it. It then writes three things: the bank file itself, an `<filename>_images/` folder holding any images the questions use, and a new pool row on the tab pointing at the file it just wrote, already showing how many questions came through.

From there it behaves like any other pool — set how many questions to draw, set a Pts/Q if you want one, and build.

## What converts and what does not

Multiple choice, multiple answer, true/false, short answer, multiple dropdown, matching, and ordering all convert.

Essay, numerical, fill-in-multiple-blanks, calculated, file upload, text-only, categorization, and hot spot questions have no place on a bubble sheet. Each one is skipped, and **each one is named in the log by its plain-English type**, so the number of questions in the pool can be reconciled against the quiz it came from. A silent drop would be indistinguishable from a bug.

Two conversions are also worth knowing about. A matching question's right-hand labels are renumbered `right1`, `right2`, and so on, because Canvas identifies them with hyphenated UUIDs that the bank format cannot express. And a matching or ordering question that arrives with more items than the six-bubble sheet can hold is trimmed or skipped by the same rules that apply to any bank file — see [Question bank format](question-bank-format.md).

## Read the converted file

**Canvas stores question text as HTML, and the bank format is plain text, so block structure is flattened.** Inline emphasis survives — bold, italic, superscript, subscript — but a table, a nested list, or a paragraph break inside a stem does not, and the result is a stem that reads oddly rather than one that fails loudly. The log says this after every import, and the converted file carries the same warning in a header comment.

The file is ordinary text. Open it, fix what the flattening mangled, and build from the corrected version. It is also now a bank file like any other, so it can be edited, split, merged into an existing pool, or fed back to [qtiConverter](https://github.com/backyardbiomech/qtiConverter) to make a new Canvas quiz.

For the reasoning behind how the reader is built — why it keys on XML structure rather than on Canvas's identifiers, and where the format forced a translation — see [docs/dev/qti-import.md](dev/qti-import.md).

---

Previous: [Building an exam](building-exams.md) · Next: [Answer sheets](answer-sheets.md)
