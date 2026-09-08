# One app, one language: merging pyExamPaper into pyExamScan and making it install cleanly

*Written 2026-09-04. Supersedes `pyExamPaper/docs/tauri-port-plan.md`, which is shelved rather than discarded. Read `docs/scanner-packaging-options.md` first for the audit this rests on.*

## The decision

Merge them, keep everything in Python, and do not do the Tauri port.

That reverses the recommendation from two days ago, and it is worth being clear about why. The Tauri port was never about wanting TypeScript. It was about escaping a Python packaging problem. The audit found that the packaging problem is caused by two libraries supplying eight functions, all in one 217-line file. Fix that and the reason to leave Python disappears, which means the reason to keep the two programs in separate languages disappears too, which is what made merging them awkward in the first place.

There is a sequencing point buried in that, and it is the most important thing in this document. **pyExamPaper is a far easier PyInstaller target than the scanner.** Its only dependencies are PySide6 and Jinja2. If PyInstaller can be made to ship the scanner reliably, it can certainly ship pyExamPaper, and the entire premise of porting pyExamPaper to Tauri evaporates. So the scanner experiment has to run before any more work happens on either app. It is an afternoon, and it decides everything downstream.

## Why merging is right, with evidence

The two programs already share a file format, and that format is currently implemented three times across two repositories. pyExamPaper's `key_generator.py` writes it. The scanner's `openQ.py` both writes it, in `save_key_csv`, and reads it, in `load_key_file`. Three implementations of one contract, maintained separately, is a drift problem waiting to happen.

It is not waiting any more. **The two writers disagree today.** `key_generator.py` emits ten columns, ending in `points`. `openQ.py:save_key_csv` emits nine, with no `points` column at all. The scanner's reader does parse `points` when it is present. So the round trip is lossy: build an exam in pyExamPaper with per-pool point values, open the key in the scanner's open-question editor, save it, and every per-question point value is silently gone and every question reverts to the default. Nothing errors. The grades are just quietly wrong.

There is a smaller version of the same problem in the encodings. `key_generator.py` writes plain UTF-8; `save_key_csv` writes UTF-8 with a byte-order mark. Both readers happen to tolerate both, which is luck rather than design.

That single bug is worth more than every convenience argument for merging. One repo with one `keyformat.py` that both halves import is the fix, and it is not achievable while the two programs live apart in different languages.

The convenience arguments are real too, and they all point the same way. One download and one install instead of two. One version number, so an exam built by version 4.1 is known to be readable by the grader in version 4.1. One place for the shared markdown question-bank parser, which the scanner does not currently have and would benefit from. And a workflow the user experiences as one thing, because building an exam and grading it are two ends of the same job.

## What the merged app looks like

One repository, one PyInstaller bundle, one GUI toolkit, two tabs or two entry screens.

**Rename the repo.** Both existing names describe half the product. `pyExamKit` is the suggestion. GitHub keeps redirects from the old name, so nothing breaks. Use `pyExamScan_v2` as the base of the merge, since it is 6,327 lines against pyExamPaper's 1,921, and move pyExamPaper in rather than the other way around.

**Drop PySide6 and standardize on customtkinter.** This is the one piece of real GUI work in the merge, and it is smaller than it sounds: pyExamPaper's window is 703 lines of Qt describing a plain form, and the scanner already has about eighty customtkinter widgets doing similar things, so there are patterns to copy. It is also a packaging win on its own. Qt bundles run past 200 MB and need careful exclusion of unused modules; customtkinter is a fraction of that and the spec already handles it correctly.

The resulting dependency list is short and every entry on it is well behaved under PyInstaller:

```
numpy, pandas, Pillow, opencv-python-headless, pymupdf, fpdf2, customtkinter, anthropic, jinja2
```

No scipy. No scikit-image. No Qt. That is the whole point.

Proposed layout:

```
pyExamKit/
  pyexamkit/
    __init__.py
    app.py                  main window, tab or mode switcher
    keyformat.py            THE shared key CSV reader/writer, single source of truth
    build/                  from pyExamPaper
      models.py  parser.py  exam_builder.py  renderer.py  exam_config.py
      templates/exam.html
    scan/                   from pyExamScan_v2
      scanner.py  scan_functions.py  grade_functions.py  keymaker.py
      openQ.py  ocr.py  ai_ocr.py  init_functions.py  image.py
      settings.py  dicts.py
    ui/
      build_tab.py          replaces pyExamPaper's gui.py
      scan_tab.py           the current scanner gui.py
      review.py             the open-question review window from openQ.py
  tests/
    fixtures/
  pyexamkit.spec
  .github/workflows/build.yml
```

`keyformat.py` is the reason the merge is worth doing, so it should be written first and both halves converted to call it. It owns the ten-column layout including `points`, the `metadata` rows, the `bubble` and `open` row shapes, the pipe-separated answer lists, and the encoding decision. Nothing else in the codebase is allowed to write a key CSV.

## Phases

### Phase 0: the gate, half a day

Run the OpenCV experiment described in `scanner-packaging-options.md` before touching anything else, on a branch, in the scanner repo as it stands.

Rewrite `scan_functions.py` against `opencv-python-headless`: `cvtColor`, `medianBlur`, `threshold`, `erode`, `dilate`, `connectedComponentsWithStats`, `getAffineTransform`, `warpAffine`. Remove scipy and scikit-image from `pyproject.toml` and delete the two `collect_submodules` sweeps from the spec. Note that you dropped OpenCV once before to chase better PyInstaller behavior, but from the plain `opencv-python` package; `opencv-python-headless` is the variant to use, since it omits the GUI bindings that pull in Qt and the video libraries, and those were the parts that misbehaved.

Then verify. Take an exam PDF you have already graded, run it through both old and new code, and diff the bubble dictionaries and the graded CSV. They should match exactly, because the same pixels go through the same arithmetic. Build with PyInstaller on macOS and on Windows, record both bundle sizes, and install the macOS build on a machine that has never had Python.

Two failure modes to watch. If the alignment looks plausible but slightly wrong, the affine inverse-map direction is backwards; skimage's `warp` treats its transform as an output-to-input map, so `cv2.warpAffine` needs `flags=cv2.WARP_INVERSE_MAP`. If the median blur errors on the size-15 call, the grayscale conversion is happening after the blur instead of before, because `cv2.medianBlur` only accepts kernels above 5 on 8-bit input.

**If the outputs match and the clean-machine install works, proceed to phase 1 and abandon the Tauri port.** If PyInstaller is still unreliable with a clean dependency tree, stop and reopen the question, because then the Tauri plan for pyExamPaper comes back off the shelf and the two apps stay separate.

### Phase 1: the shared contract, one to two days

Before merging any code, write `keyformat.py` in the scanner repo and make the scanner use it. It needs a reader that accepts both the nine-column and ten-column layouts, since keys written by both programs exist on disk today, and a writer that emits only the ten-column form with `points`. Fix the encoding to plain UTF-8 on write and tolerate a byte-order mark on read.

Test it against every key CSV you can find in `tests/` and in your course folders. This is the step that fixes the silent points loss, and it is worth doing carefully and on its own, so that if something breaks later you know it was not this.

### Phase 2: move pyExamPaper in, two to three days

Copy `models.py`, `parser.py`, `exam_builder.py`, `renderer.py`, `exam_config.py`, and `templates/exam.html` into `pyexamkit/build/` unchanged. They are pure Python with no GUI coupling and should need no edits. Delete `key_generator.py` and route its callers to `keyformat.py`.

Generate golden fixtures from the current pyExamPaper before the move, the way phase 0 of the shelved Tauri plan described, and check the moved code against them. The fixture work is not wasted by the change of plan; it is the only way to know the move was clean, and it is cheaper here because both sides are Python and byte-identical output is the expected result rather than an aspiration.

The scanner's markdown parsing, wherever it duplicates what `parser.py` does, should be pointed at `parser.py` instead.

### Phase 3: one interface, three to five days

Rebuild pyExamPaper's window as `ui/build_tab.py` in customtkinter, then remove PySide6 from the dependencies. Reproduce the existing layout rather than redesigning it: title and course, the exact-file or pools radio pair, the pool table with its running totals and per-pool points column, the shuffle and version options, the conditional same-questions row, the version-identifier question with its position dropdown, the output folder picker, config load and save, the generate button, and the log pane. Carry the validation messages over word for word.

The pool table is the only widget without a direct customtkinter equivalent, since there is no table widget. A scrollable frame of row widgets is the normal approach and is adequate for the handful of pools an exam uses.

Wire both halves into `app.py` behind a tab switcher. Keep the two workflows visually distinct; a professor building an exam and a professor grading one are in different modes of thought and should not have to hunt for the right controls.

### Phase 3.5: ordering and matching questions, three to four days

Add support for the qtiConverter `OR` and `MT` types, which currently exist in the pools and are skipped silently. The full specification, including a survey of the eight real items in the BIOL 206 pools and the six-bubble limit they have to fit, is in `docs/ordering-matching-spec.md`. It also fixes an existing points bug in MD questions, so read it before phase 1 rather than after, since the fix belongs in `keyformat.py`.

Build it here rather than earlier. Doing it before the merge means writing it twice.

### Phase 4: ship it, one to two days

Write `pyexamkit.spec` from the existing one, with the scipy and scikit-image sweeps gone and `collect_data_files('customtkinter')` kept. Add a GitHub Actions workflow that builds macOS and Windows on tag pushes; schedulingApp's `build-tauri.yml` is the wrong toolchain but the right shape, and its artifact upload and tag trigger can be copied directly.

Rewrite the README. The current one is stale on two counts: it documents a Miniconda and OpenCV install that no longer matches `pyproject.toml`, and after this work there is no install procedure left to document beyond downloading a file. Reuse schedulingApp's wording for the Windows SmartScreen warning and the macOS `xattr -cr` step, since your users have been walked through both already.

## Risks, honestly

The GUI rewrite in phase 3 is the largest chunk of work and the least interesting. It is a straight transcription with no new behavior, which makes it tedious and easy to rush. Budget for it properly and resist redesigning the form while transcribing it.

Merging means one release train. A bug in the exam builder now blocks a scanner release and the reverse. At your scale that is a fair trade for the shared key format, but it is a real cost and it argues for keeping `build/` and `scan/` genuinely independent, talking only through `keyformat.py`.

The bundle will be larger than either app alone, probably 150 to 250 MB. That is invisible to a user who downloads it once a year.

PyMuPDF is AGPL, which carries obligations when distributing binaries. Your repository is public so you are almost certainly compliant already, but it is worth knowing before the app goes to other departments. It is used in three places, all rasterizing a PDF page at 200 DPI, and `pypdfium2` is a permissively licensed substitute if it ever matters.

## What happens to the Tauri work

`pyExamPaper/docs/tauri-port-plan.md` stays in the repo. If phase 0 fails, it is the fallback and it is still accurate. If phase 0 succeeds, it is a record of a road not taken and of why, which is worth more than deleting it.

The `src-tauri` directory restored in schedulingApp today is unaffected either way. That repo stays a Tauri app; it has no Python in it and no reason to change.
