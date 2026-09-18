# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Define data files to include
added_files = [
    ('src/icon/*.png', 'src/icon'),
    ('src/icon/*.ico', 'src/icon'),
    ('drivers/camera/DLL/*.dll', 'drivers/camera/DLL'),
    ('calib/*.yaml', 'calib'),
    ('translations.yaml', '.'),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    # Pillow 11 已无 PIL._tkinter_guess，留着只会让 PyInstaller 报一行
    # "Hidden import not found"（无实际影响），删掉。
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Torch/jupyter/pandas 一类只在可选 GPU 分支(try-except)或第三方包内部被引用，
    # 本程序一行都没用。不排除的话 PyInstaller 会把 torch+cu128 DLL 全打进 dist
    # (0.4GB -> 7.6GB)。现场机器无 GPU，排除不影响运行行为。
    excludes=[
        'torch', 'torchvision', 'torchaudio', 'torchtext',
        'tensorflow', 'tensorboard',
        'pandas',
        'IPython', 'jedi', 'parso', 'pygments', 'astroid',
        'nbformat', 'jsonschema', 'jsonschema_specifications', 'traitlets',
        'zmq', 'sympy',
    ],
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
    name='vsDriverBox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src/icon/State_Standby.ico', # Use the multi-resolution ICO file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='vsDriverBox',
)
