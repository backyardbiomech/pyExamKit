# Open-ended questions

An open-ended question is one a student answers in writing on the answer sheet rather than by filling a bubble — a fill-in-the-blank, a term, a short phrase, a small equation. pyExamKit crops each student's answer area, transcribes the handwriting, suggests a grade against your key, and shows you both so you can accept or override it in one keystroke.

The grading is yours. The transcription and the suggestion are there to make going through 90 sheets fast, not to decide anything.

## Setting up the run

On the [Scan Exams](scanning-and-grading.md) tab, **Grade written answers on screen** is checked for you when the key has written questions. With no key file, check it yourself, and list any mid-exam written question under **More options → Also skip questions**, since its bubble row would otherwise be graded as a wrong answer. Then run the scan as usual. A scan of several versions grades each version's written answers in turn, against that version's key.

After the bubble questions are graded, the key image appears. **Drag a box around the answer area for each open-ended question**, in question order. Include only the space where students wrote — not the printed question number, not the label, not the printed line. Each box prompts for a label, which defaults to the next number in your ignore list, so a question numbered 14 on the exam stays question 14 in the results; labels can also be alphanumeric, so `1A` and `1B` work for two blanks in one question. The only way to correct a box is to remove the last one drawn and redraw it. When all the boxes are drawn, **press `g`** and the window closes.

Those same coordinates can be prepared ahead of time and stored in a key file, which is what the [Standard Sheet](building-keys.md) tab is for. An exam built on the [Build Exam](building-exams.md) tab needs neither: its answer sheet prints a writing box for each short-answer question, and its key already records where each box is. With a key file that has the boxes, the drawing step is skipped.

## Handwriting transcription

**Transcription is done by the Claude API, and there is no local alternative.** With **Use AI OCR** left unchecked, every answer arrives at the grading window blank and every question is graded by eye — which works, and is a reasonable choice, but is slower and offers no suggestions.

Check **Use AI OCR (Claude) for handwriting recognition**, then click **Configure API Key…** and paste an Anthropic API key. The key is saved to `~/.pyexamkit_config.json`, created readable and writable only by you on macOS and Linux; on Windows it is protected by your user profile's own permissions. Get a key from [console.anthropic.com](https://console.anthropic.com); usage is billed to that account, and the transcription runs use a small, inexpensive model in batches of twenty images per call.

**Exam context** tells the model what kind of answers to expect, which measurably improves transcription of technical terms. Presets cover anatomy and physiology, biology, chemistry, physics, mathematics, computer science, and history, plus a generic short-answer option; **Custom…** opens a free-text field for anything else.

### What gets sent

Cropped answer images and an anonymized index — a row number, not a name — are sent to Anthropic's servers. **No identifying information is sent unless it appears inside the crop box you drew**, which is the practical argument for cropping tightly around the writing and excluding the header of the sheet.

## The grading window

The window takes one question at a time and goes through every student who answered it, then moves to the next question. The top line names the question (with its text, for a lab practical) and how far through it you are, and the line below names the student: the roster name, and a picture of the name they wrote, so a student with a spelling accommodation is recognized before you grade.

Below that, **what the student wrote** is on the left and **what the key accepts** is on the right, each shown once. The student's answer is the picture from their sheet, outlined in blue; the AI's reading of it is the small gray line underneath, since it is an interpretation of the handwriting rather than part of the answer. The key box lists the full-credit answers and then the partial-credit ones. On an exam graded without a key file, the key sheet's own crop sits at the top of the key box.

At the bottom are the grade buttons. The suggested grade is the button with a colored ring (green for correct, amber for partial, red for wrong), and the sentence under the buttons says why: which key answer the reading matched, or came closest to, and how alike they are. An empty box is suggested as wrong, so Enter moves past it. When the box has writing but no reading came back (AI transcription off, or handwriting it could not read), nothing is suggested and Enter does nothing: grade it with `c`, `p`, or `x`, so an unread answer is never marked wrong by reflex. Color in the window means only the suggestion.

| Key | Meaning |
|---|---|
| `c` | Correct — full points |
| `p` | Partial — half the question's points |
| `x` | Wrong — no points |
| `b` | Back one student |
| `Enter` | Accept the suggested grade |

**Back** (`b`) returns to the last answer you reviewed, to fix a grade given in error. Answers accepted without review (perfect matches, and listed partial-credit answers) are skipped over, since you never saw them, and so is the boundary between questions: Back from the first student of 2A reaches the last answer you graded on 1D. The answer comes back into view even if a key answer you have added since would now accept it on sight. After you re-grade it, grading moves forward again to where you were, re-showing any other answers you had reviewed in between. Back reaches as far as the start of this sitting; after resuming an interrupted session, answers graded before the interruption are corrected on the Re-grade tab instead.

**Changing the key while grading.** Under the student's answer, **Add to key as full credit** and **Add to key as partial credit** take what the student wrote, let you edit it, and add it to the key. The field at the bottom of the key box adds an answer of your own, as full or partial credit. Either way, **every student already graded on that question is re-checked against the new answer and upgraded where it now matches**, and the window reports how many changed. This is what makes it safe to start grading before you have thought of every acceptable phrasing: the twentieth student's unexpectedly reasonable answer fixes the first nineteen. Double-click a key answer to correct it (a misread key sheet, say), which re-checks the same way; select one and press **Remove selected** to take it out, which never lowers a grade already given. When you are grading against a key file, every change is written back to that file as you go, so next year's key starts where this year's ended.

## How a grade is suggested

The transcription is compared against every answer in the key's full-credit list using normalized Levenshtein similarity, where 1.0 is identical.

A similarity of **0.80 or better against any full-credit answer suggests correct**. That tolerance is what absorbs spelling errors and transcription noise: "stratum basile" against "stratum basale" clears it comfortably.

Below that, the **partial credit strictness** slider decides. It is the similarity at which a near miss is offered partial credit instead of none — at 0, no near miss earns partial credit and only your explicitly listed partial answers do; at 1, nothing short of an exact match qualifies. The default of 0.50 is fairly generous. Separately, anything scoring **0.70 or better against an explicitly listed partial-credit answer** is suggested as partial.

Two shortcuts skip the window entirely. A perfect-match suggestion is **accepted automatically** unless you check **Review perfect matches?**, which is the setting to use when you would rather see every sheet. And a partial suggestion is auto-accepted when it came from an explicit partial answer in the key or from a strictness threshold you set, on the grounds that you already made that decision when you set it.

A box with no writing in it is suggested as wrong. Where the box has writing but no transcription came back, no grade is suggested and the answer is shown to you to grade by eye.

Basically, no points are lost unless you confirm it, but points can be gained without confirmation (depending on settings).

## Interruptions

Grading progress — transcriptions, grades so far, and your position in the stack — is written to `app_data/` beside the results after every answer. If the app is closed or crashes partway through, the next run on the same scans offers to resume where you stopped. It reuses the transcriptions already made, so resuming does not pay for the same API calls twice.

## Re-grading afterward

The **Re-grade** tab reopens a finished `results.csv` and lets you edit the acceptable-answer lists for open-ended questions, then re-runs the grading against the transcriptions saved during the original scan. Nothing is rescanned and no API calls are made.

Re-grading **only upgrades** — wrong to partial, wrong to correct, partial to correct. It never takes points away. That makes it the right tool for a key that turned out to be too strict, which is the mistake that actually happens, and it means a student cannot lose points because you edited a key after handing work back. To lower a grade, edit the results file directly.

Point the tab at the `results.csv` from the scan (or a version's `results_versionA.csv`), click **Open Re-grader**, edit the answers, and it reports how many grades changed. Scores are recalculated with the per-question points from the key the scan used.

---

Previous: [Class rosters](roster.md) · Next: [Outputs](outputs.md)
