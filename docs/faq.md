# FAQ and troubleshooting

## Recommended workflows

**All bubbles.** Build the exam here and use the key CSV it writes. For an exam built elsewhere, either fill in an answer sheet by hand and scan it as the first page of the stack, or build a reusable key from that filled sheet on the [Build Key](building-keys.md) tab.

**A few written questions mixed into a bubble exam.** Filling in the key by hand is usually easiest, especially when you intend to be strict about the written answers. Scan the key as its own file, load it in the key builder, set the bubble answers and draw the boxes around the written-answer areas, and save it as a CSV. Then scan the students' sheets against that key.

**Mostly or entirely written questions.** Do not fill in a key by hand. Make a PDF of your blank answer sheet — several pages, if the questions need them — load it into the key builder in blank-sheet mode, and draw boxes around every answer area. Save the key, then open the CSV in a spreadsheet and type the answers in: full-credit answers in the `answer` column and partial-credit ones in `partial_answers`, each pipe-separated. Scan against that key.

## Building exams

**A question is missing from the built exam.** Read the log. Every skipped block is reported with a reason: an unsupported question type, an ordering that is too long or numbered wrong, a matching question that references a right-hand label that does not exist, or a block the parser could not read at all. The most common cause of the last one is a blank line inside a question block, which splits it in two.

**The exam has more questions than the answer sheet has rows.** Ordering, matching, and multiple dropdown questions take one row per item, not one per question, so the row count runs well ahead of the question count. The log warns when a build needs more than 150 rows.

**A question printed with fewer choices than the bank file lists.** Choices past six are trimmed to fit the sheet. Correct answers are always kept; wrong answers are sampled. See [Question bank format](question-bank-format.md).

**Ordering and matching questions came out scrambled even with shuffling off.** That is deliberate, and it is not optional. Their source order is the answer.

## Scanning

**Answers came back blank, or a `-` shows up in the results.** The fill threshold is probably too high for how these sheets were marked. Check **Skip alignment** and re-run at a lower threshold — 0.20 catches lighter marks — which reuses the aligned images and takes seconds. Check `ALERT.txt` for exactly which students and questions were affected.

**Erasures are being counted as answers.** Raise the threshold toward 0.30.

**A page failed to align, or the whole scan looks wrong.** Alignment depends on the three large black registration circles. Anything covering, cropping, or badly reproducing one of them breaks it. Rescan that page in color at 200 dpi or higher, with the whole sheet inside the scan area.

**Everything is graded as wrong on one question.** Check whether that question's row was supposed to be in the ignore list — a written question in the middle of the exam has an untouched bubble row, and an untouched row is a wrong answer unless the scanner is told to skip it.

**A student got zero on a question where they marked the right answer and one other.** With select-all-that-apply grading on, a single-answer question awards one point for the correct mark and deducts one for the incorrect one. See [Scanning and grading](scanning-and-grading.md).

**A student's version was not detected.** The app shows their sheet and asks you to assign a version by hand or skip them. Skipped students appear in no version's results and are named in the log.

## Open-ended questions

**Every transcription is blank.** Transcription needs **Use AI OCR** checked and an API key configured. There is no local recognition engine. Without it, the workflow still runs, but every answer is graded by eye.

**The transcriptions are poor.** The crop is usually the cause. Crop tightly around the handwriting only, excluding the printed line and any label. Beyond that, the design of the blank itself matters — a light gray underline rather than a black box, at least 6 to 8 cm wide, with the label above rather than beside it. [Answer sheets](answer-sheets.md) has the details. Setting the **exam context** to match your subject also helps noticeably on technical terms.

**The key's transcription is wrong.** Edit it in the grading window. The correction applies to every student from that point on.

**I graded twenty students before realizing an answer should have counted.** Use **Add as partial credit** in the grading window, which upgrades everyone already graded whose answer matches. After the scan, the [Re-grade](open-ended-questions.md#re-grading-afterward) tab does the same thing against a finished results file.

**Can re-grading lower a grade?** No. It only upgrades. Edit the results file directly to lower one.

**The app closed partway through grading.** Run the same scan again and it offers to resume where you stopped, reusing the transcriptions it already made.

## Privacy and cost

**What leaves my computer?** Only the cropped answer images and a row number, and only when AI OCR is checked. Nothing else in the app sends anything anywhere. Crop tightly and no name or ID is in the image at all.

**What does it cost?** Transcription uses a small Anthropic model, batched twenty images at a time, billed to your own API account. A typical exam is cents rather than dollars, but it is your account and your key.

**Where is my API key stored?** In `~/.pyexamkit_config.json`, in plain text, created readable and writable only by you on macOS and Linux. On Windows the file is protected by your user profile's permissions.

## Installing

**macOS says the app is damaged or from an unidentified developer.** Run `xattr -cr` on the app as described in [Installation](installation.md). The app is not code-signed.

**Windows SmartScreen blocks it.** Click **More info**, then **Run anyway**. Same reason.

**The Windows app will not start.** Keep the extracted folder together — the `.exe` needs the files beside it.

---

Previous: [Outputs](outputs.md)
