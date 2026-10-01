from __future__ import annotations

import pytest

from autopost import rules
from autopost.tests.conftest import TODAY, make_candidate


def errors(issues):
    return [m for lvl, m in issues if lvl == "error"]


@pytest.mark.parametrize("text,grade,rtype,expect", [
    ("가볍고 부드러워서 초가을부터 입기 좋아요 색감도 사진이랑 똑같고 자주 손이 갑니다", 5, "general", None),
    ("짧아요", 5, "general", "길이"),
    ("가볍고 부드러워서 초가을부터 입기 좋아요 색감도 사진이랑 똑같고 자주 손이 갑니다", 3, "general", "별점"),
    ("가볍고 부드러워서 좋은데 사이즈가 커서 결국 반품했어요 색감은 사진이랑 똑같아요 아쉽네요", 5, "general", "반품"),
    ("163cm 52kg인데 M 사이즈가 딱 맞아요 색감도 예쁘고 가벼워서 자주 입을 것 같아요 추천해요", 5, "general", "신체"),
    ("가볍고 부드러워서 초가을부터 입기 좋아요 색감도 사진이랑 똑같고 자주 손이 갑니다", 5, "experience", "체험단"),
])
def test_quote_problem(text, grade, rtype, expect):
    got = rules.quote_problem(text, grade, rtype)
    assert (got is None) if expect is None else (expect in got)


def test_flatten_keeps_spacing_and_typos():
    assert rules.flatten_quote("입어봤는데 \n 넘 좋아용  ㅎㅎ") == "입어봤는데 넘 좋아용  ㅎㅎ"


def test_valid_episode_has_no_errors(episode, cands, handles):
    assert errors(rules.check_episode(episode, cands, [], handles, TODAY)) == []


def test_cover_and_caption_need_season_and_item_words(episode, cands, handles):
    episode["cover"]["title"] = "아침저녁만 추운 날<br><em>겉옷</em> 다섯"
    episode["caption"] = "하나를 잘못 고르면 계절 내내 다른 옷을 사게 됩니다 🍂🧵🔖"
    errs = errors(rules.check_episode(episode, cands, [], handles, TODAY))
    assert any("표지" in e for e in errs)
    assert any("캡션 첫 문장" in e for e in errs)


def test_cover_photo_must_differ_from_card_photos(episode, cands, handles):
    episode["cover"]["image"] = 0  # 103번 상품 카드도 image 0
    assert any("같은 원본" in e for e in errors(rules.check_episode(episode, cands, [], handles, TODAY)))


def test_sold_out_old_and_excluded_brand_blocked(episode, cands, handles):
    cands["candidates"][0]["sold_out"] = True
    cands["candidates"][1]["release_date"] = "2024-12-31"
    cands["candidates"][4]["brand"] = "미치코런던 코시노"
    errs = errors(rules.check_episode(episode, cands, [], handles, TODAY))
    assert any("품절" in e for e in errs)
    assert any("신상 기준" in e for e in errs)
    assert any("미치코런던" in e for e in errs)


def test_exclusion_expires(episode, cands, handles):
    from datetime import date
    cands["candidates"][4]["brand"] = "미치코런던 코시노"
    errs = errors(rules.check_episode(episode, cands, [], handles, date(2026, 10, 6)))
    assert not any("미치코런던" in e for e in errs)


def test_quote_must_come_from_candidate_list(episode, cands, handles):
    episode["products"][0]["quote_no"] = 999
    assert any("quote_no 999" in e for e in errors(rules.check_episode(episode, cands, [], handles, TODAY)))


def test_spec_line_numbers_must_exist_in_source(episode, cands, handles):
    p = episode["products"][2]
    p.pop("quote_no")
    p["spec_line"] = "총장 62cm · 어깨너비 51.5cm"
    assert errors(rules.check_episode(episode, cands, [], handles, TODAY)) == []
    p["spec_line"] = "총장 70cm · 중량 450g"
    assert any("상세 페이지 텍스트에 없음" in e for e in errors(rules.check_episode(episode, cands, [], handles, TODAY)))


def test_caption_rules(episode, cands, handles):
    episode["caption"] += "\n#가을재킷 댓글로 알려주세요 @someone"
    errs = errors(rules.check_episode(episode, cands, [], handles, TODAY))
    assert any("해시태그" in e for e in errs)
    assert any("댓글로 알려주세요" in e for e in errs)
    assert any("@멘션" in e for e in errs)


def test_previous_episode_brand_and_keyword_blocked(episode, cands, handles):
    hist = [{"keyword": "가을 재킷", "posted_at": "2026-10-01T09:00+09:00", "brands": ["유라고"]}]
    errs = errors(rules.check_episode(episode, cands, hist, handles, TODAY))
    assert any("직전 회차" in e for e in errs)
    assert any("같은 키워드" in e for e in errs)


def test_headline_tags_and_particle_emphasis(episode, cands, handles):
    episode["products"][0]["headline"] = "<b>굵게</b> 편한<em>데</em>"
    errs = errors(rules.check_episode(episode, cands, [], handles, TODAY))
    assert any("허용되지 않은 태그" in e for e in errs)
    assert any("조사·어미" in e for e in errs)


def test_ranking_keyword_blocked(episode, cands, handles):
    episode["keyword"] = "가을 재킷 TOP 10"
    episode["folder"] = "20261002 가을 재킷 TOP 10"
    assert any("랭킹" in e for e in errors(rules.check_episode(episode, cands, [], handles, TODAY)))


def test_roster_count_warns(episode, cands, handles):
    handles["brands"][0]["roster"] = False
    warns = [m for lvl, m in rules.check_episode(episode, cands, [], handles, TODAY) if lvl == "warn"]
    assert any("로스터 브랜드가 0곳" in w for w in warns)


def test_brand_lines_skip_unverified(handles):
    prods = [make_candidate(1, "제너럴아이디어"), make_candidate(2, "신규브랜드")]
    lines, skipped = rules.brand_lines(prods, handles)
    assert lines == ["제너럴아이디어 @generalidea_official"]
    assert skipped == ["신규브랜드"]


def test_unknown_product_keys_are_errors(episode, cands, handles):
    episode["products"][0]["sale_price"] = 1
    episode["products"][1]["quote_text"] = "지어낸 문장"
    errs = errors(rules.check_episode(episode, cands, [], handles, TODAY))
    assert sum("쓸 수 없는 키" in e for e in errs) == 2


def test_cover_must_be_one_of_five(episode, cands, handles):
    cands["candidates"].append(make_candidate(999, "다른브랜드"))
    episode["cover"]["goodsNo"] = 999
    assert any("5종 중 하나" in e for e in errors(rules.check_episode(episode, cands, [], handles, TODAY)))


def test_br_variants_count_as_lines(episode, cands, handles):
    episode["products"][0]["headline"] = "가<br/>나<br />다"
    assert any("너무 김" in e for e in errors(rules.check_episode(episode, cands, [], handles, TODAY)))


def test_spec_numbers_need_boundaries_and_units():
    src = "총장 62cm 어깨너비 51.5cm 2024년"
    assert rules.spec_missing("총장 62cm · 어깨 51.5cm", src) == []
    assert rules.spec_missing("총장 6cm", src) == ["6cm"]
    assert rules.spec_missing("굽 4cm", src) == ["4cm"]
    assert rules.spec_missing("62mm", src) == ["62mm"]


def test_pos_and_cover_tags_validated(episode, cands, handles):
    episode["products"][0]["pos"] = '50%" onerror="x'
    episode["cover"]["sub"] = "<b>굵게</b>"
    errs = errors(rules.check_episode(episode, cands, [], handles, TODAY))
    assert any("pos" in e for e in errs) and any("표지 sub" in e for e in errs)


def test_keyword_repeat_ignores_spacing_and_brand_prefix(episode, cands, handles):
    cands["candidates"][1]["brand"] = "파르티멘토 우먼"
    hist = [{"keyword": "가을재킷", "posted_at": "2026-10-01T09:00+09:00", "brands": ["파르티멘토"]}]
    errs = errors(rules.check_episode(episode, cands, hist, handles, TODAY))
    assert any("같은 키워드" in e for e in errs) and any("직전 회차" in e for e in errs)


def test_ranking_pattern_does_not_hit_vest(episode, cands, handles):
    episode["keyword"] = "가을 니트 베스트"; episode["item_word"] = "니트 베스트"
    episode["folder"] = "20261002 가을 니트 베스트"
    episode["cover"]["title"] = "조끼처럼 걸치는<br><em>가을 니트 베스트</em> 다섯"
    episode["caption"] = "가을 니트 베스트는 겉옷 전에 한 번 더 고민하게 됩니다 🍂\n\n저장해 두세요 🧶 친구에게 보내 주세요 🔖"
    assert not any("랭킹" in e for e in errors(rules.check_episode(episode, cands, [], handles, TODAY)))


def test_display_name_required_and_caption_range_warn(episode, cands, handles):
    episode["products"][0]["display_name"] = ""
    episode["caption"] = episode["caption"].replace("따뜻한 순서로 놓았습니다 🧵", "브이넥에서 터틀넥까지 놓았습니다 🧵")
    issues = rules.check_episode(episode, cands, [], handles, TODAY)
    assert any("display_name" in m for l, m in issues if l == "error")
    assert any("까지" in m for l, m in issues if l == "warn")


def warns(issues):
    return [m for lvl, m in issues if lvl == "warn"]


def _fact_warns(episode, cands, handles):
    return [w for w in warns(rules.check_episode(episode, cands, [], handles, TODAY)) if "캡션 소재·세탁 표현" in w]


def test_caption_material_term_must_be_in_detail_text(episode, cands, handles):
    episode["caption"] += "\n\n울 100%라 가볍고 드라이 클리닝만 됩니다"
    got = _fact_warns(episode, cands, handles)
    assert any("'울'" in w for w in got) and any("'드라이클리닝'" in w for w in got)
    cands["candidates"][2]["spec_text"] += " 소재 울 100% 세탁방법 드라이크리닝 권장"   # 원문 표기 '크리닝'도 같은 것
    assert _fact_warns(episode, cands, handles) == []


def test_caption_material_check_ignores_unrelated_words(episode, cands, handles):
    episode["caption"] += "\n\n앞면과 측면, 정면 화면이 면접처럼 깔끔해서 입으면 겨울 서울에도 어울리는 그런 면에서 좋습니다"
    assert _fact_warns(episode, cands, handles) == []


def test_caption_material_synonyms_and_brand_names(episode, cands, handles):
    cands["candidates"][0]["material"] = ["소재: 면 100%"]
    cands["candidates"][1]["brand"] = "코튼하우스"
    episode["caption"] += "\n\n코튼 100%라 부드럽고 코튼하우스 셔츠는 가볍습니다"
    assert _fact_warns(episode, cands, handles) == []   # 코튼=면, 브랜드명 속 '코튼'은 주장이 아님


def test_spec_line_without_digits_warns(episode, cands, handles):
    p = episode["products"][2]
    p.pop("quote_no")
    p["spec_line"] = "안감 기모 · 발볼 넓은 라스트"
    issues = rules.check_episode(episode, cands, [], handles, TODAY)
    assert errors(issues) == []
    assert any("숫자 없는 스펙 주장" in w for w in warns(issues))


def test_spec_line_checks_material_when_spec_text_empty(episode, cands, handles):
    c = cands["candidates"][2]
    c["spec_text"] = None
    c["material"] = "겉감: 면 100% · 총장 70cm"     # 목록이 아니라 문자열이어도 숫자가 쪼개지지 않게
    p = episode["products"][2]
    p.pop("quote_no")
    p["spec_line"] = "총장 70cm · 면 100%"
    assert errors(rules.check_episode(episode, cands, [], handles, TODAY)) == []
    c["material"] = []
    errs = errors(rules.check_episode(episode, cands, [], handles, TODAY))
    assert any("비어" in e and "70cm" in e for e in errs)


def test_cheaper_mall_claim_needs_successful_comparison(episode, cands, handles):
    episode["caption"] += "\n\n두 몰 중 더 저렴한 쪽 가격으로 적었습니다"
    assert not any("저렴" in m for _, m in rules.check_episode(episode, cands, [], handles, TODAY))
    cands["candidates"][0]["cheaper_elsewhere"] = {"unavailable": "다른 몰 검색 실패"}
    assert any("확인할 수 없음" in w for w in warns(rules.check_episode(episode, cands, [], handles, TODAY)))
    cands["candidates"][1]["cheaper_elsewhere"] = {"mall": "29CM", "goodsNo": 1, "sale_price": 1000, "url": "u"}
    errs = errors(rules.check_episode(episode, cands, [], handles, TODAY))
    assert any("사실과 다름" in e and "각 몰 판매가 기준" in e for e in errs)
