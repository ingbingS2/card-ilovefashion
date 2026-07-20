"""수집 대상·상수 설정. 카테고리 추가/제거는 이 파일만 수정."""
from __future__ import annotations

# 무신사 카테고리 코드 → 한글명 (FINDINGS.md 실측 확인분)
MUSINSA_CATEGORIES: dict[str, str] = {
    "001": "상의",
    "002": "아우터",
    "003": "바지",
    "100": "원피스/스커트",
    "004": "가방",
    "103": "신발",
}

TOP_N = 50          # 카테고리당 저장 상위 개수
REVIEW_SIZE = 10    # 상품당 후기 수집 개수
HISTORY_CAP = 168   # 상품 이력 보존 개수 (시간당 1개 기준 약 1주)
