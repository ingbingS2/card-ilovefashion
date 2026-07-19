"""probe_lib 단위 테스트 — 네트워크 호출 없음, 문자열 픽스처만 사용."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_lib import extract_next_data, safe_name, summarize_json


def test_summarize_json_dict_and_scalar_types():
    data = {"name": "셔츠", "price": 10000, "soldout": False}
    assert summarize_json(data) == {"name": "str", "price": "int", "soldout": "bool"}


def test_summarize_json_list_shows_len_and_first():
    data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
    assert summarize_json(data) == {
        "items": {"__len__": 3, "__first__": {"id": "int"}}
    }


def test_summarize_json_empty_list():
    assert summarize_json([]) == {"__len__": 0, "__first__": None}


def test_summarize_json_respects_max_depth():
    data = {"a": {"b": {"c": {"d": 1}}}}
    # depth 0=a-dict, 1=b-dict, 2=c-dict 에서 절단 → "dict" 타입명
    assert summarize_json(data, max_depth=3) == {"a": {"b": {"c": "dict"}}}


def test_extract_next_data_found():
    html = '<html><script id="__NEXT_DATA__" type="application/json">{"props": {"ok": true}}</script></html>'
    assert extract_next_data(html) == {"props": {"ok": True}}


def test_extract_next_data_missing_or_broken():
    assert extract_next_data("<html></html>") is None
    broken = '<script id="__NEXT_DATA__">{not json}</script>'
    assert extract_next_data(broken) is None


def test_safe_name():
    assert safe_name("https://api.a.com/v1/best?x=1") == "https_api.a.com_v1_best_x_1"
    assert len(safe_name("a" * 200)) == 80
