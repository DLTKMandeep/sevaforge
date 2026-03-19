"""
ForgeFlow Stack Suggester
Suggests optimal technology stack based on wizard answers.

Provides intelligent recommendations for:
- Base container images
- Framework versions
- Database configurations
- Infrastructure (Terraform modules)
- CI/CD pipeline configurations
- Monitoring stack
"""
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()


# Base image recommendations
BASE_IMAGES = {
    "python": {
        "default": "python:3.11-slim",
        "alpine": "python:3.11-alpine",
        "debian": "python:3.11-bookworm",
    },
    "nodejs": {
        "default": "node:20-slim",
        "alpine": "node:20-alpine",
        "debian": "node:20-bookworm",
    },
    "typescript": {
        "default": "node:20-slim",
        "alpine": "node:20-alpine",
        "debian": "node:20-bookworm",
    },
    "go": {
        "default": "golang:1.21-alpine",
        "alpine": "golang:1.21-alpine",
        "scratch": "scratch",  # For final stage
    },
    "java": {
        "default": "eclipse-temurin:17-jdk-alpine",
        "debian": "eclipse-temurin:17-jdk-jammy",
    },
    "rust": {
        "default": "rust:1.75-slim",
        "alpine": "rust:1.75-alpine",
        "scratch": "scratch",  # For final stage
    },
}

# Framework version recommendations
FRAMEWORK_VERSIONS = {
    "fastapi": {"version": "0.109.0", "extras": ["uvicorn[standard]>=0.27.0"]},
    "django": {"version": "5.0", "extras": ["gunicorn>=21.0.0"]},
    "flask": {"version": "3.0.0", "extras": ["gunicorn>=21.0.0"]},
    "express": {"version": "4.18.2", "extras": ["helmet", "cors"]},
    "nestjs": {"version": "10.3.0", "extras": ["@nestjs/platform-express"]},
    "fastify": {"version": "4.25.0", "extras": ["@fastify/cors"]},
    "nextjs": {"version": "14.1.0", "extras": ["react", "react-dom"]},
    "gin": {"version": "v1.9.1", "extras": []},
    "echo": {"version": "v4.11.4", "extras": []},
    "fiber": {"version": "v2.52.0", "extras": []},
    "spring-boot": {"version": "3.2.1", "extras": []},
    "quarkus": {"version": "3.6.0", "extras": []},
    "micronaut": {"version": "4.2.0", "extras": []},
    "actix-web": {"version": "4.4.1", "extras": []},
    "axum": {"version": "0.7.3", "extras": []},
    "rocket": {"version": "0.5.0", "extras": []},
}

# Database configurations
DATABASE_CONFIGS = {
    "postgresql": {
        "image": "postgres:16-alpine",
        "port": 5432,
        "driver": {
            "python": "asyncpg>=0.29.0",
            "nodejs": "pg@8.11.3",
            "go": "github.com/lib/pq",
            "java": "postgresql:42.7.1",
            "rust": "sqlx = { version = \"0.7\", features = [\"postgres\"] }",
        },
        "orm": {
            "python": "sqlalchemy[asyncio]>=2.0.0",
            "nodejs": "prisma@5.8.0",
            "go": "gorm.io/gorm",
            "java": "spring-boot-starter-data-jpa",
            "rust": "diesel = { version = \"2.1\", features = [\"postgres\"] }",
        },
    },
    "mysql": {
        "image": "mysql:8.0",
        "port": 3306,
        "driver": {
            "python": "aiomysql>=0.2.0",
            "nodejs": "mysql2@3.7.0",
            "go": "github.com/go-sql-driver/mysql",
        },
    },
    "mongodb": {
        "image": "mongo:7.0",
        "port": 27017,
        "driver": {
            "python": "motor>=3.3.0",
            "nodejs": "mongodb@6.3.0",
            "go": "go.mongodb.org/mongo-driver",
        },
    },
    "redis": {
        "image": "redis:7-alpine",
        "port": 6379,
        "driver": {
            "python": "redis>=5.0.0",
            "nodejs": "redis@4.6.0",
            "go": "github.com/redis/go-redis/v9",
        },
    },
    "dynamodb": {
        "image": "amazon/dynamodb-local:latest",
        "port": 8000,
        "driver": {
            "python": "aioboto3>=12.0.0",
            "nodejs": "@aws-sdk/client-dynamodb@3.490.0",
            "go": "github.com/aws/aws-sdk-go-v2/service/dynamodb",
        },
    },
}

# Terraform module recommendations by cloud
TERRAFORM_MODULES = {
    "aws": {
        "network": "terraform-aws-modules/vpc/aws",
        "cluster": "terraform-aws-modules/eks/aws",
        "database": "terraform-aws-modules/rds/aws",
        "storage": "terraform-aws-modules/s3-bucket/aws",
        "iam": "terraform-aws-modules/iam/aws",
    },
    "gcp": {
        "network": "terraform-google-modules/network/google",
        "cluster": "terraform-google-modules/kubernetes-engine/google",
        "database": "terraform-google-modules/sql-db/google",
        "storage": "terraform-google-modules/cloud-storage/google",
    },
    "azure": {
        "network": "Azure/vnet/azurerm",
        "cluster": "Azure/aks/azurerm",
        "database": "Azure/postgresql/azurerm",
        "storage": "Azure/storage/azurerm",
    },
}

# CI/CD pipeline configurations
CICD_CONFIGS = {
    "github-actions": {
        "path": ".github/workflows",
        "files": ["ci.yml", "cd.yml", "release.yml"],
        "features": ["matrix builds", "caching", "artifacts", "environments"],
    },
    "gitlab-ci": {
        "path": ".gitlab-ci.yml",
        "files": [".gitlab-ci.yml"],
        "features": ["stages", "caching", "artifacts", "environments"],
    },
    "jenkins": {
        "path": "jenkins",
        "files": ["Jenkinsfile", "jenkins/config.groovy"],
        "features": ["pipeline", "agents", "stages"],
    },
    "argocd": {
        "path": "infrastructure/argocd",
        "files": ["application.yaml", "appproject.yaml", "kustomization.yaml"],
        "features": ["GitOps", "sync policies", "health checks"],
    },
    "circleci": {
        "path": ".circleci",
        "files": ["config.yml"],
        "features": ["workflows", "orbs", "caching"],
    },
}

# Monitoring stack recommendations
MONITORING_STACKS = {
    "default": {
        "metrics": "prometheus",
        "visualization": "grafana",
        "logging": "loki",
        "tracing": "jaeger",
    },
    "aws": {
        "metrics": "cloudwatch",
        "visualization": "grafana",
        "logging": "cloudwatch-logs",
        "tracing": "x-ray",
    },
    "gcp": {
        "metrics": "cloud-monitoring",
        "visualization": "grafana",
        "logging": "cloud-logging",
        "tracing": "cloud-trace",
    },
}


def suggest_stack(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate stack suggestions based on wizard configuration.
    
    Args:
        config: Configuration dictionary from wizard
        
    Returns:
        Stack suggestion dictionary with recommendations and reasoning
    """
    language = config.get("language", "python")
    framework = config.get("framework", "none")
    cloud = config.get("cloud", "aws")
    kubernetes = config.get("kubernetes", True)
    database = config.get("database", "postgresql")
    services = config.get("services", [])
    cicd = config.get("cicd", "github-actions")
    team_size = config.get("team_size", "small")
    app_type = config.get("app_type", "api")
    
    stack = {
        "base_image": _suggest_base_image(language, app_type),
        "framework": _suggest_framework(framework, language),
        "database": _suggest_database(database, language),
        "infrastructure": _suggest_infrastructure(cloud, kubernetes, team_size),
        "cicd": _suggest_cicd(cicd, cloud, kubernetes),
        "monitoring": _suggest_monitoring(cloud, services),
        "dependencies": _suggest_dependencies(language, framework, database, services),
    }
    
    # Add reasoning for each suggestion
    stack["reasoning"] = _generate_reasoning(config, stack)
    
    return stack


def _suggest_base_image(language: str, app_type: str) -> Dict[str, Any]:
    """Suggest base Docker image."""
    images = BASE_IMAGES.get(language, BASE_IMAGES["python"])
    
    # For production, prefer slim/alpine
    recommended = images.get("default", "python:3.11-slim")
    
    return {
        "recommended": recommended,
        "alternatives": list(images.values()),
        "reason": f"Slim image for {language} - smaller size, faster pulls, reduced attack surface",
    }


def _suggest_framework(framework: str, language: str) -> Dict[str, Any]:
    """Suggest framework version and dependencies."""
    if framework == "none":
        return {
            "name": "none",
            "version": None,
            "extras": [],
            "reason": "No framework selected - using standard library",
        }
    
    fw_config = FRAMEWORK_VERSIONS.get(framework, {"version": "latest", "extras": []})
    
    return {
        "name": framework,
        "version": fw_config["version"],
        "extras": fw_config["extras"],
        "reason": f"{framework} {fw_config['version']} - stable, well-supported version",
    }


def _suggest_database(database: str, language: str) -> Dict[str, Any]:
    """Suggest database configuration."""
    if database == "none":
        return {
            "type": "none",
            "image": None,
            "driver": None,
            "reason": "No database required",
        }
    
    db_config = DATABASE_CONFIGS.get(database, {})
    
    return {
        "type": database,
        "image": db_config.get("image"),
        "port": db_config.get("port"),
        "driver": db_config.get("driver", {}).get(language),
        "orm": db_config.get("orm", {}).get(language),
        "reason": f"{database} - reliable, production-ready database with excellent {language} support",
    }


def _suggest_infrastructure(cloud: str, kubernetes: bool, team_size: str) -> Dict[str, Any]:
    """Suggest infrastructure modules."""
    modules = TERRAFORM_MODULES.get(cloud, TERRAFORM_MODULES["aws"])
    
    # Adjust based on team size
    replicas = {"solo": 1, "small": 2, "medium": 3, "large": 5}.get(team_size, 2)
    
    infra = {
        "cloud": cloud,
        "modules": modules,
        "kubernetes": kubernetes,
        "suggested_replicas": replicas,
        "environments": ["dev", "staging", "prod"],
    }
    
    if kubernetes:
        infra["reason"] = f"Kubernetes on {cloud.upper()} with {replicas} default replicas for {team_size} team"
    else:
        infra["reason"] = f"Container deployment on {cloud.upper()} without Kubernetes orchestration"
    
    return infra


def _suggest_cicd(cicd: str, cloud: str, kubernetes: bool) -> Dict[str, Any]:
    """Suggest CI/CD configuration."""
    cicd_config = CICD_CONFIGS.get(cicd, CICD_CONFIGS["github-actions"])
    
    suggestion = {
        "platform": cicd,
        "path": cicd_config["path"],
        "files": cicd_config["files"],
        "features": cicd_config["features"],
    }
    
    if kubernetes and cicd == "github-actions":
        suggestion["recommendation"] = "Consider adding ArgoCD for GitOps-based deployments"
    
    suggestion["reason"] = f"{cicd} provides {', '.join(cicd_config['features'][:2])}"
    
    return suggestion


def _suggest_monitoring(cloud: str, services: List[str]) -> Dict[str, Any]:
    """Suggest monitoring stack."""
    # Use cloud-native if available, otherwise default
    stack = MONITORING_STACKS.get(cloud, MONITORING_STACKS["default"])
    
    enabled = {
        "metrics": True,
        "visualization": True,
        "logging": "logging" in services,
        "tracing": "tracing" in services,
    }
    
    return {
        "stack": stack,
        "enabled": enabled,
        "reason": f"Integrated monitoring with {stack['metrics']} and {stack['visualization']}",
    }


def _suggest_dependencies(
    language: str,
    framework: str,
    database: str,
    services: List[str]
) -> Dict[str, Any]:
    """Compile suggested dependencies."""
    deps = {
        "core": [],
        "database": [],
        "services": [],
        "dev": [],
    }
    
    # Framework dependencies
    if framework != "none":
        fw_config = FRAMEWORK_VERSIONS.get(framework, {})
        if language == "python":
            deps["core"].append(f"{framework}>={fw_config.get('version', '0.0.0')}")
            deps["core"].extend(fw_config.get("extras", []))
        elif language in ["nodejs", "typescript"]:
            deps["core"].append(f"{framework}@{fw_config.get('version', 'latest')}")
    
    # Database dependencies
    if database != "none":
        db_config = DATABASE_CONFIGS.get(database, {})
        driver = db_config.get("driver", {}).get(language)
        if driver:
            deps["database"].append(driver)
        orm = db_config.get("orm", {}).get(language)
        if orm:
            deps["database"].append(orm)
    
    # Service dependencies
    if "auth" in services:
        if language == "python":
            deps["services"].append("python-jose[cryptography]>=3.3.0")
        elif language in ["nodejs", "typescript"]:
            deps["services"].append("jsonwebtoken@9.0.0")
    
    if "caching" in services:
        db_config = DATABASE_CONFIGS.get("redis", {})
        driver = db_config.get("driver", {}).get(language)
        if driver:
            deps["services"].append(driver)
    
    # Dev dependencies
    if language == "python":
        deps["dev"] = ["pytest>=7.0.0", "pytest-cov>=4.0.0", "black>=23.0.0", "mypy>=1.0.0"]
    elif language in ["nodejs", "typescript"]:
        deps["dev"] = ["jest@29.7.0", "eslint@8.56.0", "prettier@3.2.0"]
    
    return deps


def _generate_reasoning(config: Dict[str, Any], stack: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generate reasoning explanations for the suggestions."""
    reasoning = []
    
    # Base image reasoning
    reasoning.append({
        "area": "Container Image",
        "recommendation": stack["base_image"]["recommended"],
        "reason": stack["base_image"]["reason"],
    })
    
    # Framework reasoning
    if stack["framework"]["name"] != "none":
        reasoning.append({
            "area": "Framework",
            "recommendation": f"{stack['framework']['name']} {stack['framework']['version']}",
            "reason": stack["framework"]["reason"],
        })
    
    # Database reasoning
    if stack["database"]["type"] != "none":
        reasoning.append({
            "area": "Database",
            "recommendation": stack["database"]["type"],
            "reason": stack["database"]["reason"],
        })
    
    # Infrastructure reasoning
    reasoning.append({
        "area": "Infrastructure",
        "recommendation": f"{stack['infrastructure']['cloud'].upper()} with Terraform" if stack['infrastructure']['kubernetes'] else stack['infrastructure']['cloud'].upper(),
        "reason": stack["infrastructure"]["reason"],
    })
    
    # CI/CD reasoning
    reasoning.append({
        "area": "CI/CD",
        "recommendation": stack["cicd"]["platform"],
        "reason": stack["cicd"]["reason"],
    })
    
    return reasoning


def display_stack_suggestion(stack: Dict[str, Any], config: Dict[str, Any]):
    """Display stack suggestions in a formatted way."""
    console.print()
    console.print(Panel(
        "[bold cyan]📦 Recommended Technology Stack[/]",
        box=box.DOUBLE,
        border_style="cyan"
    ))
    
    # Main recommendations table
    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Component", style="white", width=20)
    table.add_column("Recommendation", style="green", width=30)
    table.add_column("Reason", style="dim", width=40)
    
    for item in stack.get("reasoning", []):
        table.add_row(
            item["area"],
            item["recommendation"],
            item["reason"]
        )
    
    console.print(table)
    
    # Dependencies section
    console.print()
    console.print("[bold yellow]📚 Dependencies[/]")
    
    deps = stack.get("dependencies", {})
    if deps.get("core"):
        console.print(f"  [cyan]Core:[/] {', '.join(deps['core'][:3])}")
    if deps.get("database"):
        console.print(f"  [cyan]Database:[/] {', '.join(deps['database'][:2])}")
    if deps.get("services"):
        console.print(f"  [cyan]Services:[/] {', '.join(deps['services'][:2])}")
    
    # CI/CD files
    console.print()
    console.print("[bold yellow]🔄 CI/CD Files to Generate[/]")
    cicd = stack.get("cicd", {})
    console.print(f"  [cyan]Path:[/] {cicd.get('path', 'N/A')}")
    console.print(f"  [cyan]Files:[/] {', '.join(cicd.get('files', []))}")
    
    # Infrastructure
    infra = stack.get("infrastructure", {})
    if infra.get("kubernetes"):
        console.print()
        console.print("[bold yellow]☸️  Kubernetes Configuration[/]")
        console.print(f"  [cyan]Default Replicas:[/] {infra.get('suggested_replicas', 2)}")
        console.print(f"  [cyan]Environments:[/] {', '.join(infra.get('environments', []))}")
    
    console.print()


def approve_stack(stack: Dict[str, Any]) -> bool:
    """Ask user to approve the suggested stack."""
    from rich.prompt import Confirm
    return Confirm.ask("[bold]Approve this stack configuration?[/]", default=True)


def modify_stack(stack: Dict[str, Any]) -> Dict[str, Any]:
    """Allow user to modify specific stack elements."""
    from rich.prompt import Prompt
    
    console.print()
    console.print("[yellow]You can modify specific elements:[/]")
    console.print("[dim]Press Enter to keep current value, or type new value[/]")
    console.print()
    
    # Allow modification of key elements
    current_image = stack["base_image"]["recommended"]
    new_image = Prompt.ask("Base image", default=current_image)
    if new_image != current_image:
        stack["base_image"]["recommended"] = new_image
        stack["base_image"]["reason"] = "User-specified base image"
    
    current_replicas = stack["infrastructure"]["suggested_replicas"]
    new_replicas = Prompt.ask("Default replicas", default=str(current_replicas))
    try:
        stack["infrastructure"]["suggested_replicas"] = int(new_replicas)
    except ValueError:
        pass
    
    return stack
