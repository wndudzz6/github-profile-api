# cache_redis.py
import redis
import os
import json

r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

def redis_cache_key(url: str, params: dict) -> str:
    return f"{url}?{json.dumps(params, sort_keys=True)}"

def cache_get(url: str, params: dict):
    key = redis_cache_key(url, params)
    value = r.get(key)
    if value:
        print(f"📦 Redis HIT: {key}")
        try:
            return json.loads(value), key
        except json.JSONDecodeError:
            print("❌ 캐시된 데이터 디코딩 실패")
            return None, key
    else:
        print(f"🧪 Redis MISS: {key}")
        return None, key

def cache_put(url: str, params: dict, value: dict, ttl=60 * 60):
    key = redis_cache_key(url, params)
    try:
        r.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
        print(f"✅ Redis STORED: {key}")
    except Exception as e:
        print(f"❌ Redis 저장 실패: {e}")
