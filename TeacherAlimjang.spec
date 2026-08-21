# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/privacy/roster_sample.csv', 'app/privacy'),
        # 앱 전체가 나눔고딕 하나로 통일되어 있다(main.py의
        # _register_bundled_fonts() 참고). 이 datas 목록은 파일이 있어야
        # 할 자리에 실수로 빠지면 배포된 exe에서만 조용히 폰트가 시스템
        # 기본값으로 대체되는(개발 중엔 안 드러나는) 문제가 실제로 있었던
        # 적이 있어 — 폰트 파일을 추가/교체할 땐 항상 여기도 같이 고칠 것.
        ('app/ui/assets/fonts/NanumGothic-Regular.ttf', 'app/ui/assets/fonts'),
        ('app/ui/assets/fonts/NanumGothic-Bold.ttf', 'app/ui/assets/fonts'),
        # 체크박스 체크 표시 아이콘 (app/config.py의 checkmark_icon_path() 참고)
        ('app/ui/assets/checkmark.png', 'app/ui/assets'),
        # QSpinBox 위/아래 화살표 아이콘 (app/config.py의
        # spin_arrow_icon_path() 참고) — 이 datas 목록에 안 넣으면
        # 개발 환경(python main.py)에서는 소스 트리 경로로 잘 뜨다가,
        # 배포된 exe에서만 sys._MEIPASS 밑에 파일이 없어서 화살표가 조용히
        # 안 보이는 문제가 실제로 있었다(위 나눔고딕 폰트 주석과 같은 종류의
        # 함정 — QTest로 python main.py를 검증해도 안 걸러진다).
        ('app/ui/assets/spin_up_arrow.png', 'app/ui/assets'),
        ('app/ui/assets/spin_down_arrow.png', 'app/ui/assets'),
        # 트레이/창 아이콘을 런타임에 QIcon으로 다시 로드하기 위해 필요
        # (app/config.py의 icon_path() 참고). EXE 리소스 아이콘(icon=
        # 파라미터, 아래)과는 별개 — 그건 exe 파일 자체의 아이콘일 뿐,
        # 코드에서 QIcon(...)으로 읽어들일 수 있는 파일이 아니다.
        ('app/ui/assets/app_icon.ico', 'app/ui/assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TeacherAlimjang',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app/ui/assets/app_icon.ico'],
)
