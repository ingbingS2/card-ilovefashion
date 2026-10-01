"""게시 전 재검증 — 무신사·29CM 가격·후기 수·평점·구매 가능·인용 원문 존재 + 몰 간 최저가.

실행:  python verify.py            (Chrome 확장 불필요. Playwright + 실제 Chrome 헤드리스)
출력:  카드별 [OK]/[CHECK]. 카드(index.html)의 숫자와 다르거나 다른 몰이 더 싸면 CHECK.
       CHECK 가 나오면 cards 배열을 고치고 다시 렌더한다.
Playwright 가 없는 PC 에서는 앱 브라우저로 두 몰 페이지를 열고 아래와 같은 API 를 페이지 안에서 fetch 한다.
"""
import sys

from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# 카드에 적힌 값. mall = 카드에 표기한 판매처. other = 다른 몰의 같은 상품. quote=None = 후기 없는 신상(스펙 카드).
# 29CM 가격은 쿠폰 미적용 정상가(product-detail sellPrice), 무신사는 goodsPrice.salePrice.
CARDS = [
    dict(brand="기호", mall="29cm", no="4113080", price=130670, normal=179000, reviews=9, score=5.0,
         quote="미들부츠로 마무리 되는게 완전 유니크하면서", other=("musinsa", "7011657")),
    dict(brand="엘리자베스 스튜어트", mall="musinsa", no="7121523", price=118600, normal=199000, reviews=2, score=5.0,
         quote="스트랩으로 길이도 조절할 수 있고", other=("29cm", "4146739")),
    dict(brand="사뿐", mall="29cm", no="3594802", price=69900, normal=69900, reviews=97, score=4.5,
         quote="스퀘어토라서 거슬리는거 없이 발가락도 편안해요", other=("musinsa", "5617680")),
    # 타크트로이메 하비스트는 29CM 단독(29EDITION) — 무신사에 같은 상품 없음(09-17 무신사 검색 API 확인)
    dict(brand="타크트로이메", mall="29cm", no="3535947", price=120450, normal=165000, reviews=108, score=5.0,
         quote="자연스럽게 흘러내려서 예쁘고 색상도 빈티지하고", other=None),
    dict(brand="에트오소메", mall="musinsa", no="6961595", price=168300, normal=187000, reviews=3, score=5.0,
         quote="부츠 큰 아일렛에 리본으로 묶여있은거", other=("29cm", "4127635")),
]


def fetch_json(page, url):
    return page.evaluate(f"fetch('{url}').then(r => r.json())")


def squash(text):
    return " ".join((text or "").split())


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
    found = quote is None
    if quote:
        r = fetch_json(page, "https://goods.musinsa.com/api2/review/v1/view/list?page=0&pageSize=50"
                             f"&goodsNo={no}&sort=up_cnt_desc&selectedSimilarNo={no}&myFilter=false"
                             "&hasPhoto=false&isExperience=false")
        found = any(quote in squash(x.get("content")) for x in (r.get("data") or {}).get("list") or [])
    return dict(price=price["salePrice"], normal=price["normalPrice"],
                reviews=summ["totalCount"], score=summ["satisfactionScore"] or None,
                buyable="구매하기" in text, quote=found)


def cm29(page, no, quote=None):
    det = fetch_json(page, f"https://bff-api.29cm.co.kr/api/v5/product-detail/{no}")["data"]
    agg = (fetch_json(page, f"https://review-api.29cm.co.kr/api/v4/reviews?itemId={no}&page=0&size=1").get("data") or {})
    found = quote is None
    for pg in range(0, 5 if quote else 0):
        r = fetch_json(page, f"https://review-api.29cm.co.kr/api/v4/reviews?itemId={no}&page={pg}&size=20&sort=BEST")
        res = (r.get("data") or {}).get("results") or []
        if any(quote in squash(x.get("contents")) for x in res):
            found = True
            break
        if not res:
            break
        page.wait_for_timeout(400)  # 29CM API 연속 호출 차단 대비(crawler/FINDINGS.md)
    return dict(price=det.get("sellPrice"), normal=det.get("consumerPrice"),
                reviews=agg.get("count"), score=agg.get("averagePoint") or None,
                buyable=det.get("frontItemStockStatus") == "ON_STOCK", quote=found)


def get(page, mall, no, quote=None):
    if mall == "musinsa":
        return musinsa(page, no, quote)
    page.goto("https://www.29cm.co.kr/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    return cm29(page, no, quote)


def main():
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True,
                                    args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(locale="ko-KR", user_agent=UA, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        for card in CARDS:
            got = get(page, card["mall"], card["no"], card["quote"])
            diff = {k: (card[k], got[k]) for k in ("price", "normal", "reviews", "score") if card[k] != got[k]}
            o = get(page, *card["other"]) if card["other"] else None
            cheaper = bool(o) and o["price"] < got["price"]
            ok = got["buyable"] and got["quote"] and not diff and not cheaper
            print(f"[{'OK' if ok else 'CHECK'}] {card['brand']} ({card['mall']} {card['no']}): "
                  f"판매가 {got['price']:,} (정가 {got['normal']:,}) · 후기 {got['reviews']} · ⭐{got['score']} · "
                  f"구매 {'가능' if got['buyable'] else '불가(품절)'} · "
                  f"인용문 {'스펙 카드' if card['quote'] is None else ('존재' if got['quote'] else '없음!!')} · "
                  + (f"다른 몰 {card['other'][0]} {o['price']:,}" if o else "단독 판매")
                  + (f" · 카드와 다름 {diff}" if diff else "")
                  + (" · ⚠️ 다른 몰이 더 싸다" if cheaper else ""))
            if not ok:
                problems.append(card["brand"])
        browser.close()
    print("\n결과:", "전부 일치 — 게시 가능" if not problems else f"확인 필요 {problems}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
