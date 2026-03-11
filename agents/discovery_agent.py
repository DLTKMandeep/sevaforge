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
        
        # Save inventory to .forgeflow/
        forgeflow_dir = repo_path / '.forgeflow'
        forgeflow_dir.mkdir(exist_ok=True)
        inventory_file = forgeflow_dir / 'inventory.json'
        with open(inventory_file, 'w') as f:
            json.dump(inventory, f, indent=2)
        
        self.log(f"Discovered {len(inventory)} files across {len(components)} components")
        
        return self.create_result(
            status='success',
            summary=f"Discovered {len(inventory)} files across {len(components)} components",
            data={
                'total_files': len(inventory),
                'languages': dict(languages.most_common(10)),
                'components': dict(components.most_common(10)),
                'types': dict(types),
                'inventory_file': str(inventory_file)
            },
            findings=[
                f"Total files: {len(inventory)}",
                f"Languages: {', '.join(languages.keys())}",
                f"Components: {', '.join(list(components.keys())[:5])}"
            ]
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
