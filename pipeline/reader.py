"""선택 상품 보강: Firestore 공개 REST 로 후기 로드 + 썸네일 다운로드."""
from __future__ import annotations

import os

import requests

PROJECT = "fashion-cardnews"
KEY = "AIzaSyBZIp-NLD8rw6asKSAwIOH-4I4hg9ecALo"  # 공개 웹 API 키 (규칙으로 보호)
BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fv(v):
    if not isinstance(v, dict):
        return None
    if "stringValue" in v: return v["stringValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue" in v: return v["doubleValue"]
    if "booleanValue" in v: return v["booleanValue"]
    if "nullValue" in v: return None
    if "mapValue" in v:
        return {k: fv(x) for k, x in (v["mapValue"].get("fields") or {}).items()}
    if "arrayValue" in v:
        return [fv(x) for x in (v["arrayValue"].get("values") or [])]
    return None


def _fetch_reviews(mall: str, pid: str) -> list[dict]:
    url = f"{BASE}/products/{mall}_{pid}?key={KEY}&mask.fieldPaths=reviews"
    try:
        r = requests.get(url, timeout=30, headers=UA)
        if not r.ok:
            return []
        fields = r.json().get("fields") or {}
        reviews = fv(fields.get("reviews", {"arrayValue": {}})) or []
        return [rv for rv in reviews if isinstance(rv, dict) and rv.get("text")]
    except (requests.exceptions.RequestException, ValueError):
        return []


def _download_image(url: str | None, dest: str) -> str | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=60, headers=UA)
        if not r.ok or len(r.content) < 1000:
            return None
        with open(dest, "wb") as f:
            f.write(r.content)
        return os.path.abspath(dest)
    except requests.exceptions.RequestException:
        return None


def load_products(items: list[dict], assets_dir: str) -> list[dict]:
    os.makedirs(assets_dir, exist_ok=True)
    out = []
    for it in items:
        pid, mall = str(it["product_id"]), it["mall"]
        reviews = _fetch_reviews(mall, pid)
        image_path = _download_image(
            it.get("thumbnail"), os.path.join(assets_dir, f"{mall}_{pid}.jpg"))
        out.append({**it, "reviews": reviews, "image_path": image_path})
    return out
