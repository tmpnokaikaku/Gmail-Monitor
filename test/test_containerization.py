import os
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))


class AppConfigRuntimeTests(unittest.TestCase):
    def test_build_app_config_from_env_preserves_defaults(self):
        from app import build_app_config_from_env

        with patch.dict(os.environ, {}, clear=True):
            cfg = build_app_config_from_env()

        self.assertEqual(cfg.creds_path, "credentials.json")
        self.assertEqual(cfg.token_path, "token.json")
        self.assertEqual(cfg.filter_path, "filters.json")
        self.assertEqual(cfg.flask_port, 8080)
        self.assertEqual(cfg.number_to_fetch, 10)

    def test_build_app_config_from_env_applies_container_overrides(self):
        from app import build_app_config_from_env

        env = {
            "GMM_CREDS_PATH": "/runtime/credentials.json",
            "GMM_TOKEN_PATH": "/runtime/token.json",
            "GMM_FILTER_PATH": "/runtime/filters.json",
            "GMM_FLASK_PORT": "9090",
            "GMM_NUMBER_TO_FETCH": "3",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = build_app_config_from_env()

        self.assertEqual(cfg.creds_path, "/runtime/credentials.json")
        self.assertEqual(cfg.token_path, "/runtime/token.json")
        self.assertEqual(cfg.filter_path, "/runtime/filters.json")
        self.assertEqual(cfg.flask_port, 9090)
        self.assertEqual(cfg.number_to_fetch, 3)

    def test_build_app_config_from_env_rejects_invalid_integer(self):
        from app import build_app_config_from_env

        with patch.dict(os.environ, {"GMM_FLASK_PORT": "not-a-port"}, clear=True):
            with self.assertRaisesRegex(ValueError, "GMM_FLASK_PORT"):
                build_app_config_from_env()


class GMMServerRuntimeTests(unittest.TestCase):
    def test_flask_host_defaults_to_loopback(self):
        from gmm_server import GMMServer

        with patch.dict(os.environ, {}, clear=True):
            server = GMMServer()

        self.assertEqual(server.host, "127.0.0.1")

    def test_flask_host_can_be_overridden_for_container(self):
        from gmm_server import GMMServer

        with patch.dict(os.environ, {"GMM_FLASK_HOST": "0.0.0.0"}, clear=True):
            server = GMMServer()

        self.assertEqual(server.host, "0.0.0.0")


class ContainerCheckTests(unittest.TestCase):
    def test_preflight_reports_missing_runtime_files(self):
        from scripts.container_check import run_checks

        missing = ROOT / "missing-container-check"
        env = {
            "GMM_CREDS_PATH": str(missing / "credentials.json"),
            "GMM_TOKEN_PATH": str(missing / "token.json"),
            "GMM_FILTER_PATH": str(missing / "filters.json"),
        }
        result = run_checks(env=env, check_routes=False)

        self.assertFalse(result.ok)
        self.assertIn("GMM_CREDS_PATH", "\n".join(result.errors))
        self.assertIn("GMM_TOKEN_PATH", "\n".join(result.errors))
        self.assertIn("GMM_FILTER_PATH", "\n".join(result.errors))

    def test_preflight_and_route_check_succeed_without_external_api_calls(self):
        from extract_gmail_content import ExtractGmailContent
        from scripts import container_check

        def fake_extract_init(self, *args, **kwargs):
            self.fields = {}
            self.groups = {}

        env = {
            "GMM_CREDS_PATH": "credentials.json",
            "GMM_TOKEN_PATH": "token.json",
            "GMM_FILTER_PATH": "filters.json",
            "LINE_CHANNEL_ACCESS_TOKEN": "dummy",
            "LINE_CHANNEL_SECRET": "dummy",
            "MY_LINE_UID": "dummy",
        }
        with patch.object(container_check, "_check_readable_file", lambda *args, **kwargs: None), \
             patch.object(container_check, "_check_writable_file", lambda *args, **kwargs: None), \
             patch.object(container_check, "_check_log_path", lambda *args, **kwargs: None), \
             patch.object(ExtractGmailContent, "__init__", fake_extract_init):
            result = container_check.run_checks(env=env, check_routes=True)

        self.assertTrue(result.ok, result.errors)
        self.assertIn("/health", result.details["routes"])
        self.assertIn("/oauth/callback", result.details["routes"])
        self.assertIn("/callback", result.details["routes"])


if __name__ == "__main__":
    unittest.main()
