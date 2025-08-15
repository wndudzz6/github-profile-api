# cache_redis.py
from upstash_redis import Redis
import os
import json
r = Redis(
    url=os.getenv("UPSTASH_URL"),
    token=os.getenv("UPSTASH_TOKEN")
)
def redis_cache_key(url: str, params: dict) -> str:
    if url is None:
        print("❌ [버그] 캐시 키 생성 시 url이 None입니다!")
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
        # 👇 디버깅: value가 dict가 아닐 경우 프린트하고 저장 중단
        if not isinstance(value, dict):
            print(f"❌ [캐시 실패] 저장하려는 값이 dict가 아님: {type(value)}")
            print(f"내용 일부: {str(value)[:200]}")
            return
        
        # 정상 저장
        r.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
        print(f"✅ Redis STORED: {key}")
    except Exception as e:
        print(f"❌ Redis 저장 실패: {e}")
