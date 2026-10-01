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
    episode["keyword"] = "가을 재킷 TOP"
    episode["folder"] = "20261002 가을 재킷 TOP"
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
