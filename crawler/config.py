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

# 29CM 카테고리 → {문서키: {한글명, facets}} (2026-07-22 실측).
# facets 는 categoryFacetInputs 로 보낼 {large, middle?} 목록. 여러 개면 랭킹을
# 교차 병합한다(무신사 "원피스/스커트" 단일 탭에 대응 — 29CM 은 원피스·스커트가 분리).
# large=여성의류 268100100 하위 middle: 상의 268103100 / 바지 268106100 /
#   원피스 268104100 / 스커트 268107100. 가방=269100100, 여성슈즈=270100100.
CM29_CATEGORIES: dict[str, dict] = {
    "sang": {"name": "상의", "facets": [{"large": 268100100, "middle": 268103100}]},
    "baji": {"name": "바지", "facets": [{"large": 268100100, "middle": 268106100}]},
    "opset": {"name": "원피스/스커트", "facets": [
        {"large": 268100100, "middle": 268104100},   # 원피스
        {"large": 268100100, "middle": 268107100},   # 스커트
    ]},
    "bag": {"name": "가방", "facets": [{"large": 269100100}]},
    "shoes": {"name": "신발", "facets": [{"large": 270100100}]},
}

TOP_N = 50          # 카테고리당 저장 상위 개수
REVIEW_SIZE = 10    # 상품당 후기 수집 개수
HISTORY_CAP = 168   # 상품 이력 보존 개수 (시간당 1개 기준 약 1주)
