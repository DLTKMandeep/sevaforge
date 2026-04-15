"""
CostGuardianPersona — budget alerts, auto-shutdown scheduler, teardown workflow.

Replaces the ad-hoc gke-scheduler.yml / gke-teardown.yml we wrote earlier:
these now come out of a persona that reads the intent's cost_controls block.

Artifacts:
  deploy/cost/budget-alert.tf                    — native cloud budget alert
  .github/workflows/cost-shutdown.yml            — nightly scale-down/up
  .github/workflows/cost-teardown.yml            — one-shot teardown on date
  deploy/cost/README.md                          — human-readable plan
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import yaml

from .base_persona import BasePersona


class CostGuardianPersona(BasePersona):
    """Budget alerts + auto-shutdown + teardown date."""

    persona_name = "cost-guardian"
    owned_paths = [".github/workflows/cost-shutdown.yml",
                   ".github/workflows/cost-teardown.yml",
                   "deploy/cost/"]

    def __init__(self):
        super().__init__(
            name="cost_guardian_persona",
            description="Emits budget alerts, scheduler, and teardown workflows",
        )

    def produce_artifacts(self, overwrite=True):
        actions: List[Dict[str, Any]] = []
        findings: List[str] = []
        cc = self.intent["cost_controls"]
        cloud = self.intent["cloud"]["provider"]
        app = self.intent["app"]["name"]

        # Budget alert (cloud-native)
        if cc.get("budget_usd_monthly", 0) > 0:
            actions.append(self._budget_terraform(cloud, app, cc["budget_usd_monthly"], overwrite))
        else:
            findings.append("No budget set — skipped budget alert terraform")

        # Nightly auto-shutdown
        shutdown = cc.get("auto_shutdown", {})
        if shutdown.get("enabled"):
            actions.append(self._shutdown_workflow(cloud, app, shutdown, overwrite))
        else:
            findings.append("Auto-shutdown disabled")

        # Teardown
        if cc.get("teardown_date"):
            actions.append(self._teardown_workflow(cloud, app, cc["teardown_date"], overwrite))
            findings.append(f"Teardown scheduled for {cc['teardown_date']}")
        else:
            findings.append("No teardown date set — resources will run indefinitely")

        # Human-readable plan
        actions.append(self._cost_readme(app, cc, overwrite))

        return actions, findings, {"budget": cc.get("budget_usd_monthly"),
                                   "shutdown": shutdown.get("enabled"),
                                   "teardown_date": cc.get("teardown_date")}

    # --------------------------------------------------------------- budget

    def _budget_terraform(self, cloud: str, app: str, usd: float, overwrite: bool) -> Dict[str, Any]:
        if cloud == "gcp":
            content = f'''# Billing budget alert at {usd} USD/mo
# Requires roles/billing.admin on the billing account.
resource "google_billing_budget" "main" {{
  billing_account = var.billing_account_id
  display_name    = "{app} monthly budget"

  amount {{
    specified_amount {{
      currency_code = "USD"
      units         = "{int(usd)}"
    }}
  }}

  threshold_rules {{
    threshold_percent = 0.5
  }}
  threshold_rules {{
    threshold_percent = 0.9
  }}
  threshold_rules {{
    threshold_percent = 1.0
  }}
}}

variable "billing_account_id" {{
  description = "GCP billing account id"
  type        = string
}}
'''
        elif cloud == "aws":
            content = f'''resource "aws_budgets_budget" "main" {{
  name         = "{app}-monthly"
  budget_type  = "COST"
  time_unit    = "MONTHLY"
  limit_amount = "{usd}"
  limit_unit   = "USD"
}}
'''
        else:
            content = f"# Budget alert for {cloud} — not yet templated\n"

        return self.write_file("deploy/cost/budget-alert.tf", content, overwrite)

    # ------------------------------------------------------------- shutdown

    def _shutdown_workflow(self, cloud: str, app: str, shutdown: Dict[str, Any], overwrite: bool) -> Dict[str, Any]:
        down = shutdown.get("schedule_down", "0 4 * * *")
        up = shutdown.get("schedule_up", "0 14 * * *")
        # Only GKE is fully templated; other clouds get a stub
        if cloud == "gcp":
            content = f"""name: Cost — Nightly Shutdown/Startup

on:
  schedule:
    - cron: '{down}'  # shutdown
    - cron: '{up}'    # startup
  workflow_dispatch:
    inputs:
      action:
        required: true
        type: choice
        options: [shutdown, startup]

env:
  CLUSTER: {app}-cluster
  REGION: ${{{{ secrets.GCP_REGION }}}}
  PROJECT: ${{{{ secrets.GCP_PROJECT_ID }}}}

jobs:
  determine:
    runs-on: ubuntu-latest
    outputs:
      action: ${{{{ steps.set.outputs.action }}}}
    steps:
      - id: set
        run: |
          if [ "${{{{ github.event_name }}}}" = "workflow_dispatch" ]; then
            echo "action=${{{{ inputs.action }}}}" >> $GITHUB_OUTPUT
          else
            HOUR=$(date -u +%H)
            if [ "$HOUR" -lt 10 ]; then
              echo "action=shutdown" >> $GITHUB_OUTPUT
            else
              echo "action=startup" >> $GITHUB_OUTPUT
            fi
          fi

  run:
    needs: determine
    runs-on: ubuntu-latest
    steps:
      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{{{ secrets.GCP_SA_KEY }}}}
      - uses: google-github-actions/setup-gcloud@v2
      - run: gcloud components install gke-gcloud-auth-plugin --quiet
      - run: gcloud container clusters get-credentials $CLUSTER --region $REGION --project $PROJECT
      - name: Execute
        run: |
          ACTION=${{{{ needs.determine.outputs.action }}}}
          for NS in $(kubectl get ns -o jsonpath='{{.items[*].metadata.name}}'); do
            case "$NS" in kube-*|gke-*|gmp-system) continue ;; esac
            for DEP in $(kubectl get deploy -n $NS -o jsonpath='{{.items[*].metadata.name}}' 2>/dev/null); do
              if [ "$ACTION" = "shutdown" ]; then
                REPLICAS=$(kubectl get deploy $DEP -n $NS -o jsonpath='{{.spec.replicas}}')
                kubectl annotate deploy $DEP -n $NS sevaforge.io/pre-shutdown-replicas=$REPLICAS --overwrite
                kubectl scale deploy $DEP -n $NS --replicas=0
              else
                REPLICAS=$(kubectl get deploy $DEP -n $NS -o jsonpath='{{.metadata.annotations.sevaforge\\.io/pre-shutdown-replicas}}' 2>/dev/null || echo 1)
                [ -z "$REPLICAS" ] && REPLICAS=1
                kubectl scale deploy $DEP -n $NS --replicas=$REPLICAS
              fi
            done
          done
"""
        else:
            content = f"# Auto-shutdown workflow for {cloud} — not yet templated\n"

        return self.write_file(".github/workflows/cost-shutdown.yml", content, overwrite)

    # ------------------------------------------------------------- teardown

    def _teardown_workflow(self, cloud: str, app: str, teardown_date: str, overwrite: bool) -> Dict[str, Any]:
        # Parse into cron for the specific day
        try:
            dt = datetime.fromisoformat(teardown_date).date()
            cron = f"0 6 {dt.day} {dt.month} *"
        except Exception:
            cron = "0 6 8 7 *"  # safe fallback: July 8 at 6 UTC

        if cloud == "gcp":
            content = f"""name: Cost — Full Teardown

on:
  schedule:
    - cron: '{cron}'  # {teardown_date}
  workflow_dispatch:
    inputs:
      confirm:
        description: 'Type DESTROY to confirm'
        required: true
        type: string

env:
  PROJECT: ${{{{ secrets.GCP_PROJECT_ID }}}}
  REGION: ${{{{ secrets.GCP_REGION }}}}

jobs:
  teardown:
    if: >
      github.event_name == 'schedule' ||
      (github.event_name == 'workflow_dispatch' && inputs.confirm == 'DESTROY')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{{{ secrets.GCP_SA_KEY }}}}
      - uses: google-github-actions/setup-gcloud@v2
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.7.x"
          terraform_wrapper: false
      - name: Terraform destroy
        working-directory: forgeflow/infrastructure/gcp
        env:
          TF_VAR_project_id: ${{{{ secrets.GCP_PROJECT_ID }}}}
          TF_VAR_region: ${{{{ secrets.GCP_REGION }}}}
        run: |
          terraform init
          terraform destroy -auto-approve

      - name: Disable scheduler workflow
        env:
          GH_TOKEN: ${{{{ secrets.GH_TOKEN }}}}
        run: |
          gh workflow disable cost-shutdown.yml --repo ${{{{ github.repository }}}} || true
"""
        else:
            content = f"# Teardown workflow for {cloud} — not yet templated\n"

        return self.write_file(".github/workflows/cost-teardown.yml", content, overwrite)

    # ---------------------------------------------------------------- readme

    def _cost_readme(self, app: str, cc: Dict[str, Any], overwrite: bool) -> Dict[str, Any]:
        budget = cc.get("budget_usd_monthly", 0)
        shutdown = cc.get("auto_shutdown", {})
        teardown = cc.get("teardown_date", "")

        content = f"""# Cost Controls — {app}

## Budget

- Monthly budget: **${budget:.2f} USD** {"(alerts at 50% / 90% / 100%)" if budget else "(not set)"}

## Auto-shutdown

- Enabled: **{shutdown.get("enabled", False)}**
- Shutdown cron (UTC): `{shutdown.get("schedule_down", "n/a")}`
- Startup cron (UTC): `{shutdown.get("schedule_up", "n/a")}`

During shutdown all deployments are scaled to 0 replicas; the GKE Autopilot control plane remains free.

## Teardown

- Auto-teardown date: **{teardown or "not scheduled"}**

On that date `.github/workflows/cost-teardown.yml` runs `terraform destroy` and disables the scheduler.
You can also trigger it manually with `gh workflow run cost-teardown.yml -f confirm=DESTROY`.

## Manual check

```bash
gh workflow list --repo $REPO | grep Cost
gh run list --workflow=cost-shutdown.yml --repo $REPO
```
"""
        return self.write_file("deploy/cost/README.md", content, overwrite)
