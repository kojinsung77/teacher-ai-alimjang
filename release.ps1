# 교사업무 AI 알림장 — 배포 원스톱 스크립트.
#
# "release.ps1 1.2.0 -Notes '이번 버전 변경 내용'" 한 줄이면: 버전 문자열
# 갱신 -> build.ps1로 클린 빌드 -> Setup.exe SHA256 계산 -> version.json
# 갱신(download_url을 이번 버전의 깃허브 릴리스 첨부파일 주소로 계산) ->
# git tag -> gh release create로 설치 파일을 깃허브 릴리스에 첨부 ->
# version.json을 git commit/push까지 전부 끝난다.
#
# 배포 채널을 구글 드라이브 수동 복사에서 깃허브(코드 저장소 + 릴리스
# 첨부파일)로 옮기면서 마지막 단계를 통째로 바꿨다 — 예전에는 로컬
# 드라이브 동기화 폴더에 파일을 복사만 해두고 실제 업로드는 Drive
# 클라이언트가 알아서 하길 기다려야 했지만, 지금은 gh release create가
# 끝나는 시점에 실제로 업로드가 완료된 것까지 보장된다.
#
# build.ps1과 분리한 이유: build.ps1은 "지금 소스로 그냥 한 번 빌드해보고
# 싶다"는 개발 중 빠른 확인용으로 계속 남겨 두고(버전 번호를 안 건드림),
# 실제 배포(버전 올리고 해시 계산해서 배포 채널까지 올리는 것)는 별도
# 스크립트로 명확히 분리했다.
#
# -SkipPublish를 주면 로컬 빌드 + version.json 갱신까지만 하고 태그
# 생성/gh release create/git push는 하지 않는다 — 특히 다른 학교
# 선생님들도 자동 업데이트로 받게 되는 배포라, "실제로 공개 릴리스가
# 나가기 직전에 한 번은 사람이 눈으로 확인하고 싶다"는 요청 때문에 넣은
# 옵션이다. 확인 후 같은 버전으로 -SkipPublish 없이 다시 실행하면(빌드는
# 이미 끝났어도 재빌드 자체는 멱등이라 문제없다) 이어서 배포까지 끝난다.
#
# 사용법: 프로젝트 루트에서 실행
#   powershell -ExecutionPolicy Bypass -File release.ps1 1.2.0 -Notes "이번 버전에서 고친 내용"
#   powershell -ExecutionPolicy Bypass -File release.ps1 1.2.0 -Notes "..." -SkipPublish

param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [string]$Notes,

    [switch]$SkipPublish
)

$GhOwner = "kojinsung77"
$GhRepo = "teacher-ai-alimjang"

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
Write-Step "1/6  app/config.py APP_VERSION -> $Version"
$configPath = Join-Path $root "app\config.py"
$configContent = [System.IO.File]::ReadAllText($configPath)
# "바뀐 내용이 있는지"(-eq 비교)가 아니라 "패턴 자체가 있었는지"(-match)로
# 검사해야 한다 — -SkipPublish로 미리 버전을 올려 둔 뒤 같은 버전으로
# 다시 실행하면(오늘 이 케이스처럼) 치환 전후 내용이 똑같아서 -eq 비교로는
# "못 찾음"으로 잘못 판단해버린다.
if ($configContent -notmatch 'APP_VERSION = "[^"]*"') { throw "app/config.py에서 APP_VERSION 줄을 찾지 못했습니다." }
$newConfigContent = $configContent -replace 'APP_VERSION = "[^"]*"', "APP_VERSION = `"$Version`""
Write-Utf8NoBom $configPath $newConfigContent
Write-Output "완료"

# ---------- 2) installer/setup.iss의 MyAppVersion 갱신 ----------
Write-Step "2/6  installer/setup.iss MyAppVersion -> $Version"
$issPath = Join-Path $root "installer\setup.iss"
$issContent = [System.IO.File]::ReadAllText($issPath)
if ($issContent -notmatch '#define MyAppVersion "[^"]*"') { throw "installer/setup.iss에서 MyAppVersion 줄을 찾지 못했습니다." }
$newIssContent = $issContent -replace '#define MyAppVersion "[^"]*"', "#define MyAppVersion `"$Version`""
Write-Utf8NoBom $issPath $newIssContent
Write-Output "완료"

# ---------- 3) build.ps1로 클린 빌드 (PyInstaller + Inno Setup) ----------
Write-Step "3/6  build.ps1 클린 빌드"
& (Join-Path $root "build.ps1")
if ($LASTEXITCODE -ne 0) { throw "build.ps1 실패 (exit $LASTEXITCODE)" }

$setupPath = Get-ChildItem (Join-Path $root "installer\output\*.exe") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setupPath) { throw "installer\output\*.exe 를 찾지 못했습니다." }
Write-Output "빌드된 설치 파일: $($setupPath.FullName)"

# ---------- 4) SHA256 계산 + version.json 갱신 ----------
Write-Step "4/6  SHA256 계산 및 version.json 갱신"
$hash = (Get-FileHash $setupPath.FullName -Algorithm SHA256).Hash.ToLower()
Write-Output "SHA256: $hash"

# 깃허브 릴리스 첨부파일의 다운로드 주소는 태그·파일명만 알면 gh release
# create가 끝나기 전에도 미리 계산할 수 있다(깃허브의 고정된 URL 규칙).
$downloadUrl = "https://github.com/$GhOwner/$GhRepo/releases/download/v$Version/$($setupPath.Name)"
Write-Output "download_url: $downloadUrl"

python (Join-Path $root "scripts\bump_version_json.py") $Version $hash $downloadUrl $Notes
if ($LASTEXITCODE -ne 0) { throw "version.json 갱신 실패 (exit $LASTEXITCODE)" }

if ($SkipPublish) {
    Write-Step "완료 (-SkipPublish로 실행됨 — 태그/릴리스/푸시는 건너뜀)"
    Write-Output "버전: $Version"
    Write-Output "SHA256: $hash"
    Write-Output "설치 파일: $($setupPath.FullName)"
    Write-Output ""
    Write-Output "확인 후 실제로 공개 배포하려면 같은 버전으로 -SkipPublish 없이 다시 실행하세요:"
    Write-Output "  powershell -ExecutionPolicy Bypass -File release.ps1 $Version -Notes `"$Notes`""
    exit 0
}

# ---------- 5) git tag + gh release create (설치 파일 첨부) ----------
Write-Step "5/6  git tag + 깃허브 릴리스 생성"
$tag = "v$Version"
git -C $root tag $tag
if ($LASTEXITCODE -ne 0) { throw "git tag 실패 (이미 존재하는 태그인지 확인: $tag)" }
git -C $root push origin $tag
if ($LASTEXITCODE -ne 0) { throw "git push (태그) 실패" }

gh release create $tag $setupPath.FullName --repo "$GhOwner/$GhRepo" --title $tag --notes $Notes
if ($LASTEXITCODE -ne 0) { throw "gh release create 실패" }
Write-Output "릴리스 생성 완료: https://github.com/$GhOwner/$GhRepo/releases/tag/$tag"

# ---------- 6) 버전 문자열이 바뀐 파일 전부 커밋 + 푸시 ----------
Write-Step "6/6  버전 관련 파일 커밋 + 푸시"
# version.json만 커밋하면 1/2단계에서 로컬에 반영한 app/config.py의
# APP_VERSION, installer/setup.iss의 MyAppVersion은 빠진 채로 남는다 —
# 태그·릴리스·version.json은 새 버전인데 저장소 소스 코드만 이전 버전
# 문자열을 담고 있는 불일치가 실제로 두 번(v1.2.1, v1.2.2) 발생했던
# 문제라, 이 세 파일을 항상 함께 커밋한다.
git -C $root add version.json app/config.py installer/setup.iss
git -C $root commit -m "release: v$Version"
if ($LASTEXITCODE -ne 0) { throw "git commit 실패" }
git -C $root push origin master
if ($LASTEXITCODE -ne 0) { throw "git push (master) 실패" }

Write-Step "완료"
Write-Output "버전: $Version"
Write-Output "SHA256: $hash"
Write-Output "설치 파일: $($setupPath.FullName)"
Write-Output "릴리스: https://github.com/$GhOwner/$GhRepo/releases/tag/$tag"
