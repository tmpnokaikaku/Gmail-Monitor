from flask import Flask

import threading
import sys
import os

class GMMServer():
    def __init__(self, flask_port:int=8080, env_key_for_domain:str="SERVER_DOMAIN"):
        self.app = Flask(__name__)
        self.port = flask_port
        self.webhook_domain = os.getenv(env_key_for_domain)
        self.public_url = None
        self.server_running = False

    # flaskサーバーを外部に公開
    def run_and_expose_server(self):
        # ヘルスチェック（任意）
        if not hasattr(self, "_health_added"):
            self.app.add_url_rule("/health", "health", lambda: "ok", methods=["GET"])
            self._health_added = True

        def run_flask():
            # 127.0.0.1 で待受けさせ、Nginx からプロキシ
            self.app.run(host="127.0.0.1", port=self.port, threaded=True)

        self.flask_thread = threading.Thread(target=run_flask, daemon=True)
        self.flask_thread.start()
        self.server_running = True
        if self.webhook_domain:
            self.public_url = f"https://{self.webhook_domain}"

    # サーバー終了
    def stop_server(self):
        if self.public_url:
            sys.exit()
            self.server_running = False
        else:
            pass
