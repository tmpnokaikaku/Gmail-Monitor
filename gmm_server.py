from __future__ import annotations

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from logging.handlers import RotatingFileHandler
import threading
import sys
import os
import logging


class GMMServer():
    def __init__(
            self,
            flask_port: int = 8080,
            env_key_for_domain: str = "SERVER_DOMAIN",
            flask_host: str | None = None
        ):
        # Flask app
        self.app = Flask(__name__)
        """
        リバースプロキシ越しの元情報を解釈する
        NginxからFlaskに中継するとき、http接続と認識されるのを防ぐ
            x_for=1: X-Forwarded-For
            x_proto=1: X-Forwarded-Proto (https 判定に必須)
            x_host=1, x_port=1, x_prefix=1 は念のため
        """
        self.app.wsgi_app = ProxyFix(self.app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
        self.port = flask_port
        self.host = flask_host or os.getenv("GMM_FLASK_HOST", "127.0.0.1")
        self.webhook_domain = os.getenv(env_key_for_domain)
        self.public_url = None
        self.server_running = False

        # 共通ロガー初期化
        self._init_logger()
        self._ensure_health_routes()

    def _ensure_health_routes(self):
        if not hasattr(self, "_health_added"):
            self.app.add_url_rule("/health", "health", lambda: ("ok", 200), methods=["GET", "HEAD"])
            self.app.add_url_rule("/", "root", lambda: ("ok", 200), methods=["GET", "HEAD"])
            self._health_added = True

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

                # 明示的にゼロクリア
                log_mode_env = os.getenv("GMM_LOG_MODE", "append").lower()
                if log_mode_env in ("overwrite", "w", "truncate", "reset"):
                    try:
                        fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
                        os.close(fd)
                    except Exception as e:
                        # ゼロクリア失敗時も続行（次で open して書ける可能性はある）
                        pass

                # ハンドラ自体は常に append で作成（ダブル truncate を避ける）
                from logging.handlers import RotatingFileHandler
                fh = RotatingFileHandler(log_file, mode="a", maxBytes=1_000_000, backupCount=3, delay=False)
                fh.setFormatter(fmt)
                self.logger.addHandler(fh)

                # 起動時に有効設定を見える化
                self.logger.info(f"Log config: file={log_file}, init={'truncate' if log_mode_env in ('overwrite','w','truncate','reset') else 'append'}, "
                                f"rotate=maxBytes=1MB backupCount=3")

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
    def run_and_expose_server(self):
        # ヘルスチェック
        self._ensure_health_routes()

        def run_flask():
            self.logger.info(f"Starting Flask on {self.host}:{self.port}")
            self.app.run(host=self.host, port=self.port, threaded=True)

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
