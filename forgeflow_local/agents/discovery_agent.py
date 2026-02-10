#!/usr/bin/env python3
"""
Discovery Agent - Scans repository to discover structure, components, and files.
Mapped to: discover command → discovery_mcp
"""
import os
import json
from pathlib import Path
from collections import Counter
from typing import Dict, Any

from .base_agent import BaseAgent
from core.ai_enhancer import get_ai_enhancer


LANGUAGE_EXTENSIONS = {
    '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
    '.jsx': 'React', '.tsx': 'React TypeScript', '.java': 'Java',
    '.go': 'Go', '.rs': 'Rust', '.rb': 'Ruby', '.php': 'PHP',
    '.c': 'C', '.cpp': 'C++', '.cs': 'C#', '.swift': 'Swift',
    '.kt': 'Kotlin', '.scala': 'Scala', '.r': 'R',
    '.yaml': 'YAML', '.yml': 'YAML', '.json': 'JSON',
    '.xml': 'XML', '.html': 'HTML', '.css': 'CSS',
    '.md': 'Markdown', '.tf': 'Terraform', '.sh': 'Shell',
    '.dockerfile': 'Docker', '.sql': 'SQL'
}

IGNORE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv',
               '.tox', '.pytest_cache', 'dist', 'build', '.idea', '.vscode'}


class DiscoveryAgent(BaseAgent):
    """Agent that discovers repository structure and components."""
    
    def __init__(self):
        super().__init__(
            name="discovery_agent",
            description="Scans repository to discover structure, components, and files"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute discovery scan on repository."""
        repo_path = Path(params.get('path', '.'))
        inventory = []
        
        self.log(f"Scanning {repo_path.absolute()}...")
        
        for root, dirs, files in os.walk(repo_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for filename in files:
                file_path = Path(root) / filename
                try:
                    rel_path = file_path.relative_to(repo_path)
                    language = self._detect_language(file_path)
                    component_type = self._detect_component_type(file_path)
                    
                    # Get component name (parent folder or root)
                    parts = rel_path.parts
                    component_name = parts[0] if len(parts) > 1 else 'root'
                    
                    inventory.append({
                        'path': str(rel_path),
                        'filename': filename,
                        'language': language,
                        'component_type': component_type,
                        'component_name': component_name,
                        'size': file_path.stat().st_size if file_path.exists() else 0
                    })
                except Exception:
                    pass  # Skip files that can't be processed
        
        # Build summary
        languages = Counter([f['language'] for f in inventory])
        components = Counter([f['component_name'] for f in inventory])
        types = Counter([f['component_type'] for f in inventory])
        
        # Create .forgeflow directory first
        forgeflow_dir = repo_path / '.forgeflow'
        forgeflow_dir.mkdir(exist_ok=True)
        inventory_file = forgeflow_dir / 'inventory.json'
        
        basic_discovery = {
            'total_files': len(inventory),
            'languages': dict(languages.most_common(10)),
            'components': dict(components.most_common(10)),
            'types': dict(types),
            'inventory_file': str(inventory_file)
        }
        
        # AI Enhancement: Extract dependency files and get AI insights
        ai_enhancer = get_ai_enhancer()
        if ai_enhancer.is_available():
            self.log("🤖 AI enhancement enabled - analyzing with Claude...")
            
            # Collect dependency files and key files for AI analysis
            sample_files = self._collect_sample_files(repo_path)
            
            # Get AI-enhanced discovery
            enhanced_discovery = ai_enhancer.enhance_discovery(
                str(repo_path),
                basic_discovery,
                sample_files
            )
            
            self.log(f"✅ AI detected: {len(enhanced_discovery.get('services', []))} services, "
                    f"{len(enhanced_discovery.get('frameworks', []))} frameworks, "
                    f"{len(enhanced_discovery.get('databases', []))} databases")
            
            final_discovery = enhanced_discovery
        else:
            self.log("⚠️  AI enhancement disabled (CLAUDE_API_KEY not set)")
            final_discovery = basic_discovery
        
        # Save inventory to .forgeflow/ (directory already created above)
        with open(inventory_file, 'w') as f:
            json.dump(inventory, f, indent=2)
        
        # Save discovery results with AI insights
        discovery_file = forgeflow_dir / 'discovery.json'
        with open(discovery_file, 'w') as f:
            json.dump(final_discovery, f, indent=2)
        
        self.log(f"Discovered {len(inventory)} files across {len(components)} components")
        
        # Build findings with AI insights
        findings = [
            f"Total files: {len(inventory)}",
            f"Languages: {', '.join(languages.keys())}",
            f"Components: {', '.join(list(components.keys())[:5])}"
        ]
        
        if 'frameworks' in final_discovery:
            # Handle both list of strings and list of dicts
            frameworks = final_discovery['frameworks']
            if frameworks and isinstance(frameworks[0], dict):
                framework_names = [f.get('name', str(f)) for f in frameworks]
            else:
                framework_names = frameworks
            findings.append(f"Frameworks: {', '.join(framework_names)}")
        
        if 'databases' in final_discovery:
            # Handle both list of strings and list of dicts
            databases = final_discovery['databases']
            if databases and isinstance(databases[0], dict):
                db_names = [d.get('type', str(d)) for d in databases]
            else:
                db_names = databases
            findings.append(f"Databases: {', '.join(db_names)}")
        
        if 'architecture' in final_discovery:
            findings.append(f"Architecture: {final_discovery['architecture']}")
        if 'services' in final_discovery:
            findings.append(f"Services detected: {len(final_discovery['services'])}")
        
        return self.create_result(
            status='success',
            summary=f"Discovered {len(inventory)} files across {len(components)} components",
            data=final_discovery,
            findings=findings
        )
    
    def _detect_language(self, path: Path) -> str:
        """Detect language from file extension."""
        ext = path.suffix.lower()
        if path.name.lower() == 'dockerfile':
            return 'Docker'
        return LANGUAGE_EXTENSIONS.get(ext, 'Other')
    
    def _detect_component_type(self, path: Path) -> str:
        """Detect component type from path."""
        path_str = str(path).lower()
        if 'test' in path_str or 'spec' in path_str:
            return 'test'
        if 'config' in path_str or path.suffix in ['.yaml', '.yml', '.json', '.toml']:
            return 'config'
        if 'docker' in path_str or path.name.lower() == 'dockerfile':
            return 'container'
        if '.github' in path_str or 'ci' in path_str:
            return 'cicd'
        if 'src' in path_str or 'lib' in path_str:
            return 'source'
        return 'other'
    
    def _collect_sample_files(self, repo_path: Path) -> Dict[str, str]:
        """Collect key files for AI analysis."""
        sample_files = {}
        
        # Key dependency files to look for
        key_files = [
            'requirements.txt', 'Pipfile', 'pyproject.toml', 'setup.py',
            'package.json', 'package-lock.json', 'yarn.lock',
            'go.mod', 'go.sum',
            'Gemfile', 'Gemfile.lock',
            'pom.xml', 'build.gradle',
            'Cargo.toml',
            'README.md', 'README.txt',
            'docker-compose.yml', 'docker-compose.yaml',
            'Dockerfile',
            '.env.example', 'config.yaml', 'config.json'
        ]
        
        # Search for key files
        for filename in key_files:
            file_path = repo_path / filename
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(5000)  # Read first 5KB
                        sample_files[filename] = content
                except Exception:
                    pass
        
        # Also check subdirectories for multi-service apps
        for subdir in ['backend', 'frontend', 'api', 'web', 'client', 'server']:
            subdir_path = repo_path / subdir
            if subdir_path.exists() and subdir_path.is_dir():
                for filename in ['requirements.txt', 'package.json', 'Dockerfile']:
                    file_path = subdir_path / filename
                    if file_path.exists():
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read(5000)
                                sample_files[f"{subdir}/{filename}"] = content
                        except Exception:
                            pass
        
        return sample_files
