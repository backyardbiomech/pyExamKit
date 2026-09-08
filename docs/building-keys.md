# Building a key

Grading needs a key: which bubble is correct for each question, where on the page each written answer sits, and what counts as a correct answer there. There are three ways to get one.

**Build the exam here and the key comes with it.** The [Build Exam](building-exams.md) tab writes `Title_vA_key.csv` beside each version. Load it on the Scan Exams tab and you are done. This is the path to prefer, since the key cannot disagree with the exam it came from, as long as your exam files were correct.

**Scan a sheet you filled in yourself.** The **Build Key** tab reads an answer sheet you bubbled by hand and turns it into the same CSV. Use this for an exam that was not built by this app.

**Put the key sheet at the front of the stack.** The scanner will read the first page as the key. This is the oldest workflow and it still works, but it produces no reusable file, so the key has to be re-read on every scan.

## The Build Key tab

Pick a mode, set the options that appear, and click **Build Key from Exam Scan…** to open the builder on your scanned sheet.

**Blank sheet** mode is for marking where the **written answers** go, and nothing else. Load a blank sheet — a PDF, which can run to several pages, each of which needs the three registration circles— draw a box around each answer area, and save. You then type the bubble answers in afterward, either in this dialog or in a spreadsheet. This is the mode for an exam that is mostly or entirely written answers.

**Instructor-filled sheet** mode is for a sheet you bubbled in as the key. Tell it **how many bubble questions** to read and **which question numbers to skip** — the rows you covered over or reused, comma-separated — and the bubbles are read automatically as each page loads. Then draw boxes around the written-answer areas and click **Scan handwriting (OCR)** to have your own handwriting transcribed into the answer fields. That last step needs [AI transcription configured](open-ended-questions.md#handwriting-transcription); check **Use AI OCR** and set an exam context to enable it.

## Inside the key builder

The builder shows the aligned page on the left and the question list on the right.

Add pages with **Add page**, and step between them with the previous and next controls; a multi-page exam keeps each question's page number with its coordinates. Drag on the image to draw a box around an answer area, which creates a new open-ended question. **Undo last box** removes the most recent one — boxes cannot be edited in place, so a badly drawn box needs to be removed and redrawn.

Select any question in the list to edit it. An open-ended question has two answer lists: **full credit** answers and **partial credit** answers. Every string in either list is compared against what the student wrote, so this is where you decide how generous the grading is. Listing "stratum basale" and "basal layer" as full credit and "stratum basil" as partial is a perfectly ordinary key if you are a little generous with spelling.

Bubble questions can be added, removed, and edited by hand in the same panel, which is how a blank-sheet key gets its multiple choice answers.

**Save as CSV** writes the key. It records the number of bubble questions and the list of skipped questions as metadata rows, so loading the key back on the Scan Exams tab fills those fields in for you.

## Editing an existing key

**Create / Edit…**, next to the key file field on the Scan Exams tab, opens the same key in a lighter editor: add or remove questions, change acceptable answers, redraw a coordinate box against a page image, and save in place or save as a copy. Use it when a key is nearly right — when one question's answer was wrong, or when an answer box was drawn a little too tight.

Note that acceptable answers also get written back to the key file *during* grading. If you add an alternative answer while grading open-ended questions, and you are grading against a key file, that answer is saved to the key as you go. The key you finish a scan with is more permissive than the one you started with, which is what you want the next time the same exam is used.

## The key CSV format

The key is an ordinary CSV with a header row, so it can be opened and edited in any spreadsheet app. It has ten columns:

```
type, question, page, x1, y1, x2, y2, answer, partial_answers, points
```

**`type`** is `metadata`, `bubble`, or `open`. A row with a blank type, or a type starting with `#`, is ignored, which makes comment rows possible.

**Metadata rows** carry the settings the Scan Exams tab fills in for you. `num_questions` holds the bubble question count and `questions_to_skip` holds the comma-separated skip list, each with its value in the `answer` column.

**Bubble rows** name the question in `question` — `Q001`, or just `1`, which is normalized on read — and put the correct letters in `answer`. Multiple letters run together with no separator: `ABD`. The coordinate columns stay empty. `points` is the value of that question, and it is what the grader uses; leave it blank and the question falls back to the exam-wide points-per-bubble-question setting.

**Open rows** name the question as `openQ_1` (or just `1`) and carry the crop rectangle in `page`, `x1`, `y1`, `x2`, `y2`. The `answer` column holds the full-credit answers and `partial_answers` holds the partial-credit ones, **each pipe-separated**: `stratum basale|basal layer`. That is the layout to use if you would rather type a key in a spreadsheet than draw it in the builder.

Files are written as plain UTF-8 without a byte-order mark, and read tolerantly: a nine-column key with no `points` column still loads, and simply yields no per-question point values.

---

Previous: [Answer sheets](answer-sheets.md) · Next: [Scanning and grading](scanning-and-grading.md)
