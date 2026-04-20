# AWS IAM Policy Files — sevaforge_unified

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
