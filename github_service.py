# github_service.py
import os
import json
import time
import requests
from datetime import datetime as dt, timezone, timedelta
from functools import lru_cache
from bs4 import BeautifulSoup  # 현재 미사용이지만 향후 스크래핑용으로 유지
from cache_redis import cache_get, cache_put

# ===== 기본 설정 =====
GITHUB_API_BASE = os.getenv("GITHUB_API_BASE", "https://api.github.com")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "10"))
PER_PAGE = int(os.getenv("PER_PAGE", "100"))
MAX_LANG_REPOS = int(os.getenv("MAX_LANG_REPOS", "60"))
LANG_SLEEP = float(os.getenv("LANG_SLEEP", "0.03"))  # 언어 API 호출 간 간격

# ===== 공통 유틸 =====
def _auth_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gh-profile-demo/1.3",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        print("🔐 인증 토큰 적용됨")
    else:
        print("🚨 GITHUB_TOKEN 없음 (인증 없이 호출 중)")
    return headers

def _ensure_valid_url(url):
    # 실수로 None/빈문자/타입충돌이 생기면 즉시 원인 노출
    if not isinstance(url, str):
        raise TypeError(f"URL must be str, got {type(url).__name__}: {url!r}")
    if not url:
        raise ValueError("URL is empty string")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"URL must start with http:// or https://, got: {url}")

def api_get(url, params=None, etag=None):
    _ensure_valid_url(url)
    headers = _auth_headers()
    if etag:
        headers["If-None-Match"] = etag
    try:
        r = requests.get(url, headers=headers, params=params, timeout=API_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error while GET {url}: {e}")

    # 레이트리밋 초과
    if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
        reset_time = r.headers.get("X-RateLimit-Reset")
        raise RuntimeError(f"Rate limit exceeded. Try again after {reset_time} (epoch seconds).")

    # 기타 에러는 응답 본문 메시지도 함께 보여주자
    if r.status_code >= 400:
        try:
            body = r.json()
            msg = body.get("message") if isinstance(body, dict) else None
        except Exception:
            msg = r.text[:200]
        raise RuntimeError(f"API error {r.status_code} for {url} — {msg}")

    return r

def iso_to_kst_str(iso_str):
    if not iso_str:
        return None
    try:
        d = dt.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(
            timezone(timedelta(hours=9))
        )
        return d.strftime("%Y-%m-%d %H:%M:%S KST")
    except Exception:
        return iso_str

# ===== 언어 통계 =====
@lru_cache(maxsize=256)
def fetch_language_stats(username: str):
    if not username:
        return {
            "total_bytes": 0,
            "by_lang": [],
            "repo_count": 0,
            "scanned_repos": 0,
            "generated_at": dt.now(tz=timezone.utc).astimezone(
                timezone(timedelta(hours=9))
            ).strftime("%Y-%m-%d %H:%M:%S KST"),
            "note": "username is empty",
        }

    url = f"{GITHUB_API_BASE}/users/{username}/repos"
    total_by_lang = {}
    repo_count = 0
    processed = 0
    page = 1

    while page <= 20:
        qp = {"type": "owner", "sort": "updated", "per_page": PER_PAGE, "page": page}
        try:
            r = api_get(url, qp)
            items = r.json()
        except RuntimeError as e:
            print(f"❌ 레포 목록 조회 실패(page={page}): {e}")
            break
        except Exception as e:
            print(f"❌ 레포 목록 JSON 파싱 실패(page={page}): {e}")
            break

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
                r2 = api_get(lang_url, etag=etag)
                if r2.status_code == 304 and cached:
                    lang_map = cached
                else:
                    lang_map = r2.json()
                    new_etag = r2.headers.get("ETag")
                    if new_etag:
                        cache_put(lang_url, None, new_etag, lang_map)
            except RuntimeError as e:
                print(f"⚠️ 언어 통계 조회 실패({full_name}): {e}")
                lang_map = {}
            except Exception as e:
                print(f"⚠️ 언어 통계 JSON 파싱 실패({full_name}): {e}")
                lang_map = {}

            for lang, bytes_ in (lang_map or {}).items():
                try:
                    total_by_lang[lang] = total_by_lang.get(lang, 0) + int(bytes_)
                except Exception:
                    pass

            processed += 1
            if LANG_SLEEP > 0:
                time.sleep(LANG_SLEEP)

        if processed >= MAX_LANG_REPOS:
            break
        page += 1

    total_bytes = sum(total_by_lang.values()) or 0
    by_lang = [
        {
            "lang": lang,
            "bytes": b,
            "pct": round((b / total_bytes) * 100, 2) if total_bytes else 0.0,
        }
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

# ===== 사용자 조회 (API) =====
def fetch_user_via_api(username: str):
    if not username or not isinstance(username, str):
        return None, "username is required", None, None

    url = f"{GITHUB_API_BASE}/users/{username}"
    try:
        r = api_get(url)
    except RuntimeError as e:
        print("❌ RuntimeError:", str(e))
        return None, str(e), None, None

    # ✅ 응답 상태 및 헤더 확인 (디버깅용)
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
    except Exception as e:
        view["language_stats_error"] = f"lang stats unexpected error: {e}"
        view["language_stats"] = None

    rate_limit = {
        "limit": r.headers.get("X-RateLimit-Limit"),
        "remaining": r.headers.get("X-RateLimit-Remaining"),
        "reset": r.headers.get("X-RateLimit-Reset"),
    }
    rate_msg = (
        f"Rate {rate_limit['remaining']}/{rate_limit['limit']}"
        if rate_limit["limit"] and rate_limit["remaining"]
        else None
    )

    return view, None, rate_msg, data

# ===== 사용자 조회 (스크래핑 – 임시) =====
def fetch_user_via_scrape(username: str):
    if not username or not isinstance(username, str):
        return None, "username is required", None, None

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

    # TODO: BeautifulSoup으로 필요한 정보 파싱
    return None, "스크래핑은 아직 미완성입니다.", None, r.text
