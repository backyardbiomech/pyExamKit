# Scanning and grading

The **Scan Exams** tab reads a stack of completed answer sheets, grades them, and writes the results. Everything it produces is described in [Outputs](outputs.md).

## Scanning the sheets

Scan at **200 dpi or better, in color**. Put every scan in a folder containing nothing else, since the app treats the folder as the job.

You can scan the whole stack to a single PDF, or to a folder of JPGs. **JPGs are the safer choice for a large stack**, because a page that scanned badly can be rescanned and dropped into the folder, while a PDF has to be remade.

If you are not loading a key file, **the key sheet goes first in the stack**. With a key file loaded, the stack is students only. A sheet built with an exam that groups rows by question needs its key file; without one the scan stops and says so.

## Setting up the run

The tab asks for three things, in order, and keeps the rest under **More options**. **Scan and Grade**, at the bottom of the tab, starts the run; the line beside it says what is about to be graded.

**1. Answer key.** **Choose key files…** picks the key CSV that the [Build Exam](building-exams.md) tab wrote. Choose any one version's key, and the other versions' keys from the same build are found beside it, so a multi-version stack needs no further setup. You can also choose several key files at once, for keys that were not written together; each must say which version it is for, in its metadata or in a name ending `_vA_key.csv` and so on. The line under the button says what was loaded: how many versions, how many questions and written answers, and whether the points came from the key. The question count, the written rows to skip, the points, and the pages per student all come from the key, so there is nothing to type. **Edit…** opens the key for editing. A lab practical's key is its source `.md` file; choose that, and edit it in a text editor, since **Edit…** is unavailable for it ([Lab practicals](lab-practicals.md#scanning-and-grading)).

With no key file, the first page of the stack is read as the key (see above). Give the **number of questions** in the box that appears, and the **points per bubble question** and **per written question**. Those point boxes also appear for a key that has no points of its own, such as one built on the [Standard Sheet](building-keys.md) tab.

**2. Scanned sheets.** **Choose scans…** points at the scans. Select the PDF, or select the first JPG with the rest in the same folder.

**3. Class roster** is optional. With a roster loaded, each sheet's bubbled ID is looked up and the names in the results come from the roster rather than from the sheet. The new answer sheets have no name bubbles, so without a roster their results carry IDs only. [Class rosters](roster.md) explains what file to use and how to get it out of Canvas.

**Written answers** appears when the key has written questions, or when there is no key file; see [Written answers](#written-answers) below.

### More options

**Save marked answer sheets**, **show the correct answers on marked sheets**, and **partial credit on select-all-that-apply questions** are on by default. Turn off the first to save time when you only need the numbers; the second adds green marks for the right answers beside the red ones; the third is described [below](#select-all-that-apply).

**Fill cutoff** decides how dark a mark has to be to count as filled, measured against that student's own marks rather than a fixed darkness (see [How a bubble becomes an answer](#how-a-bubble-becomes-an-answer)). The default of 0.35 means a bubble counts when it is at least about a third as dark as the student's typical mark; on a stack of 69 real pencil sheets, every value from 0.30 to 0.45 read identically, so it rarely needs changing. Lower it toward 0.30 if light marks are being missed; raise it toward 0.45 if erasures are being counted. Marks that could go either way are listed in `ALERT.txt` either way. **Re-read without aligning again** makes a second try cheap: it reuses the aligned images from the previous run, so a pass at a different cutoff takes seconds instead of reprocessing every page.

**Also skip questions** takes a comma-separated list of rows to leave ungraded on top of the key's written ones: a question you have decided to throw out, or rows you covered over on the sheet. A row that is skipped is neither graded nor counted. With no key file, this is the whole list of rows to skip.

**Pages per student** matters for a multi-page exam, where each student's sheets have to be grouped together. It is filled in from the key when the key's written answers are on a later page.

The **version question number** is only for older sheets without version bubbles in the header, graded with several versions' keys; give the question where students bubbled their version letter.

## Select all that apply

**Partial credit on select-all-that-apply questions**, on by default, changes how *every* question is graded, not just the multi-answer ones, and it turns on the "missing answer" mark described in [Outputs](outputs.md).

With it off, a question is right or wrong: an answer that exactly matches the key earns the question's points and anything else earns zero.

With it on, partial credit applies. If *n* is the number of correct answers on the key, *c* is the number of correct answers the student selected, and *i* is the number of incorrect ones, the score is **c(1/n) − i(1/n)**, floored at zero and scaled by the question's point value. A question with three correct answers where the student picks two of them and one wrong one earns 0.66 − 0.33 = 0.33 of the points.

**A single-answer question still grades as all-or-nothing under this rule**, which is worth understanding rather than discovering. If the key is A and the student marks A and B, then n = 1, so the correct answer earns one point and the incorrect one costs one point, and the student gets zero.

## Multiple versions

A mixed stack is graded in one pass whenever more than one version's key is loaded, which happens by itself when the build wrote several. On the new answer sheets, students bubble their version in the header. On the older sheets, give the question where students bubbled their version letter under **More options**; the [Build Exam](building-exams.md) tab can add that question for you.

Each student's version bubble is read, and each version group is graded against its own key. All versions go into one gradebook, with a tab per version, and one Canvas file; [Outputs](outputs.md#multiple-versions) has the details.

Written answers are graded one version at a time, each against its own key's boxes and accepted answers, so the on-screen grading runs once per version. The answers you accept are saved back to that version's key, and each version's grading can be revisited on the [Re-grade](open-ended-questions.md) tab, which rebuilds the gradebook and Canvas file.

A lab practical's forms are not versions: every form is graded against the one key, the practical's source file, in a single pass. See [Lab practicals](lab-practicals.md).

When a student's version bubble cannot be read — left blank, or two letters filled — a dialog shows that student's sheet and asks you to assign a version by hand, or to skip the student. Skipped students are named in the log and appear in no version's results, so they have to be dealt with separately.

## Written answers

When the key has written questions, **Grade written answers on screen** is checked for you, and its options (AI transcription and partial credit strictness) sit beneath it. [Open-ended questions](open-ended-questions.md) covers the whole of that workflow.

With no key file, check it yourself, and list every written question under **Also skip questions**, or its untouched bubble row is graded as a wrong answer.

## How a bubble becomes an answer

The scanner locates the three registration circles on each page and warps the image to a fixed size, correcting skew and scale. A small printed code tells it which answer sheet design it is reading, so old and new sheets can be scanned in one stack.

It then measures how dark the inside of every bubble is, minus the printed letter. Students shade differently, so instead of one darkness for everyone, the scanner learns each student's typical mark from the darkest bubble in each of their rows. A bubble counts as filled when it reaches the fill cutoff (0.35 of it, by default) of that student's typical mark, and when it is at least half as dark as the darkest bubble in its own row. The first rule lets a light pencil count. The second is what separates an erasure from a real answer: a heavy hand's erasure can be darker than a light hand's mark, but it is always much lighter than the fresh mark beside it. Multiple marks on one row produce a multi-letter answer such as `ABD`, and a row with nothing filled produces `-`.

Marks the scanner cannot call confidently are reported rather than guessed: a lone light mark just under the cutoff, read as blank, and a mark close to half as dark as another in its row, which could be an erasure or a second answer. Each is listed in `ALERT.txt` and drawn on the marked sheet as an orange `?` and the letter, just right of the row. A sheet whose marks are all very light is listed too, as one to look over by eye.

A `-` is not silently treated as a wrong answer. Every student with an unscanned answer is written to an `ALERT.txt` file beside the results, naming the student and the question, because the usual cause is a sheet that scanned badly rather than a student who skipped a question.

---

Previous: [Building a key](building-keys.md) · Next: [Class rosters](roster.md)
