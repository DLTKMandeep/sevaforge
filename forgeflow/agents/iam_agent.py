#!/usr/bin/env python3
"""
IAMAgent — Service Account & IAM Policy Generator.

For every cloud provider ForgeFlow supports (AWS / GCP / Azure) it generates:

  docs/IAM_POLICIES.md           Human-readable matrix of EVERY service account
                                  needed, what it does, and exact permissions.
  infrastructure/iam/aws/        AWS IAM policy JSON files (one per service account)
  infrastructure/iam/gcp/        GCP Terraform resource blocks (.tf)
  infrastructure/iam/azure/      Azure ARM-compatible role definition JSON files

Service accounts generated:
  ┌─────────────────────────────┬──────────────────────────────────────────────┐
  │ Account                     │ Used by                                      │
  ├─────────────────────────────┼──────────────────────────────────────────────┤
  │ terraform-deployer          │ CI/CD: terraform plan/apply (infra creation) │
  │ cicd-image-pusher           │ CI/CD: docker build + push to registry       │
  │ argocd-deploy               │ ArgoCD: sync Kubernetes manifests            │
  │ eks/gke/aks-node            │ Kubernetes worker nodes                      │
  │ external-secrets            │ ESO: read secrets from vault/sm/keyvault     │
  │ app-workload                │ Running pods: minimal runtime permissions    │
  └─────────────────────────────┴──────────────────────────────────────────────┘

Architecture:
  forgeflow secrets <path> → secrets_mcp → SecretsAgent → IAMAgent
"""
from pathlib import Path
from typing import Dict, Any, List

from .base_agent import BaseAgent


# =============================================================================
# AWS IAM POLICY DOCUMENTS
# =============================================================================

AWS_POLICIES: Dict[str, Dict[str, Any]] = {

    # ── 1. Terraform Deployer ─────────────────────────────────────────────────
    # This is the IAM user/role assumed by GitHub Actions `ci.yml` when running
    # terraform plan / terraform apply.  Must be able to create every resource
    # in your stack.  Scope it to your specific AWS account + region in prod.
    "terraform-deployer": {
        "description": "Used by GitHub Actions CI to run terraform plan/apply. Needs full access to the resource types in your stack.",
        "attached_policies": [
            "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
            "arn:aws:iam::aws:policy/AmazonVPCFullAccess",
            "arn:aws:iam::aws:policy/IAMFullAccess",
            "arn:aws:iam::aws:policy/AmazonEC2FullAccess",
            "arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess",
            "arn:aws:iam::aws:policy/AmazonRoute53FullAccess",
            "arn:aws:iam::aws:policy/AmazonS3FullAccess",
            "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
        ],
        "inline_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "EKSManagement",
                    "Effect": "Allow",
                    "Action": [
                        "eks:*",
                    ],
                    "Resource": "*",
                },
                {
                    "Sid": "ECRManagement",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:CreateRepository",
                        "ecr:DeleteRepository",
                        "ecr:DescribeRepositories",
                        "ecr:GetLifecyclePolicy",
                        "ecr:PutLifecyclePolicy",
                        "ecr:SetRepositoryPolicy",
                        "ecr:GetRepositoryPolicy",
                        "ecr:TagResource",
                    ],
                    "Resource": "*",
                },
                {
                    "Sid": "ACMCertificates",
                    "Effect": "Allow",
                    "Action": [
                        "acm:RequestCertificate",
                        "acm:DescribeCertificate",
                        "acm:DeleteCertificate",
                        "acm:ListCertificates",
                        "acm:AddTagsToCertificate",
                    ],
                    "Resource": "*",
                },
                {
                    "Sid": "SecretsManagerForTerraformState",
                    "Effect": "Allow",
                    "Action": [
                        "secretsmanager:CreateSecret",
                        "secretsmanager:PutSecretValue",
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret",
                        "secretsmanager:TagResource",
                    ],
                    "Resource": "*",
                },
                {
                    "Sid": "CloudWatchLogs",
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogDelivery",
                        "logs:PutRetentionPolicy",
                        "logs:TagLogGroup",
                    ],
                    "Resource": "*",
                },
                {
                    "Sid": "STSAssumeRole",
                    "Effect": "Allow",
                    "Action": ["sts:AssumeRole", "sts:GetCallerIdentity"],
                    "Resource": "*",
                },
            ],
        },
        "trust_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringLike": {
                            "token.actions.githubusercontent.com:sub": "repo:ORG/REPO:*"
                        }
                    },
                }
            ],
        },
        "how_to_create": [
            "aws iam create-user --user-name terraform-deployer",
            "aws iam attach-user-policy --user-name terraform-deployer --policy-arn arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
            "# ... attach remaining managed policies (see attached_policies list)",
            "aws iam put-user-policy --user-name terraform-deployer --policy-name TerraformInlinePolicy --policy-document file://infrastructure/iam/aws/terraform-deployer-policy.json",
            "aws iam create-access-key --user-name terraform-deployer  # → set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY secrets",
            "",
            "# RECOMMENDED: Use OIDC role instead of long-lived keys:",
            "# Replace Principal with GitHub Actions OIDC — see trust_policy above",
        ],
    },

    # ── 2. CI/CD Image Pusher ─────────────────────────────────────────────────
    # Assumed by GitHub Actions during the build-push job in ci.yml.
    # Only needs ECR push — no infra permissions.
    "cicd-image-pusher": {
        "description": "Used by GitHub Actions to push Docker images to ECR after building.",
        "attached_policies": [],
        "inline_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ECRTokenAndPush",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:GetAuthorizationToken",
                    ],
                    "Resource": "*",
                },
                {
                    "Sid": "ECRPush",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:InitiateLayerUpload",
                        "ecr:UploadLayerPart",
                        "ecr:CompleteLayerUpload",
                        "ecr:PutImage",
                        "ecr:BatchGetImage",
                        "ecr:GetDownloadUrlForLayer",
                    ],
                    "Resource": "arn:aws:ecr:REGION:ACCOUNT_ID:repository/APP_NAME",
                },
            ],
        },
        "trust_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringLike": {
                            "token.actions.githubusercontent.com:sub": "repo:ORG/REPO:ref:refs/heads/*"
                        }
                    },
                }
            ],
        },
        "how_to_create": [
            "aws iam create-role --role-name cicd-image-pusher --assume-role-policy-document file://infrastructure/iam/aws/cicd-image-pusher-trust.json",
            "aws iam put-role-policy --role-name cicd-image-pusher --policy-name ECRPush --policy-document file://infrastructure/iam/aws/cicd-image-pusher-policy.json",
            "# The role ARN goes into your workflow as the 'role-to-assume' in aws-actions/configure-aws-credentials",
        ],
    },

    # ── 3. EKS Node IAM Role ──────────────────────────────────────────────────
    # Attached to the EKS managed node group.  Gives worker nodes the minimum
    # permissions they need to join the cluster and pull images.
    "eks-node-role": {
        "description": "IAM role for EKS worker nodes. AWS-managed policies only — no custom permissions needed.",
        "attached_policies": [
            "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
            "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
            "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
            "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
        ],
        "inline_policy": None,
        "trust_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        },
        "how_to_create": [
            "aws iam create-role --role-name eks-node-role --assume-role-policy-document file://infrastructure/iam/aws/eks-node-trust.json",
            "aws iam attach-role-policy --role-name eks-node-role --policy-arn arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
            "aws iam attach-role-policy --role-name eks-node-role --policy-arn arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
            "aws iam attach-role-policy --role-name eks-node-role --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
            "aws iam attach-role-policy --role-name eks-node-role --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
            "# Reference this role ARN in your Terraform aws_eks_node_group resource",
        ],
    },

    # ── 4. External Secrets Operator (ESO) ───────────────────────────────────
    # Kubernetes ServiceAccount (via IRSA) that lets ESO pods read from
    # AWS Secrets Manager to populate Kubernetes Secrets.
    "external-secrets-operator": {
        "description": "Assumed by External Secrets Operator pods via IRSA to read secrets from AWS Secrets Manager.",
        "attached_policies": [],
        "inline_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ReadSecretsManager",
                    "Effect": "Allow",
                    "Action": [
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret",
                        "secretsmanager:ListSecretVersionIds",
                    ],
                    "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:APP_NAME/*",
                },
                {
                    "Sid": "ReadSSMParameters",
                    "Effect": "Allow",
                    "Action": [
                        "ssm:GetParameter",
                        "ssm:GetParameters",
                        "ssm:GetParametersByPath",
                    ],
                    "Resource": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/APP_NAME/*",
                },
            ],
        },
        "trust_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/oidc.eks.REGION.amazonaws.com/id/CLUSTER_OIDC_ID"},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            "oidc.eks.REGION.amazonaws.com/id/CLUSTER_OIDC_ID:sub": "system:serviceaccount:external-secrets:external-secrets-sa"
                        }
                    },
                }
            ],
        },
        "how_to_create": [
            "# 1. Get your EKS OIDC issuer URL:",
            "aws eks describe-cluster --name CLUSTER_NAME --query 'cluster.identity.oidc.issuer' --output text",
            "",
            "# 2. Create the IAM role with IRSA trust policy:",
            "aws iam create-role --role-name external-secrets-operator --assume-role-policy-document file://infrastructure/iam/aws/external-secrets-trust.json",
            "aws iam put-role-policy --role-name external-secrets-operator --policy-name SecretsAccess --policy-document file://infrastructure/iam/aws/external-secrets-policy.json",
            "",
            "# 3. Annotate the Kubernetes ServiceAccount:",
            "kubectl annotate serviceaccount external-secrets-sa -n external-secrets \\",
            "  eks.amazonaws.com/role-arn=arn:aws:iam::ACCOUNT_ID:role/external-secrets-operator",
        ],
    },

    # ── 5. App Workload Role (least-privilege runtime) ───────────────────────
    # Optional IRSA role for your application pods — only if they need to call
    # AWS services at runtime (S3, SQS, DynamoDB, etc).
    "app-workload": {
        "description": "Optional IRSA role for application pods that call AWS services at runtime. Scope to only what your app actually needs.",
        "attached_policies": [],
        "inline_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AppS3Access",
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
                    "Resource": [
                        "arn:aws:s3:::APP_NAME-*",
                        "arn:aws:s3:::APP_NAME-*/*",
                    ],
                },
                {
                    "Sid": "AppSQSAccess",
                    "Effect": "Allow",
                    "Action": ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
                    "Resource": "arn:aws:sqs:REGION:ACCOUNT_ID:APP_NAME-*",
                },
                {
                    "Sid": "AppDynamoDBAccess",
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
                        "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
                    ],
                    "Resource": "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/APP_NAME-*",
                },
            ],
        },
        "trust_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/oidc.eks.REGION.amazonaws.com/id/CLUSTER_OIDC_ID"},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            "oidc.eks.REGION.amazonaws.com/id/CLUSTER_OIDC_ID:sub": "system:serviceaccount:APP_NAME:APP_NAME-sa"
                        }
                    },
                }
            ],
        },
        "how_to_create": [
            "aws iam create-role --role-name app-workload --assume-role-policy-document file://infrastructure/iam/aws/app-workload-trust.json",
            "aws iam put-role-policy --role-name app-workload --policy-name AppPermissions --policy-document file://infrastructure/iam/aws/app-workload-policy.json",
            "kubectl annotate serviceaccount APP_NAME-sa -n APP_NAME \\",
            "  eks.amazonaws.com/role-arn=arn:aws:iam::ACCOUNT_ID:role/app-workload",
        ],
    },
}

# =============================================================================
# GCP IAM BINDINGS (Terraform resource blocks)
# =============================================================================

GCP_POLICIES: Dict[str, Dict[str, Any]] = {

    "terraform-deployer": {
        "description": "Service account used by GitHub Actions to run terraform plan/apply for GKE and networking.",
        "roles": [
            "roles/container.admin",            # GKE cluster create/delete/update
            "roles/compute.admin",              # VPC, subnets, firewall rules, load balancers
            "roles/iam.serviceAccountAdmin",    # Create service accounts for workloads
            "roles/iam.serviceAccountKeyAdmin", # Create SA keys
            "roles/iam.roleAdmin",              # Create custom IAM roles
            "roles/storage.admin",              # GCS for Terraform state bucket
            "roles/dns.admin",                  # Cloud DNS records
            "roles/certificatemanager.editor",  # Managed certificates
            "roles/secretmanager.admin",        # Secret Manager for app secrets
            "roles/artifactregistry.admin",     # Artifact Registry repos
        ],
        "terraform": """\
# Terraform Deployer Service Account
resource "google_service_account" "terraform_deployer" {{
  account_id   = "terraform-deployer"
  display_name = "Terraform Deployer (GitHub Actions)"
  project      = var.project_id
}}

locals {{
  terraform_deployer_roles = [
    "roles/container.admin",
    "roles/compute.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountKeyAdmin",
    "roles/iam.roleAdmin",
    "roles/storage.admin",
    "roles/dns.admin",
    "roles/certificatemanager.editor",
    "roles/secretmanager.admin",
    "roles/artifactregistry.admin",
  ]
}}

resource "google_project_iam_member" "terraform_deployer" {{
  for_each = toset(local.terraform_deployer_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${{google_service_account.terraform_deployer.email}}"
}}

# Workload Identity binding → GitHub Actions OIDC
resource "google_service_account_iam_binding" "terraform_deployer_wi" {{
  service_account_id = google_service_account.terraform_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  members = [
    "principalSet://iam.googleapis.com/${{var.workload_identity_pool}}/attribute.repository/${{var.github_org}}/${{var.repo_name}}",
  ]
}}
""",
        "how_to_create": [
            "gcloud iam service-accounts create terraform-deployer --display-name='Terraform Deployer'",
            "# Grant each role (or use the Terraform block above):",
            "for ROLE in roles/container.admin roles/compute.admin roles/iam.serviceAccountAdmin roles/storage.admin; do",
            "  gcloud projects add-iam-policy-binding PROJECT_ID --member=serviceAccount:terraform-deployer@PROJECT_ID.iam.gserviceaccount.com --role=$ROLE",
            "done",
            "gcloud iam service-accounts keys create terraform-deployer-key.json --iam-account=terraform-deployer@PROJECT_ID.iam.gserviceaccount.com",
            "# Base64-encode the key JSON → set as GCP_SA_KEY secret:",
            "base64 -i terraform-deployer-key.json | gh secret set GCP_SA_KEY --repo ORG/REPO",
        ],
    },

    "cicd-image-pusher": {
        "description": "Service account used by GitHub Actions to push images to Artifact Registry.",
        "roles": [
            "roles/artifactregistry.writer",   # Push images
            "roles/container.developer",       # Deploy to GKE (kubectl apply via ArgoCD)
        ],
        "terraform": """\
resource "google_service_account" "cicd_image_pusher" {{
  account_id   = "cicd-image-pusher"
  display_name = "CI/CD Image Pusher (GitHub Actions)"
  project      = var.project_id
}}

resource "google_project_iam_member" "cicd_image_pusher_registry" {{
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${{google_service_account.cicd_image_pusher.email}}"
}}
""",
        "how_to_create": [
            "gcloud iam service-accounts create cicd-image-pusher --display-name='CI/CD Image Pusher'",
            "gcloud projects add-iam-policy-binding PROJECT_ID \\",
            "  --member=serviceAccount:cicd-image-pusher@PROJECT_ID.iam.gserviceaccount.com \\",
            "  --role=roles/artifactregistry.writer",
        ],
    },

    "gke-node": {
        "description": "Service account for GKE worker nodes. Needs logging, monitoring, and registry read.",
        "roles": [
            "roles/logging.logWriter",
            "roles/monitoring.metricWriter",
            "roles/monitoring.viewer",
            "roles/artifactregistry.reader",
            "roles/storage.objectViewer",
        ],
        "terraform": """\
resource "google_service_account" "gke_node" {{
  account_id   = "gke-node"
  display_name = "GKE Node Service Account"
  project      = var.project_id
}}

locals {{
  gke_node_roles = [
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/artifactregistry.reader",
    "roles/storage.objectViewer",
  ]
}}

resource "google_project_iam_member" "gke_node" {{
  for_each = toset(local.gke_node_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${{google_service_account.gke_node.email}}"
}}
""",
        "how_to_create": [
            "gcloud iam service-accounts create gke-node --display-name='GKE Node SA'",
            "for ROLE in roles/logging.logWriter roles/monitoring.metricWriter roles/artifactregistry.reader; do",
            "  gcloud projects add-iam-policy-binding PROJECT_ID --member=serviceAccount:gke-node@PROJECT_ID.iam.gserviceaccount.com --role=$ROLE",
            "done",
            "# Reference this SA in your google_container_cluster Terraform resource:",
            "# node_config { service_account = google_service_account.gke_node.email }",
        ],
    },

    "external-secrets": {
        "description": "Workload Identity SA for External Secrets Operator to read from GCP Secret Manager.",
        "roles": [
            "roles/secretmanager.secretAccessor",
        ],
        "terraform": """\
resource "google_service_account" "external_secrets" {{
  account_id   = "external-secrets"
  display_name = "External Secrets Operator"
  project      = var.project_id
}}

resource "google_project_iam_member" "external_secrets_sm" {{
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${{google_service_account.external_secrets.email}}"
}}

# Workload Identity binding → Kubernetes ServiceAccount
resource "google_service_account_iam_binding" "external_secrets_wi" {{
  service_account_id = google_service_account.external_secrets.name
  role               = "roles/iam.workloadIdentityUser"
  members = [
    "serviceAccount:${{var.project_id}}.svc.id.goog[external-secrets/external-secrets-sa]",
  ]
}}
""",
        "how_to_create": [
            "gcloud iam service-accounts create external-secrets --display-name='External Secrets Operator'",
            "gcloud projects add-iam-policy-binding PROJECT_ID \\",
            "  --member=serviceAccount:external-secrets@PROJECT_ID.iam.gserviceaccount.com \\",
            "  --role=roles/secretmanager.secretAccessor",
            "# Annotate Kubernetes SA:",
            "kubectl annotate serviceaccount external-secrets-sa -n external-secrets \\",
            "  iam.gke.io/gcp-service-account=external-secrets@PROJECT_ID.iam.gserviceaccount.com",
        ],
    },
}

# =============================================================================
# AZURE IAM (Service Principals + Role Assignments)
# =============================================================================

AZURE_POLICIES: Dict[str, Dict[str, Any]] = {

    "terraform-deployer": {
        "description": "Service principal used by GitHub Actions to run terraform plan/apply for AKS and networking.",
        "roles": [
            "Contributor",                # Create/modify/delete most resources
            "User Access Administrator",  # Assign roles to managed identities
            "Key Vault Administrator",    # Manage Key Vault secrets for TF state
        ],
        "scope": "Subscription or Resource Group",
        "how_to_create": [
            "# Create service principal with Contributor on subscription:",
            "az ad sp create-for-rbac --name terraform-deployer --role Contributor \\",
            "  --scopes /subscriptions/SUBSCRIPTION_ID \\",
            "  --sdk-auth > terraform-deployer-credentials.json",
            "",
            "# Grant User Access Administrator (for creating role assignments in TF):",
            "SP_OID=$(az ad sp show --id http://terraform-deployer --query objectId -o tsv)",
            "az role assignment create --assignee $SP_OID \\",
            "  --role 'User Access Administrator' \\",
            "  --scope /subscriptions/SUBSCRIPTION_ID",
            "",
            "# Set the credentials as GitHub secret:",
            "gh secret set AZURE_CREDENTIALS --body \"$(cat terraform-deployer-credentials.json)\" --repo ORG/REPO",
            "",
            "# IMPORTANT: The JSON output is the full AZURE_CREDENTIALS secret value.",
            "# It contains clientId, clientSecret, subscriptionId, tenantId.",
        ],
        "arm_role": {
            "Name": "Terraform Deployer",
            "Description": "Custom role for Terraform to manage AKS, networking, ACR, and Key Vault.",
            "Actions": [
                "Microsoft.ContainerService/*",
                "Microsoft.Network/*",
                "Microsoft.Compute/*",
                "Microsoft.ContainerRegistry/*",
                "Microsoft.KeyVault/*",
                "Microsoft.ManagedIdentity/*",
                "Microsoft.Authorization/roleAssignments/*",
                "Microsoft.Resources/subscriptions/resourceGroups/*",
                "Microsoft.OperationsManagement/*",
                "Microsoft.OperationalInsights/*",
            ],
            "AssignableScopes": ["/subscriptions/SUBSCRIPTION_ID"],
        },
    },

    "cicd-image-pusher": {
        "description": "Service principal used by GitHub Actions to push images to Azure Container Registry.",
        "roles": ["AcrPush"],
        "scope": "ACR resource",
        "how_to_create": [
            "ACR_ID=$(az acr show --name ACR_NAME --query id --output tsv)",
            "az ad sp create-for-rbac --name cicd-image-pusher \\",
            "  --role AcrPush \\",
            "  --scopes $ACR_ID > cicd-pusher.json",
            "gh secret set AZURE_CLIENT_ID     --body \"$(jq -r .clientId cicd-pusher.json)\"     --repo ORG/REPO",
            "gh secret set AZURE_CLIENT_SECRET --body \"$(jq -r .clientSecret cicd-pusher.json)\" --repo ORG/REPO",
            "gh secret set AZURE_TENANT_ID     --body \"$(jq -r .tenantId cicd-pusher.json)\"     --repo ORG/REPO",
        ],
    },

    "aks-managed-identity": {
        "description": "System-assigned managed identity of AKS nodes. Needs to pull images from ACR.",
        "roles": ["AcrPull"],
        "scope": "ACR resource",
        "how_to_create": [
            "# After AKS cluster is created, get its kubelet identity:",
            "KUBELET_ID=$(az aks show --name AKS_CLUSTER --resource-group RG_NAME \\",
            "  --query identityProfile.kubeletidentity.objectId -o tsv)",
            "",
            "ACR_ID=$(az acr show --name ACR_NAME --query id --output tsv)",
            "az role assignment create --assignee $KUBELET_ID --role AcrPull --scope $ACR_ID",
            "",
            "# Or let Terraform handle it:",
            "# resource 'azurerm_role_assignment' 'aks_acr_pull' { ... }",
        ],
    },

    "external-secrets": {
        "description": "Managed identity used by External Secrets Operator to read from Azure Key Vault.",
        "roles": ["Key Vault Secrets User"],
        "scope": "Key Vault resource",
        "how_to_create": [
            "# Create User-Assigned Managed Identity:",
            "az identity create --name external-secrets-identity --resource-group RG_NAME",
            "",
            "# Get the principal ID:",
            "PRINCIPAL_ID=$(az identity show --name external-secrets-identity \\",
            "  --resource-group RG_NAME --query principalId --output tsv)",
            "",
            "# Grant Key Vault Secrets User role:",
            "KV_ID=$(az keyvault show --name KEY_VAULT_NAME --query id --output tsv)",
            "az role assignment create --assignee $PRINCIPAL_ID \\",
            "  --role 'Key Vault Secrets User' --scope $KV_ID",
            "",
            "# Annotate the Kubernetes ServiceAccount:",
            "kubectl annotate serviceaccount external-secrets-sa -n external-secrets \\",
            "  azure.workload.identity/client-id=$(az identity show --name external-secrets-identity --query clientId -o tsv)",
        ],
    },
}


# =============================================================================
# IAM Policies Markdown Guide Template
# =============================================================================

IAM_GUIDE_TEMPLATE = """\
# IAM Service Accounts & Policies — {app_name}

> Generated by ForgeFlow · Cloud: **{cloud}**
> Every service account listed here is required for the full CI → Test → CD lifecycle.

---

## Service Account Matrix

| # | Account | Used By | Permissions Level | How Created |
|---|---------|---------|-------------------|-------------|
{sa_matrix}

---

## Complete Setup Order

```
1. terraform-deployer   ← create FIRST (CI uses this to build infra)
2. cicd-image-pusher    ← create after ECR/ACR/GCR exists
3. {node_role_name}     ← Terraform creates this automatically
4. external-secrets     ← create after cluster exists (post-terraform)
5. app-workload         ← optional, only if pods call cloud services
```

---

{service_account_sections}

---

## Terraform State Backend

Before running `terraform apply`, create the state backend manually:

{state_backend_setup}

---

## Minimum Permissions Checklist

Run this to verify all service accounts exist and have correct permissions:

```bash
bash scripts/verify-iam.sh
```

The script is generated at `scripts/verify-iam.sh` alongside this guide.

---

## Security Best Practices

- **Never use root/owner credentials** in CI/CD. Always use scoped service accounts.
- **Use OIDC federation** (GitHub → cloud OIDC) instead of long-lived access keys wherever possible.
- **Rotate keys** every 90 days for any service account that uses key-based auth.
- **Scope resources**: Replace `*` in ARNs/resources with your specific account ID, region, and app name before applying.
- **Least-privilege**: The `app-workload` role only grants what your app actually needs — remove any service not in use.
- **Audit logs**: Enable CloudTrail (AWS), Cloud Audit Logs (GCP), or Azure Monitor for all service account actions.

---

*Generated by ForgeFlow IAM Agent — review all placeholder values (ACCOUNT_ID, REGION, APP_NAME, etc.) before applying.*
"""


# =============================================================================
# Agent class
# =============================================================================

class IAMAgent(BaseAgent):
    """
    Generates complete IAM service account documentation and policy files
    for every account needed in the ForgeFlow CI/CD pipeline.

    Outputs:
      docs/IAM_POLICIES.md                  — Full human-readable guide
      infrastructure/iam/aws/               — AWS IAM JSON policy files
      infrastructure/iam/gcp/               — GCP Terraform resource blocks
      infrastructure/iam/azure/             — Azure ARM role definition JSONs
      scripts/verify-iam.sh                 — Verification script
    """

    def __init__(self):
        super().__init__(
            name="iam_agent",
            description="Generate IAM service account docs + policy files for all clouds"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate IAM policy docs and files.

        Params:
            path       : repo root path (required)
            cloud      : aws | gcp | azure (auto-detected if omitted)
            app_name   : application name (default: folder name)
            overwrite  : overwrite existing files (default: False)
        """
        import json as _json

        repo_path = Path(params.get("path", ".") or ".").resolve()
        overwrite  = params.get("overwrite", False)
        app_name   = params.get("app_name") or repo_path.name
        cloud      = (params.get("cloud") or self._detect_cloud(repo_path)).lower()

        self.log(f"Generating IAM policies for cloud={cloud} app={app_name}")

        actions: List[Dict[str, Any]] = []

        # ── docs/IAM_POLICIES.md ──────────────────────────────────────────────
        docs_dir = repo_path / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        guide = self._render_guide(app_name, cloud)
        actions.append(self._safe_write(docs_dir / "IAM_POLICIES.md", guide, overwrite))

        # ── Cloud-specific policy files ───────────────────────────────────────
        if cloud == "aws":
            actions += self._write_aws_policies(repo_path, app_name, overwrite)
        elif cloud == "gcp":
            actions += self._write_gcp_policies(repo_path, app_name, overwrite)
        elif cloud == "azure":
            actions += self._write_azure_policies(repo_path, app_name, overwrite)

        # ── scripts/verify-iam.sh ─────────────────────────────────────────────
        scripts_dir = repo_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        verify_script = self._render_verify_script(cloud, app_name)
        a = self._safe_write(scripts_dir / "verify-iam.sh", verify_script, overwrite)
        if a.get("action") in ("created", "updated"):
            try:
                (scripts_dir / "verify-iam.sh").chmod(0o755)
            except Exception:
                pass
        actions.append(a)

        created = [x["file"] for x in actions if x.get("action") == "created"]
        updated = [x["file"] for x in actions if x.get("action") == "updated"]

        findings = [
            f"🔐 IAM Policies generated for {cloud.upper()}",
            "",
            "Service accounts covered:",
        ]
        if cloud == "aws":
            for name, info in AWS_POLICIES.items():
                findings.append(f"  • {name}: {info['description'][:70]}")
        elif cloud == "gcp":
            for name, info in GCP_POLICIES.items():
                findings.append(f"  • {name}: {info['description'][:70]}")
        elif cloud == "azure":
            for name, info in AZURE_POLICIES.items():
                findings.append(f"  • {name}: {info['description'][:70]}")

        findings += [
            "",
            f"✅ Created: {len(created)} files" if created else "",
            f"♻️  Updated: {len(updated)} files" if updated else "",
            "",
            "Next steps:",
            "  1. Review docs/IAM_POLICIES.md — replace placeholder values",
            "  2. Run: bash scripts/verify-iam.sh (after cluster is up)",
            "  3. Apply infrastructure/iam/ Terraform blocks or CLI commands",
        ]
        findings = [f for f in findings if f != ""]

        result = self.create_result(
            status="success",
            summary=f"IAM policies: {len(created)} created, {len(updated)} updated — {cloud.upper()} · {app_name}",
            data={
                "cloud": cloud,
                "app_name": app_name,
                "files_created": created,
                "files_updated": updated,
                "guide": str(docs_dir / "IAM_POLICIES.md"),
            },
            findings=findings,
            actions=actions,
        )
        self.save_result(result)
        return result

    # ── AWS file writers ───────────────────────────────────────────────────────

    def _write_aws_policies(self, repo_path: Path, app_name: str, overwrite: bool) -> List[Dict]:
        import json as _json
        iam_dir = repo_path / "infrastructure" / "iam" / "aws"
        iam_dir.mkdir(parents=True, exist_ok=True)
        actions = []

        for sa_name, info in AWS_POLICIES.items():
            # Inline policy JSON
            if info.get("inline_policy"):
                content = _json.dumps(info["inline_policy"], indent=2).replace("APP_NAME", app_name)
                actions.append(self._safe_write(
                    iam_dir / f"{sa_name}-policy.json", content, overwrite
                ))
            # Trust policy JSON
            if info.get("trust_policy"):
                content = _json.dumps(info["trust_policy"], indent=2).replace("APP_NAME", app_name)
                actions.append(self._safe_write(
                    iam_dir / f"{sa_name}-trust.json", content, overwrite
                ))

        # README for the IAM dir
        readme = self._render_aws_readme(app_name)
        actions.append(self._safe_write(iam_dir / "README.md", readme, overwrite))
        return actions

    def _write_gcp_policies(self, repo_path: Path, app_name: str, overwrite: bool) -> List[Dict]:
        iam_dir = repo_path / "infrastructure" / "iam" / "gcp"
        iam_dir.mkdir(parents=True, exist_ok=True)
        actions = []
        for sa_name, info in GCP_POLICIES.items():
            if info.get("terraform"):
                content = info["terraform"].format(app_name=app_name)
                actions.append(self._safe_write(
                    iam_dir / f"{sa_name}.tf", content, overwrite
                ))
        readme = self._render_gcp_readme(app_name)
        actions.append(self._safe_write(iam_dir / "README.md", readme, overwrite))
        return actions

    def _write_azure_policies(self, repo_path: Path, app_name: str, overwrite: bool) -> List[Dict]:
        import json as _json
        iam_dir = repo_path / "infrastructure" / "iam" / "azure"
        iam_dir.mkdir(parents=True, exist_ok=True)
        actions = []
        for sa_name, info in AZURE_POLICIES.items():
            if info.get("arm_role"):
                content = _json.dumps(info["arm_role"], indent=2)
                actions.append(self._safe_write(
                    iam_dir / f"{sa_name}-role.json", content, overwrite
                ))
        readme = self._render_azure_readme(app_name)
        actions.append(self._safe_write(iam_dir / "README.md", readme, overwrite))
        return actions

    # ── Guide renderer ─────────────────────────────────────────────────────────

    def _render_guide(self, app_name: str, cloud: str) -> str:
        policies = {"aws": AWS_POLICIES, "gcp": GCP_POLICIES, "azure": AZURE_POLICIES}.get(
            cloud, AWS_POLICIES
        )
        node_role = {"aws": "eks-node-role", "gcp": "gke-node", "azure": "aks-managed-identity"}.get(cloud, "node-role")

        matrix_rows = []
        for i, (name, info) in enumerate(policies.items(), 1):
            level = "Read-only" if "reader" in name or "node" in name else \
                    "Write (infra)" if "terraform" in name else \
                    "Write (registry)" if "pusher" in name else \
                    "Read secrets" if "secret" in name else "Scoped"
            how = "Terraform (auto)" if "node" in name or "managed" in name else "Manual (one-time)"
            matrix_rows.append(f"| {i} | `{name}` | {info['description'][:55]}... | {level} | {how} |")

        sections = []
        for sa_name, info in policies.items():
            section = [f"## `{sa_name}`\n"]
            section.append(f"**Purpose:** {info['description']}\n")

            if cloud == "aws":
                if info.get("attached_policies"):
                    section.append("**Managed policies to attach:**")
                    for p in info["attached_policies"]:
                        section.append(f"- `{p}`")
                    section.append("")
                if info.get("inline_policy"):
                    section.append(f"**Inline policy:** `infrastructure/iam/aws/{sa_name}-policy.json`\n")
                if info.get("trust_policy"):
                    section.append(f"**Trust policy:** `infrastructure/iam/aws/{sa_name}-trust.json`\n")

            elif cloud == "gcp":
                if info.get("roles"):
                    section.append("**IAM roles required:**")
                    for r in info["roles"]:
                        section.append(f"- `{r}`")
                    section.append("")
                if info.get("terraform"):
                    section.append(f"**Terraform:** `infrastructure/iam/gcp/{sa_name}.tf`\n")

            elif cloud == "azure":
                if info.get("roles"):
                    section.append("**Azure roles required:**")
                    for r in info["roles"]:
                        section.append(f"- `{r}` (scope: {info.get('scope','subscription')})")
                    section.append("")

            if info.get("how_to_create"):
                section.append("**One-time setup:**")
                section.append("```bash")
                section += info["how_to_create"]
                section.append("```")

            sections.append("\n".join(section))

        state_setup = self._render_state_backend(cloud, app_name)

        return IAM_GUIDE_TEMPLATE.format(
            app_name=app_name,
            cloud=cloud.upper(),
            sa_matrix="\n".join(matrix_rows),
            node_role_name=node_role,
            service_account_sections="\n\n---\n\n".join(sections),
            state_backend_setup=state_setup,
        )

    def _render_state_backend(self, cloud: str, app_name: str) -> str:
        if cloud == "aws":
            return f"""\
```bash
# S3 bucket for Terraform state
aws s3 mb s3://{app_name}-tf-state --region YOUR_REGION
aws s3api put-bucket-versioning --bucket {app_name}-tf-state --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket {app_name}-tf-state \\
  --server-side-encryption-configuration '{{"Rules":[{{"ApplyServerSideEncryptionByDefault":{{"SSEAlgorithm":"AES256"}}}}]}}'

# DynamoDB table for state locking
aws dynamodb create-table --table-name {app_name}-tf-lock \\
  --attribute-definitions AttributeName=LockID,AttributeType=S \\
  --key-schema AttributeName=LockID,KeyType=HASH \\
  --billing-mode PAY_PER_REQUEST
```"""
        elif cloud == "gcp":
            return f"""\
```bash
# GCS bucket for Terraform state
gsutil mb -p PROJECT_ID gs://{app_name}-tf-state
gsutil versioning set on gs://{app_name}-tf-state
gsutil uniformbucketlevelaccess set on gs://{app_name}-tf-state
```"""
        else:
            return f"""\
```bash
# Azure Storage Account for Terraform state
az storage account create --name {app_name[:12]}tfstate --resource-group RG_NAME \\
  --location eastus --sku Standard_LRS
az storage container create --name tfstate \\
  --account-name {app_name[:12]}tfstate
```"""

    def _render_verify_script(self, cloud: str, app_name: str) -> str:
        if cloud == "aws":
            return f"""\
#!/usr/bin/env bash
# Verify IAM service accounts exist — {app_name} (AWS)
set -euo pipefail

echo "Verifying IAM service accounts for {app_name}..."
FAIL=0

check_user() {{
  local name=$1
  if aws iam get-user --user-name "$name" &>/dev/null; then
    echo "  ✅ IAM user: $name"
  else
    echo "  ❌ MISSING: $name"
    FAIL=1
  fi
}}

check_role() {{
  local name=$1
  if aws iam get-role --role-name "$name" &>/dev/null; then
    echo "  ✅ IAM role: $name"
  else
    echo "  ❌ MISSING: $name"
    FAIL=1
  fi
}}

check_user terraform-deployer
check_role cicd-image-pusher
check_role eks-node-role
check_role external-secrets-operator

if [[ $FAIL -eq 0 ]]; then
  echo ""
  echo "✅ All IAM accounts verified."
else
  echo ""
  echo "❌ Missing accounts. See docs/IAM_POLICIES.md for setup instructions."
  exit 1
fi
"""
        elif cloud == "gcp":
            return f"""\
#!/usr/bin/env bash
# Verify GCP service accounts exist — {app_name}
set -euo pipefail

PROJECT_ID="${{1:-$(gcloud config get-value project)}}"
echo "Verifying GCP service accounts in project: $PROJECT_ID"
FAIL=0

check_sa() {{
  local name=$1
  if gcloud iam service-accounts describe "$name@$PROJECT_ID.iam.gserviceaccount.com" &>/dev/null; then
    echo "  ✅ SA: $name"
  else
    echo "  ❌ MISSING: $name@$PROJECT_ID.iam.gserviceaccount.com"
    FAIL=1
  fi
}}

check_sa terraform-deployer
check_sa cicd-image-pusher
check_sa gke-node
check_sa external-secrets

if [[ $FAIL -eq 0 ]]; then echo "✅ All service accounts verified."; else echo "❌ See docs/IAM_POLICIES.md"; exit 1; fi
"""
        else:
            return f"""\
#!/usr/bin/env bash
# Verify Azure service principals exist — {app_name}
set -euo pipefail
echo "Verifying Azure service principals..."
FAIL=0

check_sp() {{
  local name=$1
  if az ad sp show --id "http://$name" &>/dev/null; then
    echo "  ✅ SP: $name"
  else
    echo "  ❌ MISSING: $name"
    FAIL=1
  fi
}}

check_sp terraform-deployer
check_sp cicd-image-pusher

if [[ $FAIL -eq 0 ]]; then echo "✅ All service principals verified."; else echo "❌ See docs/IAM_POLICIES.md"; exit 1; fi
"""

    def _render_aws_readme(self, app_name: str) -> str:
        return f"""\
# AWS IAM Policy Files — {app_name}

Each `*-policy.json` file is the inline policy for its service account.
Each `*-trust.json` file is the trust/assume-role policy.

## Apply order
1. `eks-node-role-*`        — needed by Terraform when creating the node group
2. `terraform-deployer-*`   — needed before running `terraform apply`
3. `cicd-image-pusher-*`    — needed before first CI run
4. `external-secrets-*`     — needed after cluster is up

## Applying via CLI
```bash
aws iam create-role --role-name ROLE_NAME --assume-role-policy-document file://ROLE-trust.json
aws iam put-role-policy --role-name ROLE_NAME --policy-name Policy --policy-document file://ROLE-policy.json
```

Replace placeholder values: `ACCOUNT_ID`, `REGION`, `APP_NAME`, `CLUSTER_OIDC_ID`, `ORG`, `REPO`.
"""

    def _render_gcp_readme(self, app_name: str) -> str:
        return f"""\
# GCP IAM Terraform Files — {app_name}

Each `.tf` file defines a service account and its IAM bindings.
Include these in your root Terraform module or a dedicated `iam` module.

## Variables required
- `var.project_id`            — GCP project ID
- `var.workload_identity_pool` — WIF pool for GitHub Actions OIDC
- `var.github_org`            — GitHub organisation/user name
- `var.repo_name`             — GitHub repository name

## Apply
```bash
cd infrastructure/iam/gcp
terraform init && terraform apply
```
"""

    def _render_azure_readme(self, app_name: str) -> str:
        return f"""\
# Azure IAM Role Definitions — {app_name}

Each `*-role.json` is an ARM custom role definition.

## Apply
```bash
az role definition create --role-definition @terraform-deployer-role.json
```

Replace `SUBSCRIPTION_ID` with your Azure subscription ID.
"""

    # ── Detection helpers ──────────────────────────────────────────────────────

    def _detect_cloud(self, repo_path: Path) -> str:
        for fp in list(repo_path.glob("**/*.tf"))[:20]:
            try:
                text = fp.read_text(errors="ignore").lower()
                if "aws_" in text or "eks" in text:
                    return "aws"
                if "google_" in text or "gke" in text:
                    return "gcp"
                if "azurerm_" in text or "aks" in text:
                    return "azure"
            except Exception:
                pass
        return "aws"
