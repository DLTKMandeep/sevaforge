# IAM Least-Privilege Guidance — GCP

Replace the broad `roles/editor` on `sevaforge-deployer` with these narrower roles:

- `roles/container.admin` — manage GKE clusters
- `roles/compute.networkAdmin` — manage VPC, subnets, firewall
- `roles/iam.serviceAccountUser` — impersonate service accounts
- `roles/storage.admin` on the tfstate bucket only (conditional binding)

Apply with:
```bash
gcloud projects add-iam-policy-binding $PROJECT \
  --member=serviceAccount:sevaforge-deployer@$PROJECT.iam.gserviceaccount.com \
  --role=roles/container.admin
```

## Rotation

Rotate the deployer credentials every 90 days. If a key is ever exposed (e.g., accidentally committed),
revoke it immediately and regenerate.

## Audit

Run `gcloud asset search-all-iam-policies --scope projects/$PROJECT` (or equivalent) monthly to
verify no excess bindings have crept in.
