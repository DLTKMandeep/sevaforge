"""
ForgeFlow Interactive Wizard
Beautiful CLI prompts for Greenfield project initialization.

Uses rich library for enhanced user experience with:
- Colored prompts and selections
- Multi-select checkboxes
- Progress indicators
- Validation feedback
"""
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# Application type options
APP_TYPES = [
    ("web-app", "Full-stack web application with frontend and backend"),
    ("api", "RESTful or GraphQL API service"),
    ("microservice", "Lightweight microservice component"),
    ("cli-tool", "Command-line interface application"),
    ("library", "Reusable library/package"),
    ("fullstack", "Monorepo with frontend, backend, and shared packages"),
]

# Language options
LANGUAGES = [
    ("python", "Python 3.9+"),
    ("nodejs", "Node.js 18+"),
    ("typescript", "TypeScript with Node.js"),
    ("go", "Go 1.21+"),
    ("java", "Java 17+ (Spring Boot)"),
    ("rust", "Rust 1.70+"),
]

# Framework options by language
FRAMEWORKS = {
    "python": [
        ("fastapi", "FastAPI - Modern async API framework"),
        ("django", "Django - Full-featured web framework"),
        ("flask", "Flask - Lightweight WSGI framework"),
        ("none", "No framework (pure Python)"),
    ],
    "nodejs": [
        ("express", "Express.js - Minimal web framework"),
        ("nestjs", "NestJS - Enterprise Node.js framework"),
        ("fastify", "Fastify - High-performance framework"),
        ("none", "No framework (pure Node.js)"),
    ],
    "typescript": [
        ("nestjs", "NestJS - Enterprise TypeScript framework"),
        ("express", "Express.js with TypeScript"),
        ("nextjs", "Next.js - React fullstack framework"),
        ("none", "No framework (pure TypeScript)"),
    ],
    "go": [
        ("gin", "Gin - HTTP web framework"),
        ("echo", "Echo - High-performance framework"),
        ("fiber", "Fiber - Express-inspired framework"),
        ("none", "No framework (net/http)"),
    ],
    "java": [
        ("spring-boot", "Spring Boot - Enterprise framework"),
        ("quarkus", "Quarkus - Cloud-native framework"),
        ("micronaut", "Micronaut - Lightweight framework"),
        ("none", "No framework (pure Java)"),
    ],
    "rust": [
        ("actix-web", "Actix-web - Powerful async framework"),
        ("axum", "Axum - Ergonomic web framework"),
        ("rocket", "Rocket - Type-safe framework"),
        ("none", "No framework (pure Rust)"),
    ],
}

# Cloud provider options
CLOUD_PROVIDERS = [
    ("aws", "Amazon Web Services"),
    ("gcp", "Google Cloud Platform"),
    ("azure", "Microsoft Azure"),
    ("on-prem", "On-premises / Self-hosted"),
    ("multi-cloud", "Multi-cloud deployment"),
]

# Database options
DATABASES = [
    ("postgresql", "PostgreSQL - Advanced relational database"),
    ("mysql", "MySQL - Popular relational database"),
    ("mongodb", "MongoDB - Document database"),
    ("redis", "Redis - In-memory data store"),
    ("dynamodb", "DynamoDB - AWS managed NoSQL"),
    ("none", "No database needed"),
]

# Additional services (multi-select)
ADDITIONAL_SERVICES = [
    ("auth", "Authentication (OAuth2, JWT)"),
    ("caching", "Caching layer (Redis)"),
    ("messaging", "Message queue (RabbitMQ, Kafka)"),
    ("monitoring", "Monitoring (Prometheus, Grafana)"),
    ("logging", "Centralized logging (ELK, Loki)"),
    ("tracing", "Distributed tracing (Jaeger, Zipkin)"),
]

# CI/CD options
CICD_OPTIONS = [
    ("github-actions", "GitHub Actions"),
    ("gitlab-ci", "GitLab CI/CD"),
    ("jenkins", "Jenkins"),
    ("argocd", "ArgoCD (GitOps)"),
    ("circleci", "CircleCI"),
]

# Team size options
TEAM_SIZES = [
    ("solo", "Solo developer (1 person)"),
    ("small", "Small team (2-5 people)"),
    ("medium", "Medium team (6-15 people)"),
    ("large", "Large team (15+ people)"),
]


def print_wizard_header():
    """Print wizard header with ForgeFlow branding."""
    header = Text()
    header.append("🔨 ", style="bold yellow")
    header.append("ForgeFlow ", style="bold cyan")
    header.append("Greenfield Project Wizard", style="bold white")
    
    console.print()
    console.print(Panel(
        header,
        box=box.DOUBLE,
        border_style="cyan",
        padding=(1, 2)
    ))
    console.print()
    console.print("[dim]Answer the following questions to configure your new project.[/]")
    console.print("[dim]Press Enter to accept default values shown in brackets.[/]")
    console.print()


def print_section_header(title: str, number: int):
    """Print a section header."""
    console.print()
    console.print(f"[bold cyan]━━━ {number}. {title} ━━━[/]")
    console.print()


def display_options(options: List[tuple], title: str = None) -> None:
    """Display options in a formatted table."""
    if title:
        console.print(f"[dim]{title}:[/]")
    
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan bold", width=15)
    table.add_column("Description", style="white")
    
    for key, desc in options:
        table.add_row(key, desc)
    
    console.print(table)
    console.print()


def prompt_single_choice(
    prompt_text: str,
    options: List[tuple],
    default: str = None,
    show_options: bool = True
) -> str:
    """Prompt for a single choice from options."""
    valid_choices = [opt[0] for opt in options]
    
    if show_options:
        display_options(options)
    
    while True:
        choice = Prompt.ask(
            f"[bold]{prompt_text}[/]",
            default=default,
            show_default=True
        )
        
        if choice.lower() in valid_choices:
            return choice.lower()
        
        console.print(f"[red]Invalid choice. Please choose from: {', '.join(valid_choices)}[/]")


def prompt_multi_select(
    prompt_text: str,
    options: List[tuple],
    defaults: List[str] = None
) -> List[str]:
    """Prompt for multiple selections (comma-separated)."""
    display_options(options)
    
    default_str = ",".join(defaults) if defaults else "none"
    
    console.print(f"[dim]Enter comma-separated values, or 'none' for no selection.[/]")
    
    while True:
        choice = Prompt.ask(
            f"[bold]{prompt_text}[/]",
            default=default_str,
            show_default=True
        )
        
        if choice.lower() == "none":
            return []
        
        valid_choices = [opt[0] for opt in options]
        selected = [c.strip().lower() for c in choice.split(",")]
        
        invalid = [s for s in selected if s not in valid_choices]
        if invalid:
            console.print(f"[red]Invalid choices: {', '.join(invalid)}[/]")
            console.print(f"[dim]Valid options: {', '.join(valid_choices)}[/]")
            continue
        
        return selected


def prompt_yes_no(prompt_text: str, default: bool = True) -> bool:
    """Prompt for yes/no answer."""
    return Confirm.ask(f"[bold]{prompt_text}[/]", default=default)


def run_wizard(project_name: str = None, guided: bool = False) -> Dict[str, Any]:
    """
    Run the interactive Greenfield wizard.
    
    Args:
        project_name: Optional project name (if provided, skip that prompt)
        guided: If True, provide more explanation at each step
        
    Returns:
        Configuration dictionary with all wizard answers
    """
    print_wizard_header()
    
    config = {}
    
    # 1. Project Name
    print_section_header("Project Information", 1)
    
    if project_name:
        config["project_name"] = project_name
        console.print(f"[green]✓[/] Project name: [cyan]{project_name}[/]")
    else:
        config["project_name"] = Prompt.ask(
            "[bold]Project name[/]",
            default="my-project"
        )
    
    if guided:
        console.print("[dim]This will be the directory name and default for package naming.[/]")
    
    # 2. Application Type
    print_section_header("Application Type", 2)
    
    if guided:
        console.print("[dim]Choose the type of application you're building.[/]")
        console.print("[dim]This determines the project structure and defaults.[/]")
        console.print()
    
    config["app_type"] = prompt_single_choice(
        "Application type",
        APP_TYPES,
        default="api"
    )
    
    # 3. Programming Language
    print_section_header("Programming Language", 3)
    
    if guided:
        console.print("[dim]Select your primary programming language.[/]")
        console.print()
    
    config["language"] = prompt_single_choice(
        "Language",
        LANGUAGES,
        default="python"
    )
    
    # 4. Framework
    print_section_header("Framework", 4)
    
    available_frameworks = FRAMEWORKS.get(config["language"], [("none", "No framework")])
    
    if guided:
        console.print(f"[dim]Available frameworks for {config['language']}:[/]")
        console.print()
    
    # Set sensible default based on app type
    default_framework = "none"
    if config["app_type"] in ["api", "microservice", "web-app"]:
        default_framework = available_frameworks[0][0]  # First option
    
    config["framework"] = prompt_single_choice(
        "Framework",
        available_frameworks,
        default=default_framework
    )
    
    # 5. Target Cloud
    print_section_header("Cloud Provider", 5)
    
    if guided:
        console.print("[dim]Select your target deployment environment.[/]")
        console.print()
    
    config["cloud"] = prompt_single_choice(
        "Target cloud",
        CLOUD_PROVIDERS,
        default="aws"
    )
    
    # 6. Kubernetes
    print_section_header("Container Orchestration", 6)
    
    if guided:
        console.print("[dim]Kubernetes provides container orchestration for production workloads.[/]")
        console.print()
    
    config["kubernetes"] = prompt_yes_no("Use Kubernetes?", default=True)
    
    # 7. Database
    print_section_header("Database", 7)
    
    if guided:
        console.print("[dim]Select your primary data store.[/]")
        console.print()
    
    config["database"] = prompt_single_choice(
        "Database",
        DATABASES,
        default="postgresql"
    )
    
    # 8. Additional Services
    print_section_header("Additional Services", 8)
    
    if guided:
        console.print("[dim]Select additional infrastructure components.[/]")
        console.print("[dim]These will be included in your deployment configs.[/]")
        console.print()
    
    # Default services based on app type
    default_services = ["monitoring", "logging"]
    if config["app_type"] in ["api", "microservice"]:
        default_services.append("auth")
    
    config["services"] = prompt_multi_select(
        "Additional services",
        ADDITIONAL_SERVICES,
        defaults=default_services
    )
    
    # 9. CI/CD
    print_section_header("CI/CD Pipeline", 9)
    
    if guided:
        console.print("[dim]Select your continuous integration and deployment platform.[/]")
        console.print()
    
    config["cicd"] = prompt_single_choice(
        "CI/CD platform",
        CICD_OPTIONS,
        default="github-actions"
    )
    
    # 10. Team Size
    print_section_header("Team Size", 10)
    
    if guided:
        console.print("[dim]Team size affects default configurations for collaboration.[/]")
        console.print()
    
    config["team_size"] = prompt_single_choice(
        "Team size",
        TEAM_SIZES,
        default="small"
    )
    
    # Summary
    print_wizard_summary(config)
    
    return config


def print_wizard_summary(config: Dict[str, Any]):
    """Print a summary of wizard selections."""
    console.print()
    console.print(Panel(
        "[bold green]Configuration Summary[/]",
        box=box.ROUNDED,
        border_style="green"
    ))
    
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    table.add_column("Setting", style="cyan", width=20)
    table.add_column("Value", style="white")
    
    table.add_row("Project Name", config.get("project_name", "N/A"))
    table.add_row("Application Type", config.get("app_type", "N/A"))
    table.add_row("Language", config.get("language", "N/A"))
    table.add_row("Framework", config.get("framework", "N/A"))
    table.add_row("Cloud Provider", config.get("cloud", "N/A"))
    table.add_row("Kubernetes", "Yes" if config.get("kubernetes") else "No")
    table.add_row("Database", config.get("database", "N/A"))
    table.add_row("Services", ", ".join(config.get("services", [])) or "None")
    table.add_row("CI/CD", config.get("cicd", "N/A"))
    table.add_row("Team Size", config.get("team_size", "N/A"))
    
    console.print(table)
    console.print()


def confirm_config(config: Dict[str, Any]) -> bool:
    """Ask user to confirm the configuration."""
    return prompt_yes_no("Proceed with this configuration?", default=True)


# Quick init - minimal questions for fast setup
def run_quick_wizard(project_name: str = None) -> Dict[str, Any]:
    """
    Run a quick wizard with sensible defaults.
    Only asks for essential information.
    """
    console.print()
    console.print(Panel(
        "[bold cyan]🚀 Quick Start Wizard[/]",
        box=box.ROUNDED,
        border_style="cyan"
    ))
    console.print()
    
    config = {}
    
    # Project name
    if project_name:
        config["project_name"] = project_name
        console.print(f"[green]✓[/] Project name: [cyan]{project_name}[/]")
    else:
        config["project_name"] = Prompt.ask("[bold]Project name[/]", default="my-project")
    
    # Language
    config["language"] = prompt_single_choice(
        "Language",
        [("python", "Python"), ("nodejs", "Node.js"), ("go", "Go"), ("typescript", "TypeScript")],
        default="python",
        show_options=True
    )
    
    # App type
    config["app_type"] = prompt_single_choice(
        "Type",
        [("api", "API"), ("web-app", "Web App"), ("microservice", "Microservice"), ("cli-tool", "CLI")],
        default="api",
        show_options=True
    )
    
    # Defaults for everything else
    framework_defaults = {
        "python": "fastapi",
        "nodejs": "express",
        "typescript": "nestjs",
        "go": "gin"
    }
    
    config["framework"] = framework_defaults.get(config["language"], "none")
    config["cloud"] = "aws"
    config["kubernetes"] = True
    config["database"] = "postgresql"
    config["services"] = ["auth", "monitoring", "logging"]
    config["cicd"] = "github-actions"
    config["team_size"] = "small"
    
    print_wizard_summary(config)
    
    return config
