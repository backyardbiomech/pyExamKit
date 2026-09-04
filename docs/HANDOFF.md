# Handoff: pyExamPaper + pyExamScan merge

*Written 2026-09-04. Start here. Everything below is planning only. No code has been changed in either exam repo.*

## The decision

**Merge pyExamPaper into pyExamScan_v2 as one Python app. Do not port anything to Tauri.**

This reversed an earlier recommendation in the same session, and the reversal is the most important thing to carry forward. The original goal was easier cross-platform distribution, and the assumed route was rewriting pyExamPaper in TypeScript on Tauri, matching the `schedulingApp` repo. An audit showed the packaging pain has a much smaller cause, so the rewrite is unnecessary.

## The three documents, in reading order

1. **`pyExamScan_v2/docs/scanner-packaging-options.md`** — the audit that changed the plan. The whole scipy and scikit-image surface of the scanner is eight function calls, all in one 217-line file, `scan_functions.py`. Those two libraries are what make PyInstaller unreliable. Replace them with `opencv-python-headless` and the problem largely goes away.
2. **`pyExamScan_v2/docs/merge-and-package-plan.md`** — the plan itself, phases 0 through 4.
3. **`pyExamScan_v2/docs/ordering-matching-spec.md`** — the OR and MT feature, which is phase 3.5.

`pyExamPaper/docs/tauri-port-plan.md` is shelved, marked superseded at the bottom, and is the fallback if phase 0 fails. Do not delete it.

## Repository state right now

| Repo | State |
|---|---|
| `pyExamScan_v2` | clean except untracked `docs/`, containing the three files above |
| `pyExamPaper` | clean except untracked `docs/`, containing the shelved Tauri plan |
| `schedulingApp` | **63 restored files staged and uncommitted**, see below |

`schedulingApp` had its entire `src-tauri/` directory deleted by commit `17df1de` ("cleanup", 2026-08-13), which is still unpushed and one commit ahead of origin. That repo could not build, and neither could its CI. The files were restored this session with `git checkout 17df1de^ -- src-tauri` and are staged but **not committed**, pending Brandon confirming the deletion was unintentional. He said he did not know whether it was.

That repo is otherwise unrelated to this work. It stays a Tauri app and needs no changes.

## Next action: phase 0, the gate

Half a day, on a branch in `pyExamScan_v2`, before any merge work. Everything downstream depends on the outcome.

Rewrite `scan_functions.py` against `opencv-python-headless`, using `cvtColor`, `medianBlur`, `threshold`, `erode`, `dilate`, `connectedComponentsWithStats`, `getAffineTransform`, and `warpAffine`. Remove scipy and scikit-image from `pyproject.toml`, and delete the two `collect_submodules` sweeps from `pyexamscan.spec`.

Brandon previously dropped OpenCV to chase better PyInstaller behavior, but that was the plain `opencv-python` package. Use the **headless** variant, which omits the GUI bindings that pull in Qt and the video libraries.

Verify by running an already-graded exam PDF through old and new code and diffing the bubble dictionaries and the graded CSV. They should match exactly. Then build with PyInstaller on macOS and Windows, and install the macOS build on a machine that has never had Python.

Two failure modes. Alignment that looks plausible but is slightly off means the affine inverse-map direction is backwards; skimage's `warp` treats its transform as an output-to-input map, so `cv2.warpAffine` needs `flags=cv2.WARP_INVERSE_MAP`. An error on the size-15 median blur means grayscale conversion is happening after the blur rather than before, since `cv2.medianBlur` only accepts kernels above 5 on 8-bit input.

**If it passes, proceed to phase 1 and abandon the Tauri plan. If PyInstaller is still unreliable with a clean dependency tree, stop and reopen the question.**

## Phase 0 result (2026-09-04)

Done on branch `phase0-opencv-rewrite`, uncommitted, pending your review. Touches exactly four files: `scan_functions.py`, `pyproject.toml`, `pyexamscan.spec`, `uv.lock`.

The rewrite matches the original exactly. `results.csv`, `resultsperquestions.csv`, `resultsforCanvas.csv`, and `exam_key.csv` came out byte-identical between the old (scipy/scikit-image) and new (opencv) code, run against `tests/scannedSheets.pdf` through the full `Scanner` pipeline, not just the isolated functions. The aligned JPEGs are not bit-identical — up to 11/255 per-pixel difference, from JPEG re-encoding and cv2's bilinear sampling differing slightly from skimage's — but that magnitude never crosses a threshold decision, which is why the final dictionaries and CSVs match exactly regardless. Neither of the two predicted failure modes showed up: alignment was correct on the first attempt (the `WARP_INVERSE_MAP` direction reasoning in this doc held), and the size-15 median blur ran fine (grayscale-before-blur ordering was preserved). `cv2.threshold` ended up unused; it applies `<=` at the threshold value where the original code and every other spot in this rewrite use strict `<`, so the comparison stayed a plain numpy expression instead, to keep the match exact rather than approximate.

PyInstaller built cleanly on macOS (Apple Silicon, arm64), and the resulting `.app` launches standalone — run directly by path outside the dev venv, no dev tools on `PATH` beyond what's already on this machine — and stays up with no stderr output, which is the strongest local proxy available for "never had Python." It has **not** been installed on a genuinely clean machine; that check is still open.

**The bundle got bigger, not smaller — this contradicts `scanner-packaging-options.md`'s prediction.** Old (scipy + scikit-image, with the `collect_submodules` sweeps): 222 MB. New (opencv-python-headless): 253 MB. The audit's "one 40 MB wheel replaces about 150 MB" estimate was the wheel download size, not what PyInstaller collects. `cv2` alone accounts for 118 MB unpacked: a 40 MB `cv2.abi3.so` plus a full video-codec stack this project never touches — `libavcodec`, `libx265`, `libaom`, `libSvtAv1Enc`, `librav1e`, `libavformat`, even `libtesseract`. "Headless" strips the GUI/window bindings, not the codecs; there's no way to select OpenCV submodules from the prebuilt wheel. Trimming this (a source build with only `imgproc`, or Option B's hand-rolled numpy from the same audit doc) is a real option later if the size matters, but it wasn't attempted here — flagging it for a decision rather than deciding it. Per the plan's own risk section, a bundle this size is "invisible to a user who downloads it once a year," so this did not block the phase 0 gate, which was about correctness and PyInstaller reliability, not size.

**Still open, and outside what could be done in this session:** the Windows PyInstaller build (`.github/workflows/build.yml` already exists and builds both platforms on `workflow_dispatch` — needs a push of this branch and a triggered run, both of which need your go-ahead since they're visible/shared-state actions), and the clean-machine install check on macOS.

Given the strength of the local evidence, the recommendation is to proceed to phase 1 once the Windows build and a real clean-machine spot check confirm out — but that confirmation is still yours to run or authorize.

## Two real bugs found, both unfixed

**Points are silently lost round-tripping a key CSV.** `pyExamPaper/key_generator.py` writes ten columns ending in `points`. `pyExamScan_v2/openQ.py:save_key_csv` writes nine and has no `points` column, though its reader does parse one. Build an exam with per-pool point values, open the key in the scanner's open-question editor, save, and every per-question point value is gone with no error. This is the strongest argument for the merge and is fixed by `keyformat.py` in phase 1.

**MD questions are worth too much.** `key_generator.py` writes the full point value onto every dropdown row, and `gradeResults` sums per column, so a three-dropdown MD tagged `(1 pt)` scores three points. Fixed by the same points-distribution rule as OR and MT. Brandon may want to check recent MD-containing exams.

## Open question, deliberately parked

`BIOL207/QuestionBanks/exam3Banks/ch24urin_level1.txt` contains an eleven-step ordering question. The answer sheet has six bubbles per question, and an ordering cannot be trimmed without changing what is asked, so it cannot go on paper. Options are splitting it at a natural seam, rewriting it as MC with whole orderings as the choices, or leaving it Canvas-only. **Brandon said to leave this for now.** It is a content decision, not a blocker, but it should be settled before BIOL 207 uses the feature.

## Facts worth not rediscovering

The answer sheet has exactly **six bubbles per question, A through F**, and 150 question slots. The limit lives in the printed sheet, whose coordinates are fixed in `dicts.py`; the `range(0, 6)` in `init_functions.py:180` mirrors the paper. This is why `_trim_mc_answers` uses `max_choices=6`, and it caps OR at six items and MT at six right-side options.

`scan_functions.py` was originally written against OpenCV. Its comments still say things like "THRESH_BINARY_INV equivalent". Moving back is closer to reverting than porting.

The scanner's numpy surface is sixteen trivial calls. Pandas is four call types but used about a hundred times through `grade_functions.py` and `scanner.py`, so pandas stays.

The working scan image is 1584 by 1224, set in `settings.py`, so roughly 1.9 million pixels. None of the image work is heavy.

OR and MT questions need **no scanner changes at all**. They emit ordinary `bubble` rows carrying a single letter. If a proposal starts requiring a `group` column in the key CSV, reconsider it.

The current `pyExamScan_v2/README.md` is stale, documenting a Miniconda and OpenCV install that no longer matches `pyproject.toml`.

## Working preferences that shaped these documents

Plans go in `docs/` as markdown, never hard-wrapped. Prose over bullets. Verify claims against the actual files rather than recalling them; every number in these three documents came from reading the code or the pools. Ask before large or destructive changes.
