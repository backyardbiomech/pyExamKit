# Direct PDF exam output

## Withdrawn (2026-09-14)

This renderer shipped in v3.2.4 and was withdrawn the same day, because exams must typeset `$…$` math and a PDF laid out with PyMuPDF cannot do that easily or reliably. MuPDF's HTML layout draws MathML as flat text. Typesetting TeX to SVG with ziamath works, but MuPDF rasterizes an SVG image to about 100 dpi, ignores `vertical-align` so an equation cannot sit on the text baseline, and reports an inline image's position as a zero-width point, which defeats drawing vector math over a placeholder afterward. Each could be worked around, at the cost of three new dependencies and a chain of placement tricks that would still cover less TeX than MathJax. Math matters more than skipping the browser's print step, so the exam went back to HTML with MathJax loaded from a CDN, printed from a browser.

Everything that did not depend on the output format stayed: the five font sizes (now set in the HTML's stylesheet), 0.75 in top and bottom page margins, the page footer (CSS page margin boxes, which Chrome and Edge print), the exam recorded in the saved config for exact reprints, and the size suffix on filenames. Keeping a question whole on one page went back to the browser, through `break-inside: avoid` on each question. The rest of this document is the record of the PDF renderer as it was built.

## Goal

The Build Exam tab writes the exam as a PDF directly instead of an HTML file that has to be printed to PDF, offers a five-step font size choice, and never splits a question across pages. A question here means its stem, its image, its choices, and (for ordering and matching) its answer slots, so an image always lands on the same page as the question it belongs to. Large white gaps at the bottom of a page are acceptable.

## Why PyMuPDF's Story renderer, and not fpdf2

Both libraries are already dependencies, so neither adds a module to the PyInstaller bundle. PyMuPDF (`fitz`) is used by `init_functions.py` and `openQ.py`; fpdf2 by `scanner.py`.

PyMuPDF's `Story` lays out HTML and CSS onto PDF pages, and it ships its own Unicode serif font (Charis SIL), which covers Greek letters, ≥, and em dashes with no font file to bundle. fpdf2's built-in fonts are Latin-1 only, so a stem containing μ would need a TTF shipped with the app on both platforms. `Story` also accepts the HTML the parser already produces for bold, italic, superscript, and subscript, so question text needs no second formatter.

MuPDF ignores `page-break-inside: avoid`: a probe laying out fifteen six-choice questions as one document split question 1 between choices E and F. Keeping questions whole is therefore done in Python. Each question is its own `Story`, placed into the space left on the current page. If it does not fit and the page already holds something, it moves to a fresh page. If it does not fit on an empty page and it has images, the images shrink in 20% steps until it does. A question with no image that is taller than a whole page is allowed to split, and the log names it; nothing in the fixture bank comes close even at the largest size.

Two MuPDF behaviors surfaced after the first version shipped to testing, and both shape the layout code. MuPDF's built-in stylesheet gives `body` a 1em margin; because every question is its own `Story`, that margin padded each question on all four sides, leaving about 30 pt of white space between questions at medium and pushing the text 11 pt inside the page margins. The stylesheet now resets it, and the space between questions (1.5em, about 14 pt of white space at medium) comes from the layout code alone. Resetting it exposed the second behavior: when a question begins with an image and the space left on the page is short, `Story.place` can shrink the image to a thumbnail, report that the whole question fit, and draw the rest of the question below the bottom of the page. In a 60-question stress exam this stranded a thumbnail at the foot of several pages with its question lost. Whether a question fits is therefore judged from its height laid out with unlimited room, and it is placed into the real space only when that height fits.

## Prototype evidence

A scratch prototype rendered the fixture bank (`tests/fixtures/build_migration/input/bank1.txt`) at all five sizes, producing 2, 2, 2, 3, and 4 pages, and a 60-question stress exam with a large image on every fifth question, producing 23 pages at medium and 31 at larger. No question overflowed in any of them, and in the extracted text of every PDF each page after the first begins with a question number. Two defects were found and are part of the work below: fill-in blanks written as `<u>` around non-breaking spaces draw no underline, so they will be printed as underscores the way the Name line already is, and a question image needs space below it before the stem.

## Changes

`renderer.py` gains `to_pdf(version, output_folder, total_versions, default_points, font_size)`, which returns the saved path and a list of warnings for the log. Question markup is built in Python from the dicts `_prepare_questions_for_html` already returns (renamed `_prepare_questions`, since it no longer serves HTML only). Images are read from each question's own source folder and embedded in the PDF, so pools drawn from different folders still resolve, and no `images/` folder is copied into the output. Pages are US Letter with 0.75 in top and bottom margins on every page, which clear a corner staple and hold the footer, and 0.5 in side margins. (The HTML print stylesheet had used 0.5 in, with 0.6 in at the top of later pages; the deeper margins were asked for once the PDF existed.)

`exam_builder.py` gets `FONT_SIZES = {'smaller': 9, 'small': 10, 'medium': 11, 'large': 13, 'larger': 16}` and `BuildConfig.font_size = 'medium'`. Medium is 11 pt because that is the size the current print stylesheet prints at, so a default build looks the way printed exams look now. Headings, point labels, and notes scale with the chosen size.

`exam_config.py` saves and loads `font_size`. A `.exam.json` written before this change has no such key and loads as medium, so the schema version does not change.

`build_tab.py` adds a **Font size** dropdown to the Options section, built the same way as the existing version-position `CTkOptionMenu`. `build_config_from_fields` takes `font_size`, loading a config sets the dropdown, and the log reports `PDF → Title_vA.pdf` for each version.

`tests/test_build_migration.py` loses the golden-HTML and copied-images tests. Byte comparison of a PDF would break on every PyMuPDF upgrade, so the replacements check behavior: the fixture's question text appears in order, no page begins partway through a question at any of the five sizes, every image sits on the same page as its stem, a larger size never produces fewer pages, and a stress exam with an image taller than the page still keeps that image with its question. `tests/test_build_tab_logic.py` covers the new field mapping and a config round trip. The Markdown and key golden tests are untouched.

`docs/building-exams.md` changes its output list, adds the font size option and the keep-together behavior (including the white space it causes), and drops the instruction to keep the HTML file next to its `images/` folder. `docs/question-bank-format.md` changes its math paragraph to match whatever is decided below.

## Decisions (2026-09-14)

The HTML output is removed, not kept alongside the PDF. That also removes `templates/exam.html`, the `templates/` line in `pyexamkit.spec`, jinja2 from `pyproject.toml` and `uv.lock`, and the MathJax script the page loaded from a CDN. The Markdown export and the key CSV are unchanged.

`$…$` math prints exactly as typed, and the log warns once per question that contains it. MathJax exists only in a browser, so the PDF cannot typeset TeX; translating a subset to Unicode was rejected because math is rare in these banks, and a partial translation would print some equations correctly and others half-converted.

Every page carries a footer reading "Version A · Page 2 of 5". The version letter is left out under the same rule that hides it in the header: one version built, or a version identifier question already on the exam. The page count is only known once layout finishes, so the pages are written to memory first and the footers stamped afterward.

The size steps are 9, 10, 11, 13, and 16 pt.

The config that Generate saves records the exam exactly as printed, so it can be reprinted at another size after the app is closed. Each version's questions are stored with full text, order, and answer order, not as a random seed, because a seed reproduces an exam only until a bank file is edited. Loading such a config shows a "Reprint the saved exam" box, checked; Generate then skips the builder and prints those versions again, so the keys and any copies already printed still match. Unchecking it builds fresh from the pools as before. A PDF at any size other than medium carries the size in its name (`Title_vA_large.pdf`), so a reprint sits beside the original rather than replacing it.
