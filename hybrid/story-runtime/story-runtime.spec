# PyInstaller specification for the user-facing Runtime bundle.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("story_runtime")

a = Analysis(
    ["src/story_runtime/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="story-runtime",
    console=True,
    strip=False,
    upx=False,
)
