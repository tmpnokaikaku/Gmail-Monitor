from flask import Flask

import threading
import sys
import os

class GMMServer():
    def __init__(self, flask_port:int=8080, env_key_for_domain:str="NGROK_STATIC_DOMAIN"):
        self.app = Flask(__name__)
        self.port = flask_port
        self.webhook_domain = os.getenv(env_key_for_domain)
        self.public_url = None
        self.server_running = False

    # flaskサーバーを外部に公開
    def run_and_expose_server(self):
        # ローカルFlaskサーバー
        def run_flask():
            # ブロッキング処理
            self.app.run(host="0.0.0.0", port=self.port)

        # flask開始
        self.flask_thread = threading.Thread(target=run_flask, daemon=True)
        self.flask_thread.start()

        # フラグ
        self.server_running = True

    # サーバー終了
    def stop_server(self):
        if self.public_url:
            sys.exit()
            self.server_running = False
        else:
            pass
