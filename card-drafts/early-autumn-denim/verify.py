"""무신사 5종 게시 전 재검증 — 가격·후기 수·평점·구매 가능·인용 원문 존재.

실행:  python verify.py            (Chrome 확장 불필요. Playwright + 실제 Chrome 헤드리스)
출력:  상품별 salePrice/normalPrice/discountRate, 후기 수·평점, 구매하기 버튼 유무, 인용문 존재 여부.
       카드(index.html)의 숫자와 다르면 cards 배열을 고치고 render.py 를 다시 돌린다.
"""
import json
import re
import sys

from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# goodsNo → (카드에 적힌 값, 인용문 앞부분)
CARDS = {
    "7009519": dict(brand="아워데이즈", price=45540, normal=66000, rate=31, reviews=99, score=4.9,
                    quote="입었을 때 마른 사람도 핏 괜찮게 떨어지고"),
    "5984093": dict(brand="미치코런던 코시노", price=84550, normal=89000, rate=5, reviews=8, score=5.0,
                    quote="뒤 포켓 디자인이 너무 귀여워요!"),
    "6026753": dict(brand="미레코", price=81000, normal=90000, rate=10, reviews=35, score=4.8,
                    quote="생지 데님인데 너무 편하고"),
    "6135920": dict(brand="낫포너드", price=69000, normal=99000, rate=30, reviews=28, score=4.8,
                    quote="핏 존예 다들 어디꺼냐고 물어봐요"),
    "6507751": dict(brand="세컨드솔트", price=69520, normal=79000, rate=12, reviews=73, score=4.8,
                    quote="찢청 원래도 좋아하지만 이 벌룬핏이 신의한수"),
}


def fetch_json(page, url):
    return page.evaluate(f"fetch('{url}').then(r => r.json())")


def main():
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True,
                                    args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(locale="ko-KR", user_agent=UA,
                                  viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        for no, card in CARDS.items():
            page.goto(f"https://www.musinsa.com/products/{no}", wait_until="domcontentloaded", timeout=60000)
            # 구매 영역은 늦게 렌더된다 — '구매하기' 또는 '재입고 알림' 이 뜰 때까지 최대 20초 대기
            try:
                page.wait_for_function(
                    "() => /구매하기|재입고 알림|품절/.test(document.body.innerText)", timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            text = page.evaluate("document.body.innerText")
            buyable = "구매하기" in text
            restock = "재입고 알림" in text
            price = fetch_json(page, f"https://goods-detail.musinsa.com/api2/goods/{no}")["data"]["goodsPrice"]
            summ = fetch_json(page, f"https://goods.musinsa.com/api2/review/v1/goods/{no}/reviews/summary")["data"]
            found = False
            for pg in range(0, 20):
                url = (f"https://goods.musinsa.com/api2/review/v1/view/list?page={pg}&pageSize=20&goodsNo={no}"
                       f"&sort=up_cnt_desc&selectedSimilarNo={no}&myFilter=false&hasPhoto=false&isExperience=false")
                lst = (fetch_json(page, url).get("data") or {}).get("list") or []
                if not lst:
                    break
                if any(card["quote"] in (r.get("content") or "") for r in lst):
                    found = True
                    break
            got = dict(price=price["salePrice"], normal=price["normalPrice"], rate=price["discountRate"],
                       reviews=summ["totalCount"], score=summ["satisfactionScore"])
            diff = {k: (card[k], got[k]) for k in got if card[k] != got[k]}
            status = "OK" if (buyable and found and not diff) else "CHECK"
            print(f"[{status}] {no} {card['brand']}: 판매가 {got['price']:,} (정가 {got['normal']:,}, {got['rate']}%) · "
                  f"후기 {got['reviews']} · ⭐{got['score']} · 구매하기 {'있음' if buyable else ('없음 — 재입고 알림만(품절)' if restock else '없음(버튼 미렌더, 재실행)')} · "
                  f"인용문 {'존재' if found else '없음!!'}"
                  + (f" · 카드와 다름 {diff}" if diff else ""))
            if status != "OK":
                problems.append(no)
        browser.close()
    print("\n결과:", "전부 일치 — 게시 가능" if not problems else f"확인 필요 {problems}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
