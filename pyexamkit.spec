# pyexamkit.spec
# Build with: source .venv/bin/activate && python -m PyInstaller pyexamkit.spec -y
# NOTE: use "python -m PyInstaller" (not bare "pyinstaller") to ensure the venv
# Python is used for analysis; otherwise conda's Python may be picked up and
# packages like customtkinter won't be found.

import re

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


def _bundle_version():
    """The release version, as macOS wants it: one to three integers.

    The git tag is the only place a version number is written. hatch-vcs
    turns it into the installed package's version at `uv sync` time, and
    this reads it back, so a release cannot ship a version that disagrees
    with the tag that built it. Off a tag, hatch-vcs appends a .postN.devN
    suffix that CFBundleShortVersionString will not accept, so only the
    leading numeric part is kept.
    """
    try:
        from importlib.metadata import version
        found = version('pyexamkit')
    except Exception:
        return '0.0.0'
    match = re.match(r'^(\d+(?:\.\d+){0,2})', found)
    return match.group(1) if match else '0.0.0'


BUNDLE_VERSION = _bundle_version()

a = Analysis(
    ['pyExamKit.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('images/', 'images'),
        ('templates/', 'templates'),
        *collect_data_files('customtkinter'),
    ],
    hiddenimports=[
        *collect_submodules('pandas'),
        *collect_submodules('customtkinter'),
        'PIL._tkinter_finder',
        'fitz',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['jupyter', 'IPython', 'ipykernel', 'matplotlib'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PyExamKit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='images/AppIcon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PyExamKit',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='PyExamKit.app',
    icon='images/AppIcon.icns',
    bundle_identifier='com.pyexamkit.app',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': BUNDLE_VERSION,
        'CFBundleVersion': BUNDLE_VERSION,
        'CFBundleName': 'PyExamKit',
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
    },
)
