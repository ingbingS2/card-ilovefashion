"""autopost 테스트 공통 — 실제 몰·인스타·GitHub 호출 없음. 데이터 폴더는 tmp_path로 바꾼다."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from autopost import config  # noqa: E402

TODAY = date(2026, 10, 2)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOPOST_ALLOW_SEED", "1")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(config, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(config, "HANDLES_FILE", tmp_path / "handles.json")
    monkeypatch.setattr(config, "WORK_DIR", tmp_path / "work")
    return tmp_path


def make_candidate(no: int, brand: str, **kw) -> dict:
    c = {
        "mall": "무신사", "goodsNo": no, "url": f"https://www.musinsa.com/products/{no}", "brand": brand, "brand_en": "",
        "brand_id": "", "name": f"{brand} 상품 {no}", "genders": ["W"], "category": "아우터 > 재킷",
        "sale_price": 49900, "normal_price": 129900, "discount": 62, "review_count": 43, "rating": 4.9,
        "sold_out": False, "release_date": "2026-08-01", "season": "2026 F/W", "style_no": "",
        "material": ["두께: 보통"], "spec_text": "총장 62cm 어깨너비 51.5cm",
        "images": [f"https://image.msscdn.net/images/goods_img/20260801/{no}/{no}_{i}_big.jpg" for i in range(4)],
        "quotes": [{"no": no * 10, "text": "색감이 어두워서 과하지 않게 여기저기 걸치고 다니기 좋아요 자주 입고 다닙니다",
                    "grade": 5, "likes": 3, "date": "2026-09-01"}],
        "roster": False, "handle": None,
    }
    c.update(kw)
    return c


BRANDS = ["무드인사이드", "버던트", "제너럴아이디어", "유라고", "신규브랜드"]


@pytest.fixture
def cands():
    return {"candidates": [make_candidate(100 + i, b) for i, b in enumerate(BRANDS)]}


@pytest.fixture
def episode():
    return {
        "folder": "20261002 가을 재킷", "keyword": "가을 재킷", "season_word": "가을", "item_word": "재킷",
        "axis": "보온 정도", "mood": "상황 스케치형",
        "cover": {"goodsNo": 103, "image": 3, "kicker": "AUTUMN JACKET",
                  "title": "아침저녁만 추운 날<br><em>가을 재킷</em> 다섯", "sub": "후기로 두께를 확인했습니다"},
        "products": [
            {"goodsNo": 100 + i, "image": 0, "display_name": f"재킷 {i}",
             "headline": "검정 흰색 베이지<br><em>다 받아주는 카키</em>" if i % 2 else "<em>어깨선이 내려오는</em><br>코튼 블루종",
             "quote_no": (100 + i) * 10}
            for i in range(5)],
        "cta": {"title": "재킷 하나만 잘 골라도<br><em>가을이 편해집니다</em>", "sub": "고민이 줄어듭니다"},
        "caption": "가을 재킷은 하나를 잘못 고르면 계절 내내 다른 옷을 사게 됩니다 🍂\n\n따뜻한 순서로 놓았습니다 🧵\n\n저장해 두고 친구에게도 보내 주세요 🔖",
    }


@pytest.fixture
def handles():
    return {"brands": [
        {"name": "제너럴아이디어", "aliases": [], "handle": "generalidea_official", "verified": True, "roster": True},
        {"name": "무드인사이드", "aliases": ["MOOD INSIDE"], "handle": "moodinside_official", "verified": True, "roster": False},
        {"name": "버던트", "aliases": [], "handle": "verdnt_official", "verified": True, "roster": False},
        {"name": "유라고", "aliases": [], "handle": "we_are_urago", "verified": True, "roster": False},
    ]}


def write_episode(folder: str, ep: dict, cands: dict) -> Path:
    d = config.episode_dir(folder)
    d.mkdir(parents=True, exist_ok=True)
    (d / "episode.json").write_text(json.dumps(ep, ensure_ascii=False), encoding="utf-8")
    (d / "candidates.json").write_text(json.dumps(cands, ensure_ascii=False), encoding="utf-8")
    return d
