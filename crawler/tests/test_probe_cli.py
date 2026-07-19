"""probe.py 의 순수 함수(파서·저장 경로 계산)만 테스트 — 네트워크·브라우저 없음."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe import build_parser, classify_body, sample_filename


def test_build_parser_discover_preset():
    args = build_parser().parse_args(["discover", "musinsa_ranking"])
    assert args.command == "discover"
    assert args.name == "musinsa_ranking"
    assert args.url is None


def test_build_parser_discover_custom_with_keywords():
    args = build_parser().parse_args(
        ["discover", "custom", "https://example.com/x", "--keywords", "review,goods"]
    )
    assert args.url == "https://example.com/x"
    assert args.keywords == "review,goods"


def test_build_parser_direct_with_params():
    args = build_parser().parse_args(
        ["direct", "t1", "https://example.com/api", "--params", "a=1", "b=2"]
    )
    assert args.command == "direct"
    assert args.params == ["a=1", "b=2"]


def test_classify_body_json_vs_text():
    assert classify_body('{"a": 1}') == ("json", {"a": 1})
    kind, parsed = classify_body("<html>hi</html>")
    assert kind == "text" and parsed is None


def test_sample_filename():
    assert sample_filename(3, "https://a.com/v1/best?p=1", "json") == (
        "003_https_a.com_v1_best_p_1.json"
    )
