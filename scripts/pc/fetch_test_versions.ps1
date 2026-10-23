# 쿨브리핑 테스트 버전 폴더 자동 받기
# 깃허브에 올라온 'test-vX.Y.Z' 태그(배포 전 테스트 버전)마다 vX.Y.Z 폴더를 이 폴더 옆에 만든다.
# - 이미 있는 폴더는 절대 덮어쓰지 않는다(선생님이 넣어 둔 파일 보호).
# - 이 폴더에 google_client.json이 있으면 새 버전 폴더에도 복사한다.
# - -Quiet: 컴퓨터 켤 때 자동 확인용. 새 폴더가 생겼을 때만 알림 창을 띄운다.
param(
    [string]$Dest = $PSScriptRoot,
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Repo = 'kojinsung77/teacher-ai-alimjang'
$Headers = @{ 'User-Agent' = 'CoolBriefing-TestFolders' }

function Say([string]$m) { if (-not $Quiet) { Write-Host $m } }
function Done([int]$code) {
    if (-not $Quiet) { Write-Host ''; Read-Host '엔터를 누르면 창이 닫힙니다' | Out-Null }
    exit $code
}

$Dest = (Resolve-Path -LiteralPath $Dest).Path
Say "쿨브리핑 테스트 버전 확인 중... ($Dest)"

try {
    $tags = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/tags?per_page=100" -Headers $Headers -UseBasicParsing
} catch {
    Say "깃허브에 연결하지 못했습니다: $($_.Exception.Message)"
    Done 1
}

$made = @()
foreach ($t in $tags) {
    if ($t.name -notmatch '^test-v(\d+\.\d+\.\d+)$') { continue }
    $ver = $Matches[1]
    $target = Join-Path $Dest "v$ver"
    if (Test-Path -LiteralPath $target) { continue }

    Say "v$ver 폴더를 만드는 중..."
    $tmp = Join-Path $Dest ('_downloading_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp 'src.zip'
        Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/tags/$($t.name).zip" -OutFile $zip -Headers $Headers -UseBasicParsing
        $x = Join-Path $tmp 'x'
        Expand-Archive -LiteralPath $zip -DestinationPath $x -Force
        $inner = Get-ChildItem -LiteralPath $x -Directory | Select-Object -First 1
        if ($null -eq $inner) { throw '압축 안에 폴더가 없습니다.' }
        Move-Item -LiteralPath $inner.FullName -Destination $target
        $gc = Join-Path $Dest 'google_client.json'
        if (Test-Path -LiteralPath $gc) { Copy-Item -LiteralPath $gc -Destination (Join-Path $target 'google_client.json') }
        $made += "v$ver"
        Say "  -> v$ver 완료"
    } catch {
        Say "  v$ver 를 받지 못했습니다: $($_.Exception.Message)"
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($made.Count -gt 0) {
    Add-Type -AssemblyName System.Windows.Forms
    $msg = "새 테스트 버전 폴더가 생겼어요: " + ($made -join ', ') + "`n`n폴더 안 00_테스트_안내.txt를 먼저 읽어 주세요.`n(아직 선생님들께 배포되지 않은 버전입니다)"
    [System.Windows.Forms.MessageBox]::Show($msg, '쿨브리핑 테스트 버전') | Out-Null
    Start-Process explorer.exe -ArgumentList ('"' + (Join-Path $Dest $made[-1]) + '"')
} else {
    Say '새 테스트 버전이 없습니다. (이미 받은 버전 폴더는 그대로 둡니다)'
}
Done 0
