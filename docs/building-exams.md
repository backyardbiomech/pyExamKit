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

**Add version identifier question** appends — or, set to first, prepends — a synthetic question that instructs each student to fill in the bubble for their version letter. That one bubble is what lets the scanner sort a mixed stack of sheets and grade each one against the right key, so turn it on any time you print more than one version. It occupies a question slot like any other question, but is worth zero points. The default is to make it the last question so student's can't easily find the version when passing out exams.

## Output folder and what lands in it

Choose an **Output folder**, then click **Generate Exam**. For each version the app writes:

- `Title_vA.html` — the exam laid out for printing, with MathJax for any equations
- `Title_vA.md` — the same exam as Markdown - you probably won't use this
- `Title_vA_key.csv` — the answer key, in the format [Scan Exams](scanning-and-grading.md) reads

Any images the questions use are copied into an `images/` subfolder of the output folder, so the output folder can be moved or shared on its own without breaking the exam. Don't move the html file to a different folder though unless you also bring the images folder.

Print the HTML from a browser (or print to pdf). The students bubble their answers on a separate [answer sheet](answer-sheets.md), not on the exam pages, so the exam itself can be printed double-sided and collected without being marked up.

## Saving a build configuration

**Save Config…** writes every setting on the tab — title, course, source files, counts, points, shuffle and version options, and the output folder — to a `.exam.json` file. **Load Config…** reads one back.

This is what makes a build repeatable. Re-running a saved configuration draws a fresh random sample and produces a fresh scramble, so a make-up exam that has to be different but equivalent is a matter of loading last week's config and clicking Generate again. It also means the exact settings that produced a given exam are recoverable months later, when the only other record is the printed paper.

## Watch the log

The log at the bottom of the window is where the builder reports everything it could not do: bank blocks it could not parse, Canvas-only question types it skipped, matching questions whose correct answers exceed the sheet's six options, ordering questions that are too long or numbered wrong, and pools that came up short. None of these stop the build — you get an exam either way — so the question count on the printed page is the number to reconcile against what you expected.

One warning deserves particular attention. If the exam needs more than **150 answer-sheet slots**, the log gives a warnin, and every question past 150 prints normally but has nowhere to be bubbled. Ordering, matching, and multiple dropdown questions each take one slot per item, so an exam of 90 questions can easily need 130 slots.

---

Previous: [Question bank format](question-bank-format.md) · Next: [Importing a Canvas quiz](importing-canvas-quizzes.md)
