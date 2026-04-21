#!/usr/bin/env python3
"""
Deployment Agent - Deploys to cloud infrastructure.
Mapped to: deploy command → cloud_mcp

Pipeline position: runs after iac (Terraform generated) and ci (image built).

What it does:
  1. Locates Terraform configs (from IACAgent's output in infrastructure/terraform/)
  2. Runs terraform init → plan → apply  (apply only if dry_run=False)
  3. Optionally builds and pushes Docker image
  4. Optionally syncs ArgoCD application
"""
import subprocess
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from .base_agent import BaseAgent


# Minimal fallback Terraform when IACAgent hasn't run yet
_FALLBACK_TF_MAIN = '''\
# Minimal ForgeFlow deployment config (fallback — run `forgeflow iac` for full setup)
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.region
}}

resource "aws_ecr_repository" "app" {{
  name                 = var.app_name
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {{
    scan_on_push = true
  }}
  tags = {{
    ManagedBy = "ForgeFlow"
    Environment = var.environment
  }}
}}

resource "aws_ecs_cluster" "main" {{
  name = "${{var.app_name}}-${{var.environment}}"
  setting {{
    name  = "containerInsights"
    value = "enabled"
  }}
}}
'''

_FALLBACK_TF_VARS = '''\
variable "app_name" {{
  description = "Application name"
  type        = string
  default     = "{app_name}"
}}

variable "environment" {{
  description = "Deployment environment (dev, staging, production)"
  type        = string
  default     = "{environment}"
}}

variable "region" {{
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}}
'''


class DeploymentAgent(BaseAgent):
    """Agent that actually deploys to cloud infrastructure via Terraform, Docker, and ArgoCD."""

    intelligence_phase = 2
    intelligence_label = "Automated"

    def __init__(self):
        super().__init__(
            name="deployment_agent",
            description="Deploys to cloud: terraform init/plan/apply, docker build/push, argocd sync"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run deployment pipeline.

        Params:
            path         : repo path
            target       : deployment environment — dev | staging | production  (default: staging)
            dry_run      : True = plan only, no apply  (default: True — SAFETY)
            docker_build : also build and push Docker image  (default: False)
            argocd_sync  : trigger ArgoCD sync after apply  (default: False)
            image_tag    : Docker image tag  (default: git SHA or 'latest')
            registry     : container registry  (default: ghcr.io/org)
            tf_path      : override path to terraform directory
        """
        repo_path   = Path(params.get('path', '.'))
        target      = params.get('target', 'staging')
        dry_run     = params.get('dry_run', True)
        docker_build = params.get('docker_build', False)
        argocd_sync  = params.get('argocd_sync', False)
        image_tag   = params.get('image_tag') or self._git_sha(repo_path) or 'latest'
        registry    = params.get('registry', 'ghcr.io/org')
        tf_path_override = params.get('tf_path')

        self.log(f"Deploying to '{target}' (dry_run={dry_run})...")

        actions = []
        findings = []
        app_name = repo_path.name.lower().replace('_', '-').replace(' ', '-')

        # ── 1. Locate or generate Terraform ───────────────────────────────────
        tf_dir = self._find_terraform_dir(repo_path, tf_path_override)
        if tf_dir is None:
            tf_dir = self._generate_fallback_terraform(repo_path, app_name, target)
            actions.append({'step': 'terraform_scaffold', 'status': 'generated',
                            'note': 'Fallback Terraform generated — run iac for full setup'})
            findings.append("⚠️  Using fallback Terraform — run `forgeflow iac` for full infrastructure")
        else:
            actions.append({'step': 'terraform_located', 'status': 'found', 'path': str(tf_dir)})
            findings.append(f"✅ Terraform found at {tf_dir.relative_to(repo_path)}")

        # ── 2. Check terraform CLI ────────────────────────────────────────────
        if not shutil.which('terraform'):
            findings.append("❌ terraform CLI not found — install from https://developer.hashicorp.com/terraform/install")
            return self.create_result(
                status='error',
                summary='terraform CLI not found',
                data={'actions': actions},
                findings=findings
            )

        # ── 3. terraform init ─────────────────────────────────────────────────
        ok, out = self._run(tf_dir, ['terraform', 'init', '-input=false'])
        step = {'step': 'terraform_init', 'status': 'ok' if ok else 'failed', 'output': out[:500]}
        actions.append(step)
        if not ok:
            findings.append(f"❌ terraform init failed:\n{out[:300]}")
            return self._result(target, dry_run, actions, findings, app_name, repo_path, error=True)
        findings.append("✅ terraform init")

        # ── 4. terraform plan ─────────────────────────────────────────────────
        plan_file = tf_dir / 'tfplan'
        ok, out = self._run(tf_dir, [
            'terraform', 'plan',
            f'-var=environment={target}',
            f'-var=app_name={app_name}',
            '-input=false',
            f'-out={plan_file}',
        ])
        step = {'step': 'terraform_plan', 'status': 'ok' if ok else 'failed', 'output': out[:1000]}
        actions.append(step)
        if not ok:
            findings.append(f"❌ terraform plan failed:\n{out[:400]}")
            return self._result(target, dry_run, actions, findings, app_name, repo_path, error=True)

        # Parse plan summary
        plan_summary = self._parse_plan_summary(out)
        findings.append(f"✅ terraform plan: {plan_summary}")

        if dry_run:
            findings.append("ℹ️  dry_run=True — skipping terraform apply (pass dry_run=False to deploy)")
            return self._result(target, dry_run, actions, findings, app_name, repo_path)

        # ── 5. terraform apply ────────────────────────────────────────────────
        ok, out = self._run(tf_dir, [
            'terraform', 'apply',
            '-input=false',
            '-auto-approve',
            str(plan_file),
        ])
        step = {'step': 'terraform_apply', 'status': 'ok' if ok else 'failed', 'output': out[:1000]}
        actions.append(step)
        if not ok:
            findings.append(f"❌ terraform apply failed:\n{out[:400]}")
            return self._result(target, dry_run, actions, findings, app_name, repo_path, error=True)
        findings.append(f"✅ terraform apply complete — deployed to {target}")

        # ── 6. Terraform outputs ──────────────────────────────────────────────
        tf_outputs = self._get_tf_outputs(tf_dir)
        if tf_outputs:
            actions.append({'step': 'terraform_outputs', 'status': 'ok', 'outputs': tf_outputs})
            findings.append(f"📤 Outputs: {', '.join(tf_outputs.keys())}")

        # ── 7. Docker build + push (optional) ────────────────────────────────
        if docker_build:
            image_result = self._docker_build_push(repo_path, app_name, registry, image_tag)
            actions.append(image_result)
            findings.append(
                f"✅ Docker: {image_result['image']}" if image_result['status'] == 'ok'
                else f"❌ Docker build/push failed: {image_result.get('error', '')}"
            )

        # ── 8. ArgoCD sync (optional) ─────────────────────────────────────────
        if argocd_sync:
            argo_result = self._argocd_sync(app_name, target)
            actions.append(argo_result)
            findings.append(
                f"✅ ArgoCD synced: {app_name}-{target}" if argo_result['status'] == 'ok'
                else f"⚠️  ArgoCD sync: {argo_result.get('error', 'check ArgoCD manually')}"
            )

        return self._result(target, dry_run, actions, findings, app_name, repo_path,
                            tf_outputs=tf_outputs)

    # -----------------------------------------------------------------------
    # Terraform helpers
    # -----------------------------------------------------------------------

    def _find_terraform_dir(self, repo_path: Path, override: Optional[str]) -> Optional[Path]:
        """Locate the Terraform directory (IACAgent output or override)."""
        if override:
            p = Path(override)
            return p if p.is_dir() else None
        # IACAgent puts Terraform here
        candidate = repo_path / 'infrastructure' / 'terraform'
        if candidate.is_dir() and any(candidate.glob('*.tf')):
            return candidate
        # Fallback: bare terraform/ at root
        candidate2 = repo_path / 'terraform'
        if candidate2.is_dir() and any(candidate2.glob('*.tf')):
            return candidate2
        return None

    def _generate_fallback_terraform(self, repo_path: Path, app_name: str, environment: str) -> Path:
        """Write a minimal Terraform config when IACAgent hasn't run."""
        tf_dir = repo_path / 'terraform'
        tf_dir.mkdir(exist_ok=True)
        (tf_dir / 'main.tf').write_text(_FALLBACK_TF_MAIN)
        (tf_dir / 'variables.tf').write_text(
            _FALLBACK_TF_VARS.format(app_name=app_name, environment=environment)
        )
        self.log(f"Fallback Terraform written to {tf_dir}")
        return tf_dir

    def _parse_plan_summary(self, plan_output: str) -> str:
        """Extract 'X to add, Y to change, Z to destroy' from plan output."""
        import re
        match = re.search(
            r'(\d+ to add|[^.]+to add, \d+ to change, \d+ to destroy)',
            plan_output
        )
        if match:
            return match.group(0).strip()
        if 'No changes' in plan_output:
            return 'No changes — infrastructure is up-to-date'
        return 'plan complete'

    def _get_tf_outputs(self, tf_dir: Path) -> Dict[str, Any]:
        """Run terraform output -json and return parsed dict."""
        try:
            result = subprocess.run(
                ['terraform', 'output', '-json'],
                cwd=str(tf_dir),
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                raw = json.loads(result.stdout)
                return {k: v.get('value') for k, v in raw.items()}
        except Exception:
            pass
        return {}

    # -----------------------------------------------------------------------
    # Docker helpers
    # -----------------------------------------------------------------------

    def _docker_build_push(self, repo_path: Path, app_name: str, registry: str, tag: str) -> Dict:
        image = f"{registry}/{app_name}:{tag}"
        if not shutil.which('docker'):
            return {'step': 'docker', 'status': 'skipped', 'error': 'docker CLI not found'}

        ok, out = self._run(repo_path, ['docker', 'build', '-t', image, '.'])
        if not ok:
            return {'step': 'docker_build', 'status': 'failed', 'error': out[:300]}

        ok, out = self._run(repo_path, ['docker', 'push', image])
        if not ok:
            return {'step': 'docker_push', 'status': 'failed', 'image': image, 'error': out[:300]}

        return {'step': 'docker', 'status': 'ok', 'image': image}

    # -----------------------------------------------------------------------
    # ArgoCD helpers
    # -----------------------------------------------------------------------

    def _argocd_sync(self, app_name: str, environment: str) -> Dict:
        argocd_app = f"{app_name}-{environment}"
        if not shutil.which('argocd'):
            return {'step': 'argocd', 'status': 'skipped', 'error': 'argocd CLI not found'}
        ok, out = self._run(Path('.'), ['argocd', 'app', 'sync', argocd_app, '--prune'])
        if ok:
            return {'step': 'argocd_sync', 'status': 'ok', 'app': argocd_app}
        return {'step': 'argocd_sync', 'status': 'failed', 'app': argocd_app, 'error': out[:200]}

    # -----------------------------------------------------------------------
    # Shared helpers
    # -----------------------------------------------------------------------

    def _run(self, cwd: Path, args: list, timeout: int = 300) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                args, cwd=str(cwd),
                capture_output=True, text=True, timeout=timeout
            )
            output = (result.stdout or '') + (result.stderr or '')
            return result.returncode == 0, output.strip()
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout}s"
        except Exception as e:
            return False, str(e)

    def _git_sha(self, repo_path: Path) -> Optional[str]:
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                cwd=str(repo_path), capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _result(
        self, target, dry_run, actions, findings, app_name, repo_path,
        error=False, tf_outputs=None
    ) -> Dict:
        applied = not dry_run and not error and any(
            a.get('step') == 'terraform_apply' and a.get('status') == 'ok'
            for a in actions
        )
        status = 'error' if error else 'warning' if dry_run else 'success'
        mode = 'plan only (dry_run)' if dry_run else 'applied'
        summary = (
            f"Deployment {mode} → {target} for '{app_name}'"
            if not error else
            f"Deployment failed for '{app_name}' ({target})"
        )
        return self.create_result(
            status=status,
            summary=summary,
            data={
                'app_name': app_name,
                'target': target,
                'dry_run': dry_run,
                'applied': applied,
                'steps_run': len(actions),
                'tf_outputs': tf_outputs or {},
            },
            findings=findings,
            actions=actions
        )
