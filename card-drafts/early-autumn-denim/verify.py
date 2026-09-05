"""게시 전 재검증 — 무신사·29CM 가격·후기 수·평점·구매 가능·인용 원문 존재 + 몰 간 최저가.

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

# 카드에 적힌 값. mall = 카드에 표기한 판매처. other = 다른 몰에서 같은 상품을 찾는 검색어(없으면 None = 단독).
CARDS = [
    dict(brand="아워데이즈", mall="musinsa", no="7009519", price=45540, normal=66000, rate=31, reviews=99, score=4.9,
         quote="입었을 때 마른 사람도 핏 괜찮게 떨어지고", other=None),  # [젠플록스X아워데이즈] 협업 — 29CM 없음
    dict(brand="미치코런던 코시노", mall="29cm", no="3749085", price=72090, normal=89000, rate=19, reviews=24, score=4.5,
         quote="뒤 포켓 디자인이 너무 귀여워요", other=("musinsa", "5984093")),
    dict(brand="미레코", mall="musinsa", no="6026753", price=81000, normal=90000, rate=10, reviews=35, score=4.8,
         quote="생지 데님인데 너무 편하고", other=("29cm", "미레코 데님", "NON-FADE BOOTCUT DENIM PT TRUE BLACK")),
    dict(brand="낫포너드", mall="musinsa", no="6135920", price=69000, normal=99000, rate=30, reviews=28, score=4.8,
         quote="핏 존예 다들 어디꺼냐고 물어봐요", other=("29cm", "낫포너드 Symbol Stitch", "W Symbol Stitch Low Rise Flare Fit Denim Pants - Light Blue")),
    dict(brand="세컨드솔트", mall="musinsa", no="6507751", price=69520, normal=79000, rate=12, reviews=73, score=4.8,
         quote="찢청 원래도 좋아하지만 이 벌룬핏이 신의한수", other=("29cm", "세컨드솔트 벌룬", "벌룬 데미지 데님 팬츠 (빈티지블루)")),
]


def fetch_json(page, url):
    return page.evaluate(f"fetch('{url}').then(r => r.json())")


def musinsa(page, no, quote):
    page.goto(f"https://www.musinsa.com/products/{no}", wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_function("() => /구매하기|재입고 알림|품절/.test(document.body.innerText)", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(1500)
    text = page.evaluate("document.body.innerText")
    price = fetch_json(page, f"https://goods-detail.musinsa.com/api2/goods/{no}")["data"]["goodsPrice"]
    summ = fetch_json(page, f"https://goods.musinsa.com/api2/review/v1/goods/{no}/reviews/summary")["data"]
    found = False
    if quote:
        for pg in range(0, 20):
            url = (f"https://goods.musinsa.com/api2/review/v1/view/list?page={pg}&pageSize=20&goodsNo={no}"
                   f"&sort=up_cnt_desc&selectedSimilarNo={no}&myFilter=false&hasPhoto=false&isExperience=false")
            lst = (fetch_json(page, url).get("data") or {}).get("list") or []
            if not lst:
                break
            if any(quote in (r.get("content") or "") for r in lst):
                found = True
                break
    return dict(price=price["salePrice"], normal=price["normalPrice"], rate=price["discountRate"],
                reviews=summ["totalCount"], score=summ["satisfactionScore"],
                buyable="구매하기" in text, restock="재입고 알림" in text, quote=found)


def cm29_search(page, keyword, item_name=None):
    """29CM 검색 API (페이지 안 fetch). item_name 이 있으면 정확히 일치하는 상품만."""
    url = ("https://search-api.29cm.co.kr/api/v4/products/search?keyword="
           + urllib.parse.quote(keyword) + "&page=1&size=20")
    prods = (fetch_json(page, url).get("data") or {}).get("products") or []
    if item_name:
        prods = [p for p in prods if (p.get("itemName") or "").strip() == item_name]
    return prods


def cm29(page, item_no, quote, keyword=None, item_name=None):
    page.goto(f"https://product.29cm.co.kr/catalog/{item_no}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    text = page.evaluate("document.body.innerText")
    prods = cm29_search(page, keyword or item_name or "", item_name) if (keyword or item_name) else []
    p = prods[0] if prods else None
    si = (p or {}).get("saleInfoV2") or {}
    found = False
    if quote:
        for pg in range(0, 5):
            r = fetch_json(page, f"https://review-api.29cm.co.kr/api/v4/reviews?itemId={item_no}&page={pg}&size=20&sort=BEST")
            res = (r.get("data") or {}).get("results") or []
            if not res:
                break
            if any(quote in (x.get("contents") or "") for x in res):
                found = True
                break
    return dict(price=si.get("totalSellPrice"), normal=(p or {}).get("consumerPrice"), rate=si.get("totalSaleRate"),
                reviews=(p or {}).get("reviewCount"), score=(p or {}).get("reviewAveragePoint"),
                buyable=(p is not None and not p.get("isSoldOut")) and "품절" not in text[:2000],
                restock=False, quote=found)


def main():
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True,
                                    args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(locale="ko-KR", user_agent=UA, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        # 29CM 검색 API 는 29cm 페이지 컨텍스트에서만 200 — 미리 한 번 열어둔다
        page.goto("https://www.29cm.co.kr/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        for card in CARDS:
            # 1) 카드에 표기한 몰의 값
            if card["mall"] == "musinsa":
                got = musinsa(page, card["no"], card["quote"])
            else:
                got = cm29(page, card["no"], card["quote"], keyword="미치코런던 데님", item_name="Signatuer Wide Denim Mid blue")
            diff = {k: (card[k], got[k]) for k in ("price", "normal", "rate", "reviews", "score") if card[k] != got[k]}
            # 2) 다른 몰 가격
            other_note = "단독"
            cheaper_elsewhere = False
            if card["other"]:
                if card["other"][0] == "musinsa":
                    o = musinsa(page, card["other"][1], None)
                    other_note = f"무신사 {o['price']:,}"
                    cheaper_elsewhere = o["price"] < got["price"]
                else:
                    page.goto("https://www.29cm.co.kr/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1500)
                    prods = cm29_search(page, card["other"][1], card["other"][2])
                    if prods:
                        op = (prods[0].get("saleInfoV2") or {}).get("totalSellPrice")
                        other_note = f"29CM {op:,}"
                        cheaper_elsewhere = op is not None and op < got["price"]
                    else:
                        other_note = "29CM 없음"
            ok = got["buyable"] and got["quote"] and not diff and not cheaper_elsewhere
            status = "OK" if ok else "CHECK"
            buy = "있음" if got["buyable"] else ("없음 — 재입고 알림만(품절)" if got["restock"] else "없음(품절 또는 미렌더)")
            mall = "무신사" if card["mall"] == "musinsa" else "29CM"
            print(f"[{status}] {card['brand']} ({mall} {card['no']}): 판매가 {got['price']:,} (정가 {got['normal']:,}, {got['rate']}%) · "
                  f"후기 {got['reviews']} · ⭐{got['score']} · 구매 {buy} · 인용문 {'존재' if got['quote'] else '없음!!'} · 다른 몰: {other_note}"
                  + (f" · 카드와 다름 {diff}" if diff else "") + (" · ⚠️ 다른 몰이 더 싸다" if cheaper_elsewhere else ""))
            if status != "OK":
                problems.append(card["brand"])
        browser.close()
    print("\n결과:", "전부 일치 — 게시 가능" if not problems else f"확인 필요 {problems}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
