# endpoint_cache.py
import os, json, time
try:
    import redis
except ImportError:
    redis = None

REDIS_URL = os.getenv("REDIS_URL")  
_r = redis.from_url(REDIS_URL) if (redis and REDIS_URL) else None

# ✅ Redis가 없으면 메모리 캐시로 자동 폴백
_mem = {}
DEFAULT_TTL = int(os.getenv("PROFILE_CACHE_TTL", "300"))  # 초 단위 (기본 5분)

def _key(method: str, username: str) -> str:
    return f"profile::{method}::{username.lower()}"

def get_profile_cache(method: str, username: str):
    key = _key(method, username)
    if _r:
        raw = _r.get(key)
        try:
            return json.loads(raw) if raw else None
        except Exception as e:
            print(f"❌ [캐시 로드 오류] JSON 디코딩 실패: {e}")
            return None
    # 메모리 캐시
    item = _mem.get(key)
    if not item:
        return None
    expires, payload = item
    if time.time() > expires:
        _mem.pop(key, None)
        return None
    return payload

def set_profile_cache(method: str, username: str, data: dict, ttl: int = DEFAULT_TTL):
    key = _key(method, username)
    if not isinstance(data, dict):
        print(f"❌ [캐시 실패] 저장하려는 값이 dict가 아님: {type(data)}")
        print("내용 일부:", str(data)[:100])
        return

    try:
        json_str = json.dumps(data, ensure_ascii=False)
        if _r:
            _r.setex(key, ttl, json_str)
            return
    except Exception as e:
        print(f"❌ [캐시 실패] JSON 직렬화 오류: {e}")
        return

    # 메모리 캐시
    _mem[key] = (time.time() + ttl, data)
