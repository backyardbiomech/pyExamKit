# pyexamscan.spec
# Build with: uv run pyinstaller pyexamscan.spec

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ['pyExamScan_v2.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('images/', 'images'),
        *collect_data_files('skimage'),
        *collect_data_files('customtkinter'),
        *collect_data_files('scipy'),
    ],
    hiddenimports=[
        *collect_submodules('skimage'),
        *collect_submodules('pandas'),
        *collect_submodules('scipy'),
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
    name='PyExamScan',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PyExamScan',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='PyExamScan.app',
    icon=None,
    bundle_identifier='com.pyexamscan.app',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '3.0.0',
        'CFBundleName': 'PyExamScan',
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
    },
)
