"""
SevaForge Secrets Analyzer Agent

Analyzes code for required secrets, detects cloud provider from infrastructure
files, generates deployment guides and bootstrap scripts for secret management.

Capabilities:
  - scan_secrets_needed:        Scan code for all required secrets and env vars
  - generate_bootstrap_script:  Create shell scripts to bootstrap secret stores
  - generate_deployment_guide:  Generate deployment-ready secret management guide
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    BaseAgent,
    AgentConfig,
    AgentCapability,
    AgentExecutionContext,
)

logger = logging.getLogger(__name__)


# -- Cloud-specific secret patterns ------------------------------------------

_SECRET_NEED_PATTERNS: dict[str, tuple[str, str, str]] = {
    # (regex, cloud_provider, description)
    "aws_access_key_id": (
        r"(?i)AWS_ACCESS_KEY_ID\s*[=:]",
        "aws",
        "AWS access key ID",
    ),
    "aws_secret_access_key": (
        r"(?i)AWS_SECRET_ACCESS_KEY\s*[=:]",
        "aws",
        "AWS secret access key",
    ),
    "aws_region": (
        r"(?i)AWS_(?:DEFAULT_)?REGION\s*[=:]",
        "aws",
        "AWS region configuration",
    ),
    "gcp_service_account": (
        r"(?i)GOOGLE_APPLICATION_CREDENTIALS\s*[=:]",
        "gcp",
        "GCP service account key file",
    ),
    "gcp_project": (
        r"(?i)(?:GCP|GOOGLE|GCLOUD)_PROJECT(?:_ID)?\s*[=:]",
        "gcp",
        "GCP project identifier",
    ),
    "azure_client_id": (
        r"(?i)AZURE_CLIENT_ID\s*[=:]",
        "azure",
        "Azure service principal client ID",
    ),
    "azure_client_secret": (
        r"(?i)AZURE_CLIENT_SECRET\s*[=:]",
        "azure",
        "Azure service principal secret",
    ),
    "azure_tenant_id": (
        r"(?i)AZURE_TENANT_ID\s*[=:]",
        "azure",
        "Azure Active Directory tenant",
    ),
    "database_url": (
        r"(?i)DATABASE_URL\s*[=:]",
        "generic",
        "Primary database connection string",
    ),
    "redis_url": (
        r"(?i)REDIS_URL\s*[=:]",
        "generic",
        "Redis connection string",
    ),
    "jwt_secret": (
        r"(?i)JWT_SECRET(?:_KEY)?\s*[=:]",
        "generic",
        "JWT signing secret",
    ),
    "api_key_generic": (
        r"(?i)(?:API_KEY|APIKEY)\s*[=:]",
        "generic",
        "API key (service-specific)",
    ),
    "smtp_password": (
        r"(?i)SMTP_(?:PASSWORD|PASS)\s*[=:]",
        "generic",
        "SMTP / email service password",
    ),
    "stripe_secret": (
        r"(?i)STRIPE_SECRET_KEY\s*[=:]",
        "generic",
        "Stripe payment secret key",
    ),
    "sentry_dsn": (
        r"(?i)SENTRY_DSN\s*[=:]",
        "generic",
        "Sentry error tracking DSN",
    ),
    "openai_api_key": (
        r"(?i)OPENAI_API_KEY\s*[=:]",
        "generic",
        "OpenAI API key",
    ),
    "anthropic_api_key": (
        r"(?i)ANTHROPIC_API_KEY\s*[=:]",
        "generic",
        "Anthropic API key",
    ),
    "docker_registry_pass": (
        r"(?i)(?:DOCKER|REGISTRY)_PASSWORD\s*[=:]",
        "generic",
        "Docker / container registry password",
    ),
}

# -- Cloud provider detection from IaC files ---------------------------------

_CLOUD_DETECT_PATTERNS: dict[str, list[str]] = {
    "aws": [
        r'provider\s+"aws"',
        r"aws_",
        r"amazonaws\.com",
        r"uses:\s*aws-actions/",
    ],
    "gcp": [
        r'provider\s+"google"',
        r"google_",
        r"googleapis\.com",
        r"uses:\s*google-github-actions/",
    ],
    "azure": [
        r'provider\s+"azurerm"',
        r"azurerm_",
        r"azure\.com",
        r"uses:\s*azure/",
    ],
}

# -- Secret manager recommendations per cloud --------------------------------

_SECRET_MANAGER_MAP: dict[str, dict[str, str]] = {
    "aws": {
        "service": "AWS Secrets Manager",
        "cli": "aws secretsmanager create-secret --name {name} --secret-string '{value}'",
        "tf_resource": "aws_secretsmanager_secret",
    },
    "gcp": {
        "service": "Google Secret Manager",
        "cli": 'printf "{value}" | gcloud secrets create {name} --data-file=-',
        "tf_resource": "google_secret_manager_secret",
    },
    "azure": {
        "service": "Azure Key Vault",
        "cli": "az keyvault secret set --vault-name $VAULT --name {name} --value '{value}'",
        "tf_resource": "azurerm_key_vault_secret",
    },
    "generic": {
        "service": "HashiCorp Vault / dotenv",
        "cli": "vault kv put secret/{name} value='{value}'",
        "tf_resource": "vault_generic_secret",
    },
}


class SecretsAnalyzerAgent(BaseAgent):
    """
    Secrets analysis agent.

    Scans code and infrastructure files to identify every secret a project
    needs, detects the target cloud provider, and produces deployment-ready
    bootstrap scripts and secret management guides.
    """

    SYSTEM_PROMPT = (
        "You are a DevSecOps engineer specializing in secrets management and "
        "secure deployments. When reviewing code, identify every secret, "
        "credential, and sensitive configuration value required. Recommend "
        "the appropriate secrets management strategy based on the target "
        "cloud provider. Always prefer managed secret stores over .env files."
    )

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="secrets-analyzer",
            name="Secrets Analyzer Agent",
            description="Analyzes code for required secrets, generates deployment guides and bootstrap scripts",
            version="1.0.0",
            capabilities=[
                AgentCapability(
                    name="scan_secrets_needed",
                    description="Scan code for all required secrets and environment variables",
                    input_schema={"code": "str", "language": "str"},
                    output_schema={"secrets": "list", "cloud_provider": "str"},
                ),
                AgentCapability(
                    name="generate_bootstrap_script",
                    description="Create shell script to bootstrap secrets in a cloud secret store",
                    input_schema={"secrets": "list", "cloud_provider": "str"},
                    output_schema={"script": "str"},
                ),
                AgentCapability(
                    name="generate_deployment_guide",
                    description="Generate a deployment-ready secret management guide",
                    input_schema={"code": "str"},
                    output_schema={"guide": "str", "recommendations": "list"},
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["secrets", "security", "deployment", "devops"],
        ))

    # -- execute --------------------------------------------------------------

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Execute secrets analysis.

        ctx.input: source code, config files, or IaC to analyze
        ctx.params:
          - action: "scan" | "bootstrap" | "guide"  (default "scan")
          - language: str
          - cloud_provider: str  (override auto-detection)
        """
        code = ctx.input
        action = ctx.params.get("action", "scan")
        language = ctx.params.get("language", "python")

        # Phase 1 -- pattern-based secret detection
        secrets_found = self._scan_secrets_needed(code)
        cloud_provider = ctx.params.get(
            "cloud_provider", self._detect_cloud_provider(code),
        )

        if action == "bootstrap":
            return self._generate_bootstrap_script(secrets_found, cloud_provider)

        if action == "guide":
            return await self._generate_deployment_guide(
                ctx, code, secrets_found, cloud_provider, language,
            )

        # Default: scan
        # Phase 2 -- LLM enrichment
        prompt = self._build_scan_prompt(code, language, secrets_found, cloud_provider)
        try:
            llm_response = await self.call_llm(ctx, prompt)
            llm_recommendations = self._parse_recommendations(llm_response.content)
            model_used = llm_response.model
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        except Exception as exc:
            logger.warning("LLM unavailable for secrets analysis: %s", exc)
            llm_recommendations = []
            model_used = "pattern-only"
            input_tokens = 0
            output_tokens = 0

        manager_info = _SECRET_MANAGER_MAP.get(cloud_provider, _SECRET_MANAGER_MAP["generic"])

        return {
            "secrets": secrets_found,
            "total_secrets": len(secrets_found),
            "cloud_provider": cloud_provider,
            "recommended_store": manager_info["service"],
            "recommendations": llm_recommendations,
            "language": language,
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": 0.85 if model_used != "pattern-only" else 0.6,
        }

    # -- Pattern scanning -----------------------------------------------------

    def _scan_secrets_needed(self, code: str) -> list[dict[str, Any]]:
        """Scan code for references to secrets / env vars."""
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        lines = code.splitlines()

        for secret_id, (pattern, cloud, description) in _SECRET_NEED_PATTERNS.items():
            regex = re.compile(pattern)
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    if secret_id in seen:
                        continue
                    seen.add(secret_id)
                    found.append({
                        "id": secret_id,
                        "cloud": cloud,
                        "description": description,
                        "line": line_num,
                        "evidence": line.strip()[:120],
                        "source": "pattern",
                    })

        # Also catch generic os.environ / os.getenv references
        env_regex = re.compile(r"os\.(?:environ|getenv)\s*[\[(]\s*['\"]([^'\"]+)['\"]")
        for line_num, line in enumerate(lines, 1):
            for m in env_regex.finditer(line):
                var_name = m.group(1)
                if var_name not in seen:
                    seen.add(var_name)
                    found.append({
                        "id": var_name.lower(),
                        "cloud": "generic",
                        "description": f"Environment variable: {var_name}",
                        "line": line_num,
                        "evidence": line.strip()[:120],
                        "source": "pattern",
                    })

        return found

    # -- Cloud provider detection ---------------------------------------------

    def _detect_cloud_provider(self, code: str) -> str:
        """Detect the primary cloud provider from IaC / workflow content."""
        scores: dict[str, int] = {"aws": 0, "gcp": 0, "azure": 0}
        for provider, patterns in _CLOUD_DETECT_PATTERNS.items():
            for pattern in patterns:
                scores[provider] += len(re.findall(pattern, code, re.IGNORECASE))

        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "generic"

    # -- Bootstrap script generation ------------------------------------------

    def _generate_bootstrap_script(
        self, secrets: list[dict[str, Any]], cloud_provider: str,
    ) -> dict[str, Any]:
        """Generate a shell script that bootstraps required secrets."""
        manager = _SECRET_MANAGER_MAP.get(cloud_provider, _SECRET_MANAGER_MAP["generic"])
        lines = [
            "#!/usr/bin/env bash",
            f"# Bootstrap secrets using {manager['service']}",
            "# Generated by SevaForge Secrets Analyzer Agent",
            "set -euo pipefail",
            "",
        ]

        for secret in secrets:
            name = secret["id"].upper().replace("-", "_")
            lines.append(f"# {secret['description']}")
            cmd = manager["cli"].format(name=name, value="<REPLACE_ME>")
            lines.append(cmd)
            lines.append("")

        script = "\n".join(lines)
        return {
            "script": script,
            "cloud_provider": cloud_provider,
            "secret_store": manager["service"],
            "total_secrets": len(secrets),
            "model_used": "template",
            "input_tokens": 0,
            "output_tokens": 0,
            "confidence": 0.95,
        }

    # -- Deployment guide (LLM-enhanced) --------------------------------------

    async def _generate_deployment_guide(
        self,
        ctx: AgentExecutionContext,
        code: str,
        secrets: list[dict[str, Any]],
        cloud_provider: str,
        language: str,
    ) -> dict[str, Any]:
        """Generate a full deployment guide for secret management."""
        manager = _SECRET_MANAGER_MAP.get(cloud_provider, _SECRET_MANAGER_MAP["generic"])

        prompt = (
            f"Create a deployment guide for managing {len(secrets)} secrets on "
            f"{cloud_provider.upper()} using {manager['service']}.\n\n"
            f"Secrets required:\n"
        )
        for s in secrets:
            prompt += f"  - {s['id']}: {s['description']}\n"
        prompt += (
            f"\nLanguage: {language}\n"
            f"Code excerpt:\n```\n{code[:2000]}\n```\n\n"
            "Include: setup steps, rotation policy, access control, "
            "CI/CD integration, and monitoring for leaked secrets."
        )

        try:
            llm_response = await self.call_llm(ctx, prompt)
            return {
                "guide": llm_response.content,
                "cloud_provider": cloud_provider,
                "secret_store": manager["service"],
                "secrets": secrets,
                "total_secrets": len(secrets),
                "model_used": llm_response.model,
                "input_tokens": llm_response.input_tokens,
                "output_tokens": llm_response.output_tokens,
                "confidence": 0.85,
            }
        except Exception as exc:
            logger.warning("LLM unavailable for deployment guide: %s", exc)
            return {
                "guide": f"Use {manager['service']} to store {len(secrets)} secrets. "
                         "Rotate credentials every 90 days. Restrict IAM access to production secrets.",
                "cloud_provider": cloud_provider,
                "secret_store": manager["service"],
                "secrets": secrets,
                "total_secrets": len(secrets),
                "model_used": "template-only",
                "input_tokens": 0,
                "output_tokens": 0,
                "confidence": 0.4,
            }

    # -- LLM prompt helpers ---------------------------------------------------

    def _build_scan_prompt(
        self, code: str, language: str,
        secrets: list[dict[str, Any]], cloud_provider: str,
    ) -> str:
        pattern_summary = "\n".join(
            f"  - {s['id']}: {s['description']}" for s in secrets
        ) if secrets else "  (none found by pattern scan)"

        return (
            f"Analyze this {language} code for additional secrets, credentials, and "
            f"sensitive configuration values that the pattern scanner may have missed.\n\n"
            f"Pattern scanner found {len(secrets)} secrets:\n{pattern_summary}\n\n"
            f"Detected cloud provider: {cloud_provider}\n\n"
            f"```{language}\n{code[:4000]}\n```\n\n"
            "For each additional secret found, provide:\n"
            "- Name and description\n"
            "- Why it is sensitive\n"
            "- Recommended secret management strategy"
        )

    def _parse_recommendations(self, text: str) -> list[str]:
        """Extract actionable recommendations from LLM output."""
        recs: list[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped and len(stripped) > 15 and any(
                kw in stripped.lower()
                for kw in ["recommend", "should", "consider", "use", "rotate", "store", "encrypt"]
            ):
                recs.append(stripped.lstrip("- #*0123456789.").strip()[:200])
                if len(recs) >= 10:
                    break
        return recs
