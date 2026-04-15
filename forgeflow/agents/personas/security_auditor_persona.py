"""
SecurityAuditorPersona — network policies, image scanning, IAM minimization.

Artifacts:
  deploy/security/networkpolicy.yaml        — default-deny + app-allow rules
  deploy/security/pod-security.yaml         — restricted PodSecurity labels
  deploy/security/iam-minimization.md       — guidance on scoping roles
  .github/workflows/security-scan.yml       — trivy + checkov + gitleaks
  deploy/security/sbom/README.md            — if SBOM is enabled
"""
from typing import Any, Dict, List

import yaml

from .base_persona import BasePersona


class SecurityAuditorPersona(BasePersona):
    """Produces policy manifests and a security-scan CI workflow."""

    persona_name = "security-auditor"
    owned_paths = ["deploy/security/", ".github/workflows/security-scan.yml"]

    def __init__(self):
        super().__init__(
            name="security_auditor_persona",
            description="Emits network policies, IAM guidance, and a CI security scan",
        )

    def produce_artifacts(self, overwrite=True):
        actions: List[Dict[str, Any]] = []
        findings: List[str] = []
        sec = self.intent["security"]
        app = self.intent["app"]["name"]
        is_k8s = self.intent["compute"]["model"] == "kubernetes"

        if sec["network_policies"] and is_k8s:
            actions.append(self._network_policy(app, overwrite))
            actions.append(self._pod_security(app, overwrite))
        else:
            findings.append("Network policies not applied (non-k8s mode or disabled in intent)")

        if sec["iam_least_privilege"]:
            actions.append(self._iam_doc(overwrite))

        if sec["image_scanning"]:
            actions.append(self._scan_workflow(overwrite))

        if sec["sbom"]:
            actions.append(self._sbom_readme(overwrite))

        return actions, findings, {
            "network_policies": sec["network_policies"] and is_k8s,
            "image_scanning": sec["image_scanning"],
            "sbom": sec["sbom"],
        }

    # ----------------------------------------------------------------- netpol

    def _network_policy(self, app: str, overwrite: bool) -> Dict[str, Any]:
        doc = [
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {"name": "default-deny-ingress"},
                "spec": {"podSelector": {}, "policyTypes": ["Ingress"]},
            },
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {"name": f"{app}-allow-ingress"},
                "spec": {
                    "podSelector": {"matchLabels": {"app.kubernetes.io/name": app}},
                    "policyTypes": ["Ingress"],
                    "ingress": [{
                        "from": [
                            {"namespaceSelector": {"matchLabels": {"name": "ingress-nginx"}}},
                            {"namespaceSelector": {"matchLabels": {"name": "observability"}}},
                        ],
                        "ports": [{"protocol": "TCP", "port": "http"}],
                    }],
                },
            },
        ]
        content = "---\n".join(yaml.safe_dump(d, sort_keys=False) for d in doc)
        return self.write_file("deploy/security/networkpolicy.yaml", content, overwrite)

    def _pod_security(self, app: str, overwrite: bool) -> Dict[str, Any]:
        content = f"""apiVersion: v1
kind: Namespace
metadata:
  name: {app}
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
"""
        return self.write_file("deploy/security/pod-security.yaml", content, overwrite)

    # ------------------------------------------------------------------ IAM

    def _iam_doc(self, overwrite: bool) -> Dict[str, Any]:
        cloud = self.intent["cloud"]["provider"]
        guidance = {
            "gcp": (
                "Replace the broad `roles/editor` on `sevaforge-deployer` with these narrower roles:\n\n"
                "- `roles/container.admin` — manage GKE clusters\n"
                "- `roles/compute.networkAdmin` — manage VPC, subnets, firewall\n"
                "- `roles/iam.serviceAccountUser` — impersonate service accounts\n"
                "- `roles/storage.admin` on the tfstate bucket only (conditional binding)\n\n"
                "Apply with:\n"
                "```bash\n"
                "gcloud projects add-iam-policy-binding $PROJECT \\\n"
                "  --member=serviceAccount:sevaforge-deployer@$PROJECT.iam.gserviceaccount.com \\\n"
                "  --role=roles/container.admin\n"
                "```"
            ),
            "aws": (
                "Replace `PowerUserAccess` with a scoped custom policy covering only:\n"
                "- `eks:*` on your cluster ARN\n"
                "- `ec2:*` on VPC/subnet/SG resources tagged for this app\n"
                "- `s3:*` on the tfstate bucket only\n"
                "- `iam:PassRole` only to the EKS node role"
            ),
            "azure": "Replace Contributor with Custom Role containing only AKS + VNet + KeyVault scopes.",
            "oci": "Scope policies to the specific compartment; avoid tenancy-wide ANY_USER statements.",
        }.get(cloud, "Scope your deployer credentials to the narrowest roles required.")

        content = f"""# IAM Least-Privilege Guidance — {cloud.upper()}

{guidance}

## Rotation

Rotate the deployer credentials every 90 days. If a key is ever exposed (e.g., accidentally committed),
revoke it immediately and regenerate.

## Audit

Run `gcloud asset search-all-iam-policies --scope projects/$PROJECT` (or equivalent) monthly to
verify no excess bindings have crept in.
"""
        return self.write_file("deploy/security/iam-minimization.md", content, overwrite)

    # ---------------------------------------------------------- scan workflow

    def _scan_workflow(self, overwrite: bool) -> Dict[str, Any]:
        content = """name: Security Scan

on:
  push:
    branches: [main, gui-polish]
  pull_request:
  schedule:
    - cron: '0 6 * * 1'  # weekly Monday 6AM UTC

jobs:
  trivy:
    name: Container image scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t scan-target:latest .
      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: scan-target:latest
          format: table
          severity: CRITICAL,HIGH
          exit-code: '1'

  checkov:
    name: IaC scan (Terraform)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: bridgecrewio/checkov-action@master
        with:
          directory: forgeflow/infrastructure
          framework: terraform
          soft_fail: false

  gitleaks:
    name: Secrets scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
"""
        return self.write_file(".github/workflows/security-scan.yml", content, overwrite)

    # ---------------------------------------------------------------- SBOM

    def _sbom_readme(self, overwrite: bool) -> Dict[str, Any]:
        content = """# SBOM Generation

Add this step to your CI build workflow to emit a CycloneDX SBOM for every image:

```yaml
- name: Generate SBOM
  uses: anchore/sbom-action@v0
  with:
    image: ${{ env.IMAGE_URI }}
    format: cyclonedx-json
    output-file: sbom.cdx.json
- uses: actions/upload-artifact@v4
  with:
    name: sbom
    path: sbom.cdx.json
```

The SBOM is attached to every release and can be fed into vuln scanners (Grype, Dependency-Track).
"""
        return self.write_file("deploy/security/sbom/README.md", content, overwrite)
