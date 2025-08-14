# github_service.py
import os
import json
import time
import requests
from datetime import datetime as dt, timezone, timedelta
from functools import lru_cache
from bs4 import BeautifulSoup
from cache_redis import cache_get, cache_put

GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
API_TIMEOUT = 10
PER_PAGE = 100
MAX_LANG_REPOS = int(os.getenv("MAX_LANG_REPOS", "60"))

def _auth_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gh-profile-demo/1.3",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        print("🔐 인증 토큰 적용됨")
    else :
        print("🚨 GITHUB_TOKEN 없음 (인증 없이 호출 중)")
    return headers

def api_get(url, params=None, etag=None):
    headers = _auth_headers()
    if etag:
        headers["If-None-Match"] = etag
    r = requests.get(url, headers=headers, params=params, timeout=API_TIMEOUT)
    if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
        reset_time = r.headers.get("X-RateLimit-Reset")
        raise RuntimeError(f"Rate limit exceeded. Try again after {reset_time}")
    if r.status_code >= 400:
        raise RuntimeError(f"API error {r.status_code}")
    return r

def iso_to_kst_str(iso_str):
    try:
        d = dt.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(
            timezone(timedelta(hours=9))
        )
        return d.strftime("%Y-%m-%d %H:%M:%S KST")
    except Exception:
        return iso_str

@lru_cache(maxsize=256)
def fetch_language_stats(username: str):
    url = f"{GITHUB_API_BASE}/users/{username}/repos"
    total_by_lang = {}
    repo_count = 0
    processed = 0
    page = 1
    while page <= 20:
        qp = {"type": "owner", "sort": "updated", "per_page": PER_PAGE, "page": page}
        r = api_get(url, qp)
        items = r.json()
        if not items:
            break
        for repo in items:
            repo_count += 1
            if processed >= MAX_LANG_REPOS:
                break
            full_name = repo.get("full_name")
            if not full_name:
                continue
            lang_url = f"{GITHUB_API_BASE}/repos/{full_name}/languages"
            etag, cached = cache_get(lang_url, {})
            try:
                r = api_get(lang_url, etag=etag)
                if r.status_code == 304 and cached:
                    lang_map = cached
                else:
                    lang_map = r.json()
                    new_etag = r.headers.get("ETag")
                    if new_etag:
                        cache_put(lang_url, None, new_etag, lang_map)
            except Exception:
                lang_map = {}
            for lang, bytes_ in lang_map.items():
                total_by_lang[lang] = total_by_lang.get(lang, 0) + int(bytes_)
            processed += 1
            time.sleep(0.03)
        if processed >= MAX_LANG_REPOS:
            break
        page += 1
    total_bytes = sum(total_by_lang.values()) or 0
    by_lang = [
        {"lang": lang, "bytes": b, "pct": round((b / total_bytes) * 100, 2) if total_bytes else 0}
        for lang, b in total_by_lang.items()
    ]
    by_lang.sort(key=lambda x: x["bytes"], reverse=True)
    return {
        "total_bytes": total_bytes,
        "by_lang": by_lang,
        "repo_count": repo_count,
        "scanned_repos": processed,
        "generated_at": dt.now(tz=timezone.utc).astimezone(
            timezone(timedelta(hours=9))
        ).strftime("%Y-%m-%d %H:%M:%S KST"),
        "note": (None if processed == repo_count else f"최대 {MAX_LANG_REPOS}개 레포만 스캔"),
    }

def fetch_user_via_api(username: str):
    url = f"{GITHUB_API_BASE}/users/{username}"
    try:
        r = api_get(url)
    except RuntimeError as e:
        print("❌ RuntimeError:", str(e))
        return None, str(e), None, None

    # ✅ 응답 상태 및 헤더 확인
    print("📡 응답 상태코드:", r.status_code)
    print("📦 Content-Type:", r.headers.get("Content-Type"))
    print("📄 응답 본문 (앞부분):\n", r.text[:300])

    try:
        data = r.json()
    except Exception as e:
        print("❌ JSON 디코딩 실패!", str(e))
        return None, "JSON 파싱 실패", None, r.text

    view = {
        "login": data.get("login"),
        "name": data.get("name"),
        "avatar_url": data.get("avatar_url"),
        "html_url": data.get("html_url"),
        "blog": data.get("blog"),
        "bio": data.get("bio"),
        "location": data.get("location"),
        "email": data.get("email"),
        "twitter_username": data.get("twitter_username"),
        "public_repos": data.get("public_repos"),
        "followers": data.get("followers"),
        "following": data.get("following"),
        "created_at": data.get("created_at"),
        "created_at_fmt": iso_to_kst_str(data.get("created_at")),
    }

    try:
        view["language_stats"] = fetch_language_stats(username)
    except RuntimeError as e:
        view["language_stats_error"] = str(e)
        view["language_stats"] = None

    rate_limit = r.headers.get("X-RateLimit-Limit")
    rate_remaining = r.headers.get("X-RateLimit-Remaining")
    rate_msg = f"Rate {rate_remaining}/{rate_limit}" if rate_limit and rate_remaining else None

    return view, None, rate_msg, data

def fetch_user_via_scrape(username: str):
    url = f"https://github.com/{username}"
    headers = {
        "User-Agent": "gh-profile-demo/1.3",
        "Accept-Language": "ko,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=API_TIMEOUT)
    except requests.exceptions.RequestException as e:
        return None, f"네트워크 오류: {e}", None, None
    if r.status_code == 404:
        return None, "사용자를 찾을 수 없습니다.", None, r.text
    if r.status_code >= 400:
        return None, f"요청 실패: 상태 코드 {r.status_code}", None, r.text
    return None, "스크래핑은 아직 미완성입니다.", None, r.text  # 필요 시 정제
