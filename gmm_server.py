from flask import Flask, request, redirect
from pyngrok import ngrok

import threading
import os

class GMMServer():
    def __init__(self, flask_port:int=8080, env_key_for_domain:str="NGROK_STATIC_DOMAIN"):
        self.app = Flask(__name__)
        self.port = flask_port
        self.webhook_domain = os.getenv(env_key_for_domain)
        self.public_url = None
        self.server_open = False

    # flaskサーバーを外部に公開
    def run_and_expose_server(self):
        # ローカルFlaskサーバー
        def run_flask():
            # ブロッキング処理
            self.app.run(host="0.0.0.0", port=self.port)

        # flask開始
        self.flask_thread = threading.Thread(target=run_flask, daemon=True)
        self.flask_thread.start()
        # ngrokトンネル開始
        self.public_url = ngrok.connect(self.port, bind_tls=True, domain=self.webhook_domain)

        # フラグ
        self.server_open = True

    # サーバー終了
    def close_ngrok_tunnel(self):
        if self.public_url:
            ngrok.disconnect(self.public_url)
            ngrok.kill()
            self.server_open = False
        else:
            pass
