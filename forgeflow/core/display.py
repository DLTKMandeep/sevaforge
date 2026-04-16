"""
ForgeFlow Display Module

Rich-based display utilities for enhanced CLI UX.
Provides colored tables, progress panels, and stage-specific formatting.

Stage Colors:
    discover  = blue
    normalize = green
    scan      = red
    docs      = cyan
    generate  = yellow
    review    = white
    test      = bright_blue
    deploy    = purple
    monitor   = bright_cyan
    bridge    = magenta
    status    = white
    doctor    = bright_cyan
"""
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich import box

# Initialize console
console = Console()

# Stage color mapping (updated with new stages)
STAGE_COLORS = {
    "discover": "blue",
    "normalize": "green",
    "scan": "red",
    "docs": "cyan",
    "generate": "yellow",
    "review": "white",          # Code review
    "test": "bright_blue",      # Testing
    "deploy": "purple",         # Deployment
    "monitor": "bright_cyan",   # Monitoring
    "bridge": "magenta",
    "deploy-intent":   "bright_yellow",
    "deploy-design":   "bright_magenta",
    "deploy-validate": "bright_red",
    "status": "white",
    "doctor": "bright_cyan",
}

# Stage → MCP Server → Agent mapping
# Each stage has: mcp_server, agent, purpose (what it does), outputs (what it produces)
STAGE_MAPPING = {
    "discover": {
        "mcp_server": "discovery-mcp-server",
        "agent":      "DiscoveryAgent",
        "purpose":    "Map the codebase — detect language, frameworks, entry points, port, dependencies",
        "outputs":    "Tech stack · Entry points · Port · Dependency list · staging/discover_report.md",
    },
    "normalize": {
        "mcp_server": "normalize-mcp-server",
        "agent":      "NormalizationAgent",
        "purpose":    "Enforce a consistent project layout and standard config files",
        "outputs":    "Dockerfile · .gitignore · .editorconfig · README scaffold · staging/normalize_report.md",
    },
    "docs": {
        "mcp_server": "diagram-generator-mcp-server",
        "agent":      "DocumentationAgent",
        "purpose":    "Generate human-readable docs: architecture diagrams, API reference, runbook",
        "outputs":    "docs/architecture.md · docs/api.md · RUNBOOK.md · CONTRIBUTING.md",
    },
    "iac": {
        "mcp_server": "iac-mcp-server",
        "agent":      "IACAgent",
        "purpose":    "Provision cloud infrastructure: EKS cluster, VPC, S3, ECR via Terraform",
        "outputs":    "infrastructure/terraform/ · docker-compose.yml · staging/iac_report.md",
    },
    "cd": {
        "mcp_server": "cd-mcp-server",
        "agent":      "CDAgent",
        "purpose":    "Wire GitOps delivery: Kubernetes manifests, ArgoCD apps, staging/prod overlays",
        "outputs":    "deploy.yml · infra.yml · bootstrap.yml · k8s/base/ · k8s/overlays/",
    },
    "ci": {
        "mcp_server": "ci-mcp-server",
        "agent":      "CIAgent",
        "purpose":    "Automate build, test, and security gates on every push and pull request",
        "outputs":    "pipeline.yml (Security→Tests→Deploy) · release.yml · .gitlab-ci.yml · dependabot.yml",
    },
    "e2e": {
        "mcp_server": "e2e-mcp-server",
        "agent":      "E2ETestingAgent",
        "purpose":    "Scaffold end-to-end tests and the CI workflow to run them on every push",
        "outputs":    "tests/e2e/*.spec.ts · playwright.config.ts · e2e.yml",
    },
    "review": {
        "mcp_server": "git-mcp-server",
        "agent":      "CodeReviewAgent",
        "purpose":    "Surface code smells, complexity hotspots, uncommitted changes, and git health",
        "outputs":    "Complexity score · Smell list · Hotspot files · staging/review_report.md",
    },
    "test": {
        "mcp_server": "cicd-mcp-server",
        "agent":      "TestingAgent",
        "purpose":    "Discover and execute the test suite, report pass/fail and coverage gaps",
        "outputs":    "Test results · Coverage % · staging/test_report.md",
    },
    "scan": {
        "mcp_server": "security-mcp-server",
        "agent":      "SecurityAgent",
        "purpose":    "Detect hardcoded secrets, vulnerable dependencies, and SAST issues",
        "outputs":    "CVE list · Severity breakdown · staging/scan_report.md",
    },
    "deploy": {
        "mcp_server": "cloud-mcp-server",
        "agent":      "DeploymentAgent",
        "purpose":    "Apply Terraform and trigger ArgoCD sync to release the app to cloud",
        "outputs":    "Deployed endpoints · Health check URLs · ArgoCD sync status",
    },
    "monitor": {
        "mcp_server": "observability-mcp-server",
        "agent":      "MonitoringAgent",
        "purpose":    "Wire up Prometheus metrics, Grafana dashboards, and alerting rules",
        "outputs":    "Prometheus config · Grafana dashboards · Alert rules · staging/monitor_report.md",
    },
    "deploy-intent": {
        "mcp_server": "intent-mcp-server",
        "agent":      "DeployIntentAgent",
        "purpose":    "Interactive deployment interview — capture cloud, compute model, SLOs, cost controls",
        "outputs":    ".sevaforge/deployment-intent.yaml (cached, survives re-runs)",
    },
    "deploy-design": {
        "mcp_server": "design-mcp-server",
        "agent":      "DeployOrchestratorAgent",
        "purpose":    "Fan out to 7 personas in parallel: infra, cluster, app, secrets, observability, security, cost",
        "outputs":    "forgeflow/infrastructure/ · deploy/helm/ · deploy/secrets/ · deploy/observability/ · deploy/security/ · deploy/cost/ · .github/workflows/cost-*.yml",
    },
    "deploy-validate": {
        "mcp_server": "validate-mcp-server",
        "agent":      "DeployValidatorAgent",
        "purpose":    "Cross-check persona artefacts (secrets inventory, crons, SLOs, TF vars, image repo) — blocks push on failure",
        "outputs":    "Validation report · updates _meta.last_validated in deployment-intent.yaml",
    },
    "bridge": {
        "mcp_server": "github-mcp-server",
        "agent":      "BridgeAgent",
        "purpose":    "Commit all ForgeFlow-generated artifacts to GitHub and open a pull request",
        "outputs":    "Git commit · GitHub PR URL · Branch pushed",
    },
    "generate": {
        "mcp_server": "deployment-mcp-server",
        "agent":      "GenerationAgent",
        "purpose":    "Generate deployment artifacts using the detected stack",
        "outputs":    "Deployment configs · staging/generate_report.md",
    },
}


def get_stage_color(stage: str) -> str:
    """Get the color for a given stage."""
    return STAGE_COLORS.get(stage, "white")


def get_stage_info(stage: str) -> Dict[str, str]:
    """Get MCP server and agent info for a stage."""
    return STAGE_MAPPING.get(stage, {
        "mcp_server": "unknown",
        "agent": "Unknown",
        "description": "Unknown stage"
    })


def print_header(title: str = "FORGEFLOW"):
    """Print the ForgeFlow header banner."""
    console.print()
    console.print(Panel(
        Text(f"🔥 {title}", justify="center", style="bold white"),
        border_style="bright_blue",
        box=box.DOUBLE
    ))
    console.print()


def print_mode_indicator(mode: str, endpoint: str = None):
    """Print deployment mode indicator."""
    if mode == "public":
        content = "[bold cyan]☁️  PUBLIC MODE[/] - All MCPs running in cloud (thin client)"
        if endpoint:
            content += f"\n[dim]Connected to: {endpoint}[/]"
        console.print(Panel(
            content,
            border_style="cyan",
            box=box.ROUNDED
        ))
    elif mode == "hybrid":
        console.print(Panel(
            "[bold yellow]🌐 HYBRID MODE[/] - Using mix of local and public MCPs",
            border_style="yellow",
            box=box.ROUNDED
        ))
    else:
        console.print(Panel(
            "[bold green]💻 LOCAL MODE[/] - All MCPs running locally (offline capable)",
            border_style="green",
            box=box.ROUNDED
        ))


def print_stage_start(stage: str, path: str = ".", stage_num: int = 0, total: int = 0):
    """Display a clear phase announcement before running a stage."""
    color = get_stage_color(stage)
    info = get_stage_info(stage)

    stage_label = stage.upper()
    num_label = f"STAGE {stage_num}/{total}  " if stage_num and total else ""

    # Top section: what this phase is and what it does
    content = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    content.add_column("Icon", style=f"bold {color}", no_wrap=True, width=4)
    content.add_column("Label", style="dim", no_wrap=True, width=12)
    content.add_column("Value", style="white")

    content.add_row(
        "🎯", "PURPOSE",
        f"[bold white]{info.get('purpose', info.get('description', 'Running stage'))}[/]"
    )
    content.add_row("", "", "")  # spacer
    content.add_row(
        "📦", "OUTPUTS",
        f"[dim]{info.get('outputs', 'See staging/ for reports')}[/]"
    )
    content.add_row("", "", "")  # spacer
    content.add_row("🤖", "Agent",  f"[{color}]{info.get('agent', 'Unknown')}[/]")
    content.add_row("🔌", "MCP",    f"[dim]{info.get('mcp_server', 'unknown')}[/]")
    content.add_row("📂", "Path",   f"[dim]{path}[/]")

    console.print()
    console.print(Panel(
        content,
        title=f"[bold {color}] {num_label}▶  {stage_label} [/]",
        border_style=color,
        box=box.HEAVY,
        expand=False,
    ))
    console.print()


def print_stage_result(stage: str, result: Dict[str, Any]):
    """Display results after a stage completes — status + findings."""
    color = get_stage_color(stage)
    status = result.get("status", "unknown")

    # Status icon and style
    if status == "success":
        status_icon, status_style, status_bar = "✅", "bold green", "[bold green]━━━ PASSED ━━━[/]"
    elif status == "warning":
        status_icon, status_style, status_bar = "⚠️ ", "bold yellow", "[bold yellow]━━━ WARNING ━━━[/]"
    else:
        status_icon, status_style, status_bar = "❌", "bold red", "[bold red]━━━ FAILED ━━━[/]"

    # Compact result summary
    table = Table(
        title=f"[bold {color}]{stage.upper()} Results[/]",
        box=box.ROUNDED,
        border_style=color,
        show_header=False,
        expand=False,
    )
    table.add_column("Field", style="dim", width=10)
    table.add_column("Value")

    table.add_row("Status",  Text(f"{status_icon} {status.upper()}", style=status_style))
    table.add_row("Summary", result.get("summary", "No summary"))
    table.add_row("Mode",    result.get("deployment_mode", "local").upper())

    console.print(table)

    # Findings — labeled by stage context
    findings = result.get("findings", [])
    if findings:
        info = get_stage_info(stage)
        label = f"{stage.upper()} Findings"
        print_findings_table(label, findings, color)

    console.print()


def print_findings_table(stage_or_label: str, findings: List[Any], color: str = "white"):
    """Display findings in a formatted table. stage_or_label can be a stage name or display label."""
    if not findings:
        return

    label = stage_or_label if " " in stage_or_label else f"{stage_or_label.upper()} Findings"

    table = Table(
        title=f"[bold {color}]{label} ({len(findings)})[/]",
        box=box.SIMPLE,
        border_style=color,
        show_header=True,
        header_style=f"bold {color}"
    )
    
    # Determine columns based on finding structure
    if findings and isinstance(findings[0], dict):
        table.add_column("#", style="dim", width=4)
        table.add_column("Type", style="cyan", width=15)
        table.add_column("Severity", width=10)
        table.add_column("Message", style="white")
        table.add_column("File", style="dim", width=30)
        
        for i, finding in enumerate(findings[:15], 1):
            severity = finding.get("severity", finding.get("type", "info"))
            sev_style = _get_severity_style(severity)
            
            table.add_row(
                str(i),
                str(finding.get("type", "info")),
                Text(str(severity).upper(), style=sev_style),
                str(finding.get("message", finding.get("description", str(finding))))[:60],
                str(finding.get("file", finding.get("path", "")))[:30]
            )
    else:
        table.add_column("#", style="dim", width=4)
        table.add_column("Finding", style="white")
        
        for i, finding in enumerate(findings[:15], 1):
            table.add_row(str(i), str(finding)[:80])
    
    if len(findings) > 15:
        console.print(f"  [dim]... and {len(findings) - 15} more findings[/]")
    
    console.print(table)


def _get_severity_style(severity: str) -> str:
    """Get style for severity level."""
    severity_lower = str(severity).lower()
    if severity_lower in ["critical", "error"]:
        return "bold red"
    elif severity_lower == "high":
        return "red"
    elif severity_lower in ["medium", "warning"]:
        return "yellow"
    elif severity_lower == "low":
        return "cyan"
    return "white"


def print_pipeline_header(title: str = "RUN-ALL PIPELINE", mode: str = "local"):
    """Print pipeline header for run-all command."""
    if mode == "public":
        mode_text = " [☁️  PUBLIC]"
        border_color = "cyan"
    elif mode == "hybrid":
        mode_text = " [🌐 HYBRID]"
        border_color = "yellow"
    else:
        mode_text = ""
        border_color = "bright_blue"
    
    console.print()
    console.print(Panel(
        Text(f"🚀 FORGEFLOW {title}{mode_text}", justify="center", style="bold white"),
        border_style=border_color,
        box=box.DOUBLE
    ))
    console.print()


def print_pipeline_progress(stages: List[str], current_stage: int):
    """Show pipeline progress with stage indicators."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    
    for i, stage in enumerate(stages):
        color = get_stage_color(stage)
        if i < current_stage:
            icon = "✅"
            style = "green"
        elif i == current_stage:
            icon = "▶"
            style = f"bold {color}"
        else:
            icon = "○"
            style = "dim"
        
        table.add_row(Text(f"{icon} {stage.upper()}", style=style))
    
    console.print(Panel(table, title="[bold]Pipeline Progress[/]", border_style="blue"))


def print_pipeline_summary(results: List[tuple], success: bool = True):
    """Print final pipeline summary table."""
    table = Table(
        title="[bold]Pipeline Summary[/]",
        box=box.ROUNDED,
        border_style="green" if success else "red",
        show_header=True,
        header_style="bold white"
    )
    
    table.add_column("Stage", style="cyan", width=12)
    table.add_column("MCP Server", style="blue", width=25)
    table.add_column("Agent", style="yellow", width=20)
    table.add_column("Status", width=10)
    
    for stage_name, result in results:
        info = get_stage_info(stage_name)
        status = result.get("status", "unknown")
        
        if status == "success":
            status_text = Text("✅ PASS", style="bold green")
        elif status == "warning":
            status_text = Text("⚠️ WARN", style="bold yellow")
        else:
            status_text = Text("❌ FAIL", style="bold red")
        
        color = get_stage_color(stage_name)
        table.add_row(
            Text(stage_name.upper(), style=f"bold {color}"),
            info["mcp_server"],
            info["agent"],
            status_text
        )
    
    console.print(table)


def prompt_bridge_approval() -> bool:
    """Prompt user for manual approval before bridge operation."""
    console.print()
    console.print(Panel(
        "[bold yellow]⚠️  All stages passed. Ready to push to GitHub.[/]\n\n"
        "The bridge operation will:\n"
        "  • Create a new GitHub repository (if needed)\n"
        "  • Push all code to the repository\n\n"
        "[dim]This action requires GitHub CLI (gh) to be authenticated.[/]",
        title="[bold magenta]Bridge Confirmation[/]",
        border_style="magenta",
        box=box.ROUNDED
    ))
    
    return Confirm.ask(
        "[bold]Proceed to push to GitHub?[/]",
        default=False,
        console=console
    )


def prompt_post_merge() -> bool:
    """Prompt user for running post-merge stages (deploy, monitor)."""
    console.print()
    console.print(Panel(
        "[bold cyan]🚀 Bridge completed. Ready for post-merge stages.[/]\n\n"
        "Post-merge operations will:\n"
        "  • [purple]DEPLOY[/] - Generate/apply cloud infrastructure\n"
        "  • [bright_cyan]MONITOR[/] - Setup monitoring configurations\n\n"
        "[dim]These stages prepare your application for production.[/]",
        title="[bold purple]Post-Merge Stages[/]",
        border_style="purple",
        box=box.ROUNDED
    ))
    
    return Confirm.ask(
        "[bold]Run post-merge stages (deploy, monitor)?[/]",
        default=False,
        console=console
    )


def print_success_banner(message: str = "All stages passed!"):
    """Print success completion banner."""
    console.print()
    console.print(Panel(
        Text(f"✅ {message}", justify="center", style="bold green"),
        border_style="green",
        box=box.DOUBLE
    ))
    console.print()


def print_error_banner(message: str, stage: str = None):
    """Print error banner."""
    error_msg = f"❌ {message}"
    if stage:
        error_msg += f"\n[dim]Failed at: {stage.upper()}[/]"
    
    console.print()
    console.print(Panel(
        error_msg,
        title="[bold red]Pipeline Failed[/]",
        border_style="red",
        box=box.DOUBLE
    ))
    console.print()


def print_skipped_banner(message: str = "Bridge skipped by user."):
    """Print skipped operation banner."""
    console.print()
    console.print(Panel(
        Text(f"⏭️  {message}", justify="center", style="bold yellow"),
        border_style="yellow",
        box=box.ROUNDED
    ))
    console.print()


def print_mission_start(command: str, path: str = ".", mode: str = "local"):
    """Print mission start info (for single commands)."""
    color = get_stage_color(command)
    info = get_stage_info(command)
    mode_text = f" [{mode.upper()}]" if mode != "local" else ""
    
    console.print()
    console.print(f"[bold {color}]🚀 [MISSION: {command.upper()}]{mode_text}[/] Starting...")
    console.print(f"   [dim]MCP Server:[/] {info['mcp_server']}")
    console.print(f"   [dim]Agent:[/] {info['agent']}")
    console.print(f"   [dim]Path:[/] {path}")
    console.print()


def print_generated_files(result: Dict[str, Any]):
    """Display generated infrastructure files in a formatted table."""
    data = result.get("data", {})
    artifacts = data.get("artifacts", [])
    generated_files = data.get("generated_files", [])
    
    if not artifacts:
        return
    
    # Header info
    console.print()
    console.print(Panel(
        f"[bold yellow]Infrastructure Generation Complete[/]\n\n"
        f"  [cyan]Language:[/] {data.get('primary_language', 'Unknown')}\n"
        f"  [cyan]App Name:[/] {data.get('app_name', 'Unknown')}\n"
        f"  [cyan]Cloud:[/] {data.get('cloud_provider', 'AWS').upper()}\n"
        f"  [cyan]Output:[/] {data.get('infrastructure_path', 'N/A')}",
        title="[bold yellow]🏗️  Generated Infrastructure[/]",
        border_style="yellow",
        box=box.ROUNDED
    ))
    
    # Group artifacts by type
    terraform_files = [a for a in artifacts if a.get('type', '').startswith('terraform')]
    docker_files = [a for a in artifacts if a.get('type') == 'docker']
    cicd_files = [a for a in artifacts if a.get('type') == 'cicd']
    
    # Terraform files table
    if terraform_files:
        tf_table = Table(
            title="[bold blue]Terraform Files[/]",
            box=box.SIMPLE,
            border_style="blue",
            show_header=True,
            header_style="bold blue"
        )
        tf_table.add_column("File", style="cyan", width=45)
        tf_table.add_column("Status", width=12)
        tf_table.add_column("Description", style="dim")
        
        for artifact in terraform_files:
            status = artifact.get('status', 'unknown')
            if status == 'generated':
                status_text = Text("✅ Generated", style="green")
            else:
                status_text = Text("○ Exists", style="dim")
            
            tf_table.add_row(
                artifact.get('file', ''),
                status_text,
                artifact.get('description', '')
            )
        
        console.print(tf_table)
    
    # Docker files table
    if docker_files:
        docker_table = Table(
            title="[bold cyan]Docker Files[/]",
            box=box.SIMPLE,
            border_style="cyan",
            show_header=True,
            header_style="bold cyan"
        )
        docker_table.add_column("File", style="cyan", width=30)
        docker_table.add_column("Status", width=12)
        docker_table.add_column("Description", style="dim")
        
        for artifact in docker_files:
            status = artifact.get('status', 'unknown')
            if status == 'generated':
                status_text = Text("✅ Generated", style="green")
            else:
                status_text = Text("○ Exists", style="dim")
            
            docker_table.add_row(
                artifact.get('file', ''),
                status_text,
                artifact.get('description', '')
            )
        
        console.print(docker_table)
    
    # CI/CD files table
    if cicd_files:
        cicd_table = Table(
            title="[bold magenta]CI/CD Files[/]",
            box=box.SIMPLE,
            border_style="magenta",
            show_header=True,
            header_style="bold magenta"
        )
        cicd_table.add_column("File", style="cyan", width=40)
        cicd_table.add_column("Status", width=12)
        cicd_table.add_column("Description", style="dim")
        
        for artifact in cicd_files:
            status = artifact.get('status', 'unknown')
            if status == 'generated':
                status_text = Text("✅ Generated", style="green")
            else:
                status_text = Text("○ Exists", style="dim")
            
            cicd_table.add_row(
                artifact.get('file', ''),
                status_text,
                artifact.get('description', '')
            )
        
        console.print(cicd_table)
    
    # Summary
    generated_count = len([a for a in artifacts if a.get('status') == 'generated'])
    existing_count = len([a for a in artifacts if a.get('status') == 'exists'])
    
    console.print()
    console.print(f"  [green]✅ Generated:[/] {generated_count} files")
    console.print(f"  [dim]○ Existing:[/] {existing_count} files (skipped)")
    console.print()
    
    # Next steps
    if generated_count > 0:
        console.print(Panel(
            "[bold]Next Steps:[/]\n\n"
            "  1. Review generated Terraform files:\n"
            "     [cyan]cd infrastructure && terraform init[/]\n\n"
            "  2. Customize terraform.tfvars:\n"
            "     [cyan]cp terraform.tfvars.example terraform.tfvars[/]\n\n"
            "  3. Build Docker image:\n"
            "     [cyan]docker build -t app .[/]\n\n"
            "  4. Start local development:\n"
            "     [cyan]docker-compose up[/]",
            title="[bold green]🚀 Getting Started[/]",
            border_style="green",
            box=box.ROUNDED
        ))
