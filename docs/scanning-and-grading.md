# Scanning and grading

The **Scan Exams** tab reads a stack of completed answer sheets, grades them, and writes the results. Everything it produces is described in [Outputs](outputs.md).

## Scanning the sheets

Scan at **200 dpi or better, in color**. Put every scan in a folder containing nothing else, since the app treats the folder as the job.

You can scan the whole stack to a single PDF, or to a folder of JPGs. **JPGs are the safer choice for a large stack**, because a page that scanned badly can be rescanned and dropped into the folder, while a PDF has to be remade.

If you are not loading a key file, **the key sheet goes first in the stack**. With a key file loaded, the stack is students only.

## Setting up the run

**Load Key File…** picks the key CSV — either one the [Build Exam](building-exams.md) tab wrote or one from the [Build Key](building-keys.md) tab. Loading it fills in the question count and the skip list from the key's own metadata, so those fields agree with the key by construction. **Create / Edit…** opens the same file for editing.

**Choose PDF of scans or JPG of key** points at the scans. Select the PDF, or select the first JPG with the rest in the same folder.

**Number of questions to grade** is the last question number to read. **Question numbers to ignore** is a comma-separated list of rows to skip — the rows you covered over on the sheet, or the ones holding a written answer. A row that is ignored is neither graded nor counted.

**Pages per student** matters for a multi-page exam, where each student's sheets have to be grouped together.

**Points per bubble question** and **points per open-ended question** set the default value of each. A per-question `points` value in the key file overrides both, so a key built from an exam carries its own weighting.

**Fill threshold** decides how dark a mark has to be to count as filled. The default of 0.25 suits ordinary pencil. Lower it toward 0.20 to catch light marks; raise it toward 0.30 to ignore incomplete erasures. This is the setting to revisit when a scan produces a suspicious number of blank answers, and the **Skip alignment** checkbox exists to make that cheap — it reuses the aligned images from the previous run, so a second pass at a different threshold takes seconds instead of reprocessing every page.

**Save marked answer sheets** writes the annotated copies; turn it off to save time when you only need the numbers. **Mark correct answers on graded sheets** adds the green marks as well as the red ones.

Then click **Run Scan**.

## Select all that apply

Checking **Select-all-that-apply questions?** changes how *every* question is graded, not just the multi-answer ones, and it turns on the "missing answer" mark described in [Outputs](outputs.md).

With it off, a question is right or wrong: an answer that exactly matches the key earns the question's points and anything else earns zero.

With it on, partial credit applies. If *n* is the number of correct answers on the key, *c* is the number of correct answers the student selected, and *i* is the number of incorrect ones, the score is **c(1/n) − i(1/n)**, floored at zero and scaled by the question's point value. A question with three correct answers where the student picks two of them and one wrong one earns 0.66 − 0.33 = 0.33 of the points.

**A single-answer question still grades as all-or-nothing under this rule**, which is worth understanding rather than discovering. If the key is A and the student marks A and B, then n = 1, so the correct answer earns one point and the incorrect one costs one point, and the student gets zero.

## Multiple versions

Check **Multiple exam versions?** to grade a mixed stack in one pass. Give the **version question number** — the question where students bubble their version letter, which the [Build Exam](building-exams.md) tab can add for you — and a key file for each version in use. Leave a version's key blank if that version was not printed.

Each student's version bubble is read, and each version group is graded against its own key. Results are written per version: `results_versionA.csv`, `marked_versionA/`, and so on.

When a student's version bubble cannot be read — left blank, or two letters filled — a dialog shows that student's sheet and asks you to assign a version by hand, or to skip the student. Skipped students are named in the log and appear in no version's results, so they have to be dealt with separately.

## Written answers

If any question is answered in writing rather than in bubbles, check **Open-ended questions to grade on-screen?** and see [Open-ended questions](open-ended-questions.md), which covers the whole of that workflow.

Remember to also list any mid-exam written question in **Question numbers to ignore**, or its untouched bubble row is graded as a wrong answer.

## How a bubble becomes an answer

The scanner locates the three registration circles on each page and warps the image to a fixed size, correcting skew and scale. It reads the four calibration bubbles on the outside to learn how dark a filled bubble looks on this scan, then measures each answer bubble against the fill threshold. Anything at or above the threshold counts as marked, so multiple marks on one row produce a multi-letter answer such as `ABD`, and a row with nothing above the threshold produces `-`.

A `-` is not silently treated as a wrong answer. Every student with an unscanned answer is written to an `ALERT.txt` file beside the results, naming the student and the question, because the usual cause is a sheet that scanned badly rather than a student who skipped a question.

---

Previous: [Building a key](building-keys.md) · Next: [Open-ended questions](open-ended-questions.md)
