"""자동 게시 설정. 정책 원본은 KEYWORD-POLICY.md — 여기엔 코드가 강제하는 숫자만 둔다."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = Path(__file__).resolve().parent
TEMPLATE_HTML = PKG_DIR / "template" / "index.html"
ZZAL_DIR = REPO_ROOT / "CARD" / "zzal"

# 데이터 브랜치(claude/autopost-data)를 worktree로 체크아웃한 위치. 회차·이력·핸들이 여기 쌓인다.
DATA_DIR = Path(os.environ.get("AUTOPOST_DATA_DIR", REPO_ROOT / "autopost-data"))
EPISODES_DIR = DATA_DIR / "episodes"
HISTORY_FILE = DATA_DIR / "history.json"
HANDLES_FILE = DATA_DIR / "handles.json"
SEED_DIR = PKG_DIR / "seed"
# 커밋하지 않는 작업 파일(상품 사진 시트 등)
WORK_DIR = Path(os.environ.get("AUTOPOST_WORK_DIR", REPO_ROOT / ".autopost-work"))

DATA_BRANCH = "claude/autopost-data"
GITHUB_REPO = os.environ.get("AUTOPOST_GITHUB_REPO", "ingbingS2/card-ilovefashion")

ACCOUNT = "@i_s2_fashion"
CARD_W, CARD_H = 540, 675      # 렌더는 2배 → 1080×1350
PRODUCTS_PER_POST = 5
TEXT_BLOCK_MAX_RATIO = 0.35    # 하단 텍스트 블록 ≤ 카드 높이 35% (KEYWORD-POLICY §4)
# §9 "직전 게시물과 하루 이상" — 매일 게시라 승인 시각이 들쭉날쭉하므로 '다른 날(KST) + 20시간 이상'으로 해석
MIN_HOURS_BETWEEN_POSTS = 20
MEASURE_AFTER_HOURS = 72       # +72h 측정 (§8)
VERIFY_FRESH_MINUTES = 60      # 게시 직전 재검증 유효 시간
APPROVAL_TTL_HOURS = 48        # 기록된 승인의 유효 시간 — 지나면 새 카드로 다시 승인받는다

# 인용 후기 기준 (§3)
QUOTE_MIN_LEN = 40
QUOTE_MAX_LEN = 120
QUOTE_MIN_GRADE = 4
QUOTE_BANNED = ("반품", "환불", "불량", "배송", "교환", "고객센터", "문의", "하자", "택배", "AS", "CS")

# 브랜드 일시 제외: {표시명: (제외 마지막 날짜, 한글·영문 부분 문자열들)} (사용자 지시)
BRAND_EXCLUSIONS: dict[str, tuple[date, tuple[str, ...]]] = {
    "미치코런던": (date(2026, 10, 5), ("미치코런던", "michiko")),
}
# 대형 계정 — 반응 기대치가 낮아 경고만 한다 (BRAND-ROSTER)
BIG_ACCOUNTS = ("나이키", "크록스", "휠라", "아디다스", "에잇세컨즈", "미쏘", "무신사 스탠다드", "스컬프터")

# 캡션 금지 문형 (§1·§5) — 대소문자 무시
CAPTION_BANNED = ("댓글로 알려주세요", "번호 남겨주세요", "진심", "무조건", "못 참지", "...", "…")
# 랭킹 키워드(§1) — '니트 베스트(조끼)' 같은 품목어는 잡지 않도록 랭킹 문맥만 (정규식, 대소문자 무시)
RANKING_PATTERN = r"랭킹|베스트\s*셀러|베스트\s*\d|top\s*\d|인기\s*순위|\d+\s*위"
CAPTION_WARN_PATTERNS = {r"[가-힣A-Za-z]+(?:에서|부터)\s.{0,40}까지": "'A부터 B까지' 나열 문형(§5 금지)"}

# episode.json에서 세션이 쓸 수 있는 키 — 사실(가격·후기·인용 원문 등)은 candidates.json에서만 온다
PRODUCT_KEYS = {"goodsNo", "image", "pos", "display_name", "color", "headline", "quote_no", "spec_line"}
COVER_KEYS = {"goodsNo", "image", "pos", "kicker", "title", "sub", "collage"}
COLLAGE_MIN, COLLAGE_MAX = 2, 5   # 표지 콜라주(10-07 사용자 지시: 여러 색을 한 표지에) — 세로 띠 2~5개
CTA_KEYS = {"zzal", "title", "sub"}
ZZAL_INDEX = ZZAL_DIR / "index.json"   # 저장소에 든 짤 목록(자막·장면·무드·어울리는 주제·last_used)
ZZAL_WEB_DIR = DATA_DIR / "zzal"       # 인터넷에서 채택한 짤 — 데이터 브랜치에 쌓인다(main 커밋 금지·클라우드 보존)
ZZAL_WEB_INDEX = ZZAL_WEB_DIR / "index.json"
ZZAL_COOLDOWN_DAYS = 21                # 같은 짤은 3주 안에 다시 쓰지 않는다
TOKEN_META_FILE = DATA_DIR / "token-meta.json"   # 토큰별(sha256 앞 12자) 처음 본 날·연장 시각·만료일 — 토큰 값은 저장하지 않음
TOKEN_LIFETIME_DAYS = 60
TOKEN_WARN_DAYS = 14

# 무신사 랭킹 카테고리 (crawler/FINDINGS.md)
MUSINSA_CATEGORIES = {"001": "상의", "002": "아우터", "003": "바지", "100": "원피스/스커트",
                      "004": "가방", "103": "신발"}


def now_kst() -> datetime:
    return datetime.now(KST)


def new_since(today: date) -> date:
    """신상 기준: 올해 기준 전년도 1월 1일 이후 판매 개시 (§2)."""
    return date(today.year - 1, 1, 1)


def episode_dir(folder: str) -> Path:
    return EPISODES_DIR / folder
