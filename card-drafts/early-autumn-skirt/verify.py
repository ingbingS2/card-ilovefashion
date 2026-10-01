"""게시 전 재검증 — 29CM·무신사 가격·후기 수·평점·구매 가능·인용 원문 존재 + 몰 간 최저가.

실행:  python verify.py            (Chrome 확장 불필요. Playwright + 실제 Chrome 헤드리스)
출력:  카드별 [OK]/[CHECK]. 카드(index.html)의 숫자와 다르거나 다른 몰이 더 싸면 CHECK.
       CHECK 가 나오면 cards 배열을 고치고 render.py 를 다시 돌린다.
"""
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# 카드에 적힌 값. mall = 카드에 표기한 판매처. other = 다른 몰의 같은 상품(없으면 None = 단독).
CARDS = [
    dict(brand="드로우핏 우먼", mall="29cm", no="2427640", price=49500, normal=55000, rate=10, reviews=86, score=5.0,
         kw="드로우핏 플리츠 스커트", name="스티치 플리츠 미니 스커트 [BEIGE]",
         quote="계단 올라갈 때도 괜찮습니다", other=("musinsa", "3783636")),
    dict(brand="노티아", mall="29cm", no="3007788", price=104500, normal=110000, rate=5, reviews=163, score=5.0,
         kw="노티아 스탠다드 핏 롱 스커트", name="STANDARD FIT LONG SKIRT_BEIGE",
         quote="출근할때 너무 편해서 회색이랑 번갈아", other=("musinsa", "4701033")),
    dict(brand="로에일", mall="29cm", no="1794854", price=58000, normal=72500, rate=20, reviews=156, score=4.5,
         kw="로에일 코듀로이 핀턱", name="마일드 코듀로이 핀턱 스커트 - 카키 베이지",
         quote="차르르 떨어져 다림질 필요 없네요", other=("musinsa", "2890244")),
    dict(brand="커스텀어클락 우먼", mall="29cm", no="3462638", price=49600, normal=62000, rate=20, reviews=555, score=5.0,
         kw="커스텀어클락 H라인 맥시 스커트", name="[듀닝 PICK] 포멀 슬릿 H라인 맥시 스커트 차콜 COWSK002CHARCOAL",
         quote="앉을때나 움직일깨 편안해요", other=("musinsa", "5366191")),
    dict(brand="노우드", mall="29cm", no="3736187", price=56000, normal=56000, rate=0, reviews=560, score=5.0,
         kw="노우드 Soft Ease Skirt", name="Soft Ease Skirt (Black)",
         quote="슬릿없는스커트 찾고있었는데 딱이에요", other=("musinsa", "5984932"),
         # 09-11 무신사도 56,000 동가(09-08엔 53,200/5%로 2,800원 쌌다). 다시 무신사가 싸지더라도
         # 무신사 후기는 3개뿐이라 근거가 무너지고, 29CM 은 쿠폰 적용 시 실구매가 42,840 이라
         # "팔로워를 비싼 몰로 보내지 않는다"는 규칙의 목적에도 맞으므로 29CM 을 유지한다.
         # 카드에는 쿠폰 미적용 정상가 56,000 을 적는다(할인 배지 없음).
         allow_pricier="29CM 후기 560 vs 무신사 3 · 29CM 실구매가(쿠폰) 42,840"),
]


def fetch_json(page, url):
    return page.evaluate(f"fetch('{url}').then(r => r.json())")


def musinsa(page, no, quote=None):
    page.goto(f"https://www.musinsa.com/products/{no}", wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_function("() => /구매하기|재입고 알림|품절/.test(document.body.innerText)", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(1200)
    text = page.evaluate("document.body.innerText")
    price = fetch_json(page, f"https://goods-detail.musinsa.com/api2/goods/{no}")["data"]["goodsPrice"]
    summ = fetch_json(page, f"https://goods.musinsa.com/api2/review/v1/goods/{no}/reviews/summary")["data"]
    return dict(price=price["salePrice"], normal=price["normalPrice"], rate=price["discountRate"],
                reviews=summ["totalCount"], score=summ["satisfactionScore"],
                buyable="구매하기" in text, restock="재입고 알림" in text, quote=True)


def cm29_search(page, keyword, item_name=None):
    """29CM 검색 API (페이지 안 fetch). item_name 이 있으면 정확히 일치하는 상품만."""
    url = ("https://search-api.29cm.co.kr/api/v4/products/search?keyword="
           + urllib.parse.quote(keyword) + "&page=1&size=40")
    prods = (fetch_json(page, url).get("data") or {}).get("products") or []
    if item_name:
        prods = [p for p in prods if (p.get("itemName") or "").strip() == item_name.strip()]
    return prods


def cm29(page, card):
    no = card["no"]
    det = fetch_json(page, f"https://bff-api.29cm.co.kr/api/v5/product-detail/{no}")["data"]
    stock = det.get("frontItemStockStatus")
    cnt = fetch_json(page, f"https://review-api.29cm.co.kr/api/v4/reviews/count?itemId={no}")
    agg = fetch_json(page, f"https://review-api.29cm.co.kr/api/v4/reviews?itemId={no}&page=0&size=1&sort=BEST")
    found = False
    for pg in range(0, 8):
        r = fetch_json(page, f"https://review-api.29cm.co.kr/api/v4/reviews?itemId={no}&page={pg}&size=20&sort=BEST")
        res = (r.get("data") or {}).get("results") or []
        if not res:
            break
        if any(card["quote"] in " ".join((x.get("contents") or "").split()) for x in res):
            found = True
            break
    rd = agg.get("data") or {}
    return dict(price=det.get("sellPrice"), normal=det.get("consumerPrice"), rate=det.get("discountRate"),
                reviews=(cnt.get("data") if isinstance(cnt.get("data"), int) else rd.get("count")),
                score=rd.get("averagePoint"),
                buyable=(stock == "ON_STOCK"),
                restock=False, quote=found, searched=True,
                coupon=(det.get("internalDisplayPrice") or {}).get("totalDiscountedItemPrice"))


def main():
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True)  # 자동화 탐지 회피 플래그 없음(10-02: 봇 차단 우회 금지)
        ctx = browser.new_context(locale="ko-KR", viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        # 29CM API 는 29cm 페이지 컨텍스트에서만 200 — 미리 한 번 열어둔다
        page.goto("https://www.29cm.co.kr/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        for card in CARDS:
            got = cm29(page, card)
            if not got["searched"]:
                print(f"[CHECK] {card['brand']}: 29CM 검색에서 상품을 못 찾음 (검색어/상품명 확인)")
                problems.append(card["brand"])
                page.goto("https://www.29cm.co.kr/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1200)
                continue
            diff = {k: (card[k], got[k]) for k in ("price", "normal", "rate", "reviews", "score") if card[k] != got[k]}
            other_note, cheaper = "단독", False
            if card["other"]:
                o = musinsa(page, card["other"][1])
                other_note = f"무신사 {o['price']:,}"
                cheaper = o["price"] < got["price"]
                page.goto("https://www.29cm.co.kr/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1200)
            waived = card.get("allow_pricier")
            ok = got["buyable"] and got["quote"] and not diff and (not cheaper or bool(waived))
            print(f"[{'OK' if ok else 'CHECK'}] {card['brand']} (29CM {card['no']}): "
                  f"판매가 {got['price']:,} (정가 {got['normal']:,}, {got['rate']}%) · "
                  f"후기 {got['reviews']} · ⭐{got['score']} · 구매 {'가능' if got['buyable'] else '불가(품절)'} · "
                  f"인용문 {'존재' if got['quote'] else '없음!!'} · 다른 몰: {other_note}"
                  + f" · (29CM 쿠폰가 {got['coupon']:,} — 카드에는 쓰지 않는다)"
                  + (f" · 카드와 다름 {diff}" if diff else "")
                  + (" · ⚠️ 다른 몰이 더 싸다" if cheaper else "")
                  + (f" · 예외 승인: {waived}" if (cheaper and waived) else ""))
            if not ok:
                problems.append(card["brand"])
        browser.close()
    print("\n결과:", "전부 일치 — 게시 가능" if not problems else f"확인 필요 {problems}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
