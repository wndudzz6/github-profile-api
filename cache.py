# cache.py
import json
import hashlib
from pathlib import Path

# 캐시 디렉토리 (기본: .ghcache/)
CACHE_DIR = Path(".ghcache")
CACHE_DIR.mkdir(exist_ok=True)

def _cache_key(url: str, params: dict = None) -> str:
    """URL과 파라미터를 조합해 고유한 캐시 키 생성 (SHA256)"""
    raw = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def cache_get(url: str, params: dict = None):
    """ETag와 본문을 캐시에서 불러오기"""
    key = _cache_key(url, params)
    meta_file = CACHE_DIR / f"{key}.meta.json"
    body_file = CACHE_DIR / f"{key}.json"

    if not (meta_file.exists() and body_file.exists()):
        return None, None

    try:
        etag = json.loads(meta_file.read_text(encoding="utf-8")).get("etag")
        body = json.loads(body_file.read_text(encoding="utf-8"))
        return etag, body
    except Exception:
        return None, None

def cache_put(url: str, params: dict, etag: str, body: dict):
    """ETag와 본문을 캐시로 저장하기"""
    key = _cache_key(url, params)
    (CACHE_DIR / f"{key}.meta.json").write_text(json.dumps({"etag": etag}, ensure_ascii=False), encoding="utf-8")
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
