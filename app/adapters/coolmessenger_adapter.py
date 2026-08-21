# -*- coding: utf-8 -*-
"""쿨메신저 어댑터.

설계 기준: '쿨메신저_연동_설계.md' (install_path/data_dir/db_path 분리,
자동 탐색 우선, 관대한 DB 검증, WAL 안전 복사, 다중 계정 후보, 친절한 오류).

check_coolmessenger_udb.py 진단(2026-08-18, 실제 업무 PC)으로 확정된 실제 스키마:
  tbl_recv: MessageKey, Sender, Title, MessageText(본문), ReceiveDate, FilePath ...
  (MessageBody는 내부 렌더링용 원시 포맷이라 사용하지 않음 — MessageText 우선)
이 값들은 SCHEMA_HINT / _EXPECTED_COLUMNS 의 '기본 힌트'일 뿐이며,
validate_database()는 이 값과 정확히 다르더라도 관대하게 후보로 인정한다
(설계 문서 5장: "예상 테이블/컬럼은 추정치이므로 실제와 다를 수 있다").

외부에 노출되는 인터페이스는 base.MessengerAdapter 그대로다
(is_available, fetch_recent_messages) — task_manager.py 등 호출부는
변경할 필요가 없다. 내부는 설계 문서 11~12장 기준으로 세분화했다:
  detect_installation() / find_data_dir() / find_databases() /
  validate_database() / read_messages() / get_attachments()
"""

import glob
import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

from .base import MessengerAdapter
from ..models import RawMessage
from ..privacy import masking
from .. import db

# ---------- 힌트 (관대하게 검증됨 — 정확히 일치하지 않아도 후보로 인정) ----------

SCHEMA_HINT = {
    "table": "tbl_recv",
    "col_id": "MessageKey",
    "col_sender": "Sender",
    "col_title": "Title",
    "col_body": "MessageText",
    "col_received_at": "ReceiveDate",
}

# 역할별로 시도해 볼 컬럼명 후보 (첫 매치 우선)
_EXPECTED_COLUMNS = {
    "id": ["MessageKey"],
    "sender": ["Sender"],
    "title": ["Title"],
    "body": ["MessageText", "MessageBody"],
    "received_at": ["ReceiveDate"],
}
_MIN_COLUMN_MATCH = 3  # 5개 역할 중 이 개수 이상 매칭되면 "후보"로 인정 (관대함)

_INSTALL_CANDIDATES = [
    r"C:\Program Files (x86)\CoolMessenger Gentoo",
    r"C:\Program Files\CoolMessenger Gentoo",
]

# "홍길동(교무부)" -> ("홍길동", "교무부")
_SENDER_PATTERN = re.compile(r"^\s*(?P<name>[^(]+?)\s*(?:\((?P<dept>[^)]*)\))?\s*$")

# "2022/03/03 15:23:31 (목)" 형태. 요일 괄호는 버린다.
_DATE_PATTERN = re.compile(r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})")

# FilePath 컬럼은 단순 경로가 아니라 "|파일ID|크기;표시명|파일명|크기|" 식의
# 내부 구분자(|, ;)가 섞인 값이라, 위치 기반 파싱 대신 확장자로 파일명만 골라낸다.
_ATTACHMENT_FILENAME_PATTERN = re.compile(
    r"[^|;]+?\.(?:hwp|hwpx|doc|docx|xls|xlsx|ppt|pptx|pdf|zip|jpg|jpeg|png|gif|bmp|txt|hml)",
    re.IGNORECASE,
)


def _extract_attachment_filenames(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [m.strip() for m in _ATTACHMENT_FILENAME_PATTERN.findall(str(raw))]


# 이미지로 취급해서 Gemini에 함께 보낼 확장자 -> MIME 타입.
_IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".bmp": "image/bmp",
}


def _resolve_local_attachment_path(filename: str, candidate_dirs: List[str]) -> Optional[str]:
    """첨부파일 실제 바이트를 로컬에서 찾아본다.

    실측 확인(2026-08-20, 실제 업무 PC): 쿨메신저는 첨부파일을 로컬에
    미리 캐시해 두지 않는다 — tbl_recv에는 파일 내용 컬럼이 없고
    FileHost/CoolFile2SessionID 컬럼만 있어, 첨부파일은 원격 파일
    서버에서 CoolDownloader.exe/CoolFile2.dll을 통해 사용자가 직접 열 때만
    온디맨드로 받아온다(데이터 폴더·설치 폴더 어디에도 별도 첨부 캐시
    폴더가 없음을 직접 확인함). 그래서 이 함수는 사실상 거의 항상 None을
    돌려준다 — 그래도 향후 버전/다른 학교 환경에서 로컬 캐시가 있을
    가능성을 완전히 배제할 수 없어 best-effort로 몇 군데는 찾아본다."""
    for base in candidate_dirs:
        if not base:
            continue
        candidate = Path(base) / filename
        if candidate.is_file():
            return str(candidate)
    return None


def _images_enabled() -> bool:
    return db.get_setting("analyze_images", "1") == "1"


def _parse_sender(raw: str) -> tuple[str, str]:
    if not raw:
        return "", ""
    m = _SENDER_PATTERN.match(raw)
    if not m:
        return raw, ""
    return m.group("name") or "", m.group("dept") or ""


def _parse_received_at(raw) -> Optional[datetime]:
    if not raw:
        return None
    m = _DATE_PATTERN.search(str(raw))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S")
    except ValueError:
        return None


def _is_sqlite(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except Exception:
        return False


# ---------- 데이터 구조 (설계 문서 5, 16장) ----------

@dataclass
class ValidationResult:
    path: str
    is_sqlite: bool
    is_candidate: bool                 # 관대한 판정: "메시지 DB로 보임"
    table_name: Optional[str] = None
    col_map: Dict[str, str] = field(default_factory=dict)
    message_count: Optional[int] = None
    last_message_at: Optional[datetime] = None
    preview_titles_masked: List[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class UdbCandidate:
    path: str
    filename: str
    size_bytes: int
    mtime: datetime
    account_name_guess: str
    validation: ValidationResult
    username_similarity: float = 0.0

    @property
    def message_count(self) -> Optional[int]:
        return self.validation.message_count

    @property
    def last_message_at(self) -> Optional[datetime]:
        return self.validation.last_message_at

    @property
    def is_candidate(self) -> bool:
        return self.validation.is_candidate


# ---------- 사용자 친화 오류 (설계 문서 17장) ----------

_ERROR_CATALOG = {
    "no_database": {
        "title": "쿨메신저 메시지 데이터를 확인할 수 없습니다.",
        "causes": [
            "쿨메신저를 한 번도 실행하지 않음",
            "다른 Windows 계정에서 사용 중",
            "메시지 데이터 위치가 기본 경로와 다름",
        ],
    },
    "not_sqlite": {
        "title": "선택한 파일을 쿨메신저 메시지 데이터로 열 수 없습니다.",
        "causes": [
            "쿨메신저 메시지 파일이 아님",
            "쿨메신저 버전이 달라 파일 형식이 다름",
        ],
    },
    "not_candidate": {
        "title": "선택한 파일이 쿨메신저 메시지 구조와 맞지 않습니다.",
        "causes": [
            "쿨메신저 버전이 달라 내부 구조가 다름",
            "메시지가 아닌 다른 용도의 파일(설정 파일 등)",
        ],
    },
    "read_failed": {
        "title": "쿨메신저 메시지를 읽는 중 문제가 발생했습니다.",
        "causes": [
            "쿨메신저가 파일을 사용 중이라 일시적으로 접근이 제한됨",
            "메시지 데이터 파일이 손상됨",
        ],
    },
}


def describe_error(kind: str, detail: str = "") -> dict:
    """설계 문서 17장 형태로 변환한 오류 설명. UI에서 causes를 목록으로,
    detail은 '더보기' 수준으로만 노출하는 걸 권장."""
    info = dict(_ERROR_CATALOG.get(kind, {
        "title": "쿨메신저 데이터를 처리하는 중 문제가 발생했습니다.",
        "causes": [],
    }))
    info["detail"] = detail
    return info


def _friendly_exception(kind: str, detail: str = "") -> Exception:
    info = describe_error(kind, detail)
    causes = "\n".join(f"- {c}" for c in info["causes"])
    msg = f"{info['title']}" + (f"\n\n가능한 원인:\n{causes}" if causes else "")
    return FileNotFoundError(msg)


class CoolMessengerAdapter(MessengerAdapter):
    name = "coolmessenger"

    def __init__(self):
        self.install_path = db.get_setting("install_path") or None
        self.data_dir = db.get_setting("data_dir") or None
        self.db_path = db.get_setting("db_path") or None

    # ---------- 1단계: 설치 여부 확인 (설계 문서 3장) ----------

    def detect_installation(self) -> Optional[str]:
        for candidate in _INSTALL_CANDIDATES:
            if os.path.isdir(candidate):
                return candidate
        return None

    # ---------- 2단계: 메시지 데이터 폴더 확인 ----------

    def find_data_dir(self) -> Optional[str]:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None
        memo_dir = Path(local_appdata) / "CoolMessenger" / "Memo"
        return str(memo_dir) if memo_dir.is_dir() else None

    # ---------- 3단계: .udb 탐색 + 검증 + 순위화 (설계 문서 16장) ----------

    def find_databases(self, search_root: Optional[str] = None) -> List[UdbCandidate]:
        """search_root(비어 있으면 저장된/자동 탐색 data_dir) 하위에서 *.udb를
        찾아 각각 validate_database()로 검증한 뒤, 메시지 건수·최근 수신
        시각·Windows 계정명 유사도로 정렬해 반환한다. (읽기 전용)"""
        root = search_root or self.data_dir or self.find_data_dir()
        found: List[str] = []
        if root:
            found.extend(glob.glob(str(Path(root) / "*.udb")))
            found.extend(glob.glob(str(Path(root) / "**" / "*.udb"), recursive=True))
        paths = sorted(set(p for p in found if os.path.isfile(p)))

        windows_user = (os.environ.get("USERNAME") or "").strip().lower()
        candidates: List[UdbCandidate] = []
        for path in paths:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            account_guess = Path(path).stem
            validation = self.validate_database(path)
            similarity = (
                SequenceMatcher(None, windows_user, account_guess.lower()).ratio()
                if windows_user else 0.0
            )
            candidates.append(UdbCandidate(
                path=path,
                filename=os.path.basename(path),
                size_bytes=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime),
                account_name_guess=account_guess,
                validation=validation,
                username_similarity=similarity,
            ))

        def sort_key(c: UdbCandidate):
            return (
                0 if c.is_candidate else 1,                                  # 후보 아닌 건 뒤로
                -(c.message_count or 0),
                -(c.last_message_at.timestamp() if c.last_message_at else 0),
                -c.username_similarity,
                -c.mtime.timestamp(),
            )

        candidates.sort(key=sort_key)
        return candidates

    # ---------- DB 유효성 검사 (설계 문서 5장 — 관대한 판정) ----------

    def validate_database(self, db_path: str) -> ValidationResult:
        """가볍게(복사 없이) 검증한다. 대용량 DB(수백MB)에서도 빨라야 하므로
        읽기 전용 URI로 원본을 직접 열어 스키마/건수/최근 메시지만 확인한다.
        원본에는 절대 쓰지 않는다 (mode=ro 라 SQLite 레벨에서도 쓰기가 막힘).
        실제 메시지를 다 읽어오는 read_messages()에서만 전체 안전 복사를 뜬다."""
        if not _is_sqlite(db_path):
            return ValidationResult(
                path=db_path, is_sqlite=False, is_candidate=False,
                reason="SQLite 형식이 아닙니다.",
            )
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                tables = [
                    r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                ]
                table_name, col_map = self._best_table_match(conn, tables)
                if table_name is None:
                    return ValidationResult(
                        path=db_path, is_sqlite=True, is_candidate=False,
                        reason="메시지 테이블로 보이는 구조를 찾지 못했습니다.",
                    )

                match_count = len(col_map)
                is_candidate = match_count >= _MIN_COLUMN_MATCH

                count_row = conn.execute(f"SELECT COUNT(*) c FROM '{table_name}'").fetchone()
                message_count = count_row["c"] if count_row else 0

                last_message_at = None
                preview_titles: List[str] = []
                title_col = col_map.get("title")
                date_col = col_map.get("received_at")
                if date_col:
                    order_cols = f"{title_col} as title, " if title_col else ""
                    query = (
                        f"SELECT {order_cols}{date_col} as received_at "
                        f"FROM '{table_name}' ORDER BY {date_col} DESC LIMIT 3"
                    )
                    for row in conn.execute(query):
                        parsed = _parse_received_at(row["received_at"])
                        if parsed and last_message_at is None:
                            last_message_at = parsed
                        if title_col and row["title"]:
                            # 미리보기도 전송 전 마스킹과 동일한 원칙 적용 (방어적으로)
                            preview_titles.append(masking.mask_text(row["title"]))

                reason = "" if is_candidate else (
                    f"예상 컬럼 {match_count}/5개만 일치 — 실제 쿨메신저 데이터가 맞는지 확인이 필요합니다."
                )
                return ValidationResult(
                    path=db_path, is_sqlite=True, is_candidate=is_candidate,
                    table_name=table_name, col_map=col_map,
                    message_count=message_count, last_message_at=last_message_at,
                    preview_titles_masked=preview_titles, reason=reason,
                )
            finally:
                conn.close()
        except Exception as e:
            return ValidationResult(
                path=db_path, is_sqlite=True, is_candidate=False,
                reason=f"검증 중 오류가 발생했습니다: {e}",
            )

    def _best_table_match(self, conn: sqlite3.Connection, tables: List[str]):
        best_table, best_map, best_score = None, {}, -1.0
        for t in tables:
            if t.startswith("sqlite_"):
                continue
            try:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{t}')")]
            except sqlite3.OperationalError:
                continue
            col_map = {}
            for role, names in _EXPECTED_COLUMNS.items():
                for name in names:
                    if name in cols:
                        col_map[role] = name
                        break
            score = len(col_map) + (0.5 if t == SCHEMA_HINT["table"] else 0.0)
            if score > best_score:
                best_table, best_map, best_score = t, col_map, score
        return best_table, best_map

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> List[str]:
        return [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")]

    # ---------- 원본 보호: WAL/SHM 안전 복사 (설계 문서 9, 10장) ----------

    def _safe_copy(self, db_path: str, dest_dir: str) -> str:
        """원본은 읽기 전용으로만 연다. sqlite3 backup() API를 우선 사용해
        WAL 내용까지 반영된 일관된 스냅샷을 뜨고(가장 안전·정확), 어떤 이유로든
        실패하면 파일 복사(+ -wal/-shm 동반 복사)로 폴백한다. 원본은 절대 쓰지 않는다."""
        dest_path = os.path.join(dest_dir, os.path.basename(db_path))
        try:
            src_uri = f"file:{db_path}?mode=ro"
            src_conn = sqlite3.connect(src_uri, uri=True)
            try:
                dest_conn = sqlite3.connect(dest_path)
                try:
                    src_conn.backup(dest_conn)
                finally:
                    dest_conn.close()
            finally:
                src_conn.close()
            return dest_path
        except sqlite3.Error:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            shutil.copy2(db_path, dest_path)  # 원본 읽기만, 쓰기는 복사본에만
            for suffix in ("-wal", "-shm"):
                side_path = db_path + suffix
                if os.path.exists(side_path):
                    shutil.copy2(side_path, dest_path + suffix)
            return dest_path

    # ---------- 메시지 읽기 (설계 문서 11~13장) ----------

    def _build_attachment_records(self, filenames: List[str]) -> List[dict]:
        """파일명 목록을 {"filename", "image_bytes", "mime_type"} 딕셔너리
        목록으로 바꾼다. 이미지 확장자가 아니거나, "캡처 이미지도 함께
        분석" 설정이 꺼져 있거나, 로컬에서 실제로 못 찾으면 image_bytes는
        None으로 남는다(항상 filename은 채워서 기존처럼 "첨부파일 있음"
        정도는 계속 전달됨)."""
        images_enabled = _images_enabled()
        candidate_dirs = [self.data_dir, self.install_path]
        records = []
        for filename in filenames:
            ext = Path(filename).suffix.lower()
            mime_type = _IMAGE_MIME_TYPES.get(ext)
            image_bytes = None
            if images_enabled and mime_type:
                local_path = _resolve_local_attachment_path(filename, candidate_dirs)
                if local_path:
                    try:
                        with open(local_path, "rb") as f:
                            image_bytes = f.read()
                    except OSError:
                        image_bytes = None
            records.append({
                "filename": filename,
                "image_bytes": image_bytes,
                "mime_type": mime_type if image_bytes else None,
            })
        return records

    def read_messages(self, db_path: str, since: Optional[datetime] = None) -> List[RawMessage]:
        validation = self.validate_database(db_path)
        if not validation.is_sqlite:
            raise _friendly_exception("not_sqlite")
        if not validation.is_candidate or not validation.table_name:
            raise _friendly_exception("not_candidate", validation.reason)

        col = validation.col_map
        id_col = col.get("id")
        date_col = col.get("received_at")
        if not id_col or not date_col:
            raise _friendly_exception("not_candidate", "id/날짜 컬럼을 찾지 못했습니다.")

        results: List[RawMessage] = []
        try:
            with tempfile.TemporaryDirectory() as tmp:
                copy_path = self._safe_copy(db_path, tmp)
                conn = sqlite3.connect(copy_path)
                conn.row_factory = sqlite3.Row
                try:
                    table_cols = self._table_columns(conn, validation.table_name)
                    file_path_col = "FilePath" if "FilePath" in table_cols else None

                    select_cols = [f"{id_col} as id", f"{date_col} as received_at"]
                    select_cols.append(f"{col['sender']} as sender" if col.get("sender") else "'' as sender")
                    select_cols.append(f"{col['title']} as title" if col.get("title") else "'' as title")
                    select_cols.append(f"{col['body']} as body" if col.get("body") else "'' as body")
                    if file_path_col:
                        select_cols.append(f"{file_path_col} as file_path")

                    query = f"SELECT {', '.join(select_cols)} FROM '{validation.table_name}'"
                    for row in conn.execute(query):
                        received_at = _parse_received_at(row["received_at"]) or datetime.now()
                        if since and received_at < since:
                            continue
                        name, department = _parse_sender(row["sender"] or "")
                        attachments = []
                        if file_path_col and row["file_path"]:
                            filenames = _extract_attachment_filenames(row["file_path"])
                            attachments = self._build_attachment_records(filenames)
                        results.append(RawMessage(
                            id=f"recv:{row['id']}",
                            sender=name,
                            department=department,
                            title=row["title"] or "",
                            body=row["body"] or "",
                            received_at=received_at,
                            attachments=attachments,
                        ))
                finally:
                    conn.close()
        except sqlite3.Error as e:
            raise _friendly_exception("read_failed", str(e))

        return results

    def get_attachments(self, db_path: str, message_id: str) -> List[str]:
        """메시지 하나의 첨부파일 '파일명' 목록만 반환한다 (내용은 절대 읽지 않음).
        단건 조회라 무거운 안전 복사 없이 읽기 전용 연결로 바로 조회한다."""
        validation = self.validate_database(db_path)
        id_col = validation.col_map.get("id")
        if not validation.table_name or not id_col:
            return []
        raw_id = message_id.split(":", 1)[-1]
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            if "FilePath" not in self._table_columns(conn, validation.table_name):
                return []
            row = conn.execute(
                f"SELECT FilePath as file_path FROM '{validation.table_name}' WHERE {id_col} = ?",
                (raw_id,),
            ).fetchone()
            if not row or not row["file_path"]:
                return []
            return _extract_attachment_filenames(row["file_path"])
        finally:
            conn.close()

    # ---------- MessengerAdapter 외부 인터페이스 (변경 금지 — task_manager.py 등이 호출) ----------

    def is_available(self) -> bool:
        if self.db_path and os.path.isfile(self.db_path):
            return True
        try:
            return any(c.is_candidate for c in self.find_databases())
        except Exception:
            return False

    def fetch_recent_messages(self, days: int = 1) -> List[RawMessage]:
        resolved = self._resolve_db_path()
        if not resolved:
            raise _friendly_exception("no_database")
        since = datetime.now() - timedelta(days=days)
        return self.read_messages(resolved, since=since)

    def _resolve_db_path(self) -> Optional[str]:
        """저장된 db_path가 있고 여전히 유효하면 그걸 쓰고, 없으면 자동 탐색해서
        가장 적합한 후보로 자가 치유한다 (설치 경로가 바뀌어도 db_path 기준이므로
        계속 동작하게 하려는 설계 문서 8장의 원칙)."""
        if self.db_path and os.path.isfile(self.db_path):
            return self.db_path
        candidates = self.find_databases()
        valid = [c for c in candidates if c.is_candidate]
        if not valid:
            return None
        best = valid[0]
        self.db_path = best.path
        db.set_setting("db_path", best.path)
        return best.path
