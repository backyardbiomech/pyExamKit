# Design notes

These document why parts of pyExamKit are built the way they are. They are aimed at anyone modifying the code, not at anyone using the app — for that, start at the [documentation index](../../README.md#documentation).

Each is dated and reflects what was true when it was written. Where one describes a decision that has since been made and implemented, it stays as the record of the reasoning rather than being rewritten into the present tense.

- [ordering-matching-spec.md](ordering-matching-spec.md) — how ordering and matching questions map onto a six-bubble answer sheet: the slot model they share with multiple dropdown questions, the trimming rules, and how points are divided across a question group.
- [pdf-output-plan.md](pdf-output-plan.md) — the direct-PDF exam renderer that shipped in v3.2.4: how it kept each question whole on a page, the MuPDF behaviors it had to work around, and why it was withdrawn for HTML so equations could be typeset.
- [qti-import.md](qti-import.md) — what a Canvas QTI export actually contains, why the reader keys on XML structure rather than on Canvas's identifiers, where the bank format forced a translation, and what the test fixtures are.
- [scanner-packaging-options.md](scanner-packaging-options.md) — the audit that established the scanner's entire scipy and scikit-image surface is eight function calls, the three ways out of that, and the measured result of taking the OpenCV route.
