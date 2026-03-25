#!/usr/bin/env python3
"""
ForgeFlow CLI Entry Point

Usage:
    forgeflow init [project-name]         # Greenfield: Interactive project wizard
    forgeflow init --guided               # Greenfield: Step-by-step guided mode
    forgeflow init --quick                # Greenfield: Quick start with defaults
    forgeflow [--mode MODE] discover [--path PATH]
    forgeflow [--mode MODE] normalize [--path PATH]
    forgeflow [--mode MODE] scan [--path PATH] [--severity LEVEL]
    forgeflow [--mode MODE] generate [--path PATH] [--stack STACK]
    forgeflow [--mode MODE] iac [--path PATH] [--cloud PROVIDER]
    forgeflow [--mode MODE] cd [--path PATH] [--repo-url URL]
    forgeflow [--mode MODE] ci [--path PATH]
    forgeflow [--mode MODE] e2e [--path PATH] [--framework FRAMEWORK]
    forgeflow [--mode MODE] review [--path PATH]
    forgeflow [--mode MODE] test [--path PATH]
    forgeflow [--mode MODE] deploy [--path PATH] [--target ENV]
    forgeflow [--mode MODE] monitor [--path PATH]
    forgeflow [--mode MODE] docs [--path PATH]
    forgeflow [--mode MODE] bridge [--repo REPO] [--branch BRANCH]
    forgeflow [--mode MODE] status [--path PATH]
    forgeflow [--mode MODE] doctor
    forgeflow [--mode MODE] audit [--path PATH]
    forgeflow [--mode MODE] run-all [PATH]

Project Modes:
    Greenfield: New project from scratch (forgeflow init)
    Brownfield: Existing repository (forgeflow run-all, discover, etc.)

Deployment Modes:
    --mode local   : All MCPs run locally (default, full offline capability)
    --mode hybrid  : Mix of local and public MCPs (requires internet for some features)

Pipeline Sequence (v2.1):
    DISCOVER → NORMALIZE → DOCS → IAC → CD → CI → E2E → REVIEW → TEST → SCAN → [APPROVAL] → BRIDGE
    Post-merge (optional): DEPLOY → MONITOR

This CLI ONLY parses commands and delegates to MissionControl.
No business logic is implemented here.
"""
import sys
import os
import argparse
from pathlib import Path

# Add parent directory to path for imports
root_dir = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(root_dir))

from core.mission_control import MissionControl
from core.display import (
    console,
    print_header,
    print_pipeline_header,
    print_stage_start,
    print_stage_result,
    print_pipeline_summary,
    print_success_banner,
    print_error_banner,
    print_generated_files,
    print_mode_indicator
)


def is_greenfield_directory(path: str) -> bool:
    """
    Detect if directory is a Greenfield (new/empty) project.
    
    Returns True if:
    - Directory doesn't exist
    - Directory is empty
    - Directory only contains .git folder
    - No source files detected
    """
    target = Path(path).absolute()
    
    if not target.exists():
        return True
    
    if not target.is_dir():
        return False
    
    # Check contents
    contents = list(target.iterdir())
    
    # Empty directory
    if len(contents) == 0:
        return True
    
    # Only .git folder
    if len(contents) == 1 and contents[0].name == '.git':
        return True
    
    # Check for source files
    source_indicators = [
        'package.json', 'requirements.txt', 'pyproject.toml',
        'go.mod', 'Cargo.toml', 'pom.xml', 'build.gradle',
        'main.py', 'index.js', 'main.go', 'src', 'lib',
        'app.py', 'server.py', 'app.js', 'server.js'
    ]
    
    for indicator in source_indicators:
        if (target / indicator).exists():
            return False
    
    # Check for any source code files
    source_extensions = {'.py', '.js', '.ts', '.go', '.java', '.rs', '.rb', '.php'}
    for item in contents:
        if item.is_file() and item.suffix in source_extensions:
            return False
        if item.is_dir() and item.name not in {'.git', '.github', 'node_modules', '__pycache__', '.venv', 'venv'}:
            # Check subdirectory for source files
            for subitem in item.rglob('*'):
                if subitem.is_file() and subitem.suffix in source_extensions:
                    return False
    
    return True


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with all canonical commands."""
    parser = argparse.ArgumentParser(
        prog="forgeflow",
        description="ForgeFlow - AI Platform Engineering CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Project Modes:
    Greenfield : New project from scratch (forgeflow init)
    Brownfield : Existing repository (forgeflow run-all, discover, etc.)

Deployment Modes:
    --mode local   : All MCPs run locally (default, full offline capability)
    --mode hybrid  : Mix of local and public MCPs (requires internet)

Pipeline Sequence (v2.1):
    DISCOVER → NORMALIZE → DOCS → IAC → CD → CI → E2E → REVIEW → TEST → SCAN → [APPROVAL] → BRIDGE

Examples:
    # Greenfield - New Project
    forgeflow init my-new-api              # Interactive wizard
    forgeflow init --quick my-service      # Quick start with defaults
    forgeflow init --guided                # Step-by-step guided mode
    
    # Brownfield - Existing Repo
    forgeflow discover --path ./my-repo
    forgeflow scan --severity high
    forgeflow iac --cloud aws              # Generate Terraform + Docker
    forgeflow ci                           # Generate GitHub Actions + GitLab CI
    forgeflow run-all ./my-repo
        """
    )
    
    # Global mode flag
    parser.add_argument("--mode", "-m", choices=["local", "hybrid"], default="local",
                        help="Deployment mode: local (default) or hybrid")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # === init (Greenfield) ===
    init_parser = subparsers.add_parser("init", help="Initialize new Greenfield project with interactive wizard")
    init_parser.add_argument("project_name", nargs="?", help="Project name (will be created as directory)")
    init_parser.add_argument("--guided", "-g", action="store_true", help="Step-by-step guided mode with explanations")
    init_parser.add_argument("--quick", "-q", action="store_true", help="Quick start with sensible defaults")
    init_parser.add_argument("--path", "-p", default=".", help="Parent directory for new project (default: .)")
    
    # === discover ===
    discover_parser = subparsers.add_parser("discover", help="Discover repository structure and components")
    discover_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    
    # === normalize ===
    normalize_parser = subparsers.add_parser("normalize", help="Normalize and standardize repository structure")
    normalize_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    
    # === scan ===
    scan_parser = subparsers.add_parser("scan", help="Run security vulnerability scan")
    scan_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    scan_parser.add_argument("--severity", "-s", default="medium", 
                             choices=["low", "medium", "high", "critical"],
                             help="Minimum severity threshold (default: medium)")
    
    # === generate ===
    generate_parser = subparsers.add_parser("generate", help="Generate deployment artifacts (legacy, uses GenerationAgent)")
    generate_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    generate_parser.add_argument("--stack", default="auto",
                                 choices=["auto", "docker", "kubernetes", "terraform", "helm"],
                                 help="Deployment stack (default: auto-detect)")
    
    # === iac === (IACAgent → iac-mcp-server)
    iac_parser = subparsers.add_parser("iac", help="Generate Infrastructure as Code (Terraform, Docker, Pulumi)")
    iac_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    iac_parser.add_argument("--cloud", "-c", default="aws",
                            choices=["aws", "gcp", "azure"],
                            help="Cloud provider (default: aws)")
    iac_parser.add_argument("--include-pulumi", action="store_true", help="Include Pulumi configuration")
    
    # === cd === (CDAgent → cd-mcp-server)
    cd_parser = subparsers.add_parser("cd", help="Generate Continuous Deployment configs (ArgoCD, Kustomize, K8s)")
    cd_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    cd_parser.add_argument("--repo-url", default="https://github.com/org/repo.git",
                           help="Git repository URL")
    cd_parser.add_argument("--include-flux", action="store_true", help="Include FluxCD configuration")
    cd_parser.add_argument("--include-helm", action="store_true", help="Include Helm charts")
    
    # === ci === (CIAgent → ci-mcp-server)
    ci_parser = subparsers.add_parser("ci", help="Generate CI pipelines (GitHub Actions, GitLab CI, Dependabot)")
    ci_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    ci_parser.add_argument("--no-gitlab", action="store_true", help="Skip GitLab CI generation")
    ci_parser.add_argument("--no-dependabot", action="store_true", help="Skip Dependabot configuration")
    
    # === e2e === (E2ETestingAgent → e2e-mcp-server)
    e2e_parser = subparsers.add_parser("e2e", help="Generate E2E testing setup (Playwright, Cypress)")
    e2e_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    e2e_parser.add_argument("--framework", "-f", default="playwright",
                            choices=["playwright", "cypress", "both"],
                            help="Testing framework (default: playwright)")
    e2e_parser.add_argument("--no-ci", action="store_true", help="Skip CI workflow generation")
    
    # === review === (CodeReviewAgent → git-mcp-server)
    review_parser = subparsers.add_parser("review", help="Run code review and quality analysis")
    review_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    
    # === test === (TestingAgent → cicd-mcp-server)
    test_parser = subparsers.add_parser("test", help="Run tests via CI/CD pipeline")
    test_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    
    # === deploy === (DeploymentAgent → cloud-mcp-server)
    deploy_parser = subparsers.add_parser("deploy", help="Deploy to cloud infrastructure")
    deploy_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    deploy_parser.add_argument("--target", "-t", default="staging",
                               choices=["staging", "production", "dev"],
                               help="Deployment target (default: staging)")
    
    # === monitor === (MonitoringAgent → observability-mcp-server)
    monitor_parser = subparsers.add_parser("monitor", help="Set up monitoring and observability")
    monitor_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    
    # === docs ===
    docs_parser = subparsers.add_parser("docs", help="Generate documentation and diagrams")
    docs_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    
    # === bridge ===
    bridge_parser = subparsers.add_parser("bridge", help="Bridge to GitHub (push, PR, sync)")
    bridge_parser.add_argument("--operation", "-o", choices=['init', 'push', 'pr', 'branch', 'status'], 
                              default='status', help="Operation: init, push, pr, branch, status (default: status)")
    bridge_parser.add_argument("--repo", "-r", help="GitHub repository (owner/repo)")
    bridge_parser.add_argument("--branch", "-b", help="Branch name (for branch/push operations)")
    bridge_parser.add_argument("--base-branch", default="main", help="Base branch for PR (default: main)")
    bridge_parser.add_argument("--message", default="Update from ForgeFlow", help="Commit message")
    bridge_parser.add_argument("--pr-title", help="Pull request title")
    bridge_parser.add_argument("--pr-body", help="Pull request body/description")
    
    # === status ===
    status_parser = subparsers.add_parser("status", help="Check pipeline status")
    status_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    
    # === doctor ===
    subparsers.add_parser("doctor", help="Run ForgeFlow internal health check")
    
    # === audit (composite command) ===
    audit_parser = subparsers.add_parser("audit", help="Run full audit pipeline (discover → normalize → scan → generate)")
    audit_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    audit_parser.add_argument("--severity", "-s", default="medium", help="Security severity threshold")
    audit_parser.add_argument("--stack", default="auto", help="Deployment stack")
    
    # === run-all (full pipeline + bridge) ===
    runall_parser = subparsers.add_parser("run-all", help="Run full pipeline: discover → normalize → docs → iac → cd → ci → e2e → review → test → scan → bridge")
    runall_parser.add_argument("path", nargs="?", default=".", help="Path to repository (default: .)")
    runall_parser.add_argument("--include-post-merge", action="store_true",
                               help="Include post-merge stages (deploy, monitor)")
    runall_parser.add_argument("--greenfield", action="store_true",
                               help="Greenfield mode: overwrite existing files (default: brownfield — skip existing)")

    return parser


def run_greenfield_init(args):
    """
    Run the Greenfield project initialization wizard.
    
    Returns the path to the created project.
    """
    from core.wizard import run_wizard, run_quick_wizard, confirm_config
    from core.stack_suggester import suggest_stack, display_stack_suggestion, approve_stack
    from agents.scaffolding_agent import ScaffoldingAgent
    
    project_name = args.project_name
    parent_path = Path(args.path).absolute()
    guided = getattr(args, 'guided', False)
    quick = getattr(args, 'quick', False)
    
    console.print()
    console.print("[bold cyan]🔨 ForgeFlow Greenfield Project Initialization[/]")
    console.print()
    
    # Step 1: Run wizard
    if quick:
        config = run_quick_wizard(project_name)
    else:
        config = run_wizard(project_name, guided=guided)
    
    # Step 2: Confirm configuration
    if not confirm_config(config):
        console.print("[yellow]Initialization cancelled.[/]")
        return None
    
    # Step 3: Generate stack suggestions
    console.print()
    console.print("[bold]Generating optimal stack recommendations...[/]")
    stack = suggest_stack(config)
    display_stack_suggestion(stack, config)
    
    # Step 4: Approve stack
    if not approve_stack(stack):
        console.print("[yellow]You can modify the stack or restart the wizard.[/]")
        return None
    
    # Step 5: Scaffold project
    console.print()
    console.print("[bold green]🚀 Scaffolding project...[/]")
    console.print()
    
    scaffolder = ScaffoldingAgent()
    result = scaffolder.execute({
        "path": str(parent_path),
        "config": config,
        "stack": stack
    })
    
    if result.get("status") == "success":
        project_path = result.get("data", {}).get("project_path", "")
        console.print()
        print_success_banner(f"Project '{config['project_name']}' created successfully!")
        console.print()
        console.print("[bold]Next steps:[/]")
        console.print(f"  1. cd {config['project_name']}")
        console.print("  2. forgeflow run-all .  # Run full pipeline")
        console.print("  3. docker compose up    # Start local development")
        console.print()
        return project_path
    else:
        print_error_banner("Failed to scaffold project", "init")
        console.print(f"[red]Error: {result.get('summary', 'Unknown error')}[/]")
        return None


def main():
    """Main entry point - parse arguments and delegate to MissionControl."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Get deployment mode
    mode = getattr(args, "mode", "local")
    
    # Change to target directory if specified
    path = getattr(args, "path", ".")
    if path != ".":
        path = os.path.abspath(path)
    
    try:
        # Handle init command separately (no MissionControl needed)
        if args.command == "init":
            result_path = run_greenfield_init(args)
            if result_path:
                sys.exit(0)
            else:
                sys.exit(1)
        
        # Create MissionControl instance with specified mode
        mc = MissionControl(mode=mode)
        
        # Show mode indicator for non-local mode
        if mode != "local":
            print_mode_indicator(mode)
        
        # Route to appropriate command
        if args.command == "discover":
            result = mc.discover(path)
            
        elif args.command == "normalize":
            result = mc.normalize(path)
            
        elif args.command == "scan":
            result = mc.scan(path, args.severity)
            
        elif args.command == "generate":
            result = mc.generate(path, args.stack)
            # Display generated files in enhanced format
            if result.get("status") == "success":
                print_generated_files(result)
            
        elif args.command == "iac":
            result = mc.iac(path, cloud=args.cloud, include_pulumi=args.include_pulumi)
            if result.get("status") == "success":
                print_generated_files(result)
            
        elif args.command == "cd":
            result = mc.cd(path, repo_url=args.repo_url,
                          include_flux=args.include_flux, include_helm=args.include_helm)
            if result.get("status") == "success":
                print_generated_files(result)
            
        elif args.command == "ci":
            result = mc.ci(path, include_gitlab=not args.no_gitlab,
                          include_dependabot=not args.no_dependabot)
            if result.get("status") == "success":
                print_generated_files(result)
            
        elif args.command == "e2e":
            result = mc.e2e(path, framework=args.framework, include_ci=not args.no_ci)
            if result.get("status") == "success":
                print_generated_files(result)
            
        elif args.command == "review":
            result = mc.review(path)
            
        elif args.command == "test":
            result = mc.test(path)
            
        elif args.command == "deploy":
            result = mc.deploy(path, args.target)
            
        elif args.command == "monitor":
            result = mc.monitor(path)
            
        elif args.command == "docs":
            result = mc.docs(path)
            
        elif args.command == "bridge":
            result = mc.bridge(
                repo=args.repo, 
                branch=args.branch,
                operation=args.operation,
                base_branch=getattr(args, 'base_branch', 'main'),
                message=getattr(args, 'message', 'Update from ForgeFlow'),
                pr_title=getattr(args, 'pr_title', None),
                pr_body=getattr(args, 'pr_body', None)
            )
            
        elif args.command == "status":
            result = mc.status(path)
            
        elif args.command == "doctor":
            result = mc.doctor()
            
        elif args.command == "audit":
            # Composite command: discover → normalize → scan → generate
            print_pipeline_header("FULL AUDIT PIPELINE", mode)
            
            stages = [
                ("discover", lambda: mc.discover(path)),
                ("normalize", lambda: mc.normalize(path)),
                ("scan", lambda: mc.scan(path, args.severity)),
                ("generate", lambda: mc.generate(path, args.stack)),
            ]
            
            results = []
            for stage_name, stage_fn in stages:
                print_stage_start(stage_name, path)
                result = stage_fn()
                results.append((stage_name, result))
                
                if result.get("status") not in ["success", "warning"]:
                    print_pipeline_summary(results, success=False)
                    print_error_banner(f"AUDIT FAILED: {stage_name.upper()} stage failed", stage_name)
                    sys.exit(1)
            
            print_pipeline_summary(results, success=True)
            print_success_banner("AUDIT COMPLETE: All stages passed")
            sys.exit(0)
        
        elif args.command == "run-all":
            # Check if this is a Greenfield or Brownfield project
            if is_greenfield_directory(path):
                console.print()
                console.print("[bold yellow]📁 Empty or new directory detected![/]")
                console.print()
                console.print("This looks like a [bold cyan]Greenfield[/] project (new/empty directory).")
                console.print()
                console.print("Options:")
                console.print("  1. Run [bold]forgeflow init[/] to create a new project with the wizard")
                console.print("  2. Add source files to the directory first")
                console.print()
                
                from rich.prompt import Confirm
                if Confirm.ask("Would you like to run the Greenfield wizard now?", default=True):
                    # Create mock args for init
                    class InitArgs:
                        project_name = Path(path).name if path != "." else None
                        path = str(Path(path).parent) if path != "." else "."
                        guided = False
                        quick = False
                    
                    result_path = run_greenfield_init(InitArgs())
                    if result_path:
                        # Ask if they want to continue with pipeline
                        if Confirm.ask("Run the full pipeline on the new project?", default=True):
                            path = result_path
                            # Auto-detected greenfield: always use greenfield=True
                            result = mc.run_all(path,
                                include_post_merge=getattr(args, 'include_post_merge', False),
                                greenfield=True)
                            if result.get("status") == "success":
                                sys.exit(0)
                            else:
                                sys.exit(1)
                        else:
                            sys.exit(0)
                    else:
                        sys.exit(1)
                else:
                    console.print("[dim]Run 'forgeflow init' when ready to create your project.[/]")
                    sys.exit(0)
            else:
                # Full pipeline: discover → normalize → docs → iac → cd → ci → e2e → review → test → scan → (approval) → bridge
                # Post-merge (optional): deploy → monitor
                include_post_merge = getattr(args, 'include_post_merge', False)
                greenfield = getattr(args, 'greenfield', False)
                result = mc.run_all(path, include_post_merge=include_post_merge, greenfield=greenfield)
                if result.get("status") == "success":
                    sys.exit(0)
                else:
                    sys.exit(1)
        
        else:
            parser.print_help()
            sys.exit(1)
        
        # Print result (for single commands)
        mc.print_result(result)
        
        # Exit with appropriate code
        if result.get("status") == "success":
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]⚠️  Operation cancelled by user[/]")
        sys.exit(130)
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Error: {str(e)}[/]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
