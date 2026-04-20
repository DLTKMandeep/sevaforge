# Deploying ForgeFlow on OCI Always Free

This guide walks you through deploying ForgeFlow to Oracle Cloud Infrastructure (OCI)
using the Always Free tier — **$0/month, no credit card charges**.

## What You Get (Always Free)

| Resource | Spec | Cost |
|---|---|---|
| 2× VM.Standard.A1.Flex | 2 oCPU + 12 GB RAM each | Free forever |
| OKE BASIC_CLUSTER | Managed Kubernetes control plane | Free forever |
| OCI Container Registry | 500 MB storage | Free forever |
| OCI Load Balancer | 1 LB, 10 Mbps | Free forever |
| Block Volume | 200 GB total | Free forever |

---

## Prerequisites

- OCI account (sign up at cloud.oracle.com — credit card required for identity but won't be charged)
- [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) installed and configured
- [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.3
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- A GitHub repository with this codebase (ForgeFlow must be your repo)

---

## Step 1 — OCI Account Setup

### 1a. Create an API Key

1. Open OCI Console → top-right profile → **My Profile**
2. Under **Resources** → **API Keys** → **Add API Key**
3. Choose **Generate API Key Pair**, download the private key
4. Copy the fingerprint shown (format: `aa:bb:cc:...`)
5. Save the private key to `~/.oci/oci_api_key.pem`

### 1b. Collect Your OCIDs

You need these four values (all look like `ocid1.xxx.oc1..aaaaaa...`):

```bash
# Tenancy OCID
oci iam tenancy get --tenancy-id $(oci iam session validate --query 'data."tenancy-id"' --raw-output) --query 'data.id' --raw-output

# User OCID
oci iam user list --query 'data[0].id' --raw-output

# Compartment OCID (use tenancy root, or create a dedicated one)
oci iam compartment list --query 'data[0].id' --raw-output
```

Or navigate in the Console: **Governance → Compartments** and copy the OCID.

### 1c. Find Your Availability Domain

```bash
oci iam availability-domain list --compartment-id <YOUR_TENANCY_OCID>
```

You'll see something like `Uocm:US-ASHBURN-AD-1` — copy this value.

### 1d. Find the ARM Node Image OCID

1. OCI Console → **Compute** → **Images** → **Platform Images**
2. Filter: **Oracle Linux 8**, **Architecture: aarch64 (ARM)**
3. Click the image → copy the **OCID**

### 1e. Create an Auth Token (for OCIR)

1. OCI Console → **Profile** → **Auth Tokens** → **Generate Token**
2. Give it a description like `sevaforge-ocir`
3. **Copy the token immediately** — it's only shown once

---

## Step 2 — Provision Infrastructure with Terraform

```bash
cd infrastructure/oci

# Copy and fill in your values
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your OCIDs, fingerprint, region, etc.

terraform init
terraform plan    # Review what will be created
terraform apply   # Type "yes" to confirm
```

After apply completes, note the outputs:

```
cluster_id        = "ocid1.cluster.oc1.iad.xxx"
kubeconfig_command = "oci ce cluster create-kubeconfig ..."
ocir_endpoint     = "iad.ocir.io"
```

---

## Step 3 — Generate kubeconfig

Run the exact command from the Terraform output:

```bash
oci ce cluster create-kubeconfig \
  --cluster-id <cluster_id_from_output> \
  --region us-ashburn-1 \
  --token-version 2.0.0 \
  --file ~/.kube/sevaforge-config

# Verify access
kubectl --kubeconfig ~/.kube/sevaforge-config get nodes
```

You should see 2 ARM nodes with status `Ready`.

### Base64-encode for GitHub Secret

```bash
base64 -w0 ~/.kube/sevaforge-config
# Copy the full output — this becomes the KUBE_CONFIG secret
```

---

## Step 4 — Set GitHub Secrets

In your GitHub repo → **Settings** → **Secrets and variables** → **Actions**, add these 11 secrets:

| Secret Name | Value | Where to find it |
|---|---|---|
| `OCI_TENANCY_OCID` | `ocid1.tenancy.oc1...` | Step 1b |
| `OCI_USER_OCID` | `ocid1.user.oc1...` | Step 1b |
| `OCI_FINGERPRINT` | `aa:bb:cc:...` | Step 1a |
| `OCI_PRIVATE_KEY` | Contents of `oci_api_key.pem` | Step 1a |
| `OCI_REGION` | `us-ashburn-1` | Your chosen region |
| `OCI_REGION_KEY` | `iad` | Short key for your region* |
| `OCI_NAMESPACE` | Your tenancy namespace | Console → Profile → Tenancy → Object Storage Namespace |
| `OCI_USERNAME` | Your OCI username (email) | Console → Profile |
| `OCI_AUTH_TOKEN` | Auth token string | Step 1e |
| `OKE_CLUSTER_ID` | `ocid1.cluster.oc1...` | Terraform output |
| `KUBE_CONFIG` | base64-encoded kubeconfig | Step 3 |
| `ANTHROPIC_API_KEY` | Your Anthropic API key | console.anthropic.com |
| `GH_TOKEN` | GitHub PAT with repo scope | github.com/settings/tokens |

*Region key examples: `iad` (us-ashburn-1), `phx` (us-phoenix-1), `fra` (eu-frankfurt-1), `syd` (ap-sydney-1)

---

## Step 5 — First Deploy

### Push to trigger CI → CD

```bash
git add .
git commit -m "chore: add OCI deployment infrastructure"
git push origin main
```

This triggers:
1. **CI workflow** — lints, tests, builds multi-arch Docker image, pushes to OCIR
2. **CD workflow** — pulls image from OCIR, deploys to OKE, runs health check

Monitor in **GitHub → Actions**.

### Manual deploy (any time)

```bash
# Trigger via GitHub CLI
gh workflow run cd.yml

# Or with a specific image tag
gh workflow run cd.yml -f image_tag=a1b2c3d4
```

---

## Step 6 — Access ForgeFlow

Get the Load Balancer IP:

```bash
kubectl get svc sevaforge --namespace sevaforge
```

The `EXTERNAL-IP` column shows your IP (may take 2–3 minutes to provision).

Open in browser: `http://<EXTERNAL-IP>`

ForgeFlow API health: `http://<EXTERNAL-IP>/health`

---

## Updating ForgeFlow

Every push to `main` automatically builds a new image and deploys it with zero downtime (rolling update). No manual steps needed after initial setup.

---

## Troubleshooting

### Nodes not Ready

```bash
kubectl describe node <node-name>
# Check for image pull or network issues
```

### Pods CrashLoopBackOff

```bash
kubectl logs -n sevaforge deployment/sevaforge --previous
```

### OCIR Pull Errors

Verify the auth token hasn't expired (they last 1 year). Regenerate in OCI Console if needed and update the `OCI_AUTH_TOKEN` GitHub secret.

### Terraform "shape not available"

A1.Flex availability varies by region. Try `us-ashburn-1` (best availability) or check: https://www.oracle.com/cloud/free/

---

## Cost Safety Check

After provisioning, in OCI Console → **Billing** → **Cost Analysis**, verify all charges show $0.00. If anything shows a cost, check that:
- Node pool uses `VM.Standard.A1.Flex` (not a paid shape)
- Total oCPUs ≤ 4 and RAM ≤ 24 GB
- Cluster type is `BASIC_CLUSTER`
- Load Balancer shape is `flexible` with 10 Mbps min/max
