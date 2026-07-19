"""discover 프리셋: 실제 브라우저로 로드할 페이지와 채집 키워드.

주의: 여기 URL 은 '페이지' 주소다. API 엔드포인트는 추측해 적지 않는다 —
페이지를 실제로 로드하며 XHR 을 가로채는 것이 이 프로브의 목적이다.
경로가 바뀌었으면 브라우저에서 실제 랭킹/베스트 페이지 주소를 확인해 갱신할 것.
"""

PAGES: dict[str, dict] = {
    # 무신사 랭킹 (전체)
    "musinsa_ranking": {
        "url": "https://www.musinsa.com/main/musinsa/ranking",
        "keywords": ["rank", "best", "goods", "api", "review"],
    },
    # 29CM 베스트 (전체) — 2026-07-19 확인: /home/best 는 홈으로 리다이렉트되어 /best-products 로 갱신
    "cm29_best": {
        "url": "https://www.29cm.co.kr/best-products",
        "keywords": ["best", "rank", "product", "api", "review", "item"],
    },
}
