# Outputs

Everything a scan produces lands in an **`ExamScanner_outputs/`** folder inside the folder holding the scans. Files you are meant to use sit at the top level; files the app uses to do its work sit in `app_data/` and can be deleted once you have what you need.

## The results

**`results.csv`** is the main output: one row per student, with every answer they gave, their score, and their partial score (this "partial" refers only for select all that apply bubble questions). The **score** column is the total without partial credit and **partialscore** includes it, so a comparison of the two shows what partial credit was worth on this exam. The last row, `numb_correct`, gives the number of students who answered each question correctly, which is the row to read for item analysis. The first row is the key itself.

**`resultsperquestions.csv`** has the same shape but holds the points each student earned on each question instead of the answers they gave. It exists so that the arithmetic behind a score is visible, which matters when a student asks.

**`resultsforCanvas.csv`** is a stripped-down upload file: last name, first name, student ID, and the "partial score", sorted by name, with the key and the statistics row removed.

**`results_gradebook.xlsx`** is the working copy. Each question gets an answer column and a points column, the key is on a highlighted row at the top, and **each student's total is a live `SUM` formula** — so changing a points cell after a regrade discussion updates the total immediately, without recomputing anything by hand. The key row shows the acceptable answers for open-ended questions, pipe-separated.

**`ALERT.txt`** appears only when something needs attention. It names every student and question where no answer could be read at all. The usual cause is a badly scanned sheet rather than a skipped question, so this is the file to check before entering grades.

## The marked sheets

**`marked/`** holds one JPG per student, named from the last name, first name, and student ID, and marked with that student's results. These are made to hand back electronically if you want. In Canvas, open the exam assignment in SpeedGrader, find the comment box for each student, and attach their file — on a Mac you can drag the file from the Finder directly onto the attach button.

Two students with the same name and no ID would produce the same filename, and the second would overwrite the first.

**`marked.pdf`** is every marked sheet including the key, in one file, for your own records.

The marks mean:

- a green **C** on a correct answer
- a red **X** on an incorrect answer
- a red **M** beside a question number where a correct answer was **missing** from the student's marks

The M only appears when select-all-that-apply grading is on, and then it appears on single-answer questions too. Expect to explain it: a student who marked B when the answer was A gets a red X on B *and* a red M for having missed A. On a genuine select-all question a student can collect green C's, red X's, and a red M all on one question.

## Multiple versions

When a mixed stack is graded by version, the outputs are written per version instead: `results_versionA.csv`, `marked_versionA/`, `marked_versionA.pdf`, and so on for each version present in the stack.

## app_data/

**`aligned/`** holds every page after skew and scale correction. These are what the **Skip alignment** option reuses, so keeping them makes a second pass at a different fill threshold nearly instant. They are also unmarked copies of every sheet, which is worth keeping if you want to delete the original scans.

**`scanJPGs/`** holds the page images extracted from a scanned PDF. The app converts a PDF to images and works on those.

**`results_openq_transcriptions.json`** holds every handwriting transcription, and **`results_openq_answers.json`** holds the acceptable-answer lists as they stood at the end of grading. Together they are what makes the [Re-grade](open-ended-questions.md#re-grading-afterward) tab possible without rescanning. **`results_openq_gradeconfig.json`** records the grading settings that run used, and a `results_openq_progress.json` appears mid-run so an interrupted session can be resumed; it is removed when grading finishes.

Delete `app_data/` and the results stay valid, but re-grading open-ended questions and fast threshold re-scans are no longer possible.

---

Previous: [Open-ended questions](open-ended-questions.md) · Next: [FAQ and troubleshooting](faq.md)
