# Cost Controls — sevaforge-unified

## Budget

- Monthly budget: **$0.00 USD** (not set)

## Auto-shutdown

- Enabled: **True**
- Shutdown cron (UTC): `0 4 * * *`
- Startup cron (UTC): `0 14 * * *`

During shutdown all deployments are scaled to 0 replicas; the GKE Autopilot control plane remains free.

## Teardown

- Auto-teardown date: **not scheduled**

On that date `.github/workflows/cost-teardown.yml` runs `terraform destroy` and disables the scheduler.
You can also trigger it manually with `gh workflow run cost-teardown.yml -f confirm=DESTROY`.

## Manual check

```bash
gh workflow list --repo $REPO | grep Cost
gh run list --workflow=cost-shutdown.yml --repo $REPO
```
