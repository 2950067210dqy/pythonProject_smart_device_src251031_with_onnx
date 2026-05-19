# -*- mode: python ; coding: utf-8 -*-

tracker_hiddenimports = [
    'lap',
    'scipy',
    'scipy.optimize',
    'scipy.optimize._lsap',
    'scipy.spatial',
    'scipy.spatial.distance',
    'scipy.spatial._distance_pybind',
    'scipy.spatial._distance_wrap',
    'ultralytics.trackers',
    'ultralytics.trackers.byte_tracker',
    'ultralytics.trackers.bot_sort',
    'ultralytics.trackers.track',
    'ultralytics.trackers.utils.matching',
]

packaging_excludes = [
    # 修改：程序运行 ONNX 推理只需要 onnxruntime；onnx 是导出/校验用，打包时排除避免 onnx.reference 崩溃。
    'onnx',
    'onnx.reference',
    'onnx.reference.ops',
    'onnx.reference.ops_optimized',
    'ml_dtypes',
    # 修改：项目运行不需要 tensorboard，排除后避免 torch.utils.tensorboard 的缺失 warning。
    'tensorboard',
    'torch.utils.tensorboard',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=tracker_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=packaging_excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='有害生物智能化数据分析平台',
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
    icon='img.ico'
)
sender_analysis = Analysis(
    ['socket_original/sender_for_dqy.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=packaging_excludes,
    noarchive=False,
    optimize=0,
)
sender_pyz = PYZ(sender_analysis.pure)

sender_exe = EXE(
    sender_pyz,
    sender_analysis.scripts,
    [],
    exclude_binaries=True,
    name='有害生物智能化数据分析平台_下位机模拟',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='img.ico'
)
coll = COLLECT(
    exe,
    sender_exe,
    a.binaries,
    a.datas,
    sender_analysis.binaries,
    sender_analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main',
)
