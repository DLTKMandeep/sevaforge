#!/usr/bin/env bash
#
# SevaForge — Production Deployment Runbook
# Deploys sevaforge.io to GCP (GKE Standard + Cloud SQL + Redis + CDN)
#
# Usage: bash deploy/deploy.sh
#
set -euo pipefail

# ─── Colors & helpers ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

step()  { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BOLD}${CYAN}STEP $1:${NC} ${BOLD}$2${NC}"; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }
info()  { echo -e "${CYAN}  ℹ ${NC} $1"; }
ok()    { echo -e "${GREEN}  ✓ ${NC} $1"; }
warn()  { echo -e "${YELLOW}  ⚠ ${NC} $1"; }
err()   { echo -e "${RED}  ✗ ${NC} $1"; }
ask()   { echo -en "${YELLOW}  ? ${NC} $1: "; read -r REPLY; }
pause() { echo -en "\n${YELLOW}  Press Enter to continue...${NC}"; read -r; }

# ─── Configuration ───────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-sevaforge-prod}"
REGION="${GCP_REGION:-us-central1}"
ZONE="${GCP_ZONE:-us-central1-a}"
CLUSTER_NAME="sevaforge-cluster"
DOMAIN="sevaforge.io"
BILLING_ACCOUNT=""
REPO_NAME="sevaforge"

echo -e "\n${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║                                                      ║"
echo "  ║   SevaForge — Production Deployment Runbook          ║"
echo "  ║   Agentic AI Driven Platform Engineering             ║"
echo "  ║                                                      ║"
echo "  ║   Target: GKE Standard · Cloud SQL · Redis · CDN     ║"
echo "  ║   Domain: sevaforge.io                               ║"
echo "  ║                                                      ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: PREREQUISITES
# ═══════════════════════════════════════════════════════════════════════════════

step "1/12" "Check Prerequisites"

# Check gcloud
if ! command -v gcloud &>/dev/null; then
  err "gcloud CLI not found"
  info "Install: https://cloud.google.com/sdk/docs/install"
  info "  brew install google-cloud-sdk   (macOS)"
  info "  curl https://sdk.cloud.google.com | bash   (Linux)"
  exit 1
fi
ok "gcloud CLI found: $(gcloud version 2>/dev/null | head -1)"

# Check terraform
if ! command -v terraform &>/dev/null; then
  err "Terraform not found"
  info "Install: https://developer.hashicorp.com/terraform/install"
  info "  brew install terraform   (macOS)"
  exit 1
fi
ok "Terraform found: $(terraform version -json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || terraform version | head -1)"

# Check kubectl
if ! command -v kubectl &>/dev/null; then
  err "kubectl not found"
  info "Install: gcloud components install kubectl"
  exit 1
fi
ok "kubectl found: $(kubectl version --client --short 2>/dev/null || kubectl version --client -o json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["clientVersion"]["gitVersion"])' 2>/dev/null || echo 'installed')"

# Check docker
if ! command -v docker &>/dev/null; then
  warn "Docker not found (needed for building images)"
  info "Install: https://docs.docker.com/get-docker/"
else
  ok "Docker found"
fi

# Check helm (optional)
if command -v helm &>/dev/null; then
  ok "Helm found (optional)"
else
  info "Helm not found (optional, can install later)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: GCP ACCOUNT & PROJECT
# ═══════════════════════════════════════════════════════════════════════════════

step "2/12" "Set Up GCP Account & Project"

info "If you don't have a GCP account yet:"
info "  1. Go to https://cloud.google.com/free"
info "  2. Sign up (you get \$300 free credits for 90 days)"
info "  3. Come back and continue this script"
echo ""

# Login
info "Authenticating with Google Cloud..."
if ! gcloud auth list --filter="status:ACTIVE" --format="value(account)" 2>/dev/null | head -1 | grep -q "@"; then
  gcloud auth login --brief
fi
ACCOUNT=$(gcloud auth list --filter="status:ACTIVE" --format="value(account)" 2>/dev/null | head -1)
ok "Logged in as: $ACCOUNT"

# Set up application default credentials
info "Setting up application default credentials for Terraform..."
if ! gcloud auth application-default print-access-token &>/dev/null 2>&1; then
  gcloud auth application-default login
fi
ok "Application default credentials configured"

# Billing account
info "Checking billing accounts..."
BILLING_ACCOUNTS=$(gcloud billing accounts list --format="value(ACCOUNT_ID,DISPLAY_NAME)" 2>/dev/null)
if [ -z "$BILLING_ACCOUNTS" ]; then
  err "No billing accounts found."
  info "Set up billing at: https://console.cloud.google.com/billing"
  info "You need a billing account before creating a project."
  pause
  BILLING_ACCOUNTS=$(gcloud billing accounts list --format="value(ACCOUNT_ID,DISPLAY_NAME)" 2>/dev/null)
fi
echo "$BILLING_ACCOUNTS"
ask "Enter your Billing Account ID (e.g., 01ABCD-2EF345-6GH789)"
BILLING_ACCOUNT="$REPLY"
ok "Using billing account: $BILLING_ACCOUNT"

# Create project
ask "GCP Project ID [default: $PROJECT_ID]"
[ -n "$REPLY" ] && PROJECT_ID="$REPLY"

if gcloud projects describe "$PROJECT_ID" &>/dev/null 2>&1; then
  ok "Project '$PROJECT_ID' already exists"
else
  info "Creating project '$PROJECT_ID'..."
  gcloud projects create "$PROJECT_ID" --name="SevaForge Production"
  ok "Project created"
fi

# Link billing
info "Linking billing account to project..."
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
ok "Billing linked"

# Set default project
gcloud config set project "$PROJECT_ID"
ok "Default project set to: $PROJECT_ID"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: ENABLE APIs
# ═══════════════════════════════════════════════════════════════════════════════

step "3/12" "Enable Required GCP APIs"

APIS=(
  "compute.googleapis.com"
  "container.googleapis.com"
  "sqladmin.googleapis.com"
  "redis.googleapis.com"
  "dns.googleapis.com"
  "secretmanager.googleapis.com"
  "artifactregistry.googleapis.com"
  "cloudresourcemanager.googleapis.com"
  "iam.googleapis.com"
  "servicenetworking.googleapis.com"
  "certificatemanager.googleapis.com"
  "cloudbuild.googleapis.com"
)

for api in "${APIS[@]}"; do
  info "Enabling $api..."
  gcloud services enable "$api" --project="$PROJECT_ID" 2>/dev/null || true
done
ok "All APIs enabled (some may take 1-2 minutes to propagate)"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: CREATE ARTIFACT REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

step "4/12" "Create Artifact Registry (Docker Container Registry)"

if gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" --project="$PROJECT_ID" &>/dev/null 2>&1; then
  ok "Artifact Registry '$REPO_NAME' already exists"
else
  info "Creating Artifact Registry..."
  gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="SevaForge container images" \
    --project="$PROJECT_ID"
  ok "Artifact Registry created"
fi

# Configure Docker auth
info "Configuring Docker authentication for Artifact Registry..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
ok "Docker auth configured for ${REGION}-docker.pkg.dev"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5: TERRAFORM STATE BUCKET
# ═══════════════════════════════════════════════════════════════════════════════

step "5/12" "Create Terraform State Bucket"

STATE_BUCKET="${PROJECT_ID}-tf-state"

if gsutil ls -b "gs://${STATE_BUCKET}" &>/dev/null 2>&1; then
  ok "State bucket '${STATE_BUCKET}' already exists"
else
  info "Creating GCS bucket for Terraform state..."
  gsutil mb -p "$PROJECT_ID" -l "$REGION" -b on "gs://${STATE_BUCKET}"
  gsutil versioning set on "gs://${STATE_BUCKET}"
  ok "State bucket created with versioning enabled"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6: TERRAFORM INIT & PLAN
# ═══════════════════════════════════════════════════════════════════════════════

step "6/12" "Terraform — Initialize & Plan"

cd deploy/terraform

# Create tfvars
info "Creating terraform.tfvars..."
cat > terraform.tfvars <<TFVARS
project_id      = "${PROJECT_ID}"
region          = "${REGION}"
environment     = "production"
domain          = "${DOMAIN}"
TFVARS
ok "terraform.tfvars created"

# Init
info "Running terraform init..."
terraform init \
  -backend-config="bucket=${STATE_BUCKET}" \
  -backend-config="prefix=terraform/state"
ok "Terraform initialized"

# Plan
info "Running terraform plan..."
terraform plan -out=tfplan
ok "Terraform plan complete"

echo ""
warn "Review the plan above carefully."
warn "This will create real GCP resources that cost money (~\$450/month)."
ask "Apply this plan? (yes/no)"
if [ "$REPLY" != "yes" ]; then
  err "Aborted. Run 'terraform apply tfplan' when ready."
  exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 7: TERRAFORM APPLY
# ═══════════════════════════════════════════════════════════════════════════════

step "7/12" "Terraform — Apply (Creating Infrastructure)"

info "This takes 10-15 minutes (GKE cluster + Cloud SQL are slow to provision)..."
terraform apply tfplan
ok "Infrastructure created successfully!"

# Capture outputs
CLUSTER_ENDPOINT=$(terraform output -raw cluster_endpoint 2>/dev/null || echo "pending")
LB_IP=$(terraform output -raw load_balancer_ip 2>/dev/null || echo "pending")
SQL_IP=$(terraform output -raw sql_private_ip 2>/dev/null || echo "pending")
DNS_NAMESERVERS=$(terraform output -raw dns_nameservers 2>/dev/null || echo "pending")

info "Cluster endpoint: $CLUSTER_ENDPOINT"
info "Load balancer IP:  $LB_IP"
info "Cloud SQL IP:      $SQL_IP"
info "DNS Nameservers:   $DNS_NAMESERVERS"

cd ../..

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8: CONFIGURE KUBECTL
# ═══════════════════════════════════════════════════════════════════════════════

step "8/12" "Configure kubectl for GKE"

info "Getting cluster credentials..."
gcloud container clusters get-credentials "$CLUSTER_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID"
ok "kubectl configured"

# Verify
info "Verifying cluster access..."
kubectl cluster-info
kubectl get nodes
ok "Cluster is accessible"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 9: DOMAIN REGISTRATION & DNS
# ═══════════════════════════════════════════════════════════════════════════════

step "9/12" "Domain Registration & DNS Setup"

echo ""
info "You need to register '${DOMAIN}' and point it to Google Cloud DNS."
echo ""
info "Option A — Register via Google Domains (domains.google.com)"
info "Option B — Register via any registrar (Namecheap, GoDaddy, Cloudflare, etc.)"
echo ""
info "After registering, update your domain's nameservers to:"
echo ""
echo -e "  ${BOLD}${DNS_NAMESERVERS}${NC}"
echo ""
info "The DNS zone has already been created by Terraform."
info "The A records for ${DOMAIN} and api.${DOMAIN} point to: ${LB_IP}"
echo ""
warn "DNS propagation can take 15 minutes to 48 hours."
info "You can check propagation at: https://dnschecker.org/#A/${DOMAIN}"
echo ""
pause

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 10: BUILD & PUSH DOCKER IMAGES
# ═══════════════════════════════════════════════════════════════════════════════

step "10/12" "Build & Push Docker Images"

IMAGE_REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")

info "Building images (this may take a few minutes)..."
echo ""

# API Server
if [ -f deploy/Dockerfile.api ]; then
  info "Building API server image..."
  docker build -f deploy/Dockerfile.api -t "${IMAGE_REGISTRY}/api:${GIT_SHA}" -t "${IMAGE_REGISTRY}/api:latest" .
  docker push "${IMAGE_REGISTRY}/api:${GIT_SHA}"
  docker push "${IMAGE_REGISTRY}/api:latest"
  ok "API server image pushed"
else
  warn "deploy/Dockerfile.api not found — skipping API build"
  info "You'll need to create Dockerfiles for each service and build them"
fi

info "For a full build, you need Dockerfiles for:"
info "  - dashboard (nginx + React SPA)"
info "  - api (FastAPI)"
info "  - auth (JWT/OAuth2 service)"
info "  - worker (ForgeFlow pipeline runner)"
info "  - webhook (GitHub webhook handler)"
echo ""
info "The CI/CD pipeline (deploy/.github/workflows/deploy.yaml) builds all 5 automatically."

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 11: DEPLOY TO KUBERNETES
# ═══════════════════════════════════════════════════════════════════════════════

step "11/12" "Deploy to Kubernetes"

info "Applying Kubernetes manifests..."
echo ""

# Apply in order
kubectl apply -f deploy/k8s/namespace.yaml
ok "Namespace created"

kubectl apply -f deploy/k8s/serviceaccount.yaml
ok "Service accounts created"

kubectl apply -f deploy/k8s/configmap.yaml
ok "ConfigMap applied"

kubectl apply -f deploy/k8s/secrets.yaml
ok "Secrets template applied (update with real values!)"

kubectl apply -f deploy/k8s/pvc.yaml
ok "Persistent volume claim created"

kubectl apply -f deploy/k8s/networkpolicy.yaml
ok "Network policies applied"

# Deployments
kubectl apply -f deploy/k8s/dashboard-deployment.yaml
kubectl apply -f deploy/k8s/api-deployment.yaml
kubectl apply -f deploy/k8s/auth-deployment.yaml
kubectl apply -f deploy/k8s/worker-deployment.yaml
kubectl apply -f deploy/k8s/webhook-deployment.yaml
ok "All deployments applied"

# HPA & Ingress
kubectl apply -f deploy/k8s/hpa.yaml
kubectl apply -f deploy/k8s/ingress.yaml
ok "HPA and Ingress configured"

# Wait for rollout
info "Waiting for deployments to be ready..."
kubectl -n sevaforge rollout status deployment/dashboard --timeout=120s 2>/dev/null || warn "Dashboard rollout pending (images may need building)"
kubectl -n sevaforge rollout status deployment/api-server --timeout=120s 2>/dev/null || warn "API server rollout pending"

echo ""
info "Checking pod status..."
kubectl -n sevaforge get pods

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 12: VERIFY & GO LIVE
# ═══════════════════════════════════════════════════════════════════════════════

step "12/12" "Verify & Go Live"

echo ""
info "Deployment summary:"
echo ""
echo -e "  ${BOLD}Project:${NC}    $PROJECT_ID"
echo -e "  ${BOLD}Region:${NC}     $REGION"
echo -e "  ${BOLD}Cluster:${NC}    $CLUSTER_NAME"
echo -e "  ${BOLD}LB IP:${NC}      $LB_IP"
echo -e "  ${BOLD}Domain:${NC}     $DOMAIN"
echo ""

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  Remaining manual steps:${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${YELLOW}1.${NC} Register domain '${DOMAIN}' if not done"
echo -e "  ${YELLOW}2.${NC} Update nameservers to Google Cloud DNS"
echo -e "  ${YELLOW}3.${NC} Update secrets in K8s (database password, API keys, etc.):"
echo -e "     ${CYAN}kubectl -n sevaforge edit secret sevaforge-secrets${NC}"
echo -e "  ${YELLOW}4.${NC} Build & push all 5 Docker images (or let CI/CD handle it)"
echo -e "  ${YELLOW}5.${NC} Set up GitHub Actions secrets for CI/CD:"
echo -e "     ${CYAN}GCP_PROJECT_ID, GCP_WORKLOAD_IDENTITY_PROVIDER, GCP_SERVICE_ACCOUNT${NC}"
echo -e "  ${YELLOW}6.${NC} Wait for DNS propagation, then verify:"
echo -e "     ${CYAN}curl -I https://${DOMAIN}${NC}"
echo -e "     ${CYAN}curl https://api.${DOMAIN}/healthz${NC}"
echo ""

echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║                                                      ║"
echo "  ║   SevaForge infrastructure is DEPLOYED!              ║"
echo "  ║                                                      ║"
echo "  ║   Dashboard:  https://${DOMAIN}                  ║"
echo "  ║   API:        https://api.${DOMAIN}              ║"
echo "  ║   Console:    console.cloud.google.com               ║"
echo "  ║                                                      ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Useful commands
echo -e "${BOLD}Useful commands:${NC}"
echo -e "  ${CYAN}kubectl -n sevaforge get pods${NC}              # Check pod status"
echo -e "  ${CYAN}kubectl -n sevaforge logs -f deploy/api-server${NC}  # Stream API logs"
echo -e "  ${CYAN}kubectl -n sevaforge get hpa${NC}               # Check autoscaling"
echo -e "  ${CYAN}terraform -chdir=deploy/terraform output${NC}   # Show all infra outputs"
echo -e "  ${CYAN}gcloud container clusters list${NC}             # List clusters"
echo ""
