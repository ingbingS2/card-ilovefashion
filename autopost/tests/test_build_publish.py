from __future__ import annotations

import json
from datetime import timedelta

import pytest

from autopost import build, config, measure, publish, state, verify
from autopost.tests.conftest import write_episode


def test_rich_escapes_everything_but_em_br():
    assert build.rich('<em>가을</em><br/><script>x</script>"') == \
        '<em>가을</em><br>&lt;script&gt;x&lt;/script&gt;&quot;'


def test_card_dicts_and_caption(episode, cands, handles):
    prods = build.enrich(episode, cands)
    cover = cands["candidates"][3]
    cards = build.card_dicts(episode, prods, cover, "assets/zzal.jpg")
    assert [c["kind"] for c in cards] == ["cover"] + ["item"] * 5 + ["cta"]
    assert cards[0]["img"] == "assets/cover-103-3.jpg" and cards[1]["img"] == "assets/01-100-0.jpg"
    item = cards[1]
    assert item["sale"] == "49,900원" and item["normal"] == "129,900원" and item["off"] == "62%"
    assert item["proof"] == "후기 43개 · ⭐ 4.9"
    assert "실제&nbsp;후기" in item["sp"] and "색감이 어두워서" in item["sp"]
    caption, skipped = build.caption_text(episode, prods, handles)
    assert caption.endswith("📌 브랜드 계정\n무드인사이드 @moodinside_official\n버던트 @verdnt_official\n"
                            "제너럴아이디어 @generalidea_official\n유라고 @we_are_urago")
    assert skipped == ["신규브랜드"]


def test_enrich_ignores_fact_overrides_from_episode(episode, cands):
    episode["products"][0].update(sale_price=1, quote_text="지어낸 문장", brand="가짜")
    p = build.enrich(episode, cands)[0]
    assert p["sale_price"] == 49900 and p["brand"] == "무드인사이드"
    assert p["quote_text"].startswith("색감이 어두워서")


def test_zero_review_spec_card(episode, cands):
    cands["candidates"][2].update(review_count=0, rating=None, quotes=[])
    p = episode["products"][2]
    p.pop("quote_no")
    p["spec_line"] = "총장 62cm"
    card = build.card_dicts(episode, build.enrich(episode, cands), cands["candidates"][3], "z.jpg")[3]
    assert card["proof"] == "후기 0개 · 2026 F/W"
    assert "상세&nbsp;페이지&nbsp;표기" in card["sp"]


def test_build_errors_mark_status_invalid(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    state.save_status(folder, {"stage": "built", "verified_at": "x", "fingerprint": "old"})
    episode["caption"] = "#해시태그"
    write_episode(folder, episode, cands)
    rep = build.build(folder)
    assert rep["rendered"] is False
    st = state.load_status(folder)
    assert st["stage"] == "invalid" and "verified_at" not in st


def test_build_refuses_posted(episode, cands):
    write_episode(episode["folder"], episode, cands)
    state.save_status(episode["folder"], {"stage": "posted"})
    with pytest.raises(SystemExit):
        build.build(episode["folder"])


def _built(folder, now, **extra):
    fp = state.fingerprint(folder)
    st = {"stage": "built", "built_at": (now - timedelta(minutes=20)).isoformat(), "issues": [],
          "fingerprint": fp}
    st.update(extra)
    state.save_status(folder, st)
    return fp


def test_publish_gate(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst().replace(hour=12)
    state.save_history([])
    assert any("--user-approved" in p for p in publish.gate(folder, False, now))
    fp = _built(folder, now)
    assert any("재검증" in p for p in publish.gate(folder, True, now))
    _built(folder, now, verified_at=(now - timedelta(minutes=5)).isoformat(), verified_fingerprint=fp)
    assert publish.gate(folder, True, now) == []
    # 검증 후 파일이 바뀌면 거부
    (config.episode_dir(folder) / "caption.txt").write_text("바뀜", encoding="utf-8")
    assert any("파일이 바뀜" in p for p in publish.gate(folder, True, now))


def test_publish_gate_spacing_and_stages(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst().replace(hour=12)
    fp = _built(folder, now)
    _built(folder, now, verified_at=now.isoformat(), verified_fingerprint=fp)
    state.save_history([{"keyword": "x", "posted_at": (now - timedelta(hours=3)).isoformat()}])
    assert any("같은 날" in p for p in publish.gate(folder, True, now))
    state.save_history([])
    state.save_status(folder, {"stage": "publishing"})
    assert any("publishing" in p for p in publish.gate(folder, True, now))
    state.save_status(folder, {"stage": "posted", "permalink": "https://instagram.com/p/x"})
    assert any("이미 게시" in p for p in publish.gate(folder, True, now))
    state.save_status(folder, {"stage": "stale"})
    assert any("stale" in p for p in publish.gate(folder, True, now))


def test_too_soon_same_day_or_20h():
    base = config.now_kst().replace(hour=23, minute=0)
    assert publish.too_soon(base, base + timedelta(hours=10))           # 다음 날 09시지만 20시간 미만
    assert not publish.too_soon(base, base + timedelta(hours=21))
    morning = base.replace(hour=0, minute=30)
    assert publish.too_soon(morning, morning + timedelta(hours=22))     # 같은 날


def test_raw_url_encodes_korean_folder():
    url = publish.raw_url("20261002 가을 재킷", "1.jpg")
    assert url.startswith("https://raw.githubusercontent.com/ingbingS2/card-ilovefashion/refs/heads/claude/autopost-data/")
    assert "%20" in url and " " not in url


def test_api_redacts_token(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("GET https://graph.instagram.com/me?access_token=SECRET123 실패")
    monkeypatch.setattr(publish.post_ig, "api", boom)
    with pytest.raises(RuntimeError) as e:
        publish.api("GET", "me", "SECRET123")
    assert "SECRET123" not in str(e.value)


def _fake_mall(monkeypatch, sold=(), price=None, missing_review=(), fail=()):
    def fake_detail(no):
        if int(no) in fail:
            raise verify.malls.MallError("timeout")
        sale = (price or {}).get(int(no), 49900)
        return {"goodsPrice": {"salePrice": sale, "normalPrice": 129900, "discountRate": 62},
                "goodsReview": {"totalCount": 43, "satisfactionScore": 4.9}, "isOutOfStock": int(no) in sold}

    def fake_review(no, rno, pages=15):
        if int(no) in missing_review:
            return None
        return {"no": rno, "content": "색감이 어두워서 과하지 않게 여기저기 걸치고 다니기 좋아요\n자주 입고 다닙니다"}

    monkeypatch.setattr(verify.malls, "detail", fake_detail)
    monkeypatch.setattr(verify, "find_review", fake_review)


def test_verify_exit_codes(episode, cands, monkeypatch):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst()
    assert verify.run(folder) == verify.EXIT_BLOCKED          # build 전
    _built(folder, now)
    _fake_mall(monkeypatch)
    assert verify.run(folder) == verify.EXIT_OK
    st = state.load_status(folder)
    assert st["verified_fingerprint"] == st["fingerprint"]
    _fake_mall(monkeypatch, fail=(101,))
    assert verify.run(folder) == verify.EXIT_LOOKUP
    _fake_mall(monkeypatch, sold=(101,), missing_review=(102,))
    assert verify.run(folder) == verify.EXIT_BLOCKED


def test_verify_apply_marks_stale(episode, cands, monkeypatch):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    _built(folder, config.now_kst(), verified_at="2026-10-02T07:00:00+09:00")
    _fake_mall(monkeypatch, price={100: 39900})
    assert verify.run(folder, do_apply=True) == verify.EXIT_CHANGED
    saved = json.loads((config.episode_dir(folder) / "candidates.json").read_text(encoding="utf-8"))
    assert saved["candidates"][0]["sale_price"] == 39900
    st = state.load_status(folder)
    assert st["stage"] == "stale" and "verified_at" not in st
    assert any("stale" in p for p in publish.gate(folder, True))


def test_record_inserts_once_then_fills_permalink(episode, cands):
    folder = episode["folder"]
    d = write_episode(folder, episode, cands)
    (d / "caption.txt").write_text("본문\n\n📌 브랜드 계정\n유라고 @we_are_urago\n", encoding="utf-8")
    (d / "result.md").write_text("## 3. 게시 정보\n- (게시 후 publish가 채운다)\n", encoding="utf-8")
    state.save_history([])
    st = {"posted_at": "2026-10-02T09:00+09:00", "media_id": "M1", "image_urls": []}
    publish.record(folder, st)
    st["permalink"] = "https://www.instagram.com/p/abc/"
    publish.record(folder, st)
    hist = state.load_history()
    assert len(hist) == 1 and hist[0]["permalink"].endswith("/abc/") and hist[0]["mentions"] == ["we_are_urago"]
    text = (d / "result.md").read_text(encoding="utf-8")
    assert text.count("<!-- publish -->") == 1 and "/abc/" in text


def test_missing_data_dir_raises_without_seed_flag(monkeypatch):
    monkeypatch.delenv("AUTOPOST_ALLOW_SEED")
    with pytest.raises(state.DataDirMissing):
        state.load_history()


def test_measure_parse_and_due():
    payload = {"data": [{"name": "reach", "values": [{"value": 250}]},
                        {"name": "shares", "total_value": {"value": 1}}]}
    m = measure.parse_insights(payload)
    assert m == {"reach": 250, "shares": 1}
    assert measure.verdict(m) == "통과"
    assert measure.verdict({"reach": 1000, "shares": 0}) == "미달"
    now = config.now_kst()
    hist = [{"media_id": "1", "posted_at": (now - timedelta(hours=80)).isoformat()},
            {"media_id": "2", "posted_at": (now - timedelta(hours=10)).isoformat()},
            {"media_id": "3", "posted_at": (now - timedelta(hours=90)).isoformat(), "metrics": {"reach": 1}},
            {"posted_at": (now - timedelta(hours=90)).isoformat()}]
    assert [h["media_id"] for h in measure.due(hist, now)] == ["1"]


def test_zzal_index_lists_real_files():
    idx = build.load_zzal_index()
    files = [z["file"] for z in idx["zzal"]]
    assert files and all((config.ZZAL_DIR / f).is_file() for f in files)


def test_zzal_rules(episode):
    from datetime import date
    from autopost import rules
    idx = {"zzal": [{"file": "20260719.jpg", "last_used": "2026-07-19"},
                    {"file": "20260917.jpg", "last_used": "2026-09-17"}]}
    today = date(2026, 10, 2)
    assert rules.check_zzal({"zzal": "20260719.jpg"}, idx, [], today) == []
    assert any("반복 금지" in m for _, m in rules.check_zzal({"zzal": "20260917.jpg"}, idx, [], today))
    hist = [{"posted_at": "2026-09-30T09:00+09:00", "zzal": "20260719.jpg"}]
    assert any("반복 금지" in m for _, m in rules.check_zzal({"zzal": "20260719.jpg"}, idx, hist, today))
    assert any("없음" in m for _, m in rules.check_zzal({"zzal": "nope.jpg"}, idx, [], today))
    assert any("cta.zzal" in m for _, m in rules.check_zzal({}, idx, [], today))
    assert rules.check_zzal({"zzal": "../x.jpg"}, idx, [], today)[0][0] == "error"  # 폴더 밖 경로 금지


def test_photo_tags_only_verified_product_cards(episode, cands, handles):
    write_episode(episode["folder"], episode, cands)
    state.save_handles(handles)
    tags = publish.photo_tags(episode["folder"])
    # 2~6번 = 상품 1~5. 5번 상품(신규브랜드)은 핸들 미검증 → 6번 사진 태그 없음, 표지(1)·CTA(7)도 없음
    assert sorted(tags) == [2, 3, 4, 5]
    assert tags[2] == [{"username": "moodinside_official", "x": publish.TAG_X, "y": publish.TAG_Y}]
    assert tags[4][0]["username"] == "generalidea_official"


def test_publish_sends_user_tags_and_falls_back(episode, cands, handles, monkeypatch):
    folder = episode["folder"]
    d = write_episode(folder, episode, cands)
    state.save_handles(handles)
    state.save_history([])
    for i in range(1, 8):
        (d / f"{i}.jpg").write_bytes(b"x")
    (d / "caption.txt").write_text("본문", encoding="utf-8")
    (d / "result.md").write_text("- (게시 후 publish가 채운다)\n", encoding="utf-8")
    state.save_status(folder, {"stage": "built"})
    calls = []

    def fake_api(method, endpoint, token, **data):
        calls.append((endpoint, data))
        if endpoint == "me":
            return {"username": "i_s2_fashion"}
        if endpoint == "me/media" and method == "GET":
            return {"data": []}
        if endpoint == "me/media" and data.get("is_carousel_item"):
            if "verdnt" in data.get("user_tags", ""):
                raise RuntimeError("invalid user tag")
            return {"id": f"c{len(calls)}"}
        if endpoint == "me/media":
            return {"id": "CAR"}
        if endpoint == "me/media_publish":
            return {"id": "M1"}
        if data.get("fields") == "status_code":
            return {"status_code": "FINISHED"}
        return {"permalink": "https://www.instagram.com/p/x/", "caption": "본문"}

    monkeypatch.setattr(publish, "api", fake_api)
    monkeypatch.setattr(publish, "public_url", lambda f, p: f"https://img/{p.name}")
    monkeypatch.setattr(publish, "push_data", lambda m: True)
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    monkeypatch.setenv("IG_ACCESS_TOKEN", "T")
    st = publish.publish(folder)
    sent = [json.loads(dt["user_tags"])[0]["username"] for ep_, dt in calls
            if ep_ == "me/media" and dt.get("user_tags")]
    assert "moodinside_official" in sent and "generalidea_official" in sent
    assert st["user_tags"]["3"]["result"] == "태그 없이 올림"   # 버던트 태그 실패 → 태그 빼고 성공
    assert st["user_tags"]["2"]["result"] == "ok"
    assert "사진 태그(user_tags): 2번 @moodinside_official" in (d / "result.md").read_text(encoding="utf-8")
