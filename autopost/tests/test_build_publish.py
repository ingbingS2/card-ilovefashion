from __future__ import annotations

import json
import subprocess
from datetime import timedelta

import pytest

from autopost import build, config, measure, publish, rules, state, verify
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
    assert item["proof"] == '후기 43개 · <b class="star">★</b> 4.9'
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


def _ok_git(*args, check=True):
    return subprocess.CompletedProcess(args, 0, "", "")


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
    assert files and all(rules.zzal_path(f).is_file() for f in files)   # 저장소 CARD/zzal + 데이터 브랜치 zzal/


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
    now = config.now_kst()
    fp = _built(folder, now)
    _built(folder, now, verified_at=now.isoformat(), verified_fingerprint=fp)
    calls = []

    def fake_api(method, endpoint, token, **data):
        calls.append((endpoint, data))
        if endpoint == "me":
            return {"username": "i_s2_fashion"}
        if endpoint == "me/media" and method == "GET":
            return {"data": []}
        if endpoint == "me/media" and data.get("is_carousel_item"):
            if "verdnt" in data.get("user_tags", ""):
                raise RuntimeError('Graph API 오류 400: {"error":{"message":"Invalid user id","code":110,"error_subcode":2207018}}')
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
    monkeypatch.setattr(publish, "_git", _ok_git)
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    monkeypatch.setenv("IG_ACCESS_TOKEN", "T")
    with pytest.raises(SystemExit):           # 내부 게이트: 승인 없이 호출하면 거부 — 인스타 호출 0회
        publish.publish(folder)
    assert calls == []
    st = publish.publish(folder, approved=True)
    sent = [json.loads(dt["user_tags"])[0]["username"] for ep_, dt in calls
            if ep_ == "me/media" and dt.get("user_tags")]
    assert "moodinside_official" in sent and "generalidea_official" in sent
    assert st["user_tags"]["3"]["result"] == "태그 없이 올림"   # 버던트 태그 실패 → 태그 빼고 성공
    assert {b["handle"]: b for b in state.load_handles()["brands"]}["verdnt_official"]["photo_tag"] is False
    assert st["user_tags"]["2"]["result"] == "ok"
    assert "사진 태그(user_tags): 2번 @moodinside_official" in (d / "result.md").read_text(encoding="utf-8")


def test_tag_blocked_handle_is_skipped_next_time(episode, cands, handles):
    write_episode(episode["folder"], episode, cands)
    state.save_handles(handles)
    publish.mark_tag_blocked(["verdnt_official"])
    saved = {b["handle"]: b for b in state.load_handles()["brands"]}
    assert saved["verdnt_official"]["photo_tag"] is False and saved["we_are_urago"].get("photo_tag", True)
    assert 3 not in publish.photo_tags(episode["folder"])          # 버던트(3번 사진) 태그 건너뜀


def test_approve_records_fingerprint_and_gate_accepts_recorded_approval(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst().replace(hour=12)
    state.save_history([])
    fp = _built(folder, now, verified_at=now.isoformat(), verified_fingerprint=None)
    with pytest.raises(SystemExit):           # error가 남아 있으면 승인 불가
        state.save_status(folder, {**state.load_status(folder), "issues": [["error", "x"]]})
        publish.approve(folder, "승인")
    _built(folder, now)
    with pytest.raises(SystemExit):           # 사용자 메시지 원문 없이는 승인 기록 불가
        publish.approve(folder, "  ")
    st = publish.approve(folder, "승인")
    assert st["stage"] == "approved" and st["approved_fingerprint"] == fp and st["approved_quote"] == "승인"
    # 기록된 승인 + 지금 파일 기준 재검증이 있으면 --user-approved 없이도 통과
    st.update(verified_at=now.isoformat(), verified_fingerprint=fp)
    state.save_status(folder, st)
    assert publish.gate(folder, approved=False, now=now) == []
    # 승인 뒤 파일이 바뀌면 거부
    (config.episode_dir(folder) / "caption.txt").write_text("바뀜", encoding="utf-8")
    assert any("승인 뒤에 파일이 바뀜" in p or "파일이 바뀜" in p for p in publish.gate(folder, approved=False, now=now))


def test_risky_changes_and_pending_list(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    fresh = {"100": {"sale_price": 49900, "normal_price": 129900, "discount": 0, "review_count": 50, "rating": 4.9, "sold_out": False},
             "101": {"sale_price": 70000, "normal_price": 129900, "discount": 46, "review_count": 43, "rating": 4.9, "sold_out": False},
             "102": {"sale_price": 51000, "normal_price": 129900, "discount": 60, "review_count": 43, "rating": 4.9, "sold_out": False}}
    risky = publish.risky_changes(folder, fresh)
    assert len(risky) == 2 and any("할인이 사라짐" in r for r in risky) and any("20% 초과" in r for r in risky)
    assert publish.pending_episodes() == []
    state.save_status(folder, {"stage": "approved", "approved_at": "2026-10-02T09:00:00+09:00"})
    assert publish.pending_episodes() == [folder]


def _approved(folder, now, hours_ago=1):
    fp = _built(folder, now, verified_at=now.isoformat())
    st = state.load_status(folder)
    st.update(stage="approved", approved_fingerprint=fp, verified_fingerprint=fp, approved_quote="승인",
              approved_at=(now - timedelta(hours=hours_ago)).isoformat())
    state.save_status(folder, st)
    return fp


def test_recorded_approval_needs_quote_and_expires(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst().replace(hour=12)
    state.save_history([])
    _approved(folder, now)
    assert publish.gate(folder, approved=False, now=now) == []
    st = state.load_status(folder)
    st.pop("approved_quote")
    state.save_status(folder, st)
    assert any("사용자 승인 없음" in p for p in publish.gate(folder, approved=False, now=now))
    _approved(folder, now, hours_ago=config.APPROVAL_TTL_HOURS + 1)
    assert any("시간이 지남" in p for p in publish.gate(folder, approved=False, now=now))
    line, done = publish._publish_one(folder, now, verify, None)     # 만료는 몰 조회 전에 걸러져 expired
    assert not done and "만료" in line and state.load_status(folder)["stage"] == "expired"
    assert publish.pending_episodes() == []


def test_gate_rechecks_brand_and_keyword_continuity(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst().replace(hour=12)
    fp = _built(folder, now, verified_at=now.isoformat())
    _built(folder, now, verified_at=now.isoformat(), verified_fingerprint=fp)
    old = (now - timedelta(days=2)).isoformat()
    state.save_history([{"folder": "x", "keyword": "겨울 코트", "posted_at": old, "brands": ["버던트"]}])
    assert any("브랜드가 겹침" in p and "버던트" in p for p in publish.gate(folder, True, now))
    state.save_history([{"folder": "y", "keyword": episode["keyword"], "posted_at": old, "brands": ["딴브랜드"]},
                        {"folder": "z", "keyword": "겨울 코트", "posted_at": (now - timedelta(days=1, hours=1)).isoformat(),
                         "brands": ["딴브랜드2"]}])
    assert any("같은 키워드" in p for p in publish.gate(folder, True, now))


def test_publish_aborts_when_lock_push_is_rejected(episode, cands, handles, monkeypatch):
    folder = episode["folder"]
    d = write_episode(folder, episode, cands)
    state.save_handles(handles)
    state.save_history([])
    for i in range(1, 8):
        (d / f"{i}.jpg").write_bytes(b"x")
    (d / "caption.txt").write_text("본문", encoding="utf-8")
    now = config.now_kst()
    _approved(folder, now)
    calls = []

    def fake_api(method, endpoint, token, **data):
        calls.append(endpoint)
        if endpoint == "me":
            return {"username": "i_s2_fashion"}
        if endpoint == "me/media" and method == "GET":
            return {"data": []}
        if endpoint == "me/media":
            return {"id": "C"}
        return {"status_code": "FINISHED"}

    def racing_git(*args, check=True):     # 잠금 커밋 푸시만 거부(다른 세션이 먼저 밀었음)
        rc = 1 if args[0] == "push" else 0
        return subprocess.CompletedProcess(args, rc, "", "")

    monkeypatch.setattr(publish, "api", fake_api)
    monkeypatch.setattr(publish, "public_url", lambda f, p: f"https://img/{p.name}")
    monkeypatch.setattr(publish, "push_data", lambda m: True)
    monkeypatch.setattr(publish, "_git", racing_git)
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    monkeypatch.setenv("IG_ACCESS_TOKEN", "T")
    with pytest.raises(SystemExit, match="동시 게시"):
        publish.publish(folder)
    assert "me/media_publish" not in calls
    # 동기화 자체가 실패해도 게시하지 않는다
    monkeypatch.setattr(publish, "push_data", lambda m: False)
    with pytest.raises(SystemExit, match="동기화 실패"):
        publish.publish(folder)
    assert "me/media_publish" not in calls


def _git_ok():
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not _git_ok(), reason="git 없음")
def test_push_data_resolves_conflicts_with_real_git(tmp_path, monkeypatch):
    """두 세션이 같은 status.json·history.json을 고친 채 푸시 — 진 쪽이 규칙대로 합쳐 푸시한다(실제 git)."""
    def g(cwd, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *a],
                              check=True, capture_output=True, text=True, encoding="utf-8")
    remote, a, b = tmp_path / "remote.git", tmp_path / "a", tmp_path / "b"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(a)], check=True, capture_output=True)
    for c in (a,):
        g(c, "checkout", "-q", "-b", config.DATA_BRANCH)
    ep = "episodes/20261002 가을 니트"
    (a / ep).mkdir(parents=True)
    (a / ep / "status.json").write_text(json.dumps({"stage": "approved", "x": 1}, indent=2) + "\n", encoding="utf-8")
    (a / "history.json").write_text(json.dumps([{"folder": "old", "posted_at": "2026-09-30T20:00+09:00", "media_id": "1"}],
                                               indent=2) + "\n", encoding="utf-8")
    g(a, "add", "-A"); g(a, "commit", "-qm", "init"); g(a, "push", "-q", "origin", f"HEAD:{config.DATA_BRANCH}")
    subprocess.run(["git", "clone", "-q", "-b", config.DATA_BRANCH, str(remote), str(b)], check=True, capture_output=True)
    for c in (a, b):
        g(c, "config", "user.name", "t"); g(c, "config", "user.email", "t@t")
    # A: 게시 완료 기록을 먼저 푸시
    (a / ep / "status.json").write_text(json.dumps({"stage": "posted", "media_id": "2"}, indent=2) + "\n", encoding="utf-8")
    hist = json.loads((a / "history.json").read_text(encoding="utf-8")) + [{"folder": "20261002 가을 니트", "media_id": "2",
                                                                            "posted_at": "2026-10-02T20:30+09:00"}]
    (a / "history.json").write_text(json.dumps(hist, indent=2) + "\n", encoding="utf-8")
    g(a, "add", "-A"); g(a, "commit", "-qm", "A posted"); g(a, "push", "-q", "origin", f"HEAD:{config.DATA_BRANCH}")
    # B: 같은 파일을 다르게 고침(재검증 기록 + 측정값)
    (b / ep / "status.json").write_text(json.dumps({"stage": "approved", "verified_at": "x"}, indent=2) + "\n", encoding="utf-8")
    (b / "history.json").write_text(json.dumps([{"folder": "old", "posted_at": "2026-09-30T20:00+09:00", "media_id": "1",
                                                 "metrics": {"reach": 300}}], indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", b)
    assert publish.push_data("B") is True
    g(a, "pull", "-q", "origin", config.DATA_BRANCH)
    st = json.loads((a / ep / "status.json").read_text(encoding="utf-8"))
    rows = {h["media_id"]: h for h in json.loads((a / "history.json").read_text(encoding="utf-8"))}
    assert st["stage"] == "posted"                                   # 더 진행된 단계(원격의 posted)가 이긴다
    assert set(rows) == {"1", "2"} and rows["1"]["metrics"] == {"reach": 300}   # 행 합집합 + 빈 칸 채움
    assert not publish._rebase_in_progress()


def test_merge_data_file_rules():
    up = json.dumps({"stage": "publishing", "a": 1})
    assert json.loads(publish.merge_data_file("episodes/x/status.json", up, json.dumps({"stage": "approved"})))["stage"] == "publishing"
    assert json.loads(publish.merge_data_file("episodes/x/status.json", up, json.dumps({"stage": "posted"})))["stage"] == "posted"
    assert publish.merge_data_file("episodes/x/episode.json", "{}", "{}") is None      # 그 밖은 원격 우선
    assert publish.merge_data_file("history.json", "[", "[]") is None


def test_gate_sees_other_episode_publishing(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst().replace(hour=12)
    state.save_history([])
    _approved(folder, now)
    assert publish.gate(folder, approved=False, now=now) == []
    state.save_status("20261001 다른 회차", {"stage": "publishing", "publishing_at": (now - timedelta(minutes=1)).isoformat()})
    assert any("같은 날" in p and "다른 회차" in p for p in publish.gate(folder, approved=False, now=now))
    assert publish.earliest_post_time(now) > now


def test_main_rejects_mixed_modes(capsys):
    with pytest.raises(SystemExit):
        publish.main(["x", "--pending", "--check"])


def test_risky_change_rerenders_and_unapproves(episode, cands, monkeypatch):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst().replace(hour=12)
    state.save_history([])
    _approved(folder, now)

    class V:
        EXIT_OK = 0

        @staticmethod
        def check(f):
            return [], ["가격 변경"], [], {"100": {"sale_price": 49900, "discount": 0}}

        @staticmethod
        def apply(f, fresh):
            pass

    built = []

    def fake_build(f):
        built.append(f)
        st = state.load_status(f)
        st["stage"] = "built"
        state.save_status(f, st)
        return {"rendered": True, "issues": []}

    line, done = publish._publish_one(folder, now, V, fake_build)
    st = state.load_status(folder)
    assert not done and built == [folder] and "다시 승인" in line
    assert st["stage"] == "built" and not st.get("approved_quote") and any("할인" in r for r in st["needs_reapproval"])


def test_blocked_mall_in_cloud_is_reported_distinctly(episode, cands):
    folder = episode["folder"]
    write_episode(folder, episode, cands)
    now = config.now_kst().replace(hour=12)
    state.save_history([])
    _approved(folder, now)

    class V:
        @staticmethod
        def check(f):
            return [], [], ["무드인사이드(100): 상세 조회 실패 무신사 차단(데이터센터 IP 403) — 우회하지 않음"], {}

    line, done = publish._publish_one(folder, now, V, None)
    assert line.startswith("🖥️") and "PC에서" in line and state.load_status(folder)["stage"] == "approved"


def test_pending_newest_first_token_check_and_isolation(episode, cands, monkeypatch, tmp_path):
    for i, day in enumerate(("01", "02")):
        state.save_status(f"202610{day} 키워드{i}", {"stage": "approved", "approved_at": f"2026-10-{day}T09:00:00+09:00"})
    assert publish.pending_episodes() == ["20261002 키워드1", "20261001 키워드0"]
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(publish.post_ig, "TOKEN_FILE", str(tmp_path / "없음.txt"))
    out = publish.publish_pending()
    assert len(out) == 1 and "토큰 없음" in out[0]
    monkeypatch.setenv("IG_ACCESS_TOKEN", "T")

    def one(folder, now, v, b):
        if folder.endswith("키워드1"):
            raise KeyError("boom")
        return f"✅ {folder}", True

    monkeypatch.setattr(publish, "_publish_one", one)
    out = publish.publish_pending()
    assert len(out) == 1 and out[0].startswith("⚠️ 20261002") and "KeyError" in out[0] and "중단" in out[0]
