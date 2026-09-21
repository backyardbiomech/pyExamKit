# Building an exam

The **Build Exam** tab turns one or more [question bank files](question-bank-format.md) into a printable exam and the answer key CSV that [Scan Exams](scanning-and-grading.md) grades against. It writes an HTML version to print and a Markdown version to keep or post.

## Where the questions come from

**Exact File** uses one bank file exactly as written, every question, in file order. Use it when the bank *is* the exam.

**Question Pools** draws a random sample from each of one or more bank files. Add a file with **Add Pool File…** and it appears in the table with the number of questions it actually contains under **In Bank**. The **# to pull** column defaults to ten, or to the bank's own total if the bank holds fewer than ten. 


**Import QTI…** builds a pool from a Canvas quiz export instead of a file you wrote. See [Importing a Canvas quiz](importing-canvas-quizzes.md).

Points resolve in three layers, most specific first. A `(N pts)` line inside the bank file always wins. Failing that, the pool's own **Pts/Q** column applies to every question drawn from that pool. Failing that, the exam-wide **Default pts/question** applies. The running total under the pool table shows both the question count and the point total as you go.

## Versions and shuffling

**Shuffle question order** and **Shuffle answer order** are independent. Shuffling answers rearranges the choices within each question, and within each dropdown of a multiple dropdown question.

Two kinds of question are scrambled whether or not you ask for it, because their source order is the answer. Ordering questions are always printed out of order, and matching questions always have their right-hand options scrambled. See [Question bank format](question-bank-format.md) for why.

One case is *un*-shuffled on purpose. When every choice in a question is a single capital letter — `A`, `B`, `C`, `D` — it's assumed the choices are pointing at labels on a diagram rather than standing on their own, so they are sorted alphabetically no matter what the shuffle settings say. Bubble A then always means label A on the figure.

**Number of versions** generates up to six lettered versions, A through F, in one pass. Six is the ceiling because the six-bubble answer sheet cannot encode a seventh.

**Use same questions across all versions** changes what "version" means. Left off, each version draws its own fresh random sample from the pools, so version B may ask about things version A never mentions. Turned on, all versions ask the identical set of questions and differ only in order. Same-questions versions are the ones to use when the versions have to be comparable to each other.

**Add version identifier question** appends — or, set to first, prepends — a synthetic question that instructs each student to fill in the bubble for their version letter. That one bubble is what lets the scanner sort a mixed stack of sheets and grade each one against the right key, so turn it on any time you print more than one version. It occupies a question slot like any other question, but is worth zero points. The default is to make it the last question so students can't easily find the version when passing out exams.

## Font size and page breaks

**Font size** sets the size of the text on the exam, in five steps: smaller (9 pt), small (10 pt), medium (11 pt), large (13 pt), and larger (16 pt). Medium is the default. A larger size gives the exam more pages rather than cramming each one, which makes it the setting to reach for when a student's accommodation calls for large print.

The exam asks the browser never to split a question across two pages when it prints, so a question's stem, image, answer choices, and ordering or matching slots stay on one page, and a question that does not fit in the space left starts the next page instead. That leaves blank space at the bottom of some pages, especially on an exam with many images. Chrome and Edge honor the request; in another browser, check the print preview. A question taller than a whole page still splits, since there is nowhere else for it to go.

## Output folder and what lands in it

Choose an **Output folder**, then click **Generate Exam**. Each build goes in its own folder inside the one you chose, named after the exam title (an exam titled `Title` lands in `Title/`), so the output folder can safely be the folder your banks live in. Building again under the same title writes into the same folder and replaces what is there. For each version the app writes:

- `Title_vA.html` — the exam laid out for printing, with MathJax for any equations (at a size other than medium, the size is added to the name, as in `Title_vA_large.html`)
- `Title_vA.md` — the same exam as Markdown - you probably won't use this
- `Title_vA_key.csv` — the answer key, in the format [Scan Exams](scanning-and-grading.md) reads

Once per build it also writes `Title.exam.json`, the settings and the exact exam, for reprinting later (see below).

Any images the questions use are copied into an `images/` subfolder of the build's folder, so that folder can be moved or shared on its own without breaking the exam. Don't move the html file to a different folder though unless you also bring the images folder. When two banks each have a different image with the same name, the second is copied as `cell_2.jpg` (and so on) and the exam points at the renamed copy; nothing already in `images/` is overwritten.

Equations are drawn by MathJax, which loads from the internet when the exam is opened, so open the exam on a connected computer before printing it.

Every printed page has a footer with its page number, so a dropped stack can be put back in order. When more than one version is built, the footer names the version as well, unless the exam carries a version identifier question, which already prints the version where the student needs it. Chrome and Edge print this footer; Safari and Firefox leave it off. Leave the print dialog's own **Headers and footers** option unchecked, since it adds the file path and date.

Print the HTML from a browser (or print to PDF). The students bubble their answers on a separate [answer sheet](answer-sheets.md), not on the exam pages, so the exam itself can be printed double-sided and collected without being marked up.

## Saving and reprinting an exam

Every build writes `Title.exam.json` to the build's folder. It holds every setting on the tab (title, course, source files, counts, points, shuffle and version options, font size, and the output folder) and the exam exactly as it was printed: each version's questions in order, with their answer choices in order. **Load Config…** reads one back. **Save Config…** writes the settings on demand, and the saved exam with them while the reprint box described below is checked.

When a loaded config holds a printed exam, a checkbox appears under the config buttons, already checked: **Reprint the saved exam (same questions, order, and answer keys)**. Generate then prints those versions again without drawing a new sample, so the answer keys still match copies already handed out. This is how to make a large-print copy for one student: load the config, set **Font size** to large or larger, and click Generate; the new file is named with its size, so it sits beside the original instead of replacing it. A reprint takes question text from the config, not from the bank files, so editing a bank afterward does not change it. Images are still read from the bank's folder, so leave those where they are.

Uncheck the box to build from the source files instead. That draws a fresh random sample and a fresh scramble, so a make-up exam that has to be different but equivalent is a matter of loading last week's config, unchecking the box, and clicking Generate. The box also appears right after a build, unchecked, so the exam just made can be reprinted at another size without reloading anything.

## Watch the log

The log at the bottom of the window is where the builder reports everything it could not do: bank blocks it could not parse, Canvas-only question types it skipped, matching questions whose correct answers exceed the sheet's six options, ordering questions that are too long or numbered wrong, pools that came up short, and images that could not be found. None of these stop the build — you get an exam either way — so the question count on the printed page is the number to reconcile against what you expected.

One warning deserves particular attention. If the exam needs more than **150 answer-sheet slots**, the log gives a warning, and every question past 150 prints normally but has nowhere to be bubbled. Ordering, matching, and multiple dropdown questions each take one slot per item, so an exam of 90 questions can easily need 130 slots.

---

Previous: [Question bank format](question-bank-format.md) · Next: [Importing a Canvas quiz](importing-canvas-quizzes.md)
