# -*- coding: utf-8 -*-
"""구글 캘린더 연결에 쓰는 '쿨브리핑 데스크톱' OAuth 클라이언트 정보.

학교 구글 클라우드 프로젝트(대상: 내부)에서 만든 데스크톱 앱 클라이언트의
값을 넣는다. 배포 전까지는 비워 두고, 테스트할 때는 구글에서 받은 JSON을
%LOCALAPPDATA%\\TeacherAlimjang\\google_client.json 으로 두면 그걸 먼저 쓴다
(app/core/google_auth.py load_client_config).

공개 저장소라 이 값은 누구나 볼 수 있다. 데스크톱 앱 클라이언트의 secret은
구글도 '비밀이 아닌 값'으로 취급하고, '내부' 앱이라 학교 계정이 아니면
로그인할 수 없어 실제 위험은 작다(CLAUDE.md '배포 범위'에 기록)."""

CLIENT_ID = ""
CLIENT_SECRET = ""
