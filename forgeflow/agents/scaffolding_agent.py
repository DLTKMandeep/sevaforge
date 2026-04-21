"""
ForgeFlow Scaffolding Agent
Generates initial project structure for Greenfield projects.

Creates:
- Project directory structure
- Boilerplate source code (main.py, app.js, etc.)
- Dockerfile with multi-stage build
- docker-compose.yml for local development
- Basic test files
- README.md
- Configuration files
"""
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent


class ScaffoldingAgent(BaseAgent):
    """
    Agent for scaffolding new Greenfield projects.
    
    Takes wizard configuration and stack suggestions to generate
    a complete project structure ready for development.
    """

    intelligence_phase = 2
    intelligence_label = "Automated"

    def __init__(self):
        super().__init__(
            name="ScaffoldingAgent",
            description="Scaffold new project structures"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute project scaffolding.
        
        Args:
            params: {
                "path": Target directory path,
                "config": Wizard configuration,
                "stack": Stack suggestions
            }
            
        Returns:
            Result with generated files list
        """
        path = Path(params.get("path", ".")).absolute()
        config = params.get("config", {})
        stack = params.get("stack", {})
        
        project_name = config.get("project_name", "my-project")
        language = config.get("language", "python")
        framework = config.get("framework", "none")
        app_type = config.get("app_type", "api")
        database = config.get("database", "none")
        kubernetes = config.get("kubernetes", True)
        cicd = config.get("cicd", "github-actions")
        services = config.get("services", [])
        
        self.log(f"Scaffolding {language} {app_type} project: {project_name}")
        
        generated_files = []
        findings = []
        
        # Create base project directory
        project_path = path / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Create directory structure
        dirs = self._create_directories(project_path, language, app_type)
        findings.append(f"Created {len(dirs)} directories")
        
        # 2. Generate source code
        src_files = self._generate_source_code(
            project_path, language, framework, app_type, project_name
        )
        generated_files.extend(src_files)
        findings.append(f"Generated {len(src_files)} source files")
        
        # 3. Generate Dockerfile
        dockerfile = self._generate_dockerfile(
            project_path, language, framework, stack
        )
        generated_files.append(dockerfile)
        findings.append("Generated multi-stage Dockerfile")
        
        # 4. Generate docker-compose.yml
        compose = self._generate_docker_compose(
            project_path, project_name, database, services
        )
        generated_files.append(compose)
        findings.append("Generated docker-compose.yml")
        
        # 5. Generate tests
        test_files = self._generate_tests(project_path, language, framework)
        generated_files.extend(test_files)
        findings.append(f"Generated {len(test_files)} test files")
        
        # 6. Generate configuration files
        config_files = self._generate_config_files(
            project_path, language, framework, stack
        )
        generated_files.extend(config_files)
        findings.append(f"Generated {len(config_files)} config files")
        
        # 7. Generate README.md
        readme = self._generate_readme(
            project_path, project_name, language, framework, app_type, config
        )
        generated_files.append(readme)
        findings.append("Generated README.md")
        
        # 8. Generate CI/CD workflows
        cicd_files = self._generate_cicd(
            project_path, cicd, language, kubernetes
        )
        generated_files.extend(cicd_files)
        findings.append(f"Generated CI/CD configuration ({cicd})")
        
        # 9. Generate .gitignore
        gitignore = self._generate_gitignore(project_path, language)
        generated_files.append(gitignore)
        
        # 10. Initialize git
        self._init_git(project_path)
        findings.append("Initialized git repository")
        
        return self.create_result(
            status="success",
            summary=f"Scaffolded {project_name} with {len(generated_files)} files",
            data={
                "project_path": str(project_path),
                "generated_files": generated_files,
                "language": language,
                "framework": framework,
                "app_type": app_type,
            },
            findings=findings
        )
    
    def _create_directories(
        self, 
        project_path: Path, 
        language: str, 
        app_type: str
    ) -> List[str]:
        """Create project directory structure."""
        dirs = []
        
        # Common directories
        common_dirs = [
            "src",
            "tests",
            "docs",
            "config",
            "scripts",
            ".forgeflow",
        ]
        
        # Language-specific directories
        if language == "python":
            common_dirs.extend(["src/__pycache__", "tests/__pycache__"])
        elif language in ["nodejs", "typescript"]:
            common_dirs.extend(["src/routes", "src/middleware", "src/utils"])
        elif language == "go":
            common_dirs.extend(["cmd", "internal", "pkg"])
        elif language == "java":
            common_dirs.extend([
                "src/main/java",
                "src/main/resources",
                "src/test/java",
            ])
        elif language == "rust":
            common_dirs.extend(["src/bin", "src/lib"])
        
        # App type specific
        if app_type == "web-app":
            common_dirs.extend(["static", "templates", "public"])
        elif app_type == "api":
            common_dirs.extend(["src/api", "src/models", "src/schemas"])
        elif app_type == "microservice":
            common_dirs.extend(["src/handlers", "src/services"])
        
        for dir_name in common_dirs:
            dir_path = project_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
            dirs.append(str(dir_path))
        
        return dirs
    
    def _generate_source_code(
        self,
        project_path: Path,
        language: str,
        framework: str,
        app_type: str,
        project_name: str
    ) -> List[str]:
        """Generate boilerplate source code."""
        files = []
        
        if language == "python":
            files.extend(self._generate_python_code(
                project_path, framework, app_type, project_name
            ))
        elif language in ["nodejs", "typescript"]:
            files.extend(self._generate_node_code(
                project_path, framework, app_type, project_name, language
            ))
        elif language == "go":
            files.extend(self._generate_go_code(
                project_path, framework, app_type, project_name
            ))
        
        return files
    
    def _generate_python_code(
        self,
        project_path: Path,
        framework: str,
        app_type: str,
        project_name: str
    ) -> List[str]:
        """Generate Python source code."""
        files = []
        
        # Main application file
        if framework == "fastapi":
            main_content = '''"""
{project_name} - FastAPI Application
Generated by ForgeFlow
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="{project_name}",
    description="API generated by ForgeFlow",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {{"message": "Welcome to {project_name}"}}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {{"status": "healthy"}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''.format(project_name=project_name)
        
        elif framework == "flask":
            main_content = '''"""
{project_name} - Flask Application
Generated by ForgeFlow
"""
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def root():
    """Root endpoint."""
    return jsonify({{"message": "Welcome to {project_name}"}})


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({{"status": "healthy"}})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
'''.format(project_name=project_name)
        
        elif framework == "django":
            main_content = '''"""
{project_name} - Django Application
Generated by ForgeFlow

Run with: python manage.py runserver
"""
# Django app will be created with django-admin startproject
# This is a placeholder main.py
print("Run: django-admin startproject {project_name}")
'''.format(project_name=project_name)
        
        else:
            main_content = '''"""
{project_name} - Python Application
Generated by ForgeFlow
"""

def main():
    """Main entry point."""
    print("Welcome to {project_name}")


if __name__ == "__main__":
    main()
'''.format(project_name=project_name)
        
        main_file = project_path / "src" / "main.py"
        main_file.write_text(main_content)
        files.append(str(main_file))
        
        # __init__.py files
        for init_path in ["src", "tests"]:
            init_file = project_path / init_path / "__init__.py"
            init_file.write_text(f'"""{project_name} - {init_path} package."""\n')
            files.append(str(init_file))
        
        return files
    
    def _generate_node_code(
        self,
        project_path: Path,
        framework: str,
        app_type: str,
        project_name: str,
        language: str
    ) -> List[str]:
        """Generate Node.js/TypeScript source code."""
        files = []
        ext = "ts" if language == "typescript" else "js"
        
        if framework == "express":
            main_content = '''/**
 * {project_name} - Express Application
 * Generated by ForgeFlow
 */
const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 8000;

// Middleware
app.use(cors());
app.use(express.json());

// Routes
app.get('/', (req, res) => {{
    res.json({{ message: 'Welcome to {project_name}' }});
}});

app.get('/health', (req, res) => {{
    res.json({{ status: 'healthy' }});
}});

// Start server
app.listen(PORT, () => {{
    console.log(`Server running on port ${{PORT}}`);
}});

module.exports = app;
'''.format(project_name=project_name)
        
        elif framework == "nestjs":
            main_content = '''/**
 * {project_name} - NestJS Application
 * Generated by ForgeFlow
 */
import {{ NestFactory }} from '@nestjs/core';
import {{ AppModule }} from './app.module';

async function bootstrap() {{
    const app = await NestFactory.create(AppModule);
    app.enableCors();
    await app.listen(process.env.PORT || 8000);
    console.log(`Application is running on: ${{await app.getUrl()}}`);
}}
bootstrap();
'''.format(project_name=project_name)
        
        else:
            main_content = '''/**
 * {project_name} - Node.js Application
 * Generated by ForgeFlow
 */
const http = require('http');

const PORT = process.env.PORT || 8000;

const server = http.createServer((req, res) => {{
    res.setHeader('Content-Type', 'application/json');
    
    if (req.url === '/') {{
        res.end(JSON.stringify({{ message: 'Welcome to {project_name}' }}));
    }} else if (req.url === '/health') {{
        res.end(JSON.stringify({{ status: 'healthy' }}));
    }} else {{
        res.statusCode = 404;
        res.end(JSON.stringify({{ error: 'Not found' }}));
    }}
}});

server.listen(PORT, () => {{
    console.log(`Server running on port ${{PORT}}`);
}});
'''.format(project_name=project_name)
        
        main_file = project_path / "src" / f"index.{ext}"
        main_file.write_text(main_content)
        files.append(str(main_file))
        
        # package.json
        package_json = {
            "name": project_name,
            "version": "0.1.0",
            "description": f"{project_name} - Generated by ForgeFlow",
            "main": f"src/index.{ext}",
            "scripts": {
                "start": f"node src/index.{ext}",
                "dev": f"nodemon src/index.{ext}",
                "test": "jest"
            }
        }
        
        import json
        package_file = project_path / "package.json"
        package_file.write_text(json.dumps(package_json, indent=2))
        files.append(str(package_file))
        
        return files
    
    def _generate_go_code(
        self,
        project_path: Path,
        framework: str,
        app_type: str,
        project_name: str
    ) -> List[str]:
        """Generate Go source code."""
        files = []
        
        if framework == "gin":
            main_content = '''// {project_name} - Gin Application
// Generated by ForgeFlow
package main

import (
    "net/http"
    "github.com/gin-gonic/gin"
)

func main() {{
    r := gin.Default()
    
    r.GET("/", func(c *gin.Context) {{
        c.JSON(http.StatusOK, gin.H{{
            "message": "Welcome to {project_name}",
        }})
    }})
    
    r.GET("/health", func(c *gin.Context) {{
        c.JSON(http.StatusOK, gin.H{{
            "status": "healthy",
        }})
    }})
    
    r.Run(":8000")
}}
'''.format(project_name=project_name)
        
        else:
            main_content = '''// {project_name} - Go Application
// Generated by ForgeFlow
package main

import (
    "encoding/json"
    "fmt"
    "net/http"
)

func main() {{
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {{
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{{
            "message": "Welcome to {project_name}",
        }})
    }})
    
    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {{
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{{
            "status": "healthy",
        }})
    }})
    
    fmt.Println("Server running on :8000")
    http.ListenAndServe(":8000", nil)
}}
'''.format(project_name=project_name)
        
        main_file = project_path / "cmd" / "main.go"
        main_file.parent.mkdir(parents=True, exist_ok=True)
        main_file.write_text(main_content)
        files.append(str(main_file))
        
        # go.mod
        go_mod = f'''module {project_name}

go 1.21
'''
        go_mod_file = project_path / "go.mod"
        go_mod_file.write_text(go_mod)
        files.append(str(go_mod_file))
        
        return files
    
    def _generate_dockerfile(
        self,
        project_path: Path,
        language: str,
        framework: str,
        stack: Dict[str, Any]
    ) -> str:
        """Generate multi-stage Dockerfile."""
        base_image = stack.get("base_image", {}).get("recommended", "python:3.11-slim")
        
        if language == "python":
            dockerfile_content = f'''# {project_path.name} Dockerfile
# Generated by ForgeFlow

# Build stage
FROM {base_image} AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM {base_image}

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["python", "-m", "src.main"]
'''
        
        elif language in ["nodejs", "typescript"]:
            dockerfile_content = f'''# {project_path.name} Dockerfile
# Generated by ForgeFlow

# Build stage
FROM node:20-slim AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Production stage
FROM node:20-slim

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /app/node_modules ./node_modules

# Copy application code
COPY src/ ./src/
COPY package.json ./

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD node -e "require('http').get('http://localhost:8000/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))"

# Run application
CMD ["node", "src/index.js"]
'''
        
        elif language == "go":
            dockerfile_content = f'''# {project_path.name} Dockerfile
# Generated by ForgeFlow

# Build stage
FROM golang:1.21-alpine AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum* ./
RUN go mod download

# Copy source code
COPY . .

# Build binary
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/main ./cmd/main.go

# Production stage
FROM alpine:latest

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/main .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD wget -q --spider http://localhost:8000/health || exit 1

# Run application
CMD ["./main"]
'''
        
        else:
            dockerfile_content = f'''# {project_path.name} Dockerfile
# Generated by ForgeFlow

FROM {base_image}

WORKDIR /app

COPY . .

EXPOSE 8000

CMD ["echo", "Configure your application startup command"]
'''
        
        dockerfile = project_path / "Dockerfile"
        dockerfile.write_text(dockerfile_content)
        return str(dockerfile)
    
    def _generate_docker_compose(
        self,
        project_path: Path,
        project_name: str,
        database: str,
        services: List[str]
    ) -> str:
        """Generate docker-compose.yml for local development."""
        compose = {
            "version": "3.8",
            "services": {
                "app": {
                    "build": ".",
                    "ports": ["8000:8000"],
                    "environment": [
                        "ENV=development",
                    ],
                    "volumes": [
                        "./src:/app/src",
                    ],
                    "depends_on": [],
                }
            },
            "volumes": {},
            "networks": {
                "default": {
                    "name": f"{project_name}-network"
                }
            }
        }
        
        # Add database service
        if database == "postgresql":
            compose["services"]["db"] = {
                "image": "postgres:16-alpine",
                "environment": [
                    "POSTGRES_USER=postgres",
                    "POSTGRES_PASSWORD=postgres",
                    f"POSTGRES_DB={project_name}",
                ],
                "ports": ["5432:5432"],
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
            }
            compose["volumes"]["postgres_data"] = {}
            compose["services"]["app"]["depends_on"].append("db")
            compose["services"]["app"]["environment"].append(
                f"DATABASE_URL=postgresql://postgres:postgres@db:5432/{project_name}"
            )
        
        elif database == "mysql":
            compose["services"]["db"] = {
                "image": "mysql:8.0",
                "environment": [
                    "MYSQL_ROOT_PASSWORD=root",
                    f"MYSQL_DATABASE={project_name}",
                ],
                "ports": ["3306:3306"],
                "volumes": ["mysql_data:/var/lib/mysql"],
            }
            compose["volumes"]["mysql_data"] = {}
            compose["services"]["app"]["depends_on"].append("db")
        
        elif database == "mongodb":
            compose["services"]["db"] = {
                "image": "mongo:7.0",
                "ports": ["27017:27017"],
                "volumes": ["mongo_data:/data/db"],
            }
            compose["volumes"]["mongo_data"] = {}
            compose["services"]["app"]["depends_on"].append("db")
        
        elif database == "redis":
            compose["services"]["redis"] = {
                "image": "redis:7-alpine",
                "ports": ["6379:6379"],
            }
            compose["services"]["app"]["depends_on"].append("redis")
        
        # Add caching service
        if "caching" in services and database != "redis":
            compose["services"]["redis"] = {
                "image": "redis:7-alpine",
                "ports": ["6379:6379"],
            }
            compose["services"]["app"]["depends_on"].append("redis")
        
        # Add monitoring services
        if "monitoring" in services:
            compose["services"]["prometheus"] = {
                "image": "prom/prometheus:latest",
                "ports": ["9090:9090"],
                "volumes": ["./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml"],
            }
            compose["services"]["grafana"] = {
                "image": "grafana/grafana:latest",
                "ports": ["3000:3000"],
                "environment": [
                    "GF_SECURITY_ADMIN_PASSWORD=admin",
                ],
            }
        
        import yaml
        compose_file = project_path / "docker-compose.yml"
        compose_file.write_text(yaml.dump(compose, default_flow_style=False, sort_keys=False))
        return str(compose_file)
    
    def _generate_tests(
        self,
        project_path: Path,
        language: str,
        framework: str
    ) -> List[str]:
        """Generate basic test files."""
        files = []
        
        if language == "python":
            test_content = '''"""
Basic tests for the application.
Generated by ForgeFlow
"""
import pytest


def test_health():
    """Test that health check returns expected response."""
    # TODO: Implement actual test
    assert True


def test_root():
    """Test root endpoint."""
    # TODO: Implement actual test
    assert True


class TestApp:
    """Application test suite."""
    
    def test_placeholder(self):
        """Placeholder test."""
        assert 1 + 1 == 2
'''
            test_file = project_path / "tests" / "test_main.py"
            test_file.write_text(test_content)
            files.append(str(test_file))
            
            # pytest.ini
            pytest_ini = '''[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short
'''
            pytest_file = project_path / "pytest.ini"
            pytest_file.write_text(pytest_ini)
            files.append(str(pytest_file))
        
        elif language in ["nodejs", "typescript"]:
            test_content = '''/**
 * Basic tests for the application.
 * Generated by ForgeFlow
 */
describe('Application', () => {
    test('health check returns expected response', () => {
        // TODO: Implement actual test
        expect(true).toBe(true);
    });
    
    test('root endpoint works', () => {
        // TODO: Implement actual test
        expect(1 + 1).toBe(2);
    });
});
'''
            test_file = project_path / "tests" / "app.test.js"
            test_file.write_text(test_content)
            files.append(str(test_file))
        
        elif language == "go":
            test_content = '''// Basic tests for the application.
// Generated by ForgeFlow
package main

import "testing"

func TestHealth(t *testing.T) {
    // TODO: Implement actual test
    if 1+1 != 2 {
        t.Error("Basic math failed")
    }
}

func TestRoot(t *testing.T) {
    // TODO: Implement actual test
    if false {
        t.Error("This should not fail")
    }
}
'''
            test_file = project_path / "cmd" / "main_test.go"
            test_file.write_text(test_content)
            files.append(str(test_file))
        
        return files
    
    def _generate_config_files(
        self,
        project_path: Path,
        language: str,
        framework: str,
        stack: Dict[str, Any]
    ) -> List[str]:
        """Generate configuration files."""
        files = []
        
        if language == "python":
            # requirements.txt
            deps = stack.get("dependencies", {})
            requirements = []
            requirements.extend(deps.get("core", []))
            requirements.extend(deps.get("database", []))
            requirements.extend(deps.get("services", []))
            
            req_file = project_path / "requirements.txt"
            req_file.write_text("\n".join(requirements) + "\n")
            files.append(str(req_file))
            
            # requirements-dev.txt
            dev_deps = deps.get("dev", ["pytest>=7.0.0", "pytest-cov>=4.0.0"])
            dev_file = project_path / "requirements-dev.txt"
            dev_file.write_text("-r requirements.txt\n" + "\n".join(dev_deps) + "\n")
            files.append(str(dev_file))
            
            # pyproject.toml
            pyproject = f'''[project]
name = "{project_path.name}"
version = "0.1.0"
description = "Generated by ForgeFlow"
requires-python = ">=3.9"

[tool.black]
line-length = 88

[tool.mypy]
python_version = "3.11"
warn_return_any = true

[tool.pytest.ini_options]
testpaths = ["tests"]
'''
            pyproject_file = project_path / "pyproject.toml"
            pyproject_file.write_text(pyproject)
            files.append(str(pyproject_file))
        
        # .env.example
        env_example = '''# Environment Variables
# Copy this to .env and fill in your values

ENV=development
PORT=8000

# Database
DATABASE_URL=

# Authentication
SECRET_KEY=your-secret-key

# External Services
# API_KEY=
'''
        env_file = project_path / ".env.example"
        env_file.write_text(env_example)
        files.append(str(env_file))
        
        return files
    
    def _generate_readme(
        self,
        project_path: Path,
        project_name: str,
        language: str,
        framework: str,
        app_type: str,
        config: Dict[str, Any]
    ) -> str:
        """Generate README.md file."""
        readme_content = f'''# {project_name}

> Generated by [ForgeFlow](https://github.com/forgeflow) 🔨

## Overview

{project_name} is a {language} {app_type} built with {framework if framework != "none" else "standard library"}.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- {language.capitalize()} {'3.11+' if language == 'python' else '20+' if language in ['nodejs', 'typescript'] else '1.21+'}

### Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd {project_name}

# Start with Docker Compose
docker compose up -d

# Or run locally
{'python -m src.main' if language == 'python' else 'npm start' if language in ['nodejs', 'typescript'] else 'go run cmd/main.go'}
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root endpoint |
| `/health` | GET | Health check |

## Project Structure

```
{project_name}/
├── src/           # Application source code
├── tests/         # Test files
├── docs/          # Documentation
├── config/        # Configuration files
├── scripts/       # Utility scripts
├── Dockerfile     # Container definition
└── docker-compose.yml  # Local development
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

## Testing

```bash
{'pytest' if language == 'python' else 'npm test' if language in ['nodejs', 'typescript'] else 'go test ./...'}
```

## Deployment

This project includes:
- Multi-stage Dockerfile for optimized builds
- {'GitHub Actions' if config.get('cicd') == 'github-actions' else config.get('cicd', 'CI/CD')} pipeline configuration
- {'Kubernetes manifests' if config.get('kubernetes') else 'Docker Compose for deployment'}

## License

MIT
'''
        readme_file = project_path / "README.md"
        readme_file.write_text(readme_content)
        return str(readme_file)
    
    def _generate_cicd(
        self,
        project_path: Path,
        cicd: str,
        language: str,
        kubernetes: bool
    ) -> List[str]:
        """Generate CI/CD configuration files."""
        files = []
        
        if cicd == "github-actions":
            workflow_dir = project_path / ".github" / "workflows"
            workflow_dir.mkdir(parents=True, exist_ok=True)
            
            # CI workflow
            ci_content = f'''name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up {'Python' if language == 'python' else 'Node.js' if language in ['nodejs', 'typescript'] else 'Go'}
        uses: {'actions/setup-python@v5' if language == 'python' else 'actions/setup-node@v4' if language in ['nodejs', 'typescript'] else 'actions/setup-go@v5'}
        with:
          {'python-version: "3.11"' if language == 'python' else 'node-version: "20"' if language in ['nodejs', 'typescript'] else 'go-version: "1.21"'}
      
      - name: Install dependencies
        run: |
          {'pip install -r requirements.txt -r requirements-dev.txt' if language == 'python' else 'npm ci' if language in ['nodejs', 'typescript'] else 'go mod download'}
      
      - name: Run tests
        run: |
          {'pytest --cov' if language == 'python' else 'npm test' if language in ['nodejs', 'typescript'] else 'go test ./...'}
      
      - name: Build Docker image
        run: docker build -t ${{{{ github.repository }}}}:${{{{ github.sha }}}} .

  security:
    runs-on: ubuntu-latest
    needs: build
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run security scan
        run: echo "Security scan placeholder"
'''
            ci_file = workflow_dir / "ci.yml"
            ci_file.write_text(ci_content)
            files.append(str(ci_file))
            
            # CD workflow
            cd_content = '''name: CD

on:
  push:
    tags:
      - 'v*'

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Build and push Docker image
        run: |
          echo "Build and push to registry"
          docker build -t ${{ github.repository }}:${{ github.ref_name }} .
      
      - name: Deploy
        run: |
          echo "Deploy to environment"
'''
            cd_file = workflow_dir / "cd.yml"
            cd_file.write_text(cd_content)
            files.append(str(cd_file))
        
        elif cicd == "gitlab-ci":
            gitlab_ci = '''stages:
  - build
  - test
  - security
  - deploy

build:
  stage: build
  script:
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .

test:
  stage: test
  script:
    - echo "Run tests"

security:
  stage: security
  script:
    - echo "Run security scan"

deploy:
  stage: deploy
  only:
    - main
  script:
    - echo "Deploy to environment"
'''
            gitlab_file = project_path / ".gitlab-ci.yml"
            gitlab_file.write_text(gitlab_ci)
            files.append(str(gitlab_file))
        
        return files
    
    def _generate_gitignore(self, project_path: Path, language: str) -> str:
        """Generate .gitignore file."""
        common = '''# Environment
.env
.env.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Docker
*.log

# ForgeFlow
.forgeflow/reports/

'''
        
        language_specific = {
            "python": '''# Python
__pycache__/
*.py[cod]
*$py.class
.Python
venv/
.venv/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
''',
            "nodejs": '''# Node.js
node_modules/
npm-debug.log
yarn-error.log
.npm
coverage/
''',
            "typescript": '''# TypeScript/Node.js
node_modules/
npm-debug.log
yarn-error.log
.npm
coverage/
dist/
*.js.map
''',
            "go": '''# Go
bin/
pkg/
*.exe
*.test
*.out
vendor/
''',
            "java": '''# Java
target/
*.class
*.jar
*.war
.gradle/
build/
''',
            "rust": '''# Rust
target/
Cargo.lock
**/*.rs.bk
''',
        }
        
        gitignore_content = common + language_specific.get(language, "")
        gitignore_file = project_path / ".gitignore"
        gitignore_file.write_text(gitignore_content)
        return str(gitignore_file)
    
    def _init_git(self, project_path: Path):
        """Initialize git repository."""
        import subprocess
        
        try:
            subprocess.run(
                ["git", "init"],
                cwd=project_path,
                capture_output=True,
                check=True
            )
            subprocess.run(
                ["git", "add", "."],
                cwd=project_path,
                capture_output=True,
                check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit - scaffolded by ForgeFlow"],
                cwd=project_path,
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            self.log(f"Git init warning: {e}", "warning")
        except FileNotFoundError:
            self.log("Git not found, skipping repository initialization", "warning")
