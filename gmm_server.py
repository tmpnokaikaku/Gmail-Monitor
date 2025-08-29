from flask import Flask
import threading
import sys
import os
import logging
from logging.handlers import RotatingFileHandler


class GMMServer():
    def __init__(self, flask_port: int = 8080, env_key_for_domain: str = "SERVER_DOMAIN"):
        # Flask app
        self.app = Flask(__name__)
        self.port = flask_port
        self.webhook_domain = os.getenv(env_key_for_domain)
        self.public_url = None
        self.server_running = False

        # 共通ロガー初期化
        self._init_logger()
        self.app.logger.info(f"ロガーは{self.log_cfg[0]}階層,ファイル出力モードは{self.log_cfg[1]}に設定されています")


    def _init_logger(self):
        self.logger = logging.getLogger("gmm")
        if not self.logger.handlers:
            level = os.getenv("GMM_LOG_LEVEL", "INFO").upper()
            self.logger.setLevel(level)
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

            # コンソール出力
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            self.logger.addHandler(sh)

            # ファイル出力
            log_file = os.getenv("GMM_LOG_FILE")
            if log_file:
                try:
                    os.makedirs(os.path.dirname(log_file), exist_ok=True)
                except Exception:
                    pass
                from logging.handlers import RotatingFileHandler
                mode = "w" if os.getenv("GMM_LOG_MODE", "append").lower() in ("overwrite", "w", "truncate") else "a"
                fh = RotatingFileHandler(log_file, mode=mode, maxBytes=1_000_000, backupCount=3)
                fh.setFormatter(fmt)
                self.logger.addHandler(fh)

        self.log_cfg = (level, log_file)

        # Flask / Werkzeug ロガーにも同ハンドラを付与
        for name in ("flask.app", "werkzeug"):
            flog = logging.getLogger(name)
            flog.handlers = []
            flog.setLevel(self.logger.level)
            flog.propagate = False
            for h in self.logger.handlers:
                flog.addHandler(h)

        # app.logger も同一化
        self.app.logger.handlers = []
        self.app.logger.setLevel(self.logger.level)
        self.app.logger.propagate = False
        for h in self.logger.handlers:
            self.app.logger.addHandler(h)



    # flaskサーバーを外部に公開
    # flaskサーバーを外部に公開
    def run_and_expose_server(self):
        # ヘルスチェック
        if not hasattr(self, "_health_added"):
            self.app.add_url_rule("/health", "health", lambda: ("ok", 200), methods=["GET", "HEAD"])
            self.app.add_url_rule("/", "root", lambda: ("ok", 200), methods=["GET", "HEAD"])
            self._health_added = True

        def run_flask():
            self.logger.info(f"Starting Flask on 127.0.0.1:{self.port}")
            self.app.run(host="127.0.0.1", port=self.port, threaded=True)

        self.flask_thread = threading.Thread(target=run_flask, daemon=True)
        self.flask_thread.start()
        self.server_running = True
        if self.webhook_domain:
            self.public_url = f"https://{self.webhook_domain}"
            self.logger.info(f"Public URL set to {self.public_url}")
        else:
            self.logger.warning("SERVER_DOMAIN is not set; public URL unavailable")


    # サーバー終了
    def stop_server(self):
        self.logger.info("Stopping server (process exit)")
        if self.public_url:
            sys.exit()
            self.server_running = False
        else:
            pass
