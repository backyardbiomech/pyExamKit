# Open-ended questions

An open-ended question is one a student answers in writing on the answer sheet rather than by filling a bubble — a fill-in-the-blank, a term, a short phrase, a small equation. pyExamKit crops each student's answer area, transcribes the handwriting, suggests a grade against your key, and shows you both so you can accept or override it in one keystroke.

The grading is yours. The transcription and the suggestion are there to make going through 90 sheets fast, not to decide anything.

## Setting up the run

On the [Scan Exams](scanning-and-grading.md) tab, check **Open-ended questions to grade on-screen?**. Also list any mid-exam written question in **Question numbers to ignore**, since its bubble row would otherwise be graded as a wrong answer. Then run the scan as usual.

After the bubble questions are graded, the key image appears. **Drag a box around the answer area for each open-ended question**, in question order. Include only the space where students wrote — not the printed question number, not the label, not the printed line. Each box prompts for a label, which defaults to the next number in your ignore list, so a question numbered 14 on the exam stays question 14 in the results; labels can also be alphanumeric, so `1A` and `1B` work for two blanks in one question. The only way to correct a box is to remove the last one drawn and redraw it. When all the boxes are drawn, **press `g`** and the window closes.

Those same coordinates can be prepared ahead of time and stored in a key file, which is what the [Build Key](building-keys.md) tab is for. With a key file loaded, the boxes are already known and the drawing step is skipped.

## Handwriting transcription

**Transcription is done by the Claude API, and there is no local alternative.** With **Use AI OCR** left unchecked, every answer arrives at the grading window blank and every question is graded by eye — which works, and is a reasonable choice, but is slower and offers no suggestions.

Check **Use AI OCR (Claude) for handwriting recognition**, then click **Configure API Key…** and paste an Anthropic API key. The key is saved to `~/.pyexamkit_config.json`, created readable and writable only by you on macOS and Linux; on Windows it is protected by your user profile's own permissions. Get a key from [console.anthropic.com](https://console.anthropic.com); usage is billed to that account, and the transcription runs use a small, inexpensive model in batches of twenty images per call.

**Exam context** tells the model what kind of answers to expect, which measurably improves transcription of technical terms. Presets cover anatomy and physiology, biology, chemistry, physics, mathematics, computer science, and history, plus a generic short-answer option; **Custom…** opens a free-text field for anything else.

### What gets sent

Cropped answer images and an anonymized index — a row number, not a name — are sent to Anthropic's servers. **No identifying information is sent unless it appears inside the crop box you drew**, which is the practical argument for cropping tightly around the writing and excluding the header of the sheet.

## The grading window

For each question, in turn, for each student, in turn, you see the crop from your key sheet on top and the crop from the student's sheet below, along with the transcription of each and a suggested grade.

The **key's** transcription is editable. Fixing it there applies to every student from that point on, so a misread key is corrected once rather than fought with all the way down the stack.

Four keys grade:

| Key | Meaning |
|---|---|
| `c` | Correct — full points |
| `p` | Partial — half the question's points |
| `x` | Wrong — no points |
| `b` | Back one student |
| `Enter` | Accept the suggested grade |

Going back re-grades: pressing `b` five times to reach a student five sheets ago means grading those five again on the way forward.

Beside the answer is the **acceptable-answers list** for the question. **Add as partial credit** takes what the student wrote, lets you edit it, and adds it to the list — and then **retroactively upgrades every student already graded** whose transcription matches the new entry, reporting how many changed. This is the feature that makes it safe to start grading before you have thought of every acceptable phrasing: the twentieth student's unexpectedly reasonable answer fixes the first nineteen. When you are grading against a key file, additions are written back to that file as you go, so next year's key starts where this year's ended.

## How a grade is suggested

The transcription is compared against every answer in the key's full-credit list using normalized Levenshtein similarity, where 1.0 is identical.

A similarity of **0.80 or better against any full-credit answer suggests correct**. That tolerance is what absorbs spelling errors and transcription noise: "stratum basile" against "stratum basale" clears it comfortably.

Below that, the **partial credit strictness** slider decides. It is the similarity at which a near miss is offered partial credit instead of none — at 0, no near miss earns partial credit and only your explicitly listed partial answers do; at 1, nothing short of an exact match qualifies. The default of 0.50 is fairly generous. Separately, anything scoring **0.70 or better against an explicitly listed partial-credit answer** is suggested as partial.

Two shortcuts skip the window entirely. A perfect-match suggestion is **accepted automatically** unless you check **Review perfect matches?**, which is the setting to use when you would rather see every sheet. And a partial suggestion is auto-accepted when it came from an explicit partial answer in the key or from a strictness threshold you set, on the grounds that you already made that decision when you set it.

Where no transcription came back at all, no grade is suggested and the answer is shown to you to grade by eye.

Basically, no points are lost unless you confirm it, but points can be gained without confirmation (depending on settings).

## Interruptions

Grading progress — transcriptions, grades so far, and your position in the stack — is written to `app_data/` beside the results after every answer. If the app is closed or crashes partway through, the next run on the same scans offers to resume where you stopped. It reuses the transcriptions already made, so resuming does not pay for the same API calls twice.

## Re-grading afterward

The **Re-grade** tab reopens a finished `results.csv` and lets you edit the acceptable-answer lists for open-ended questions, then re-runs the grading against the transcriptions saved during the original scan. Nothing is rescanned and no API calls are made.

Re-grading **only upgrades** — wrong to partial, wrong to correct, partial to correct. It never takes points away. That makes it the right tool for a key that turned out to be too strict, which is the mistake that actually happens, and it means a student cannot lose points because you edited a key after handing work back. To lower a grade, edit the results file directly.

Point the tab at the `results.csv` from the scan, click **Open Re-grader**, edit the answers, and it reports how many grades changed.

---

Previous: [Scanning and grading](scanning-and-grading.md) · Next: [Outputs](outputs.md)
