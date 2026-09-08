# Importing a Canvas quiz

**Import QTI…**, beside **Add Pool File…** on the Build Exam tab, turns a quiz you already built in Canvas into a [question bank file](question-bank-format.md) without retyping it.

## Getting the export out of Canvas

In Canvas, export the quiz QTI and download the `.zip`. On the quiz you will see export, maybe without options. That's the one. There is no way to export an Item Bank under new quizzes. So make a quiz that contains every item in the bank, and export that quiz.


## Doing the import

Click **Import QTI…** and pick the `.zip`. The app reads the quiz title out of the export and suggests it as the bank filename; choose where to save it. It then writes three things: the bank file itself, an `<filename>_images/` folder holding any images the questions use, and a new pool row on the tab pointing at the file it just wrote, already showing how many questions came through.

From there it behaves like any other pool — set how many questions to draw, set a Pts/Q if you want one, and build.

## What converts and what does not

Multiple choice, multiple answer, true/false, short answer, multiple dropdown, matching, and ordering all convert.

Essay, numerical, fill-in-multiple-blanks, calculated, file upload, text-only, categorization, and hot spot questions have no place on a bubble sheet. Each one is skipped, and **each one is named in the log by its plain-English type**, so the number of questions in the pool can be reconciled against the quiz it came from. 


Two conversions are also worth knowing about. A matching question's right-hand labels are renumbered `right1`, `right2`, and so on, because Canvas identifies them with hyphenated UUIDs that the bank format cannot express. And a matching or ordering question that arrives with more items than the six-bubble sheet can hold is trimmed or skipped by the same rules that apply to any bank file — see [Question bank format](question-bank-format.md).

## Read the converted file

**Canvas stores question text as HTML, and the bank format is plain text, so block structure is flattened.** Inline emphasis survives — bold, italic, superscript, subscript — but a table, a nested list, or a paragraph break inside a stem does not, and the result is a stem that reads oddly rather than one that fails loudly. The log says this after every import, and the converted file carries the same warning in a header comment.

The file is ordinary text. Open it, fix what the flattening mangled, and build from the corrected version. It is also now a bank file like any other, so it can be edited, split, merged into an existing pool.


---

Previous: [Building an exam](building-exams.md) · Next: [Answer sheets](answer-sheets.md)
