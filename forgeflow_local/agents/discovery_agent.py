#!/usr/bin/env python3
"""
Discovery Agent - Scans repository to discover structure, components, and files.
Mapped to: discover command → discovery_mcp

Enhanced with comprehensive language and framework detection.
"""
import os
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, Any, List, Optional, Set, Tuple

from .base_agent import BaseAgent


# Comprehensive language extension mapping
LANGUAGE_EXTENSIONS = {
    # Python
    '.py': 'Python', '.pyx': 'Python (Cython)', '.pyi': 'Python (Stub)',
    '.pyw': 'Python', '.pyd': 'Python',
    
    # JavaScript/TypeScript
    '.js': 'JavaScript', '.jsx': 'JavaScript (React)',
    '.ts': 'TypeScript', '.tsx': 'TypeScript (React)',
    '.mjs': 'JavaScript (ES Module)', '.cjs': 'JavaScript (CommonJS)',
    '.vue': 'Vue', '.svelte': 'Svelte',
    
    # Go
    '.go': 'Go', '.mod': 'Go Module',
    
    # Rust
    '.rs': 'Rust', '.toml': 'TOML',
    
    # Java/JVM
    '.java': 'Java', '.jar': 'Java Archive',
    '.kt': 'Kotlin', '.kts': 'Kotlin Script',
    '.scala': 'Scala', '.sc': 'Scala Script',
    '.groovy': 'Groovy', '.gradle': 'Gradle',
    '.clj': 'Clojure', '.cljs': 'ClojureScript',
    
    # C/C++
    '.c': 'C', '.h': 'C Header',
    '.cpp': 'C++', '.cc': 'C++', '.cxx': 'C++',
    '.hpp': 'C++ Header', '.hh': 'C++ Header', '.hxx': 'C++ Header',
    '.m': 'Objective-C', '.mm': 'Objective-C++',
    
    # C#/.NET
    '.cs': 'C#', '.csx': 'C# Script',
    '.fs': 'F#', '.fsx': 'F# Script',
    '.vb': 'Visual Basic',
    
    # Ruby
    '.rb': 'Ruby', '.erb': 'ERB Template', '.rake': 'Rake',
    '.gemspec': 'Ruby Gem Spec',
    
    # PHP
    '.php': 'PHP', '.phtml': 'PHP HTML', '.php3': 'PHP',
    '.php4': 'PHP', '.php5': 'PHP', '.phps': 'PHP',
    
    # Swift
    '.swift': 'Swift',
    
    # Shell/Scripts
    '.sh': 'Shell', '.bash': 'Bash', '.zsh': 'Zsh',
    '.fish': 'Fish', '.ps1': 'PowerShell', '.psm1': 'PowerShell Module',
    '.bat': 'Batch', '.cmd': 'Batch',
    
    # Web
    '.html': 'HTML', '.htm': 'HTML', '.xhtml': 'XHTML',
    '.css': 'CSS', '.scss': 'SCSS', '.sass': 'Sass', '.less': 'Less',
    '.styl': 'Stylus',
    
    # Data/Config
    '.json': 'JSON', '.json5': 'JSON5', '.jsonc': 'JSON with Comments',
    '.yaml': 'YAML', '.yml': 'YAML',
    '.xml': 'XML', '.xsl': 'XSLT', '.xsd': 'XSD Schema',
    '.ini': 'INI', '.cfg': 'Config', '.conf': 'Config',
    '.env': 'Environment',
    
    # Database/SQL
    '.sql': 'SQL', '.mysql': 'MySQL', '.pgsql': 'PostgreSQL',
    '.sqlite': 'SQLite', '.prisma': 'Prisma',
    
    # Documentation
    '.md': 'Markdown', '.mdx': 'MDX', '.rst': 'reStructuredText',
    '.txt': 'Text', '.adoc': 'AsciiDoc',
    
    # Infrastructure
    '.tf': 'Terraform', '.tfvars': 'Terraform Variables',
    '.hcl': 'HCL',
    '.dockerfile': 'Docker',
    '.containerfile': 'Container',
    
    # Data Science
    '.ipynb': 'Jupyter Notebook', '.r': 'R', '.rmd': 'R Markdown',
    '.jl': 'Julia', '.mat': 'MATLAB',
    
    # Other languages
    '.lua': 'Lua', '.pl': 'Perl', '.pm': 'Perl Module',
    '.ex': 'Elixir', '.exs': 'Elixir Script',
    '.erl': 'Erlang', '.hrl': 'Erlang Header',
    '.hs': 'Haskell', '.lhs': 'Literate Haskell',
    '.ml': 'OCaml', '.mli': 'OCaml Interface',
    '.nim': 'Nim', '.zig': 'Zig', '.v': 'V',
    '.dart': 'Dart', '.coffee': 'CoffeeScript',
    '.elm': 'Elm', '.purs': 'PureScript',
    
    # Assembly
    '.asm': 'Assembly', '.s': 'Assembly',
    
    # Misc
    '.proto': 'Protocol Buffers', '.thrift': 'Thrift',
    '.graphql': 'GraphQL', '.gql': 'GraphQL',
    '.wasm': 'WebAssembly', '.wat': 'WebAssembly Text',
}

# Special filenames (no extension)
SPECIAL_FILES = {
    'dockerfile': 'Docker',
    'containerfile': 'Docker',
    'makefile': 'Makefile',
    'gnumakefile': 'Makefile',
    'cmakelists.txt': 'CMake',
    'rakefile': 'Ruby',
    'gemfile': 'Ruby',
    'procfile': 'Heroku',
    'vagrantfile': 'Vagrant',
    'jenkinsfile': 'Jenkins',
    'justfile': 'Just',
    'taskfile.yml': 'Taskfile',
    'brewfile': 'Homebrew',
    '.gitignore': 'Git Config',
    '.gitattributes': 'Git Config',
    '.editorconfig': 'Editor Config',
    '.prettierrc': 'Prettier Config',
    '.eslintrc': 'ESLint Config',
    '.babelrc': 'Babel Config',
}

# Framework detection patterns in config files
FRAMEWORK_PATTERNS = {
    'package.json': {
        'react': 'React',
        'react-dom': 'React',
        'next': 'Next.js',
        'nuxt': 'Nuxt.js',
        'vue': 'Vue.js',
        '@vue/cli': 'Vue.js',
        '@angular/core': 'Angular',
        'express': 'Express.js',
        'fastify': 'Fastify',
        'nestjs': 'NestJS',
        '@nestjs/core': 'NestJS',
        'koa': 'Koa',
        'hapi': 'Hapi',
        'svelte': 'Svelte',
        'gatsby': 'Gatsby',
        'remix': 'Remix',
        'astro': 'Astro',
        'electron': 'Electron',
        'react-native': 'React Native',
        'expo': 'Expo',
        'three': 'Three.js',
        'd3': 'D3.js',
        'tailwindcss': 'Tailwind CSS',
        'webpack': 'Webpack',
        'vite': 'Vite',
        'esbuild': 'esbuild',
        'rollup': 'Rollup',
        'parcel': 'Parcel',
        'jest': 'Jest',
        'mocha': 'Mocha',
        'cypress': 'Cypress',
        'playwright': 'Playwright',
        'prisma': 'Prisma',
        'typeorm': 'TypeORM',
        'sequelize': 'Sequelize',
        'mongoose': 'Mongoose',
        'graphql': 'GraphQL',
        'apollo-server': 'Apollo GraphQL',
        'socket.io': 'Socket.IO',
        'redux': 'Redux',
        'zustand': 'Zustand',
        'mobx': 'MobX',
    },
    'requirements.txt': {
        'django': 'Django',
        'flask': 'Flask',
        'fastapi': 'FastAPI',
        'starlette': 'Starlette',
        'tornado': 'Tornado',
        'aiohttp': 'aiohttp',
        'sanic': 'Sanic',
        'pyramid': 'Pyramid',
        'bottle': 'Bottle',
        'falcon': 'Falcon',
        'celery': 'Celery',
        'dramatiq': 'Dramatiq',
        'sqlalchemy': 'SQLAlchemy',
        'peewee': 'Peewee',
        'django-rest-framework': 'Django REST Framework',
        'djangorestframework': 'Django REST Framework',
        'graphene': 'Graphene (GraphQL)',
        'strawberry-graphql': 'Strawberry GraphQL',
        'pytest': 'pytest',
        'unittest': 'unittest',
        'numpy': 'NumPy',
        'pandas': 'Pandas',
        'scipy': 'SciPy',
        'scikit-learn': 'scikit-learn',
        'tensorflow': 'TensorFlow',
        'torch': 'PyTorch',
        'keras': 'Keras',
        'transformers': 'Hugging Face Transformers',
        'langchain': 'LangChain',
        'streamlit': 'Streamlit',
        'gradio': 'Gradio',
        'dash': 'Dash',
        'plotly': 'Plotly',
        'matplotlib': 'Matplotlib',
        'seaborn': 'Seaborn',
        'pydantic': 'Pydantic',
        'httpx': 'HTTPX',
        'requests': 'Requests',
        'beautifulsoup4': 'BeautifulSoup',
        'scrapy': 'Scrapy',
        'selenium': 'Selenium',
        'playwright': 'Playwright',
    },
    'pyproject.toml': {
        'django': 'Django',
        'flask': 'Flask',
        'fastapi': 'FastAPI',
        'poetry': 'Poetry',
        'black': 'Black',
        'ruff': 'Ruff',
        'mypy': 'mypy',
    },
    'go.mod': {
        'gin-gonic/gin': 'Gin',
        'labstack/echo': 'Echo',
        'gofiber/fiber': 'Fiber',
        'gorilla/mux': 'Gorilla Mux',
        'go-chi/chi': 'Chi',
        'beego/beego': 'Beego',
        'revel/revel': 'Revel',
        'gobuffalo/buffalo': 'Buffalo',
        'gorm.io/gorm': 'GORM',
        'go.uber.org/zap': 'Zap Logger',
        'sirupsen/logrus': 'Logrus',
        'spf13/cobra': 'Cobra CLI',
        'spf13/viper': 'Viper Config',
    },
    'Cargo.toml': {
        'actix-web': 'Actix Web',
        'axum': 'Axum',
        'rocket': 'Rocket',
        'warp': 'Warp',
        'tokio': 'Tokio',
        'async-std': 'async-std',
        'diesel': 'Diesel ORM',
        'sqlx': 'SQLx',
        'serde': 'Serde',
        'clap': 'Clap CLI',
        'tauri': 'Tauri',
        'yew': 'Yew',
        'leptos': 'Leptos',
    },
    'pom.xml': {
        'spring-boot': 'Spring Boot',
        'spring-framework': 'Spring',
        'spring-webflux': 'Spring WebFlux',
        'quarkus': 'Quarkus',
        'micronaut': 'Micronaut',
        'vert.x': 'Vert.x',
        'hibernate': 'Hibernate',
        'mybatis': 'MyBatis',
        'junit': 'JUnit',
        'mockito': 'Mockito',
    },
    'build.gradle': {
        'spring-boot': 'Spring Boot',
        'ktor': 'Ktor',
        'android': 'Android',
        'kotlin': 'Kotlin',
    },
    'composer.json': {
        'laravel/framework': 'Laravel',
        'symfony/symfony': 'Symfony',
        'slim/slim': 'Slim',
        'cakephp/cakephp': 'CakePHP',
        'yiisoft/yii2': 'Yii 2',
    },
    'Gemfile': {
        'rails': 'Ruby on Rails',
        'sinatra': 'Sinatra',
        'hanami': 'Hanami',
        'grape': 'Grape',
        'rspec': 'RSpec',
    },
    'pubspec.yaml': {
        'flutter': 'Flutter',
    },
    'mix.exs': {
        'phoenix': 'Phoenix',
    },
}

IGNORE_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env',
    '.tox', '.pytest_cache', 'dist', 'build', '.idea', '.vscode',
    '.mypy_cache', '.ruff_cache', '.cache', '.eggs', '*.egg-info',
    'target', 'vendor', 'Pods', '.gradle', '.nuxt', '.next',
    'coverage', '.nyc_output', '.parcel-cache', '.turbo',
    '.terraform', '.serverless', 'cdk.out',
}

# Shebang to language mapping
SHEBANG_PATTERNS = {
    'python': 'Python',
    'python3': 'Python',
    'node': 'JavaScript',
    'nodejs': 'JavaScript',
    'ruby': 'Ruby',
    'perl': 'Perl',
    'bash': 'Bash',
    'sh': 'Shell',
    'zsh': 'Zsh',
    'php': 'PHP',
    'lua': 'Lua',
    'julia': 'Julia',
}


class DiscoveryAgent(BaseAgent):
    """Agent that discovers repository structure, languages, and frameworks."""
    
    def __init__(self):
        super().__init__(
            name="discovery_agent",
            description="Scans repository to discover structure, languages, frameworks, and components"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute discovery scan on repository."""
        repo_path = Path(params.get('path', '.'))
        inventory = []
        frameworks_detected: Set[str] = set()
        
        self.log(f"Scanning {repo_path.absolute()}...")
        
        # First pass: detect frameworks from config files
        frameworks_detected = self._detect_frameworks(repo_path)
        
        # Second pass: scan all files
        for root, dirs, files in os.walk(repo_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
            
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
        
        # Build comprehensive summary
        languages = Counter([f['language'] for f in inventory if f['language'] != 'Other'])
        all_languages = Counter([f['language'] for f in inventory])
        components = Counter([f['component_name'] for f in inventory])
        types = Counter([f['component_type'] for f in inventory])
        
        # Calculate language percentages
        total_source_files = sum(languages.values())
        language_percentages = {}
        if total_source_files > 0:
            for lang, count in languages.most_common(15):
                pct = round((count / total_source_files) * 100, 1)
                language_percentages[lang] = {'count': count, 'percentage': pct}
        
        # Detect primary language
        primary_language = languages.most_common(1)[0][0] if languages else 'Unknown'
        
        # Save inventory to .forgeflow/
        forgeflow_dir = repo_path / '.forgeflow'
        forgeflow_dir.mkdir(exist_ok=True)
        inventory_file = forgeflow_dir / 'inventory.json'
        
        discovery_data = {
            'inventory': inventory,
            'summary': {
                'primary_language': primary_language,
                'languages': language_percentages,
                'frameworks': list(frameworks_detected),
                'total_files': len(inventory),
                'components': dict(components.most_common(10)),
                'types': dict(types),
            }
        }
        
        with open(inventory_file, 'w') as f:
            json.dump(discovery_data, f, indent=2)
        
        self.log(f"Discovered {len(inventory)} files across {len(components)} components")
        
        # Build findings summary
        findings = [
            f"📁 Total files: {len(inventory)}",
            f"🔤 Primary language: {primary_language}",
        ]
        
        if language_percentages:
            lang_summary = ', '.join([f"{lang} ({data['percentage']}%)" 
                                      for lang, data in list(language_percentages.items())[:5]])
            findings.append(f"📊 Languages: {lang_summary}")
        
        if frameworks_detected:
            findings.append(f"🛠️  Frameworks: {', '.join(sorted(frameworks_detected))}")
        
        findings.append(f"📦 Components: {', '.join(list(components.keys())[:5])}")
        
        return self.create_result(
            status='success',
            summary=f"Discovered {len(inventory)} files, primary language: {primary_language}",
            data={
                'total_files': len(inventory),
                'primary_language': primary_language,
                'languages': language_percentages,
                'all_languages': dict(all_languages.most_common(20)),
                'frameworks': list(frameworks_detected),
                'components': dict(components.most_common(10)),
                'types': dict(types),
                'inventory_file': str(inventory_file)
            },
            findings=findings
        )
    
    def _detect_language(self, path: Path) -> str:
        """Detect language from file extension, name, or shebang."""
        filename_lower = path.name.lower()
        
        # Check special filenames first
        if filename_lower in SPECIAL_FILES:
            return SPECIAL_FILES[filename_lower]
        
        # Check for files without extension by name patterns
        if filename_lower.startswith('dockerfile'):
            return 'Docker'
        if filename_lower.startswith('makefile'):
            return 'Makefile'
        if filename_lower.startswith('cmakelists'):
            return 'CMake'
        
        # Check extension
        ext = path.suffix.lower()
        if ext in LANGUAGE_EXTENSIONS:
            return LANGUAGE_EXTENSIONS[ext]
        
        # Try to detect from shebang for files without extension
        if not ext or ext not in LANGUAGE_EXTENSIONS:
            shebang_lang = self._detect_from_shebang(path)
            if shebang_lang:
                return shebang_lang
        
        return 'Other'
    
    def _detect_from_shebang(self, path: Path) -> Optional[str]:
        """Detect language from shebang line."""
        try:
            with open(path, 'r', errors='ignore') as f:
                first_line = f.readline(256).strip()
                if first_line.startswith('#!'):
                    shebang = first_line[2:].strip()
                    # Handle /usr/bin/env python3 style
                    parts = shebang.split()
                    if parts:
                        interpreter = parts[-1] if 'env' in parts[0] else parts[0]
                        interpreter = Path(interpreter).name
                        # Remove version numbers
                        for pattern, lang in SHEBANG_PATTERNS.items():
                            if interpreter.startswith(pattern):
                                return lang
        except Exception:
            pass
        return None
    
    def _detect_frameworks(self, repo_path: Path) -> Set[str]:
        """Detect frameworks from config files."""
        frameworks: Set[str] = set()
        
        for config_file, patterns in FRAMEWORK_PATTERNS.items():
            config_path = repo_path / config_file
            if config_path.exists():
                try:
                    content = config_path.read_text(errors='ignore').lower()
                    for pattern, framework in patterns.items():
                        if pattern.lower() in content:
                            frameworks.add(framework)
                except Exception:
                    pass
        
        # Check for specific framework indicators
        self._check_framework_indicators(repo_path, frameworks)
        
        return frameworks
    
    def _check_framework_indicators(self, repo_path: Path, frameworks: Set[str]):
        """Check for framework-specific files and directories."""
        indicators = {
            # Django
            'manage.py': 'Django',
            'django.conf': 'Django',
            # Angular
            'angular.json': 'Angular',
            # Vue
            'vue.config.js': 'Vue.js',
            'nuxt.config.js': 'Nuxt.js',
            'nuxt.config.ts': 'Nuxt.js',
            # React/Next
            'next.config.js': 'Next.js',
            'next.config.mjs': 'Next.js',
            'next.config.ts': 'Next.js',
            'gatsby-config.js': 'Gatsby',
            # Svelte
            'svelte.config.js': 'Svelte',
            # Astro
            'astro.config.mjs': 'Astro',
            # Remix
            'remix.config.js': 'Remix',
            # Rails
            'Rakefile': 'Ruby on Rails',
            'config.ru': 'Ruby (Rack)',
            # Spring Boot
            'application.properties': 'Spring Boot',
            'application.yml': 'Spring Boot',
            # Flutter
            'pubspec.yaml': 'Flutter/Dart',
            # Terraform
            'main.tf': 'Terraform',
            # Kubernetes
            'kustomization.yaml': 'Kustomize',
            # Docker
            'docker-compose.yml': 'Docker Compose',
            'docker-compose.yaml': 'Docker Compose',
            # Serverless
            'serverless.yml': 'Serverless Framework',
            'serverless.yaml': 'Serverless Framework',
            'sam.yaml': 'AWS SAM',
            'template.yaml': 'AWS SAM/CloudFormation',
            # CDK
            'cdk.json': 'AWS CDK',
        }
        
        for indicator, framework in indicators.items():
            if (repo_path / indicator).exists():
                frameworks.add(framework)
        
        # Check directories
        dir_indicators = {
            'pages': 'Next.js',  # Next.js pages dir
            'app': 'Next.js (App Router)',  # Next.js app dir
            '.next': 'Next.js',
            '.nuxt': 'Nuxt.js',
            'migrations': 'Database Migrations',
            'terraform': 'Terraform',
            'k8s': 'Kubernetes',
            'kubernetes': 'Kubernetes',
            'helm': 'Helm',
            'charts': 'Helm',
            'ansible': 'Ansible',
        }
        
        for dir_name, framework in dir_indicators.items():
            if (repo_path / dir_name).is_dir():
                # Additional check for Next.js pages/app dir
                if dir_name in ['pages', 'app']:
                    # Only add if we have other Next.js indicators
                    if (repo_path / 'next.config.js').exists() or \
                       (repo_path / 'next.config.mjs').exists() or \
                       (repo_path / 'package.json').exists():
                        frameworks.add(framework)
                else:
                    frameworks.add(framework)
    
    def _detect_component_type(self, path: Path) -> str:
        """Detect component type from path."""
        path_str = str(path).lower()
        filename = path.name.lower()
        
        # Test files
        if 'test' in path_str or 'spec' in path_str or '__tests__' in path_str:
            return 'test'
        if filename.startswith('test_') or filename.endswith('_test.py'):
            return 'test'
        if filename.endswith('.test.js') or filename.endswith('.test.ts'):
            return 'test'
        if filename.endswith('.spec.js') or filename.endswith('.spec.ts'):
            return 'test'
        
        # Config files
        config_patterns = ['.yaml', '.yml', '.json', '.toml', '.ini', '.cfg', '.conf', '.env']
        if 'config' in path_str or any(filename.endswith(p) for p in config_patterns):
            return 'config'
        
        # Container files
        if 'docker' in path_str or filename.startswith('dockerfile') or filename == 'containerfile':
            return 'container'
        
        # CI/CD files
        if '.github' in path_str or '.gitlab' in path_str or 'ci' in filename:
            return 'cicd'
        if filename in ['jenkinsfile', '.travis.yml', 'azure-pipelines.yml', 'bitbucket-pipelines.yml']:
            return 'cicd'
        
        # Infrastructure
        if 'terraform' in path_str or 'infrastructure' in path_str or 'infra' in path_str:
            return 'infrastructure'
        if filename.endswith('.tf') or filename.endswith('.tfvars'):
            return 'infrastructure'
        
        # Documentation
        if 'doc' in path_str or filename.endswith('.md') or filename.endswith('.rst'):
            return 'documentation'
        
        # Source code
        if 'src' in path_str or 'lib' in path_str or 'app' in path_str:
            return 'source'
        if 'components' in path_str or 'pages' in path_str or 'views' in path_str:
            return 'source'
        
        # API/Routes
        if 'api' in path_str or 'routes' in path_str or 'controllers' in path_str:
            return 'api'
        
        # Models/Database
        if 'models' in path_str or 'schemas' in path_str or 'migrations' in path_str:
            return 'database'
        
        # Static assets
        if 'static' in path_str or 'assets' in path_str or 'public' in path_str:
            return 'static'
        
        return 'other'
