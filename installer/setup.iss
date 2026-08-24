; -*- coding: utf-8 -*-
; 교사업무 AI 알림장 설치 프로그램 (Inno Setup 6.3+)
;
; 빌드 방법 — 반드시 프로젝트 루트의 build.ps1 하나로만 빌드할 것:
;   powershell -ExecutionPolicy Bypass -File build.ps1
;
; 이 스크립트를 installer 폴더에서 iscc setup.iss로 단독 실행하지 말 것.
; PyInstaller exe 빌드와 Inno Setup 컴파일이 분리된 두 단계였을 때,
; "코드만 고치고 PyInstaller는 다시 안 돌린 채 여기만 재컴파일"하는
; 실수로 설치 파일이 옛날 코드를 담은 채 배포된 적이 실제로 있었다
; (dist\TeacherAlimjang.exe 타임스탬프가 여러 코드 변경 이후로도 갱신
; 안 되고 있었던 게 뒤늦게 발견됨). build.ps1은 매번 build/dist를 지우고
; PyInstaller부터 새로 돌린 뒤에만 이 스크립트를 컴파일해서 이 실수 자체를
; 막는다.
;
; 핵심 안전 원칙: 이 스크립트는 %LOCALAPPDATA%\TeacherAlimjang
; (설정/Gemini API 키 참조/SQLite DB가 저장되는 곳)을 그 어디에서도
; 언급하거나 건드리지 않는다. Inno Setup은 [Files]/[UninstallDelete]
; 등에 명시하지 않는 한 {app}(설치 폴더) 바깥은 절대 손대지 않으므로,
; 이 폴더를 스크립트에 등장시키지 않는 것 자체가 곧 "보존"을 보장한다.
; 재설치/업데이트/제거 어떤 경우에도 이 원칙은 유지해야 한다.

#define MyAppName "교사업무 AI 알림장"
; app/config.py의 APP_VERSION과 항상 맞춰서 올린다.
#define MyAppVersion "1.4.2"
#define MyAppPublisher "Gosussam"
#define MyAppExeName "TeacherAlimjang.exe"
#define MyAppId "{{0D2E7F2C-B6D4-45CF-9D4B-79DAAAF99FAB}"

[Setup]
; AppId는 고정 GUID — 버전이 올라가도 같은 프로그램으로 인식되어
; "업데이트/재설치" 흐름(참고 이미지 1번의 "이미 설치되어 있습니다")이 동작한다.
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
; 트레이에 상주한 채로 재설치/업데이트하면 exe 파일이 잠겨 있어 설치가
; 실패할 수 있다 — 이 뮤텍스가 켜져 있으면 Inno가 설치/제거 시작 전에
; "실행 중인 프로그램을 닫아 주세요" 안내를 띄운다. 앱 쪽은
; app/core/single_instance.py의 hold_install_mutex()가 같은 이름으로
; Win32 뮤텍스를 만들어 둔다 — 이름이 반드시 일치해야 한다.
AppMutex=TeacherAlimjangRunningMutex
; 설치 시 "모든 사용자" / "전용(현재 사용자만)" 선택 다이얼로그를 띄운다
; (Inno Setup 6.3+ 기본 기능 — 참고 이미지 1번과 동일한 화면)
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\app\ui\assets\app_icon.ico
OutputDir=output
OutputBaseFilename=TeacherAlimjang_Setup_v{#MyAppVersion}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
; 바탕화면/시작 메뉴 바로가기는 기본 체크(Flags 없음 = Inno 기본값이 체크됨).
; 자동 시작만 사용자가 명시적으로 켜야 하므로 기본 체크 해제.
Name: "desktopicon"; Description: "바탕 화면에 바로 가기 만들기"; GroupDescription: "바로 가기:"
Name: "startmenuicon"; Description: "시작 메뉴에 바로 가기 만들기"; GroupDescription: "바로 가기:"
Name: "startupicon"; Description: "Windows 시작 시 자동으로 실행"; GroupDescription: "시작 옵션:"; Flags: unchecked

[Files]
; PyInstaller --onefile 산출물 하나만 포함하면 된다
; (app/ui/assets 등 리소스는 이미 --add-data 로 exe 안에 번들되어 있음)
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Windows 시작 시 자동 실행. 설치 화면의 체크박스는 "설치 직후 초기값"만
; 정하고, 이후에는 앱의 '설정' 화면이 이 동일한 레지스트리 값을 직접
; 갱신/삭제한다(app/core/autostart.py — 값 이름 "TeacherAlimjang"이
; 반드시 일치해야 한다). uninsdeletevalue는 설치 시점에 이 값을 만든
; 경우의 기본 정리이고, 앱이 나중에 별도로 켠 경우까지 대비해 아래
; Code 섹션의 CurUninstallStepChanged에서 한 번 더 명시적으로 지운다.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TeacherAlimjang"; ValueData: """{app}\{#MyAppExeName}"" --autostart"; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; "설치가 끝나면 바로 실행" 체크박스 (참고 이미지 2/3번과 동일, postinstall 플래그)
; --autostart를 붙이지 않으므로 일반 실행으로 간주되어 메인 창이 뜬다.
; skipifsilent를 일부러 안 붙인다 — 앱 자체 업데이트 기능(설정 화면
; [지금 설치])이 /SILENT로 이 설치 프로그램을 실행하는데, 그때도
; 설치가 끝나면 앱이 자동으로 다시 켜져야 하기 때문이다. skipifsilent가
; 있으면 조용한 설치 뒤에 앱이 안 켜져서 사용자가 직접 다시 실행해야
; 하는 문제가 생긴다.
; 조용한 설치 쪽(CurStepChanged)에서 PyInstaller 부트로더의 부모-
; 프로세스 검증이 Setup.exe가 너무 빨리 종료돼서 실패하는 문제를
; 찾아 고쳤다(아래 CurStepChanged 주석 참고) — 여기 대화형 설치
; 경로는 마법사 화면이 남아 있는 동안 Setup.exe 프로세스 자체가
; 자연히 더 오래 살아있어서 같은 경합이 훨씬 덜 발생하는 것으로
; 보이지만(실측상 대화형 설치의 이 문제는 아직 재현 못 함), 이론상
; 완전히 배제된 건 아니다. 지금은 조용한 설치(자동 업데이트) 경로가
; 실사용자 보고의 핵심이라 그쪽부터 고쳤고, 대화형 쪽에서도 재현되면
; 같은 방식(Exec 뒤 Sleep)으로 추가 조치한다.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

; ---------------------------------------------------------------------------
; 절대 추가하면 안 되는 것 (참고용 경고 주석):
;   [UninstallDelete] 또는 [InstallDelete] 섹션에
;   "{userappdata}\..\Local\TeacherAlimjang" 같은 경로를 절대 넣지 말 것.
;   그 폴더에는 Gemini API 키 참조, roster.csv 위치, 완료 기록이 담긴
;   SQLite DB가 있다. 언인스톨 시에도 기본 동작(= {app} 폴더만 제거)이
;   이 폴더를 건드리지 않으므로, 별도 삭제 로직을 추가하지 않는 한
;   항상 안전하게 보존된다. 아래 [Code] 섹션의 데이터 삭제는 사용자가
;   커스텀 제거 확인 화면에서 체크박스를 "직접 체크했을 때만" 실행된다.
; ---------------------------------------------------------------------------

[Code]
var
  UninstallDeleteDataChecked: Boolean;
  UninstallLogMemo: TNewMemo;

function SetEnvironmentVariableW(lpName, lpValue: WideString): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

{ ---------- -2. PyInstaller onefile 부트로더의 부모-프로세스 검증
  오염 방지 ---------- }
{ "Security validation failure: parent process has different
  executable!" 오류로 자동 재실행된 앱이 뜨자마자 죽는 문제의 진짜
  원인 — 우리 앱(Python/PyInstaller onefile) 자신이 이미 부트로더의
  "2단계(자식)" 프로세스로 떠 있는 상태라 _PYI_로 시작하는 내부
  환경변수가 우리 프로세스 환경에 설정돼 있다. 앱이 [지금 설치]에서
  이 설치 프로그램(Setup.exe)을 subprocess.Popen()으로 띄우면
  Windows는 기본적으로 부모(앱)의 환경변수를 통째로 물려주므로, 이
  변수들이 Setup.exe 프로세스 환경에도 그대로 들어온다. 이 설치
  프로그램이 CurStepChanged에서 Exec()으로 새 TeacherAlimjang.exe를
  재실행할 때도 마찬가지로 Setup.exe의(=오염된) 환경을 그대로
  물려주므로, 갓 실행된 새 앱이 "나는 이미 재실행된 2단계 자식"이라고
  착각해 정상적인 1단계 부트스트랩(자기 자신을 다시 한번 자식으로
  띄우는 절차)을 건너뛰고 곧장 부모-프로세스 검증에 들어간다 — 그
  시점의 실제 부모는 Setup.exe라 실행파일이 다르다고 검증에 실패한다.

  app/ui/main_window.py의 _run_silent_install()에서도 Setup.exe를
  띄울 때 이 변수를 지운 환경을 넘기도록 고쳤지만, 그건 그 수정이
  "이미 반영된 버전"이 실행 중일 때만 효과가 있다 — 지금 v1.2.x/
  v1.3.x대 구버전을 쓰는 사람이 처음으로 [지금 설치]를 눌러 이번
  설치 프로그램을 내려받아 실행하는 바로 그 순간에는, 그 구버전
  앱의 옛날 코드가 여전히 오염된 환경 그대로 Setup.exe를 띄운다.
  그래서 여기, 매번 새로 다운로드되는 설치 프로그램 쪽에서도 독립적
  으로 방어해야 실제로 지금 이 순간의 구버전 사용자에게도 적용된다
  — Setup.exe 자신의 프로세스 환경에서 이 변수들을 명시적으로
  지워서, 이후 Exec()으로 재실행하는 새 앱이 깨끗한 환경을 물려받게
  한다. 실제 배포된 v1.3.2로 반복 재현 후 확인. }
procedure ClearPyiEnvVars();
begin
  SetEnvironmentVariableW('_PYI_APPLICATION_HOME_DIR', '');
  SetEnvironmentVariableW('_PYI_ARCHIVE_FILE', '');
  SetEnvironmentVariableW('_PYI_PARENT_PROCESS_LEVEL', '');
  SetEnvironmentVariableW('_PYI_SPLASH_IPC', '');
end;

{ ---------- -1. 앱 자체 업데이트 직후 실행될 때의 파일 잠금 경합 대비 ---------- }
{ 앱의 [지금 설치]가 이 설치 프로그램을 subprocess.Popen()으로 띄운 직후
  자기 자신은 곧바로 self.close()로 종료하는데, PyInstaller onefile
  부트로더는 실제로 프로세스가 두 개(부모 런처 + 실제로 돌아가는 자식)라
  자식 쪽 Qt 창이 닫혀도 부모 프로세스가 TeacherAlimjang.exe 이미지에
  대한 핸들을 완전히 놓기까지 짧은 시간이 더 걸릴 수 있다. 우리 코드는
  자식(Qt 창)의 종료만 요청할 뿐 부모 프로세스가 완전히 죽었는지 기다릴
  방법이 없다 — 그 사이에 이 설치 프로그램이 곧바로 파일을 덮어쓰려
  하면 RestartManager가 "아직 쓰는 중"으로 보고, 자동으로 못 닫으면
  확인창을 띄우려다 /SUPPRESSMSGBOXES에 막혀 조용히 취소되는 경우가
  실측으로 확인됐다(등록 정보는 그대로, 프로세스만 사라짐 — "지금 설치"
  눌러도 아무 일 없다는 보고와 정확히 일치하는 증상).

  v1.4.1에서 고정 Sleep(1500)으로 이 문제를 완화해뒀지만, 실사용자
  환경의 installer_last_run.log로 재현을 확인해보니 1.5초로도 부족한
  경우가 있었다: "RestartManager found an application using one of our
  files" 뒤 "일부 응용 프로그램을 종료할 수 없습니다"로 조용히 롤백된
  로그가 실제로 남았다 — 부모 프로세스 정리(임시 폴더 삭제 등)가 느린
  컴퓨터(백신 실시간 검사 등)에서는 1.5초보다 오래 걸릴 수 있다는 뜻.
  그래서 고정 시간 대기 대신, tasklist로 TeacherAlimjang.exe가 실제로
  프로세스 목록에서 사라졌는지 직접 확인하면서 짧은 간격으로 반복
  대기한다 — 뮤텍스(TeacherAlimjangRunningMutex)는 조용한 설치 직전에
  우리 쪽에서 일부러 미리 풀어버리므로(release_install_mutex() 참고)
  "아직 살아있다"를 신뢰성 있게 알려주는 신호가 못 되고, tasklist가
  실제 OS 프로세스 상태를 보는 유일하게 확실한 방법이다. 이미 죽어있는
  일반 대화형 설치(사용자가 직접 실행)에서는 첫 확인에서 곧장
  통과하므로 체감 지연이 없다. }
function ProcessRunning(const ExeName: String): Boolean;
var
  ResultCode: Integer;
  Output: TExecOutput;
  I: Integer;
begin
  Result := False;
  if not ExecAndCaptureOutput(ExpandConstant('{sys}\tasklist.exe'),
       '/FI "IMAGENAME eq ' + ExeName + '" /NH', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode, Output) then
    exit;
  for I := 0 to GetArrayLength(Output.StdOut) - 1 do
  begin
    if Pos(Lowercase(ExeName), Lowercase(Output.StdOut[I])) > 0 then
    begin
      Result := True;
      exit;
    end;
  end;
end;

procedure WaitForProcessToExit(const ExeName: String; const MaxWaitMs: Integer);
var
  Waited: Integer;
begin
  Waited := 0;
  while ProcessRunning(ExeName) and (Waited < MaxWaitMs) do
  begin
    Sleep(300);
    Waited := Waited + 300;
  end;
end;

function InitializeSetup(): Boolean;
begin
  ClearPyiEnvVars();
  WaitForProcessToExit('{#MyAppExeName}', 15000);
  { tasklist에서 사라진 직후에도 파일 핸들 해제까지 아주 짧은 여유를
    한 번 더 둔다 — 공짜에 가까운 안전망. }
  Sleep(500);
  Result := True;
end;

{ ---------- 0. 조용한 설치 뒤 앱 자동 재시작 ---------- }
{ Run 섹션의 postinstall 플래그(skipifsilent 없음)만으로는 앱 자체
  업데이트 기능이 쓰는 조용한 설치(/SILENT, 예전엔 /VERYSILENT)에서
  앱이 자동으로 안 켜지는 것이 실측으로 확인됐다 — postinstall은 원래
  "마법사 마지막 화면의
  체크박스"용 플래그라, 화면 자체가 안 뜨는 완전 침묵 모드에서는
  Inno Setup이 그 항목을 아예 건너뛰는 것으로 보인다. 그래서 조용한
  설치일 때만 여기서 명시적으로 실행한다.

  ShellExec()으로 바꿔봤지만(v1.3.6) 효과가 없었다 — PyInstaller
  공식 changelog(6.22.1)로 원인을 다시 확인해보니, 이 검증은
  "실행파일 재실행의 안쪽(부트로더 1단계→2단계) 부모-자식 관계"를
  보는 것이라 누가 Setup.exe를 거쳐 우리 exe를 최초로 띄웠는지와는
  무관하고(ShellExec이든 Exec이든 실질적으로 같은 CreateProcess로
  귀결됨 — .exe 파일은 탐색기 셸을 경유하지 않고 곧장 실행됨), 진짜
  원인은 타이밍 경합이었다: Setup.exe가 우리 exe를 띄운 직후
  ssDone이 곧바로 끝나며 Setup.exe 자신도 몇백 ms 안에 완전히
  종료되는데, 그 사이에 방금 띄운 부트로더 1단계 프로세스가 내부
  검증 시점에 "내 부모(Setup.exe)의 실행파일 경로"를 조회하면 그새
  부모가 사라져(또는 PID가 재사용돼) 조회가 어긋나면서 검증이
  실패한다(실제 배포된 v1.3.2/v1.3.6으로 재현 — 설치 자체는 매번
  성공해 레지스트리 버전은 바뀌지만, 자동 재실행된 창이 이 오류창일
  때가 있다). 그래서 Exec 뒤에 Setup.exe 프로세스 자체가 몇 초간 더
  살아있게 붙잡아 둔다 — 부트로더의 부모 검증이 이 짧은 창 안에서
  끝나므로, 부모가 아직 살아있어야 통과한다. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssDone) and WizardSilent() then
  begin
    Exec(ExpandConstant('{app}\{#MyAppExeName}'), '', '', SW_SHOWNORMAL,
      ewNoWait, ResultCode);
    Sleep(3000);
  end;
end;

{ ---------- 1. 제거 확인 화면 (커스텀) ---------- }

function ConfirmUninstallForm(): Boolean;
var
  Form: TForm;
  TitleLabel, DescLabel, SubNoteLabel: TNewStaticText;
  CheckBox: TNewCheckBox;
  BtnRemove, BtnCancel: TNewButton;
  Bevel: TBevel;
  ContentWidth: Integer;
begin
  Form := TForm.Create(nil);
  Form.ClientWidth := ScaleX(480);
  Form.ClientHeight := ScaleY(260);
  Form.Caption := '{#MyAppName} 제거';
  Form.Position := poScreenCenter;
  Form.BorderStyle := bsDialog;

  try

  ContentWidth := Form.ClientWidth - ScaleX(40);

  TitleLabel := TNewStaticText.Create(Form);
  TitleLabel.Parent := Form;
  TitleLabel.Left := ScaleX(20);
  TitleLabel.Top := ScaleY(20);
  TitleLabel.Width := ContentWidth;
  TitleLabel.AutoSize := True;
  TitleLabel.WordWrap := True;
  TitleLabel.Font.Style := [fsBold];
  TitleLabel.Font.Size := TitleLabel.Font.Size + 2;
  TitleLabel.Caption := '{#MyAppName}을(를) 제거하시겠습니까?';

  DescLabel := TNewStaticText.Create(Form);
  DescLabel.Parent := Form;
  DescLabel.Left := ScaleX(20);
  DescLabel.Top := TitleLabel.Top + TitleLabel.Height + ScaleY(12);
  DescLabel.Width := ContentWidth;
  DescLabel.AutoSize := True;
  DescLabel.WordWrap := True;
  DescLabel.Caption :=
    '프로그램 파일과 바탕화면·시작 메뉴 바로가기가 삭제됩니다.' + #13#10 +
    '기본적으로 API 키, 완료 기록과 사용자 설정은 남겨 둡니다.';

  Bevel := TBevel.Create(Form);
  Bevel.Parent := Form;
  Bevel.Left := ScaleX(20);
  Bevel.Top := DescLabel.Top + DescLabel.Height + ScaleY(16);
  Bevel.Width := ContentWidth;
  Bevel.Height := 1;
  Bevel.Shape := bsTopLine;

  CheckBox := TNewCheckBox.Create(Form);
  CheckBox.Parent := Form;
  CheckBox.Left := ScaleX(20);
  CheckBox.Top := Bevel.Top + ScaleY(16);
  CheckBox.Width := ContentWidth;
  CheckBox.Height := ScaleY(17);
  CheckBox.Caption := 'API 키, 완료 기록과 사용자 설정도 함께 삭제';
  { 반드시 기본 체크 해제 — 사용자가 직접 체크해야만 데이터가 삭제된다. }
  CheckBox.Checked := False;

  SubNoteLabel := TNewStaticText.Create(Form);
  SubNoteLabel.Parent := Form;
  SubNoteLabel.Left := CheckBox.Left + ScaleX(20);
  SubNoteLabel.Top := CheckBox.Top + CheckBox.Height + ScaleY(2);
  SubNoteLabel.Width := ContentWidth - ScaleX(20);
  SubNoteLabel.AutoSize := True;
  SubNoteLabel.WordWrap := True;
  SubNoteLabel.Font.Color := clGrayText;
  SubNoteLabel.Caption := '체크하면 되돌릴 수 없습니다. 메신저 원본 데이터는 삭제하지 않습니다.';

  BtnRemove := TNewButton.Create(Form);
  BtnRemove.Parent := Form;
  BtnRemove.Width := ScaleX(90);
  BtnRemove.Height := ScaleY(23);
  BtnRemove.Left := Form.ClientWidth - ScaleX(20) - BtnRemove.Width;
  BtnRemove.Top := Form.ClientHeight - ScaleY(20) - BtnRemove.Height;
  BtnRemove.Caption := '제거';
  BtnRemove.ModalResult := mrOk;
  BtnRemove.Default := True;

  BtnCancel := TNewButton.Create(Form);
  BtnCancel.Parent := Form;
  BtnCancel.Width := ScaleX(90);
  BtnCancel.Height := ScaleY(23);
  BtnCancel.Left := BtnRemove.Left - ScaleX(10) - BtnCancel.Width;
  BtnCancel.Top := BtnRemove.Top;
  BtnCancel.Caption := '취소';
  BtnCancel.ModalResult := mrCancel;
  BtnCancel.Cancel := True;

  Result := (Form.ShowModal() = mrOk);
  if Result then
    UninstallDeleteDataChecked := CheckBox.Checked
  else
    UninstallDeleteDataChecked := False;

  finally
    Form.Free;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := ConfirmUninstallForm();
end;

{ ---------- 3. 제거 진행/완료 로그 ---------- }

procedure EnsureUninstallLogMemo();
begin
  if not Assigned(UninstallLogMemo) then
  begin
    { 기본 제거 진행 화면(UninstallProgressForm)은 Inno Setup 6부터
      전역 변수로 노출되어 커스터마이즈할 수 있다. StatusLabel 자리에
      맞춰 로그를 누적해서 보여주는 멀티라인 메모를 대신 넣는다. }
    UninstallProgressForm.StatusLabel.Visible := False;
    UninstallLogMemo := TNewMemo.Create(UninstallProgressForm);
    UninstallLogMemo.Parent := UninstallProgressForm;
    UninstallLogMemo.Left := UninstallProgressForm.StatusLabel.Left;
    UninstallLogMemo.Top := UninstallProgressForm.StatusLabel.Top;
    UninstallLogMemo.Width :=
      UninstallProgressForm.ClientWidth - UninstallLogMemo.Left * 2;
    UninstallLogMemo.Height :=
      UninstallProgressForm.ClientHeight - UninstallLogMemo.Top - ScaleY(45);
    UninstallLogMemo.ReadOnly := True;
    UninstallLogMemo.TabStop := False;
    UninstallLogMemo.ScrollBars := ssVertical;
    UninstallLogMemo.Lines.Add('메신저 원본 데이터에는 아무 변경도 하지 않았습니다.');
    UninstallLogMemo.Lines.Add('');
  end;
end;

procedure LogUninstallLine(const Line: String);
begin
  { 이 로그 박스는 순전히 화면 표시용이다 — Inno가 자체 파일 삭제를
    끝낸 뒤(usPostUninstall 진입 시점) 진행 화면 내부 컨트롤 상태가
    바뀌면서 메모 생성/접근이 실패하는 경우가 실제로 관찰됐다. 여기서
    예외가 나도 실제 삭제 로직(DelTree, 자격 증명 삭제)까지 막히면
    안 되므로 표시 실패는 조용히 무시하고 넘어간다. }
  try
    EnsureUninstallLogMemo();
    UninstallLogMemo.Lines.Add(Line);
    UninstallProgressForm.Update;
  except
  end;
  Sleep(200);
end;

{ ---------- 2. 체크박스 상태에 따른 조건부 삭제 ---------- }

procedure DeleteGeminiApiKeyFromCredentialManager();
var
  ResultCode: Integer;
  AnyFailed: Boolean;
begin
  AnyFailed := False;

  { keyring(Windows 백엔드)이 실제로 만드는 두 가지 대상 이름 형식을
    모두 지운다 (직접 keyring.set_password로 저장해서 실측 확인함):
      - "gemini_api_key@TeacherAlimjang" (username@service, 최신 형식)
      - "TeacherAlimjang"                (service만, 레거시 호환용) }
  if not Exec('cmdkey.exe', '/delete:gemini_api_key@TeacherAlimjang', '',
     SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    AnyFailed := True;

  if not Exec('cmdkey.exe', '/delete:TeacherAlimjang', '',
     SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    AnyFailed := True;

  if AnyFailed then
    Log('일부 항목은 Windows 자격 증명 관리자에서 수동으로 확인이 필요할 수 있습니다.');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataDir: String;
begin
  case CurUninstallStep of
    usUninstall:
      begin
        LogUninstallLine('제거 위치: ' + ExpandConstant('{app}'));
        LogUninstallLine('바탕화면과 시작 메뉴 바로가기를 정리합니다...');
        LogUninstallLine('프로그램 파일을 제거합니다...');
      end;
    usPostUninstall:
      begin
        { 자동 시작 등록은 "사용자 데이터"가 아니라 프로그램 등록
          정보라서, 데이터 삭제 체크박스와 무관하게 항상 정리한다.
          위쪽 Registry 섹션의 uninsdeletevalue로도 지워지지만, 사용자가
          설치 화면 체크박스가 아니라 앱의 설정 화면에서 나중에 켰을
          수도 있으니(레지스트리 값 이름은 동일) 한 번 더 명시적으로
          지워서 확실히 한다. }
        RegDeleteValue(HKEY_CURRENT_USER,
          'Software\Microsoft\Windows\CurrentVersion\Run', 'TeacherAlimjang');

        if UninstallDeleteDataChecked then
        begin
          LogUninstallLine('이 Windows 계정의 설정과 완료 기록을 제거합니다...');

          { CoolMessenger 원본 데이터(.udb 등)는 이 앱이 애초에 읽기
            전용으로만 접근하므로 여기서도 절대 손대지 않는다.
            %LOCALAPPDATA%\TeacherAlimjang 안의 것(SQLite DB, roster.csv,
            설정)만 지운다 — 체크박스를 "직접 체크했을 때만" 실행된다. }
          AppDataDir := ExpandConstant('{localappdata}\TeacherAlimjang');
          if DirExists(AppDataDir) then
            DelTree(AppDataDir, True, True, True);

          DeleteGeminiApiKeyFromCredentialManager();
        end;
        LogUninstallLine('제거가 완료되었습니다.');
      end;
  end;
end;
