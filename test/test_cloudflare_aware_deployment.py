from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CloudflareAwareDeploymentArtifactTests(unittest.TestCase):
    def test_deploy_helper_exposes_required_actions_without_secrets(self):
        script = (ROOT / "ops" / "oci" / "deploy-image.sh").read_text(encoding="utf-8")

        for action in ("status", "pull", "check", "activate", "rollback"):
            self.assertIn(action, script)

        self.assertIn("ACTIVE_IMAGE", script)
        self.assertIn("PREVIOUS_IMAGE", script)
        self.assertIn("LAST_CHECK_STATUS", script)
        self.assertNotRegex(script, re.compile(r"(token|password|secret)\s*=", re.IGNORECASE))

    def test_publish_workflow_records_tag_and_digest(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-image.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("docker/build-push-action", workflow)
        self.assertIn("digest", workflow)
        self.assertIn("github_step_summary", workflow.lower())

    def test_build_context_excludes_operational_artifacts(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        for pattern in (".github/", "ops/", ".env", "credentials.json", "token.json", "log/"):
            self.assertIn(pattern, dockerignore)

    def test_runbook_separates_web_and_management_paths(self):
        runbook = (ROOT / "docs" / "cloudflare-aware-deployment.md").read_text(encoding="utf-8")

        self.assertIn("Cloudflare proxied", runbook)
        self.assertIn("DNS-only", runbook)
        self.assertIn("Cloudflare Tunnel", runbook)
        self.assertIn("rollback", runbook.lower())
        self.assertNotIn("lsappgmm.dpdns.org", runbook)


if __name__ == "__main__":
    unittest.main()
