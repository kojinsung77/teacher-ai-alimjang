# 교사업무 AI 알림장 — 배포 원스톱 스크립트.
#
# "release.ps1 1.2.0" 한 줄이면: 버전 문자열 갱신 -> build.ps1로 클린
# 빌드 -> Setup.exe SHA256 계산 -> version.json 갱신(download_url은
# 그대로 유지) -> 구글 드라이브 동기화 폴더로 복사까지 전부 끝난다.
#
# build.ps1과 분리한 이유: build.ps1은 "지금 소스로 그냥 한 번 빌드해보고
# 싶다"는 개발 중 빠른 확인용으로 계속 남겨 두고(버전 번호를 안 건드림),
# 실제 배포(버전 올리고 해시 계산해서 배포 채널까지 올리는 것)는 별도
# 스크립트로 명확히 분리했다.
#
# 사용법: 프로젝트 루트에서 실행
#   powershell -ExecutionPolicy Bypass -File release.ps1 1.2.0

param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Write-Step($msg) {
    Write-Output ""
    Write-Output "=== $msg ==="
}

function Write-Utf8NoBom($path, $content) {
    # PowerShell 5.1의 Set-Content -Encoding utf8은 BOM을 붙인다.
    # config.py는 BOM이 있어도 Python이 알아서 처리하지만, 일관성을 위해
    # 여기서도 항상 BOM 없이 쓴다.
    [System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding($false)))
}

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "버전 형식이 이상합니다(예: 1.2.0 처럼 숫자.숫자.숫자여야 함): $Version"
}

# ---------- 1) app/config.py의 APP_VERSION 갱신 ----------
Write-Step "1/5  app/config.py APP_VERSION -> $Version"
$configPath = Join-Path $root "app\config.py"
$configContent = [System.IO.File]::ReadAllText($configPath)
$newConfigContent = $configContent -replace 'APP_VERSION = "[^"]*"', "APP_VERSION = `"$Version`""
if ($newConfigContent -eq $configContent) { throw "app/config.py에서 APP_VERSION 줄을 찾지 못했습니다." }
Write-Utf8NoBom $configPath $newConfigContent
Write-Output "완료"

# ---------- 2) installer/setup.iss의 MyAppVersion 갱신 ----------
Write-Step "2/5  installer/setup.iss MyAppVersion -> $Version"
$issPath = Join-Path $root "installer\setup.iss"
$issContent = [System.IO.File]::ReadAllText($issPath)
$newIssContent = $issContent -replace '#define MyAppVersion "[^"]*"', "#define MyAppVersion `"$Version`""
if ($newIssContent -eq $issContent) { throw "installer/setup.iss에서 MyAppVersion 줄을 찾지 못했습니다." }
Write-Utf8NoBom $issPath $newIssContent
Write-Output "완료"

# ---------- 3) build.ps1로 클린 빌드 (PyInstaller + Inno Setup) ----------
Write-Step "3/5  build.ps1 클린 빌드"
& (Join-Path $root "build.ps1")
if ($LASTEXITCODE -ne 0) { throw "build.ps1 실패 (exit $LASTEXITCODE)" }

$setupPath = Get-ChildItem (Join-Path $root "installer\output\*.exe") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setupPath) { throw "installer\output\*.exe 를 찾지 못했습니다." }
Write-Output "빌드된 설치 파일: $($setupPath.FullName)"

# ---------- 4) SHA256 계산 + version.json 갱신 ----------
Write-Step "4/5  SHA256 계산 및 version.json 갱신"
$hash = (Get-FileHash $setupPath.FullName -Algorithm SHA256).Hash.ToLower()
Write-Output "SHA256: $hash"

python (Join-Path $root "scripts\bump_version_json.py") $Version $hash
if ($LASTEXITCODE -ne 0) { throw "version.json 갱신 실패 (exit $LASTEXITCODE)" }

# ---------- 5) 구글 드라이브 동기화 폴더로 복사 (있으면) ----------
Write-Step "5/5  구글 드라이브 동기화 폴더로 복사"
# 주의: 이 PC에는 구글 드라이브 계정이 두 개 마운트되어 있다(G: 개인
# kojinsung1472@gmail.com, H: 업무 jinsko@jungang.hs.kr). app/config.py의
# DOWNLOAD_PAGE_URL이 실제로 가리키는, 이미 공유 링크가 걸려 있는 폴더는
# H: 쪽의 "쿨메신저 AI 알림장(since2026)"이다 — G: 쪽 폴더에 복사하면
# 공유 링크와 무관한 엉뚱한 곳에 쌓이기만 하니 반드시 H:를 써야 한다.
$driveFolder = "H:\내 드라이브\쿨메신저 AI 알림장(since2026)"
if (Test-Path $driveFolder) {
    # 오래된 버전 설치 파일이 계속 쌓이지 않도록, 새로 복사하는 파일을
    # 제외한 기존 *.exe는 지운다.
    Get-ChildItem (Join-Path $driveFolder "*.exe") -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne $setupPath.Name } |
        ForEach-Object {
            Write-Output "이전 버전 정리: $($_.Name)"
            Remove-Item $_.FullName -Force
        }

    $destExe = Join-Path $driveFolder $setupPath.Name
    Copy-Item $setupPath.FullName $destExe -Force
    Copy-Item (Join-Path $root "version.json") $driveFolder -Force
    Write-Output "복사 완료: $destExe"
    Write-Output "복사 완료: $(Join-Path $driveFolder 'version.json')"
    Write-Output "주의: 로컬 폴더에 복사만 했을 뿐, 실제로 구글 드라이브 서버까지 올라갔는지는"
    Write-Output "      Drive 동기화 클라이언트가 알아서 처리한다 — drive.google.com에서 직접 확인할 것."
} else {
    Write-Output "건너뜀: 구글 드라이브 동기화 폴더($driveFolder)를 찾지 못했습니다."
    Write-Output "        Setup.exe와 version.json을 직접 업로드해 주세요:"
    Write-Output "        $($setupPath.FullName)"
    Write-Output "        $(Join-Path $root 'version.json')"
}

Write-Step "완료"
Write-Output "버전: $Version"
Write-Output "SHA256: $hash"
Write-Output "설치 파일: $($setupPath.FullName)"
