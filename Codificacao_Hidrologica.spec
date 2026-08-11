# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files, collect_submodules

# Coleta recursiva de todos os sub-módulos críticos para evitar erros de DLL
hidden_pandas = collect_submodules('pandas')
hidden_numpy = collect_submodules('numpy')

datas = collect_data_files('pyproj')
datas += collect_data_files('geopandas')
datas += collect_data_files('fiona')

block_cipher = None

a = Analysis(
    ['Codificacao_GUI.py'],
    pathex=[os.getcwd()],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PySide6',
        'pyodbc',
        'fiona',
        'shapely',
        'geopandas',
        'rtree',
        'pyogrio',
        'dotenv',
        'openpyxl',
        'pyproj',
        'pywin32',
        'encodings',
        'jaraco.text',
        'jaraco.context',
        'pkg_resources.extern',
        'platformdirs',
        'numpy',
        'pandas._libs.tslibs.timedeltas',
        'pandas._libs.window.aggregations', 
    ] + hidden_pandas + hidden_numpy,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Coleta DLLs do sistema necessárias para o interpretador
a.binaries += collect_dynamic_libs('vcruntime140')

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Codificacao_Hidrologica',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/pluviometer.ico',
)