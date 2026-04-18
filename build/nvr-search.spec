# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

LITERT_SITE = "/home/yimstar9/.local/share/uv/tools/litert-lm/lib/python3.12/site-packages"

block_cipher = None

# 각 패키지의 데이터/바이너리 수집
datas = []
binaries = []
hiddenimports = []

for pkg in ["gradio", "gradio_client", "chromadb", "sentence_transformers",
            "litert_lm", "litert_lm_cli", "tokenizers", "transformers",
            "huggingface_hub", "safetensors", "watchdog", "cv2"]:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# litert_lm .so 파일들 명시적으로 포함
litert_so_dir = os.path.join(LITERT_SITE, "litert_lm")
for so_file in Path(litert_so_dir).glob("*.so"):
    binaries.append((str(so_file), "litert_lm"))

# sentence-transformers 캐시 모델 포함 (빌드 전 미리 다운로드 필요)
EMBEDDING_MODEL_CACHE = os.path.expanduser(
    "~/.cache/nvr-search-embedding"
)
if os.path.exists(EMBEDDING_MODEL_CACHE):
    datas.append((EMBEDDING_MODEL_CACHE, "nvr_embedding_model"))

a = Analysis(
    ["../app.py"],
    pathex=["../", LITERT_SITE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "config", "pipeline", "search",
        "yaml", "chromadb.api.types",
        "hnswlib", "grpc",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PIL", "IPython"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nvr-search",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="nvr-search",
)
