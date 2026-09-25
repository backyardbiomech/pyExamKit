# Outputs

Everything a scan produces lands in an **`ExamScanner_outputs/`** folder inside the folder holding the scans. Files you are meant to use sit at the top level; files the app uses to do its work sit in `app_data/` and can be deleted once you have what you need.

| File | What it is for |
|---|---|
| `gradebook.xlsx` | Every answer and every point, with live totals and an item analysis of each question |
| `canvas_upload.csv` | Import into the Canvas gradebook as is |
| `ALERT.txt` | Sheets and marks to check before entering grades; only there when something needs checking |
| `marked/`, `marked.pdf` | Each student's sheet marked right and wrong |
| `exam_key.csv` | Only when the key was scanned rather than loaded: the key, to load next time instead of scanning it again |

A scan into a folder that already holds an earlier run's outputs replaces these files, but leaves anything an older version of the app wrote there (`results.csv`, `resultsforCanvas.csv`, `results_gradebook.xlsx` and the like). Delete those so they are not mistaken for the new results.

## The results

**`gradebook.xlsx`** is the working copy of the grades. Each question gets an answer column and a points column, the key is on a highlighted row at the top with each question's points beside it, and **each student's total is a live `SUM` formula**, so changing a points cell after a regrade discussion updates the total immediately. The key row shows the acceptable answers for written questions, pipe-separated. Students are listed in the order they were scanned.

The workbook's last tab, **Item analysis**, has one row per question: its key, its points, how many students answered it, the mean score (the fraction of its points students earned on average, so 0.9 is an easy question), its discrimination, and how many students marked each choice. The key's letters are bold among the choice counts, so a distractor that drew more students than the key stands out.

Discrimination is the correlation between a student's score on the question and their score on the rest of the exam. A good question is answered correctly more often by students who did well overall, and has a positive discrimination. A question near zero does not separate strong students from weak ones, and a negative one was answered correctly more often by weaker students; that usually means a wrong key, an ambiguous stem, or a distractor that is defensibly right. Questions below 0.2, a common rule of thumb, are shaded and marked in the **Look at** column. With a small class these numbers move a lot from one student to the next, so read them as a pointer to questions worth rereading, not a verdict.

**`canvas_upload.csv`** imports straight into the Canvas gradebook (**Grades → Import**). It has Canvas's own header: `Student` (Last, First), `SIS User ID`, and one column named for the exam, then a `Points Possible` row, then one row per student sorted by name. Canvas matches students by SIS User ID and asks which assignment the column belongs to, so the column name need not match the assignment. The name comes from the exam's title in a key made by Build Exam, and otherwise from the folder holding the scans. The SIS User ID is the bubbled ID with a prefix in front, `L` by default, which is how Canvas stores Longwood IDs; change it under **More options** on the Scan tab. The file is in the same format as a Canvas gradebook export, so it also works as a [class roster](roster.md).

**`ALERT.txt`** appears only when something needs attention, and it is the file to check before entering grades. It names every student and question where no answer could be read at all (usually a badly scanned sheet rather than a skipped question). It lists marks the scanner was unsure of (`CHECK MARK`) and sheets marked very lightly (`LIGHT MARKS`). With a class roster loaded, it lists IDs not on the roster, IDs corrected by one digit, and two sheets reading as the same ID (`ROSTER`). Each line gives the scan number, which is the sheet's position in the stack.

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

A stack graded against several versions' keys still produces one of each file. `gradebook.xlsx` has a tab per version, each numbered and lettered as that version's sheet was, so a student's question about their Q17 is answered on their own version's tab. The marked sheets for every version go into the one `marked/` folder and `marked.pdf`, and `canvas_upload.csv` lists every student.

With keys made by Build Exam, the versions are also combined question by question. Each key records which bank question sits at each position and where each choice sat in the bank, so the **By question** tab lists every student in one table with a column per bank question, answers translated back to the bank's letters, and **Item analysis** reports each bank question once, across all versions. A question is named by its bank file and block number, `bank.md#12` for the twelfth question block in `bank.md`; a question that takes several rows (dropdowns, ordering, matching) adds the row, `bank.md#12.3`. **On sheet** gives where it was printed on each version, `A3, B17`. Keys made before this, or made any other way, grade as before, and their item analysis is per version.

A lab practical's outputs differ a little: a `form` column, blanks for questions not on a student's form, and marked pages per student. [Lab practicals](lab-practicals.md#what-the-results-hold) has the details.

## app_data/

**`results.csv`** (or `results_versionA.csv` and so on, one per version) holds the answers as read and graded, one row per student with the key first; `results_points.csv` beside it holds the points each student earned on each question, and `results_grading.json` what each question is worth. These are what `gradebook.xlsx` and `canvas_upload.csv` are built from, and what the Re-grade tab updates. `outputs.json` lists which results files the last scan produced.

**`aligned/`** holds every page after skew and scale correction. These are what the **Re-read without aligning again** option reuses, so keeping them makes a second pass at a different fill cutoff nearly instant. They are also unmarked copies of every sheet, which is worth keeping if you want to delete the original scans.

**`scanJPGs/`** holds the page images extracted from a scanned PDF. The app converts a PDF to images and works on those.

**`results_openq_transcriptions.json`** holds every handwriting transcription, and **`results_openq_answers.json`** holds the acceptable-answer lists as they stood at the end of grading. Together they are what makes the [Re-grade](open-ended-questions.md#re-grading-afterward) tab possible without rescanning. **`results_openq_gradeconfig.json`** records the grading settings that run used, and a `results_openq_progress.json` appears mid-run so an interrupted session can be resumed; it is removed when grading finishes.

Delete `app_data/` and the gradebook and Canvas file stay valid, but re-grading written answers and fast re-reads at a new fill cutoff are no longer possible.

---

Previous: [Open-ended questions](open-ended-questions.md) · Next: [Lab practicals](lab-practicals.md)
