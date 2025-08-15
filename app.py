from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
from flasgger import Swagger
from flask_cors import CORS

from github_service import fetch_user_via_api, fetch_user_via_scrape
from endpoint_cache import get_profile_cache, set_profile_cache  # ✅ 추가

app = Flask(__name__)
CORS(app)

swagger_config = {
    "headers": [],
    "specs": [
        {"endpoint": "apispec_1", "route": "/apispec_1.json",
         "rule_filter": lambda rule: True, "model_filter": lambda tag: True}
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}
swagger = Swagger(app, config=swagger_config)

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
        enum: [api, scrape]
        default: api
        description: 조회 방식
    responses:
      200:
        description: 사용자 정보 반환
    """
    try:
        username = (request.args.get("username") or "").strip()
        if not username:
            return jsonify({"error": "username 파라미터가 없습니다."}), 400

        method = (request.args.get("method") or "api").strip().lower()
        if method not in ("api", "scrape"):
            method = "api"

        # ✅ 1) 캐시 조회
        cached = get_profile_cache(method, username)
        if cached:
            return jsonify(cached), 200

        # ✅ 2) 실조회
        if method == "scrape":
            view, err, rate_msg, raw = fetch_user_via_scrape(username)
        else:
            view, err, rate_msg, raw = fetch_user_via_api(username)

        # 상태코드
        status = 404 if (view is None and err and "찾을 수 없" in str(err)) else (200 if view else 502)

        # ✅ 3) 응답 조립 (언어 통계 없음)
        resp = {
            "data": view or {},
            "error": err,
            "method": method,
            "rate_limit": {"message": rate_msg} if rate_msg else {},
            "details": {"raw_json": raw if isinstance(raw, dict) else None},
        }

        # ✅ 4) 캐시 저장 (5분 기본)
        set_profile_cache(method, username, resp)

        return jsonify(resp), status

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
