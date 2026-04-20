# Deployment Secrets Guide — sevaforge-unified

This guide walks through every GitHub secret required for deploying to **GCP**.
Run `./deploy/secrets/bootstrap.sh` to set them all interactively, or set them one at a time with `gh secret set`.

| Secret | Required by | Source |
|---|---|---|
| `GH_TOKEN` | ci_cd, infra | github-actions |
| `GCP_SA_KEY` | infra, cluster, app | github-actions |
| `GCP_PROJECT_ID` | infra, cluster, app | github-actions |
| `GCP_REGION` | infra, cluster | github-actions |
| `DATABASE_URL` | app | github-actions |
| `JWT_SECRET` | app | github-actions |
| `REDIS_URL` | app | github-actions |
| `SESSION_SECRET` | app | github-actions |
| `STRIPE_API_KEY` | app | github-actions |
| `OPENAI_API_KEY` | app | github-actions |
| `ANTHROPIC_API_KEY` | app | github-actions |
| `SENDGRID_API_KEY` | app | github-actions |
| `SMTP_PASSWORD` | app | github-actions |

## How to obtain each secret

### `GH_TOKEN`

GitHub PAT with 'repo' + 'workflow' scope for CI/CD automation

1. Go to https://github.com/settings/tokens?type=beta
2. Create a fine-grained PAT with **Actions: read/write**, **Contents: read/write**, **Metadata: read** on this repo
3. Copy the token and set it via `gh secret set GH_TOKEN`

### `GCP_SA_KEY`

JSON key for the deployer service account (IAM > Service Accounts)

1. `gcloud iam service-accounts create sevaforge-deployer --project=`
2. `gcloud projects add-iam-policy-binding  --member=serviceAccount:sevaforge-deployer@.iam.gserviceaccount.com --role=roles/editor`
3. `gcloud iam service-accounts keys create gcp-sa-key.json --iam-account=sevaforge-deployer@.iam.gserviceaccount.com`
4. `gh secret set GCP_SA_KEY < gcp-sa-key.json`
5. Delete the local key file: `rm gcp-sa-key.json`

### `GCP_PROJECT_ID`

GCP project id, e.g. divine-data-469116-b2

Your project id: ``. Find it with `gcloud projects list`.

### `GCP_REGION`

Primary GCP region, e.g. us-central1

Pick a region near your users; `us-central1` is the default for free-tier friendliness.

### `DATABASE_URL`

Connection string for primary database

If you are using a managed database, copy the connection string from your provider's console (e.g. Cloud SQL, RDS, Atlas). Format: `postgres://user:pass@host:5432/dbname`

### `JWT_SECRET`

Secret key for signing JWT tokens

Generate a 32-byte random string:
```
openssl rand -base64 32
```

### `REDIS_URL`

Connection string for Redis

See the service's own documentation for how to obtain this credential.

### `SESSION_SECRET`

Secret key for signing session cookies

Same as JWT_SECRET — generate with `openssl rand -base64 32`.

### `STRIPE_API_KEY`

Stripe API key

See the service's own documentation for how to obtain this credential.

### `OPENAI_API_KEY`

OpenAI API key

https://platform.openai.com/api-keys → Create new secret key.

### `ANTHROPIC_API_KEY`

Anthropic API key

https://console.anthropic.com/settings/keys → Create Key.

### `SENDGRID_API_KEY`

SendGrid API key

See the service's own documentation for how to obtain this credential.

### `SMTP_PASSWORD`

SMTP password for outbound email

See the service's own documentation for how to obtain this credential.

## Rotation policy

- Rotate every 90 days: `GH_TOKEN`, cloud service-account keys, JWT/session secrets.
- Rotate on employee offboarding: any secret owned by the departing user.
- Rotate immediately if leaked: all of the above.

## Storage

All secrets live in **GitHub Actions secrets** for this repository. For production-grade workloads, migrate sensitive values (database URLs, JWT secrets) to a managed secret store:
- GCP: Secret Manager
- AWS: Secrets Manager / SSM Parameter Store
- Azure: Key Vault
- Self-hosted: HashiCorp Vault

