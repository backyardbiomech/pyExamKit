# pyExamScan_v2: what the scientific libraries actually do, and how to package this reliably

*Written 2026-09-04, after an audit of all 6,327 lines. Companion to `pyExamPaper/docs/tauri-port-plan.md`.*

## The short answer

Yes, every one of those functions is transferable, and the job is far smaller than the dependency list suggests. **The entire scipy and scikit-image surface of this program is eight function calls, and all eight live in one 217-line file, `scan_functions.py`.** Nothing else in the codebase imports either library.

That reframes the whole problem. The packaging pain is not caused by the app being scientific. It is caused by two large, awkward libraries being pulled in to supply eight functions, one of which is a weighted sum of three numbers.

## Exactly what is used

| Call | Where | What it really is |
|---|---|---|
| `rgb2gray` | `scan_functions.py:40, 92` | `0.2125·R + 0.7154·G + 0.0721·B`, one line |
| `median_filter(size=7)` and `(size=15)` | `:41, 93` | square median blur |
| `binary_erosion` / `binary_dilation`, 4x4 rectangle, 3 iterations | `:111, 112` | rectangular morphology, separable, equivalent to one pass with a 10x10 box |
| `label(connectivity=2)` | `:46, 136` | 8-connected component labeling |
| `regionprops` | `:47, 137` | only `.area`, `.bbox`, and `.centroid` are read |
| `AffineTransform.from_estimate` | `:20` | three point pairs solve an affine exactly, no least squares involved |
| `warp(order=1)` | `:24` | bilinear inverse warp to a fixed 1584x1224 canvas |

The numpy surface is just as thin: sixteen distinct calls across the whole program, and they are `array`, `uint8`, `median`, `full`, `ones`, `argmax`, `vstack`, `hstack`, and `delete`. Nothing exotic. Pandas is four calls, `read_csv`, `DataFrame`, `concat`, and `Series`, but they are used about a hundred times through `grade_functions.py` and `scanner.py`, so pandas stays.

Two more things worth knowing. The working image is 1584 by 1224, which is 1.9 million pixels, not the eight or ten million a raw 300 DPI scan would be, so none of this is heavy by modern standards. And the comments in `scan_functions.py` still say things like "THRESH_BINARY_INV equivalent", which means this file was originally written against OpenCV and was ported to scipy plus scikit-image at some point. That matters below.

## The real diagnosis

The current `pyexamscan.spec` calls `collect_submodules` and `collect_data_files` on both scipy and scikit-image. Those two calls are a confession. They exist because PyInstaller cannot trace those libraries statically, so the spec sweeps in everything and hopes. Between them, scipy and scikit-image add roughly 150 MB of compiled extensions, lazy loaders, and data files, and they are the two packages most likely to produce a bundle that builds on your machine and dies on someone else's with a missing `.so`.

The rest of the dependency list is well behaved. Numpy, Pillow, and pandas have official PyInstaller hooks. PyMuPDF ships a self-contained wheel with MuPDF compiled in. fpdf2 is pure Python. The Anthropic SDK is pure Python over httpx. customtkinter needs its data files collected, which the spec already does correctly, and that is the whole of its awkwardness.

**Remove scipy and scikit-image and the packaging problem is mostly gone.** That is a change to one file.

## Three options

### Option A: stay in Python, replace the eight functions with OpenCV

`opencv-python-headless` is a single self-contained wheel per platform whose only dependency is numpy, and PyInstaller has a built-in hook for it. It supplies direct replacements for all eight calls: `cvtColor`, `medianBlur`, `threshold`, `erode`, `dilate`, `connectedComponentsWithStats`, `getAffineTransform`, and `warpAffine`. Since the file was written against OpenCV to begin with, this is closer to reverting than to porting.

The old README's OpenCV horror story, the one with `conda install openblas=0.2.19` in it, was a conda problem, not an OpenCV problem. The pip wheels have been reliable for years, and the headless variant drops the GUI bindings that caused most of the remaining trouble.

Cost: about a day. Net bundle change is a reduction, since one 40 MB wheel replaces about 150 MB of scipy and scikit-image.

Two details that will bite if missed. `cv2.medianBlur` accepts a kernel larger than 5 only on 8-bit images, which is satisfied here because the grayscale conversion produces uint8, but the conversion has to happen before the blur. And skimage's `warp` treats the transform it is handed as an output-to-input map, while `cv2.warpAffine` maps input to output by default, so the call needs `flags=cv2.WARP_INVERSE_MAP` or an inverted matrix. Getting that backwards produces a plausible-looking but wrongly aligned page, which is the worst kind of bug here.

### Option B: stay in Python, hand-roll the eight functions in numpy

Zero new dependencies, smallest possible bundle, and nothing left in the tree that PyInstaller cannot trace. Seven of the eight are genuinely easy: the grayscale conversion is one line, the threshold already is numpy, the rectangular erosion and dilation are separable and can also be had from Pillow's `MinFilter` and `MaxFilter`, the affine solve is `np.linalg.solve` on two three-unknown systems, and the bilinear warp is a `meshgrid` and some fancy indexing, about twenty lines and fully vectorized.

The eighth is real work. Connected-component labeling with 8-connectivity means a two-pass union-find, roughly a hundred lines, and a naive Python implementation over 1.9 million pixels will be slow enough to notice. It is solvable, by labeling row runs rather than pixels, but it needs writing and benchmarking rather than assuming.

The median filter also needs measuring. Pillow's `ImageFilter.MedianFilter` handles arbitrary odd sizes in C and is the obvious substitute, but its edge handling differs from scipy's, so a few boundary pixels will change. That is immaterial to blob detection downstream, and it does mean outputs will not be bit-identical to today's.

Cost: three or four days, most of it on labeling.

### Option C: rewrite the scanner in Rust or TypeScript behind a Tauri front end

Now that the surface is known, this is smaller than it looked. In Rust, `imageproc` supplies median filtering, morphology, and connected components, and `image` handles decoding, so the work is roughly the same 217 lines plus glue. The rest of the program, all 6,100 lines of grading, key building, the open-question review interface, and the OCR calls, would also have to move, and that is the real cost. It is a project measured in weeks, and at the end you own a codebase in two languages you do not write.

There is no technical reason it cannot be done. There is a good practical reason not to do it now.

## Recommendation

**Take Option A, and keep the scanner in Python.** Swap the eight calls to OpenCV, delete scipy and scikit-image from `pyproject.toml`, strip the two `collect_submodules` sweeps out of `pyexamscan.spec`, and build on both platforms in GitHub Actions the way schedulingApp already does. You keep working in the language you know, in a codebase you understand, and the install instructions collapse from a six-step Miniconda walkthrough into "download this and double-click it".

Do Option B later only if the OpenCV wheel disappoints, and treat Option C as something to revisit in a year, if ever.

One thing worth deciding separately: whether you want the scanner's interface rebuilt. customtkinter is about eighty widgets across `gui.py` and `openQ.py`, and it works. If the interface is fine and only distribution hurts, Option A fixes distribution on its own and the GUI never needs touching. If you find yourself wanting the scanner to look like schedulingApp and pyExamPaper, that is a separate project, and the honest way to do it is a Tauri front end talking to the Python as a bundled command-line tool, which still requires Option A to have been done first.

## The experiment to run before committing

This is a claim that can be checked in an afternoon rather than argued about.

Branch, rewrite `scan_functions.py` against OpenCV, and drop scipy and scikit-image from the dependencies. Take a scanned exam PDF you have already graded, run it through both the old and new code, and compare the resulting bubble dictionaries and the graded CSV. They should match exactly, because thresholds and areas are computed from the same pixels by the same arithmetic. Then build with PyInstaller on macOS and on Windows, note the two bundle sizes, and install the macOS build on a machine that has never had Python on it.

If the outputs match and the clean-machine install works, Option A is done and the packaging question is answered. If the outputs diverge, the affine inverse-map direction is the first place to look.

## Correction, after running the experiment (2026-09-04)

The bundle prediction above was wrong. Phase 0 built both versions with PyInstaller to check: the scipy+scikit-image bundle is 222 MB, and the opencv-python-headless bundle is 253 MB, larger rather than smaller. The "40 MB wheel" figure was the download size, not what PyInstaller collects. Unpacked, `cv2` alone accounts for 118 MB: a 40 MB `cv2.abi3.so` plus a full video-codec stack this project never calls into — `libavcodec`, `libx265`, `libaom`, `libSvtAv1Enc`, `librav1e`, `libavformat`, even `libtesseract`. The headless variant strips the GUI/window bindings, as expected, but "headless" does not mean "codec-free," and there is no way to select individual OpenCV modules from the prebuilt wheel. The functional case for Option A is unaffected — the rewrite still produced byte-identical grading output and PyInstaller still built and ran cleanly — but the size argument in the recommendation below does not hold. If the extra ~30 MB ever matters, Option B (hand-rolled numpy) or a source build of OpenCV limited to `imgproc` are the ways to claw it back; neither was attempted here. Full numbers are in `docs/HANDOFF.md`'s phase 0 result section.

## Two smaller notes

The README in this repo is stale. It documents a Miniconda and OpenCV install that no longer matches the dependencies in `pyproject.toml`, which now say scipy and scikit-image. Whichever option you take, that file needs rewriting, and after Option A it gets much shorter.

PyMuPDF is licensed AGPL, which carries obligations when you distribute binaries. Your repo is public, so you are almost certainly already satisfying it, but it is worth being aware of before the app is handed to other departments. It is used in exactly three places, all of them rasterizing a PDF page at 200 DPI, so it is replaceable with `pypdfium2` under a permissive license if that ever becomes a problem.
