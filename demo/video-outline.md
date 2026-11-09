# pyExamKit video outline

Ten clips, about 50 minutes in all. Each stands alone, so a colleague can watch only the one they need. Clip times are rough. Clips 2 to 9 use the invented data in `demo/film/`; every name and ID there is made up, so any of it can be on screen.

| # | Clip | Time | Folder in `demo/film/` |
|---|---|---|---|
| 0 | What it does and where to start | 2 min | none |
| 1 | Download, install, first-time setup | 3 min | none |
| 2 | Write a question bank | 5 min | `1_bubble_build/` |
| 3 | Build a bubble exam | 6 min | `1_bubble_build/` |
| 4 | Grade a bubble exam | 7 min | `2_bubble_grade/` |
| 5 | Fix and export grades (Results tab) | 7 min | continues clip 4 |
| 6 | Written answers, on screen and on Results | 7 min | `3_written/` |
| 7 | Build a lab practical | 4 min | `4_practical/` |
| 8 | Grade a lab practical | 6 min | `4_practical/` |
| 9 | An exam made somewhere else (Standard Sheet) | 4 min | `5_standard_sheet/` |

## Before filming

Run this once before the first take and again between takes. It wipes `demo/film/` and rebuilds it, which undoes everything a take changed: keys edited while grading, answers written back into the practical source, results, and Results-tab edits.

```bash
uv run python tools/make_demo_data.py
```

Film with the packaged v3.9.0 or later, so the window title and icon match what colleagues will download and the marked sheets show the current marks. Close anything with student data, and clear the file dialog's recent-items list. Paste the API key off camera, or leave the "show" box unchecked; the field is masked by default. AI transcription bills your Anthropic account a small amount per take.

`demo/film/cues.csv` lists every planted problem by scan number, for use off camera.

The questions were written for the demo and are not source-checked. They are fine as props but should not reach students. Question 6 in `skin.md` is deliberately miskeyed.

## Clip 0: What it does and where to start

**Have open:** [README, Where to start](https://github.com/backyardbiomech/pyExamKit#where-to-start)

- One app replaces the Scantron workflow: build, print, scan, grade, Canvas
- Tour the five tabs in one pass, without clicking into any
- "Where to start" chart from the README: practical, question bank, Canvas quiz, or exam made elsewhere
- Every path goes through Scan Exams and ends at Results
- Point at the Help button: each tab opens its own guide page

## Clip 1: Download, install, first-time setup

**Have open:** [Latest release](https://github.com/backyardbiomech/pyExamKit/releases/latest) · [Installation](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/installation.md) · [Handwriting transcription](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/open-ended-questions.md#handwriting-transcription) · [Anthropic console](https://console.anthropic.com) (signed out, so no account shows)

- Releases page, latest release
- **Mac:** DMG, drag to Applications, the `xattr -cr` step before first open, why that step exists
- **Windows (instructions only, not filmed):** a text card with the steps: extract the zip, keep the folder together, run `PyExamKit.exe`, SmartScreen "More info / Run anyway"
- First launch: the window, the log at the bottom
- **Sheet settings…**: logo, ID label, prefix, digits; Longwood defaults need no change
- **Configure API Key…**: only needed for handwriting transcription; where to get one; images sent are crops only

## Clip 2: Write a question bank

**Have open:** [Question bank format](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/question-bank-format.md)

Open `1_bubble_build/skin.md` in a text editor next to the docs page.

- A bank is a plain text file; one question per block, blank line between
- The shape of a block: optional type line, image line, points; numbered stem; lettered answers; `*` marks correct
- Walk the types in `skin.md` and `skeleton.md`: MC, MA, TF, ordering, matching, dropdown
- Comments with `#`
- Limits worth stating: six choices, 150 rows, ordering and matching use one row per item
- Image question (`skin_layers.png`): single-letter choices stay in order so bubble A means label A
- Mention the same file also feeds qtiConverter for Canvas

## Clip 3: Build a bubble exam

**Have open:** [Building an exam](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/building-exams.md) · [Importing a Canvas quiz](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/importing-canvas-quizzes.md)

Build into `1_bubble_build/`. The title and course are `Exam 1` and `DEMO 101`.

- Question Pools: add `skin.md` (pull 12 of 13) and `skeleton.md` (pull 8 of 10); the running total of questions and points
- Three layers of points: bank, pool, exam default
- Two versions, shuffle questions and answers, "Use same questions across all versions" and why
- Skip the version identifier question; the new sheets have version bubbles
- Generate; read the log aloud as the habit to build
- Open the output folder: exam HTML and PDF per version, one answer sheet, one key per version, `.exam.json`
- Printing: 100%, double-sided exam, answer sheets separate
- Reprinting: Load Config for a large-print copy (font size), or uncheck for a make-up with new questions
- **Import QTI…** aside (optional cut): `canvas_quiz_export.zip` becomes a pool; the log names the five questions it skipped; open the file and check it. The sample's text is test filler, so consider a real export of your own

## Clip 4: Grade a bubble exam

**Have open:** [Scanning and grading](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/scanning-and-grading.md) · [Class rosters](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/roster.md) · [Outputs](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/outputs.md) · [The marked sheets](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/outputs.md#the-marked-sheets)

An exam built on camera shuffles differently from the prebuilt one, so grade the prebuilt `2_bubble_grade/Exam_1/`. To grade the one you just built instead, run the command below and use the stack it writes beside the build.

```bash
uv run python tools/make_demo_data.py --refill demo/film/1_bubble_build/Exam_1
```

- Scanning advice, in one line: the whole stack to a single PDF, 200 dpi, grayscale is fine, in a folder of its own
- **Choose key files…**: pick `Exam_1_vA_key.csv`; the vB key is found beside it; read the summary line
- **Choose scans…**: the single PDF `scans/Exam_1_scans.pdf`, 24 students, both versions mixed
- **Load Class Roster…**: `class_roster.csv`, in the shape of a Canvas gradebook export; show how to get one from Canvas
- More options: leave alone, name the fill cutoff
- Scan and Grade. Two windows interrupt the run, both worth keeping:
    - Scan 5 (Juniper, Avery): ID not on the roster; the "Who is scan 5?" window shows the handwriting; type the name
    - Scan 8 (Oakley, Emerson): no version bubble; the window asks which version; choose B
- Open `ExamScanner_outputs/`, then `ALERT.txt` line by line:
    - Scan 2 (Birch): light marks, check by eye
    - Scan 3 (Cedar): Q15 erasure the scanner flags as a check mark; two other erasures read as erased with no flag
    - Scan 4 (Hawthorn): ID one digit off, corrected
    - Scan 6 (Linden): Q5 left blank
- Marked sheet for Cedar: green right, red X wrong, blue `#` on the answer they should have marked
- `gradebook.xlsx` in Excel: one tab per version, By question, Item analysis, Exam stats

## Clip 5: Fix and export grades (Results tab)

**Have open:** [The Results tab](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/results.md) · [Item analysis, in Outputs](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/outputs.md#the-results)

Continues from clip 4's scan. Open the Results tab on `2_bubble_grade/scans/ExamScanner_outputs/`.

- Summary: class stats, grade chart, per-version columns
- Questions: sort by discrimination. Two planted problems surface:
    - *Arrector pili* (A24, B26): negative discrimination, as many students chose B as the key. Selecting it shows why. The key is wrong: **Change key** to `B` with a note
    - *Eccrine sweat glands* (A1, B2): low discrimination, strong students chose B. Defensible: **Also accept** `B` with a note
- Keys are typed in the bank's letters, and the view maps every version back
- Students: Pine, Harper (scan 9) has about 6 of 20, having bubbled B after taking A. **Scored as version** A brings it to about 19
- One student's points for a regrade request; points added for a curve
- Edits view: every change, its note, undo by deleting
- **Export** rewrites `gradebook.xlsx` and `canvas_upload.csv`
- `canvas_upload.csv` is the file to import to Canvas; name it and move on, no import demo
- Marked sheets are not redrawn after a key change

## Clip 6: Written answers, on screen and on Results

**Have open:** [Open-ended questions](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/open-ended-questions.md) · [Written answers on the sheet](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/answer-sheets.md#written-answers-on-the-sheet) · [Changing the key afterward](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/open-ended-questions.md#changing-the-key-afterward)

Key: `3_written/Quiz_2/Quiz_2_vA_key.csv`. Scans: `3_written/scans/Quiz_2_scans.pdf`, 14 students. Roster: `class_roster.csv`. A 12-question quiz: 8 bubbled at 1 point each and 4 written at 2.

- The bank: an `SA` block, starred answers full credit, unstarred partial
- The answer sheet: writing boxes appear on their own, and the key knows where they are
- Scan tab: Grade written answers on screen, Use AI OCR, model, exam context (anatomy preset)
- What leaves the computer: crops of the writing and an anonymous index
- The grading window, about 18 answers once exact matches are skipped:
    - Left the student's writing, right the key; suggested grade is the colored ring; `c`, `p`, `x`, `b`, Enter
    - A misread answer: the AI's reading is in a field under the handwriting; press `e`, fix it to what the student wrote, Enter; the suggestion updates. Readings vary by take ("acetylcholine" came back as "acetulcholine" in the first filming), so use whichever misreading turns up
    - Question 11: several students wrote "ACh". **Add to key as full credit**, and earlier students are re-checked and upgraded
    - Question 9: three students wrote "stratum germinativum", which is not in the key. Mark them wrong for now
- Interruptions: closing mid-way offers to resume
- **Results** tab, **Written** view: on question 9, click a reading of "stratum germinativum" and **Add full**; those three are upgraded on every version; nothing rescanned, nothing billed; delete the edit to take it back
- **Remove** on an answer that came with the key: a key error, so everyone who wrote exactly that answer loses the credit; delete the edit to bring it back

## Clip 7: Build a lab practical

**Have open:** [Lab practicals, the source file](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/lab-practicals.md#the-source-file) · [Printing and handing out](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/lab-practicals.md#printing-and-handing-out)

Source: `4_practical/Demo_Practical.md`, twelve stations, so each form sheet is two pages: one piece of paper, printed on both sides.

- The idea: four questions per station, two per student, the pair is the form, neighbors share nothing
- The source file in a text editor: settings block, `# Station`, `setup:`, `image:`, questions, `=` full and `~` partial
- Why one file is better than a key per form
- Build Practical tab: source, output folder, class size 10; Build
- The output folder: form sheets, combined sheet, placards, setup guide, instructor key
- Hold up the setup guide and instructor key as the two to keep from students
- Printing: double-sided, no staples, forms dealt in order

## Clip 8: Grade a lab practical

**Have open:** [Lab practicals, scanning and grading](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/lab-practicals.md#scanning-and-grading) · [What the results hold](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/lab-practicals.md#what-the-results-hold)

Key: `4_practical/Demo_Practical.md` (the source file itself). Scans: `4_practical/scans/scans.pdf`, 10 students, 20 pages. Roster: `4_practical/practical_roster.csv`.

- The key's summary line says it is a practical; forms come from the printed squares, never from the student
- Each student is two pages, front and back; the scanner groups them by what is printed on each page, so each student's page 1 has to stay ahead of their page 2
- Grading window goes by station and letter, about 85 answers with AI on and exact matches skipped (cut the middle)
- The name crop beside each answer
- A misread answer: press `e`, fix the reading to what the student wrote, Enter; the suggestion updates
- Add an answer in the window; open `Demo_Practical.md` to show it written back as a new `=` line
- An answer accepted later on the **Written** view of Results is written back the same way (mention, no need to film)
- `ALERT.txt`: scan 2 (Linden) light pencil, scan 5 (Birch) one digit off the roster
- Marked sheet: form and score on page 1, each box's points beside it. Spruce has a crossed-out answer, and Cedar's box 3C shows writing that runs past the box
- Results: a `form` column; blank, not zero, for questions not on a form; points possible is one form's

## Clip 9: An exam made somewhere else (Standard Sheet)

**Have open:** [Answer sheets](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/answer-sheets.md) · [The Standard Sheet tab](https://github.com/backyardbiomech/pyExamKit/blob/main/docs/building-keys.md#the-standard-sheet-tab)

All in `5_standard_sheet/`. A 20-question exam that was not built here.

- **Make Answer Sheet…**: 20 questions, heading, save (a copy is at `blank_answer_sheet.pdf`)
- Fastest route, once-only: `key_first/stack_with_key_first.pdf`, no key file, 20 questions, Scan. The first page is read as the key, and `exam_key.csv` is written for next time
- Reusable route: **Build Key from Exam Scan…**, Instructor-filled mode, 20 questions, `key_scan/filled_key_sheet.pdf`, Save as CSV; then grade `with_key_file/students_only.pdf` against it
- Blank sheet mode: draw boxes for written answers. Name it; no need to film
- Close on the rule for modifying a sheet: cover things up, never move anything

## Not covered, on purpose

The Windows install on screen, a physical scanner, the Canvas import itself, scanning to JPGs, running from source, building the app with PyInstaller, the older sheets with name bubbles, `practical_from_keys.py`, and the key CSV's column-by-column format. Each is in the docs.
