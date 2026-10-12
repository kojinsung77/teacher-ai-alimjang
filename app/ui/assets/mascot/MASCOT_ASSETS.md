# 쿨브리핑 마스코트(파랑새) 알림 이미지 규격
모든 수치는 @2x 픽셀 기준이며, 화면에는 절반 크기로 표시한다 (devicePixelRatio 2).
같은 값이 layout.json 에도 들어 있다 — 코드에서는 layout.json 을 읽어 쓰는 것을 권장.

## 파일
- mascot_walk_0.png ~ mascot_walk_3.png : 걷기 프레임 4장, 모두 311x312, 투명 배경
  - 0: 오른발 내딛기 / 1: 두 발 모음(살짝 위로) / 2: 왼발 내딛기 / 3: 두 발 모음(살짝 위로)
  - 이 순서로 반복 재생(간격은 app/ui/mascot_walker.py의 FRAME_INTERVAL_MS = 220ms).
    4장 캔버스·발 기준선이 모두 맞춰져 있어 위치 보정 불필요.
- mascot_idle.png : 서 있는 자세(311x312) — 필요할 때만 사용
- speech_bubble.png : 글자 없는 빈 말풍선(380x297, 투명 배경), 꼬리는 왼쪽 아래
- layout.json : 아래 배치 좌표

## 합성 배치 (합성 창 626 x 457 @2x → 화면 약 313 x 229)
- 걷기 프레임 좌상단: (0, 145)
- 말풍선 좌상단: (246, 0) → 말풍선 꼬리 끝이 확성기 입구 바로 위에 닿는다
- 말풍선 글자 (말풍선 좌표 기준)
  - 글자 영역 중심: (190, 126), 글자가 들어갈 수 있는 흰 영역: x 24~360, y 20~281
  - 1줄 "쿨브리핑": 파랑 #1656E8, 굵게, 26px(1x)
  - 2줄 동적 문구(예: "오늘 할 일 3건!"): 진한 남색 #191E2D, 굵게, 17px(1x)
  - 실제 위치·크기는 app/ui/mascot_walker.py의 paintEvent가 기준이다.

## 이동
- 마스코트가 오른쪽(확성기 방향)을 보고 있으므로 화면 왼쪽 밖 → 오른쪽 밖으로 걷는다.
- 합성 창 아래쪽을 주 모니터 availableGeometry 하단(작업표시줄 바로 위)에 맞춘다.
- 속도: 초당 45px(WALK_SPEED_PX_PER_SEC) — 1920px 화면을 약 50초에 지나간다.
  처음 80px/초는 "너무 빠르다"는 의견이 있어 낮췄다.
- 마우스를 올리면 서 있는 자세(mascot_idle.png)로 멈춰 기다리고, 떼면 다시 걷는다.
- 클릭하면 사라지면서 앱 창이 열리고 '오늘' 화면이 보인다.

## 미리보기
- reference-images/mascot-real-speed.mp4 : 실제 속도·발걸음 간격 그대로 만든 영상
  (1920x1080 화면을 1280x720으로 줄여 표시). mascot-walk-preview.gif는 빠르게
  돌린 초기 미리보기라 실제 속도와 다르다.
- 실제 화면에서 바로 보기: python scripts/preview_mascot.py [건수]


## 2026-10-12 변경 (크기 2/3·말풍선 직접 그리기·왕복)
- 걷기 프레임은 이제 배율 3(SPRITE_DPR)으로 그린다 → 처음 버전의 약 2/3 크기
  (파랑새 키 약 104px).
- speech_bubble.png는 더 이상 쓰지 않는다. 말풍선은 app/ui/mascot_walker.py의
  paintEvent가 글자 크기(쿨브리핑 18px / 건수 13px)에 맞춰 직접 그린다.
  layout.json의 bubble_* 값도 쓰지 않고, frame_size·megaphone_mouth_in_frame만 쓴다.
- 배치는 compute_layout(): 파랑새를 창 가운데 두고 양옆에 말풍선 자리를 같게
  둬서, 뒤돌 때 창을 옮기지 않고 그림·말풍선만 좌우로 뒤집는다(글자는 안 뒤집음).
- 이동은 walk_bounds(): 처음엔 파랑새가 주 모니터 왼쪽 끝에 붙어 나타나고,
  말풍선이 화면 끝에 닿으면 0.7초 서 있다가 뒤돈다. 클릭할 때까지 왕복.
- 오른쪽 클릭은 앱을 열지 않고 닫기만 한다. 할 일이 0건이 되면 스스로 사라진다.
- 미리보기: reference-images/mascot-pingpong-preview.png, mascot-pingpong-real-speed.mp4
