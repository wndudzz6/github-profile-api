from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
from flasgger import Swagger
from flask_cors import CORS

from github_service import fetch_user_via_api, fetch_user_via_scrape
from cache_redis import cache_get, cache_put
import json  # 🔧 raw_json을 위해 필요

app = Flask(__name__)
CORS(app)
swagger = Swagger(app)

@app.route("/")
def index():
    return "GitHub Profile API Server Running"

@app.route("/api/profile", methods=["GET"])
def profile_api():
    """
    GitHub 프로필 조회 API
    ---
    parameters:
      - name: username
        in: query
        type: string
        required: true
        description: GitHub 사용자명
      - name: method
        in: query
        type: string
        required: false
        default: api
        enum: [api, scrape]
        description: 조회 방식
    responses:
      200:
        description: 유저 정보 반환 성공
    """
    username = (request.args.get("username") or "").strip()
    method = (request.args.get("method") or "api").lower()

    if not username:
        return jsonify({"error": "username query param required"}), 400

    print(f"🔍 요청 수신: username={username}, method={method}")
    params = {"username": username}
    url = f"https://api.github.com/users/{username}"

    if method == "scrape":
        print("🕸️ 스크래핑 방식 사용 중")
        data, err, rate_msg, details = fetch_user_via_scrape(username)
    else:
        cached_body, _ = cache_get(url, params)  # ✅ 순서 수정!
        if cached_body:
            print("📦 캐시 HIT → 응답 반환")
            return jsonify({
                "data": cached_body,
                "error": None,
                "details": {},
                "method": method,
                "rate_info": "from-cache",
                "raw_json": json.dumps(cached_body, ensure_ascii=False)  # ✅ 안정화
            })

        print("🧪 캐시 MISS → API 호출 시도")
        data, err, rate_msg, details = fetch_user_via_api(username)
        print(f"🔍 API 호출 결과: data={'✅ 있음' if data else '❌ 없음'}, err={err}")

        if data and not err:
            print("✅ 캐시 저장 시도")
            cache_put(url, params, data)

    # ⚠️ Swagger 파싱 오류 방지를 위한 타입 안정화
    safe_details = details if isinstance(details, dict) else {}
    safe_raw_json = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else None

    return jsonify({
        "data": data,
        "error": err,
        "details": safe_details,
        "method": method,
        "rate_info": rate_msg,
        "raw_json": safe_raw_json
    })

if __name__ == "__main__":
    app.run(debug=True)
