#!/usr/bin/env python3
"""
ForgeFlow CLI Entry Point

Usage:
    forgeflow [--mode MODE] discover [--path PATH]
    forgeflow [--mode MODE] normalize [--path PATH]
    forgeflow [--mode MODE] scan [--path PATH] [--severity LEVEL]
    forgeflow [--mode MODE] generate [--path PATH] [--stack STACK]
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

Deployment Modes:
    --mode local   : All MCPs run locally (default, full offline capability)
    --mode hybrid  : Mix of local and public MCPs (requires internet for some features)
    --mode public  : All MCPs run in cloud (thin client, requires FORGEFLOW_API_KEY)

New Pipeline Sequence:
    DISCOVER → NORMALIZE → DOCS → GENERATE → REVIEW → TEST → SCAN → [APPROVAL] → BRIDGE
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


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with all canonical commands."""
    parser = argparse.ArgumentParser(
        prog="forgeflow",
        description="ForgeFlow - AI Platform Engineering CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Deployment Modes:
    --mode local   : All MCPs run locally (default, full offline capability)
    --mode hybrid  : Mix of local and public MCPs (requires internet)
    --mode public  : All MCPs run in cloud (thin client, requires FORGEFLOW_API_KEY)

Pipeline Sequence:
    DISCOVER → NORMALIZE → DOCS → GENERATE → REVIEW → TEST → SCAN → [APPROVAL] → BRIDGE

Examples:
    forgeflow discover --path ./my-repo
    forgeflow scan --severity high
    forgeflow generate --stack kubernetes
    forgeflow --mode hybrid bridge --repo owner/repo
    forgeflow --mode public discover --path ./my-repo
    forgeflow run-all ./my-repo

Environment Variables (PUBLIC mode):
    FORGEFLOW_API_KEY  : API key for ForgeFlow cloud service
    FORGEFLOW_API_URL  : Optional custom API endpoint
        """
    )
    
    # Global mode flag
    parser.add_argument("--mode", "-m", choices=["local", "hybrid", "public"], default="local",
                        help="Deployment mode: local (default), hybrid, or public")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
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
    generate_parser = subparsers.add_parser("generate", help="Generate deployment artifacts")
    generate_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    generate_parser.add_argument("--stack", default="auto",
                                 choices=["auto", "docker", "kubernetes", "terraform", "helm"],
                                 help="Deployment stack (default: auto-detect)")
    
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

    # === iac ===
    iac_parser = subparsers.add_parser("iac", help="Generate Infrastructure-as-Code (Terraform, Pulumi)")
    iac_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    iac_parser.add_argument("--cloud", "-c", default="aws", choices=["aws", "gcp", "azure"],
                            help="Cloud provider (default: aws)")
    iac_parser.add_argument("--include-pulumi", action="store_true", help="Also generate Pulumi configs")

    # === cd ===
    cd_parser = subparsers.add_parser("cd", help="Generate Continuous Delivery configs (ArgoCD, Helm)")
    cd_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    cd_parser.add_argument("--repo-url", help="Git repository URL for ArgoCD")
    cd_parser.add_argument("--include-flux", action="store_true", help="Also generate Flux configs")

    # === ci ===
    ci_parser = subparsers.add_parser("ci", help="Generate Continuous Integration pipelines (GitHub Actions, GitLab)")
    ci_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    ci_parser.add_argument("--no-gitlab", action="store_true", help="Skip GitLab CI generation")
    ci_parser.add_argument("--no-dependabot", action="store_true", help="Skip Dependabot config")

    # === e2e ===
    e2e_parser = subparsers.add_parser("e2e", help="Generate E2E test scaffolding (Playwright, Cypress)")
    e2e_parser.add_argument("--path", "-p", default=".", help="Path to repository (default: .)")
    e2e_parser.add_argument("--framework", "-f", default="playwright",
                            choices=["playwright", "cypress", "selenium"],
                            help="E2E framework (default: playwright)")
    e2e_parser.add_argument("--no-ci", action="store_true", help="Skip CI integration for E2E tests")

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
    runall_parser = subparsers.add_parser("run-all", help="Run full pipeline: discover → normalize → docs → generate → review → test → scan → bridge")
    runall_parser.add_argument("path", nargs="?", default=".", help="Path to repository (default: .)")
    runall_parser.add_argument("--include-post-merge", action="store_true", 
                               help="Include post-merge stages (deploy, monitor)")
    
    return parser


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
        # Create MissionControl instance with specified mode
        mc = MissionControl(mode=mode)
        
        # PUBLIC mode: Check API key is configured
        if mode == "public":
            api_key = os.environ.get("FORGEFLOW_API_KEY")
            if not api_key:
                console.print("[bold yellow]⚠️  WARNING: FORGEFLOW_API_KEY not set[/]")
                console.print("[dim]Set your API key: export FORGEFLOW_API_KEY=your_key_here[/]")
                console.print()
        
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

        elif args.command == "iac":
            result = mc.iac(path, cloud=getattr(args, 'cloud', 'aws'),
                            include_pulumi=getattr(args, 'include_pulumi', False))

        elif args.command == "cd":
            result = mc.cd(path, repo_url=getattr(args, 'repo_url', None),
                           include_flux=getattr(args, 'include_flux', False))

        elif args.command == "ci":
            result = mc.ci(path,
                           include_gitlab=not getattr(args, 'no_gitlab', False),
                           include_dependabot=not getattr(args, 'no_dependabot', False))

        elif args.command == "e2e":
            result = mc.e2e(path, framework=getattr(args, 'framework', 'playwright'),
                            include_ci=not getattr(args, 'no_ci', False))

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
            # Full pipeline: discover → normalize → docs → generate → review → test → scan → (approval) → bridge
            # Post-merge (optional): deploy → monitor
            include_post_merge = getattr(args, 'include_post_merge', False)
            result = mc.run_all(path, include_post_merge=include_post_merge)
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
