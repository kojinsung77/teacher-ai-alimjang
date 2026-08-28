# 교사업무 AI 알림장 — 설치 파일을 처음부터 끝까지 한 번에 만드는 스크립트.
#
# 왜 이 스크립트가 필요한가:
#   PyInstaller로 exe를 만드는 단계와 Inno Setup으로 설치 파일을 만드는
#   단계가 분리되어 있으면, "코드만 고치고 PyInstaller는 다시 안 돌린 채
#   Inno Setup만 재컴파일"하는 실수가 생기기 쉽다. 이 스크립트는 그 실수
#   자체가 불가능하도록 두 단계를 하나의 명령으로 묶고, 매번 build/·dist/
#   폴더를 깨끗이 지우고 처음부터 다시 빌드한다(증분 빌드가 뭔가를
#   놓칠 가능성 자체를 원천 차단).
#
# 사용법: 프로젝트 루트에서 실행
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# 실행 파일만 필요하면(설치 프로그램 없이): -SkipInstaller
#   powershell -ExecutionPolicy Bypass -File build.ps1 -SkipInstaller
#
# 앱 아이콘 파일을 이번 릴리스에서 실제로 바꿨을 때만: -IconChanged
#   powershell -ExecutionPolicy Bypass -File build.ps1 -IconChanged
#   -> 설치 프로그램이 설치 마지막에 탐색기(explorer.exe)를 재시작해 아이콘
#      캐시를 확실히 비운다(화면이 한 번 깜빡임). 옵션을 안 주면 화면에
#      영향 없는 가벼운 캐시 갱신만 한다. ISCC에 /DIconChanged=1로 전달된다.

param(
    [switch]$SkipInstaller,
    [switch]$IconChanged
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Write-Step($msg) {
    Write-Output ""
    Write-Output "=== $msg ==="
}

# ---------- 1) 이전 빌드 산출물 완전히 정리 ----------
Write-Step "1/4  이전 빌드 정리 (build/, dist/)"
Remove-Item -Path (Join-Path $root "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path (Join-Path $root "dist") -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "정리 완료"

# ---------- 2) 실행 중인 인스턴스가 있으면 exe 파일이 잠겨서 새로
#    쓰지 못할 수 있으니 미리 종료를 시도한다 (없으면 조용히 넘어감) ----------
# 와일드카드로 잡는다 — "TeacherAlimjang" 정확히 일치만 찾으면
# TeacherAlimjang_debug 같은 다른 빌드 변종을 놓친다. 실제로 그런
# 변종 하나가 자동 시작 레지스트리 잔재로 인해 며칠째 안 죽고 백그라운드에서
# 실행 중이었던 게 발견된 적이 있다(실데이터 손실 사건의 유력한 원인 중
# 하나로 의심됨) — 그 교훈으로 여기서도 패턴을 넓혀 잡는다.
Write-Step "2/4  실행 중인 인스턴스 확인"
$existing = Get-Process -Name "TeacherAlimjang*" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "종료 시도: $(($existing | Select-Object -ExpandProperty ProcessName -Unique) -join ', ')"
    $existing | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    $stillRunning = Get-Process -Name "TeacherAlimjang*" -ErrorAction SilentlyContinue
    if ($stillRunning) {
        Write-Output "경고: 다음 프로세스를 종료하지 못했습니다(권한 문제 등) — 빌드 산출물이 잠겨 있을 수 있습니다: $(($stillRunning | Select-Object -ExpandProperty ProcessName -Unique) -join ', ')"
    }
}
Write-Output "확인 완료"

# ---------- 3) PyInstaller로 처음부터 새로 빌드 ----------
Write-Step "3/4  PyInstaller 빌드 (clean)"
Push-Location $root
try {
    python -m PyInstaller --noconfirm --clean TeacherAlimjang.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 빌드 실패 (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$exePath = Join-Path $root "dist\TeacherAlimjang.exe"
if (-not (Test-Path $exePath)) { throw "dist\TeacherAlimjang.exe 가 생성되지 않았습니다." }
$exeInfo = Get-Item $exePath
Write-Output "빌드 완료: $($exeInfo.FullName) ($([math]::Round($exeInfo.Length / 1MB, 1)) MB, $($exeInfo.LastWriteTime))"

if ($SkipInstaller) {
    Write-Step "완료 (설치 프로그램은 건너뜀 -SkipInstaller)"
    exit 0
}

# ---------- 4) Inno Setup으로 설치 프로그램 컴파일 ----------
Write-Step "4/4  Inno Setup 컴파일"
$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    )
    $found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $found) { throw "ISCC.exe(Inno Setup 컴파일러)를 찾을 수 없습니다." }
    $isccPath = $found
} else {
    $isccPath = $iscc.Source
}

Push-Location (Join-Path $root "installer")
try {
    $isccArgs = @()
    if ($IconChanged) {
        $isccArgs += "/DIconChanged=1"
        Write-Output "아이콘 변경 모드(-IconChanged): 설치 마지막에 탐색기를 재시작해 아이콘 캐시를 확실히 갱신합니다(화면이 한 번 깜빡임)."
    } else {
        Write-Output "기본 모드: 가벼운 아이콘 캐시 갱신만(SHChangeNotify + ie4uinit). 탐색기는 건드리지 않습니다."
    }
    $isccArgs += "setup.iss"
    & $isccPath @isccArgs
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup 컴파일 실패 (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$setupPath = Get-ChildItem (Join-Path $root "installer\output\*.exe") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Step "완료"
Write-Output "설치 프로그램: $($setupPath.FullName) ($([math]::Round($setupPath.Length / 1MB, 1)) MB)"
Write-Output "exe 빌드 시각과 비교해서 이 설치 프로그램이 방금 만든 exe를 담고 있는지 확인하려면:"
Write-Output "  dist\TeacherAlimjang.exe LastWriteTime: $($exeInfo.LastWriteTime)"
