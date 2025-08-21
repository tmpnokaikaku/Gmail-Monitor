# app.py  — テスト用シンプル Flask アプリ
# 目的:
# - Nginx 逆プロキシ/HTTPS/ヘッダ(X-Forwarded-Proto等)の確認
# - 内部(:8080)疎通、LINE Webhook風POST、OAuth風リダイレクトの動作確認

from flask import Flask, request, jsonify, redirect
import datetime as dt
import sys, logging

app = Flask(__name__)

# ログをstdoutへ（systemd/journalに出る）
logging.basicConfig(stream=sys.stdout,
                    level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

def _proto():
    # 逆プロキシ下で https を正しく認識しているか確認
    return request.headers.get("X-Forwarded-Proto", request.scheme)

def _host():
    return request.headers.get("Host", "localhost")

def _client_ip():
    xff = request.headers.get("X-Forwarded-For")
    return (xff.split(",")[0].strip() if xff else request.remote_addr)

@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "service": "GMM test app",
        "ok": True,
        "server_time_utc": dt.datetime.utcnow().isoformat() + "Z",
        "host": _host(),
        "scheme": _proto(),
        "client_ip_seen": _client_ip(),
        "path": request.path
    })

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

@app.route("/readyz", methods=["GET"])
def readyz():
    return jsonify({"ready": True}), 200

@app.route("/echo", methods=["GET", "POST"])
def echo():
    # ヘッダ/クエリ/JSON/フォームの受け取り確認
    try_json = None
    try:
        try_json = request.get_json(silent=True)
    except Exception:
        try_json = None
    return jsonify({
        "method": request.method,
        "headers": {k: v for k, v in request.headers.items()},
        "args": request.args,
        "form": request.form,
        "json": try_json
    }), 200

@app.route("/callback", methods=["POST", "GET"])
def callback():
    # LINE Webhook風の受信確認（署名ヘッダが来ていれば表示）
    sig = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    logging.info(f"/callback received method={request.method} sig={sig} body_len={len(body)}")
    return jsonify({
        "received": True,
        "method": request.method,
        "x_line_signature": sig,
        "body_len": len(body)
    }), 200

@app.route("/oauth/start", methods=["GET"])
def oauth_start():
    # 本番想定の https://{host}/oauth/callback へリダイレクト（疑似）
    url = f"{_proto()}://{_host()}/oauth/callback?code=TEST_CODE&state=xyz"
    logging.info(f"redirecting to {url}")
    return redirect(url, code=302)

@app.route("/oauth/callback", methods=["GET"])
def oauth_callback():
    return jsonify({
        "callback": True,
        "args": request.args,
        "scheme_seen": _proto(),
        "host_seen": _host()
    }), 200

if __name__ == "__main__":
    # 手動起動用（Gunicornを使う場合は不要）
    app.run(host="127.0.0.1", port=8080)
