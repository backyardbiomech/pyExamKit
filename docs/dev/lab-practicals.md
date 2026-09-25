# Lab practicals: one source, one key, one stack

*Plan written 2026-09-25.*

## The problem

The A&P lab practical has about 25 stations, each with four written questions, A to D. Each student answers two of the four at every station (A and C, say), and the pairing is fixed for that student across the whole exam. Today the exam is written outside pyExamKit, and grading needs one answer sheet and one key per pairing: six keys for AB, AC, AD, BC, BD, and CD. Question 1A appears in three of those keys, so an acceptable answer added to 1A while grading the AB stack has to be copied by hand into the AC and AD keys. The stacks are also scanned and graded separately, six times.

The goal is one source file per practical, from which pyExamKit builds everything the practical needs, and one key that grades a single mixed stack of every form.

## Terms

A **station** is a numbered table. A **question** is one letter at one station (`7C`). A **form** is the set of letters a student answers (`AC`); every station uses the same form for that student. The printed sheet for a form is a **form sheet**.

## The source file

A plain markdown file, readable in any editor or previewer, with images beside it as in the question bank format. Each station is a heading; each question is a letter; `=` lines are full credit and `~` lines partial credit, pipe-separated or one per line.

```markdown
---
title: BIOL 207 Lab Practical 3
forms: AB, CD, AC, BD, AD, BC
points: 1
---

# Station 1
setup: Kidney model, frontal section. Pins A to D.
image: images/kidney_frontal.png

A. Name the structure at pin A.
= renal pelvis
~ pelvis

B. Name the structure at pin B.
= renal pyramid | medullary pyramid

C. Name the structure at pin C.
= renal cortex | cortex

D. What passes through the structure at pin D?
= urine
(2 pts)

# Station 2
setup: Microscope, slide 14 (kidney, H&E), 40x, pointer on a glomerulus.
...
```

`setup:` lines go to the setup guide only; students never see them. `image:` under a station heading prints on that station's placard; under a question, it prints beside that question. A `(2 pts)` line sets one question's points, as in the question bank. `forms:` lists the pairings in the order the builder deals them out (below).

The question bank's own short-answer syntax (starred lettered answers) cannot be reused, because the letters A to D are already the question letters. `=` and `~` stay readable in a markdown preview, where list bullets would all look alike.

## What the builder writes

From the source file, a new **Build Practical** mode writes one folder:

1. **Form sheets**, one PDF per form, plus one combined PDF in dealing order (AB, CD, AC, BD, AD, BC, repeated to a given class size), so a stack handed down a row gives neighbors different forms.
2. **Placards**, one page per station: the station number large, all four questions, and the station's images. All four letters print, since students at one table answer different letters.
3. **The setup guide**, for the instructor and TAs: per station, the setup lines, the images to print, and each question with its accepted answers, so whoever places a pin can confirm it is on the structure the key names. A checkbox column makes it usable as a walk-through list on the day.
4. **An instructor key** PDF, all four letters per station, for reading answers without the app.

Placards and the setup guide use the exam renderer's HTML path, as the exam does. The form sheets are drawn by `answer_sheet.py` from `sheet_layout.py`, so printing and scanning share one geometry.

## The form sheet

Page 1 has the v2 name line and ID block, with no bubbling guide and no version row, since the form is printed rather than bubbled. In the guide's place is a note: answer only the letters printed on this sheet, and only what is written inside each box will be graded, and everything written inside a box will be graded. Below the ID bubbles, each station is a row of two boxes, left for the form's first letter and right for its second, labeled with the station number and letters. Boxes are 72 px tall on an 86 px pitch (0.5 and 0.6 in), close to the old practical sheet's; that fits 11 stations on page 1 and 15 on each later page, so 25 stations take two pages and 41 is the most a sheet holds. Later pages have a name line only.

**The form is printed as small black squares**: four squares, one per letter A to D, inked when the form includes that letter, on the bottom margin beside the layout code squares (`sheet_layout.FORM_CELLS`). Layout codes 3, 4, and 5 mark pages 1, 2, and 3 of a form sheet, so a page from the wrong form, or pages out of order, can be caught rather than graded. Every page carries the three registration circles, the layout code, the form squares, and "Form AC, page 1 of 2" in small print for whoever staples and hands them out.

The printed letters beside each box are for the student; the squares are for the scanner. Nothing about the form comes from anything a student writes.

This also closes the open item in [answer-sheet-redesign.md](answer-sheet-redesign.md) that nothing checks a student used the matching form: on a practical, the sheet *is* the form.

**Reading the ID without answer bubbles.** The reader sets each student's fill level from their answer bubbles, and falls back to an assumed 0.45 when a sheet has too few marks. A practical page has no answer bubbles, so the fallback would set the cutoff at 0.16, above a light pencil mark. On a page with no answer rows, the eight ID marks set the level instead (`bubbles._read_gray`). In a rendered test, a mark scoring 0.12 reads correctly and would have been missed under the fallback. Real light-pencil IDs on this sheet are still unmeasured.

## The key

One key per practical, holding all four letters at every station. Crop boxes are not stored in it: given the form and the station, the box follows from the layout, the same way a v2-keyed sheet's rows follow from `sheet_layout.keyed_layout`. The key carries the station count and the form list as metadata, and question rows `1A` to `25D` with their full and partial answers and points.

The source file is that key (see Decisions): Scan Exams reads it directly, and these values come from its front matter and stations.

## Scanning

The stack goes through Scan Exams in one pass, every form mixed, two pages per student. For each student the scanner reads the form squares on both pages (flagging a disagreement), reads the ID, matches the roster, and knows which 50 of the key's 100 questions apply: `1A, 1C, 2A, 2C, ...` for an AC student.

The written-answer grader runs once for the whole stack rather than once per version. Today `OpenQs` takes one crop box per question for every student. For a practical, the box depends on the student's form (1A is the left box on an AB sheet and the left box on an AC sheet, but 1C is the right box on an AC sheet and the left box on a CD sheet), and each question applies to only half the students. That generalization is the main structural change in `openQ.py`: crop coordinates per question and form, and a per-question list of the students it applies to. AI transcription batches per question over that subset, as now.

Results: one `results.csv` with a column per question, blank (not zero) where the question was not on the student's form, one Canvas upload, and per-question statistics by letter. Adding an acceptable answer to 1A upgrades every student who answered 1A, whatever their form, because there is only one 1A.

## The grading window

**Order.** The window already works question by question, every student in turn, which is what is wanted. The order of questions becomes station, then letter: all of 1A, all of 1B, 1C, 1D, then 2A. The existing sort (`keyformat._openq_sort_key`) already gives that order, 1A to 1D, then 2A, with 10A after 9D; the change is that each question's pass covers only the students whose form includes it.

**Who wrote it.** The window gains a line naming the student: the roster name matched from the ID, or the scanned ID when there is no match, with a crop of the handwritten name line from the top of page 1 beside it. The name crop is shown on screen only. It is never sent for transcription; only the answer boxes are, as now.

**Accommodations.** The grader applies spelling accommodations by name; the app does not track them.

## What does not change

Bubble exams, the question bank format, v2 and v2-keyed sheets, and multi-version bubble grading are untouched. The existing practical sheets and their six per-form keys still scan and grade as they do today, one stack per form, since those sheets carry no form code.

## Decisions (2026-09-25)

1. **The source markdown file is the key.** Scan Exams loads the `.md` directly, and answers added while grading are written back into it as new `=` or `~` lines under the question, leaving everything else in the file as it was. Next year's build starts with this year's answers.
2. **Spelling accommodations are handled by the grader.** The window shows the roster name and the handwritten name crop; there is no roster flag and auto-acceptance is unchanged.
3. **Practicals are written as source files directly.** APexams is not imported from.
4. **Old keys get a one-time import.** A tool folds a past practical's per-form CSV keys into one source file, with the question text left for the instructor to fill in.

## Order of work

1. Source parser and model (`practical.py`), with tests, including writing added answers back into the file without disturbing it. The per-form key import tool.
2. Form sheet layout and drawing, with the form and page squares; scanner detection of both. Print one and check it by eye and by scanning it.
3. Placards, setup guide, instructor key, and the Build Practical UI.
4. Scanner: one pass, per-student form, per-question student subsets, form-dependent crops in `OpenQs`.
5. Grading window: station-then-letter order, name line and name crop.
6. Results and Canvas output, Re-grade tab against the practical key.
7. User documentation (`docs/lab-practicals.md`) and a test stack: a filled set of sheets, two per form, scanned.

## Registration at reduced print scale (2026-09-25)

The department's office printer shrinks answer sheets to as low as 85% to fit the registration circles inside its margins. `scan_functions.getRegPts` accepted a circle only between 0.8 and 1.2 times the full-size area as it measures it (about 1224 px of 1385). At 85% a circle measures about 1000 before blur, near the floor, and a blurred circle scanned 1.5% large measured 1470, over the ceiling; the synthetic stack found the second. Checking the old finder also showed that on a slightly blurred v2 sheet it took the Longwood logo's emblem for a circle, because it kept the first three blobs by size rather than by shape and position.

The finder now accepts 0.45 to 1.6 times the full-size area (about 67% to 125% print scale), keeps only round, solid blobs, and of the eight largest candidates takes the three with the most similar sizes whose arrangement best matches the printed right triangle. On the four real scans in `tests/scannedSheets.pdf` it returns exactly the old points. `tests/test_registration.py` checks the classic, v2, and practical sheets at 80%, 85%, 92%, 100%, and 103% with blur; the old finder failed at 80% and 103% on all three and misplaced a point on v2 and practical sheets at 85% and 100%.

## Status

Steps 1, 2, and 4 are built, with steps 5 and 6 folded into step 4 where they were small. Step 3 (placards, setup guide, instructor key, and the Build Practical UI) is next, then step 7.

- **Step 1**: `practical.py` (parser, validation, `to_key_data`, `sync_answers`), `keyformat` loading and saving a practical `.md`, `tools/practical_from_keys.py`.
- **Step 2**: practical geometry and `read_form` in `sheet_layout`, `answer_sheet.build_practical_sheet`, and `practical_build.py` writing each form's sheet and a combined dealing-order PDF. `tools/make_practical_test_stack.py` fills sheets in software and degrades them like a copier scan, printed at 85% by default. No sheet has been printed or scanned on real hardware.
- **Step 4**: `Scanner._run_practical` and `practical_scan.py`. Pages are grouped into students by their printed page code and form, so a missing or foreign page raises an alert without shifting later students. `OpenQs` takes `locate` and `student_info` hooks: each question is graded across only the students whose form has it, station by station, and the window shows the roster name, the handwritten name line, the question text, and the position within the question (3 of 24). Results carry a `form` column and leave off-form questions blank; scores, the gradebook, and the Canvas file come from the existing `gradeResults`. Marked sheets carry C, P, or X in each graded box and the form and score on page 1. Answers added while grading, or later on the Re-grade tab, are written back into the `.md`. The Scan Exams key chooser accepts a `.md`.
- **Grading window redesign** (after the first look at it): the student's answer and the key's answers side by side, each shown once and labeled; the AI reading demoted to a gray line under the handwriting; color only on the suggested grade button, with a sentence saying why (`ocr.explain_suggestion`). The student's answer or a typed answer can be added to the key as full or partial credit, and double-clicking a key answer edits it; each re-checks earlier students (`OpenQs._upgrade_earlier`). Driven in Tk here and checked widget by widget, but not seen, since screen capture is blocked in this environment.
- **Tested** on synthetic stacks only (`tests/test_practical_scan.py`, five students printed at 85%), with the grading window replaced by a stand-in, because Tk does not start in the environment this was built in. **The real grading window with the new name and question lines has not been seen.** Nor has **Edit…** on a practical key; it should load and save answers, but its box-drawing tools mean nothing for a practical.
