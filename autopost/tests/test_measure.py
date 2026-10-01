"""measure(+72h 측정·브랜드 댓글·토큰 메타)와 result.md 기록 — 인스타 호출은 전부 목."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import pytest

from autopost import build, config, measure, publish, state
from autopost.tests.conftest import write_episode

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=config.KST)
POSTED = NOW - timedelta(hours=74, minutes=30)
INSIGHTS = {"data": [{"name": "reach", "values": [{"value": 250}]},
                     {"name": "shares", "total_value": {"value": 1}}]}


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "now_kst", lambda: NOW)
    monkeypatch.setattr(config, "TOKEN_META_FILE", tmp_path / "token-meta.json")


def _posted_episode(episode, cands, mentions=("generalidea_official", "we_are_urago")):
    folder = episode["folder"]
    d = write_episode(folder, episode, cands)
    (d / "result.md").write_text("## 4. 측정값 — 게시 +72시간\n- (measure가 채운다)\n", encoding="utf-8")
    state.save_status(folder, {"stage": "posted", "user_tags": {
        "2": {"tags": ["moodinside_official"], "result": "ok"},
        "3": {"tags": ["verdnt_official"], "result": "태그 없이 올림"}}})
    state.save_history([{"folder": folder, "media_id": "M1", "posted_at": POSTED.isoformat(timespec="minutes"),
                         "mentions": list(mentions)}])
    return d


def _fake_api(comment_pages=None, comment_error=None, calls=None):
    """insights는 고정값, comments는 pages를 차례로(마지막 쪽 반복). calls에 (endpoint, params)를 남긴다."""
    pages = comment_pages or [{"data": []}]
    calls = [] if calls is None else calls

    def fake(method, endpoint, token, **data):
        calls.append((endpoint, dict(data)))
        if endpoint.endswith("/insights"):
            return INSIGHTS
        if endpoint.endswith("/comments"):
            if comment_error:
                raise RuntimeError(comment_error)
            n = sum(1 for e, _ in calls if e.endswith("/comments"))
            return pages[min(n, len(pages)) - 1]
        raise AssertionError(endpoint)
    return fake


def test_measure_records_hours_and_only_brand_commenters(episode, cands, monkeypatch):
    d = _posted_episode(episode, cands)
    calls = []
    pages = [{"data": [{"username": "random_person", "timestamp": "t"}, {"username": "Verdnt_Official"}],
              "paging": {"cursors": {"after": "CUR1"}, "next": "https://graph/next"}},
             {"data": [{"username": "generalidea_official"}, {"username": "another_fan"}]}]
    monkeypatch.setattr(measure, "api", _fake_api(pages, calls=calls))
    done, errors = measure.measure("TOK")
    assert errors == [] and len(done) == 1
    row = state.load_history()[0]
    assert row["measured_at"] == "2026-10-05T12:00+09:00" and row["measured_hours"] == 74.5
    # 캡션 멘션 + 사진 태그 핸들 중 댓글 단 계정만. 다른 사람 아이디는 어디에도 남기지 않는다
    assert row["brand_comments"] == ["generalidea_official", "verdnt_official"]
    assert row["comment_count"] == 4
    saved = config.HISTORY_FILE.read_text(encoding="utf-8")
    assert "random_person" not in saved and "another_fan" not in saved
    comment_calls = [dt for e, dt in calls if e == "M1/comments"]
    assert comment_calls[0]["fields"] == "username,timestamp" and comment_calls[1]["after"] == "CUR1"
    text = (d / "result.md").read_text(encoding="utf-8")
    assert "측정 시점: 게시 +74.5h" in text
    assert "브랜드 반응(댓글): @generalidea_official, @verdnt_official (댓글 4개 중)" in text
    assert "random_person" not in text and "좋아요·스토리 공유는 Graph API로 볼 수 없음" in text


def test_comment_paging_stops_at_three_pages(episode, cands, monkeypatch):
    _posted_episode(episode, cands)
    calls = []
    endless = [{"data": [{"username": "x"}], "paging": {"cursors": {"after": "C"}, "next": "https://graph/next"}}]
    monkeypatch.setattr(measure, "api", _fake_api(endless, calls=calls))
    measure.measure("TOK")
    assert sum(1 for e, _ in calls if e.endswith("/comments")) == measure.COMMENT_PAGES == 3
    assert state.load_history()[0]["comment_count"] == 3


def test_comment_error_does_not_fail_measurement(episode, cands, monkeypatch):
    d = _posted_episode(episode, cands)
    err = 'Graph API 오류 400: {"error":{"message":"(#10) permission","code":10}} access_token=SECRETTOK'
    monkeypatch.setattr(measure, "api", _fake_api(comment_error=err))
    done, errors = measure.measure("SECRETTOK")
    assert errors == [] and len(done) == 1
    row = state.load_history()[0]
    assert row["metrics"]["reach"] == 250 and row["verdict"] == "통과"
    assert "brand_comments" not in row and "permission" in row["brand_comments_error"]
    assert "SECRETTOK" not in config.HISTORY_FILE.read_text(encoding="utf-8")
    assert "브랜드 반응(댓글): 조회 실패" in (d / "result.md").read_text(encoding="utf-8")


def test_episode_handles_merge_mentions_and_photo_tags(episode, cands):
    _posted_episode(episode, cands, mentions=("@We_Are_Urago",))
    row = state.load_history()[0]
    assert measure.episode_handles(row) == ["moodinside_official", "verdnt_official", "we_are_urago"]


# ---------- 토큰 메타 (값은 저장하지 않는다) ----------

def _key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def test_token_meta_keys_by_hash_and_never_stores_token():
    measure.token_age_note("FILE_TOKEN_abc")
    measure.token_age_note("ENV_TOKEN_xyz")
    raw = config.TOKEN_META_FILE.read_text(encoding="utf-8")
    meta = json.loads(raw)
    assert set(meta["tokens"]) == {_key("FILE_TOKEN_abc"), _key("ENV_TOKEN_xyz")}   # 서로 덮어쓰지 않는다
    assert "FILE_TOKEN_abc" not in raw and "ENV_TOKEN_xyz" not in raw
    assert "추정" in measure.token_age_note("FILE_TOKEN_abc")


def test_refresh_expiry_preferred_and_warns_when_close():
    measure.record_token_refresh("TOK", 50 * 86400)
    note = measure.token_age_note("TOK")
    assert "만료 약 50일 남음" in note and "만료 임박" not in note
    measure.record_token_refresh("TOK", 10 * 86400)
    note = measure.token_age_note("TOK")
    assert "만료 약 10일 남음" in note and "⚠️ 토큰 만료 임박" in note
    assert "TOK" not in config.TOKEN_META_FILE.read_text(encoding="utf-8")


def test_old_single_hash_format_is_migrated():
    old = {"hash": hashlib.sha256(b"OLD").hexdigest()[:16], "first_seen": "2026-08-01"}
    config.TOKEN_META_FILE.write_text(json.dumps(old), encoding="utf-8")
    note = measure.token_age_note("OLD")
    assert "처음 확인 2026-08-01" in note and "⚠️ 토큰 만료 임박" in note   # 60일 - 65일 경과


def test_main_token_refresh_records_new_token_expiry(monkeypatch, capsys):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "OLD_ENV_TOKEN")
    monkeypatch.setattr(measure, "refresh_token",
                        lambda t: {"access_token": "NEW_TOKEN_123", "expires_in": 5184000})
    pushed = []
    monkeypatch.setattr(publish, "push_data", lambda m: pushed.append(m) or True)
    measure.main(["--token"])
    out = capsys.readouterr().out
    assert "OLD_ENV_TOKEN" not in out and "NEW_TOKEN_123" not in out and "IG_ACCESS_TOKEN을 바꿔야" in out
    meta = json.loads(config.TOKEN_META_FILE.read_text(encoding="utf-8"))
    entry = meta["tokens"][_key("NEW_TOKEN_123")]
    assert entry["refreshed_at"].startswith("2026-10-05") and entry["expires_at"].startswith("2026-12-04")
    assert pushed


# ---------- result.md (build) ----------

def test_result_md_cover_type_confounds_and_build_time_handles(episode, cands, handles):
    # 수집 시점 candidates의 handle은 비어 있어도(None) build 시점 handles.json 값이 표에 들어간다
    assert all(c["handle"] is None for c in cands["candidates"])
    episode.update(cover_type="무드형", confounds=["로스터 1곳", "29CM 혼합"])
    text = build.result_md(episode, build.enrich(episode, cands, handles), [], [])
    assert "**표지 유형**: 무드형" in text and "**변수 오염·주의**: 로스터 1곳 · 29CM 혼합" in text
    assert "@moodinside_official |" in text and "@generalidea_official ★로스터" in text
    assert "(태그 안 함)" in text   # 신규브랜드는 미검증
    episode.pop("cover_type"); episode.pop("confounds")
    text = build.result_md(episode, build.enrich(episode, cands, handles), [], [])
    assert "**표지 유형**: 기록 없음" in text and "**변수 오염·주의**: 기록 없음" in text


def test_token_refresh_skipped_within_24h(monkeypatch, capsys):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "TOKEN-A")
    measure.record_token_refresh("TOKEN-A", 5184000)
    called = []
    monkeypatch.setattr(measure, "refresh_token", lambda t: called.append(t) or {})
    measure.main(["--token"])
    assert called == [] and "건너뜀" in capsys.readouterr().out
