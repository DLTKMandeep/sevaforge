"""
SevaForge Scaffolding Agent

Generates initial project structure for greenfield projects.  Supports
Python (FastAPI / Flask), Node (Express / NestJS), and Go (Gin / stdlib)
frameworks with opinionated defaults for production readiness.

Capabilities:
  - generate_project_structure:  Create full directory tree for a new project
  - generate_boilerplate:        Generate starter code for the chosen framework
  - generate_configs:            Generate build, lint, test, and CI config files
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


# -- Framework directory trees ------------------------------------------------

_PROJECT_TREES: dict[str, list[str]] = {
    "python-fastapi": [
        "src/{project}/",
        "src/{project}/__init__.py",
        "src/{project}/main.py",
        "src/{project}/config.py",
        "src/{project}/models/",
        "src/{project}/models/__init__.py",
        "src/{project}/routes/",
        "src/{project}/routes/__init__.py",
        "src/{project}/routes/health.py",
        "src/{project}/services/",
        "src/{project}/services/__init__.py",
        "src/{project}/middleware/",
        "src/{project}/middleware/__init__.py",
        "tests/",
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/test_health.py",
        "Dockerfile",
        "docker-compose.yml",
        "pyproject.toml",
        "README.md",
        ".gitignore",
        ".editorconfig",
        ".env.example",
    ],
    "python-flask": [
        "app/",
        "app/__init__.py",
        "app/config.py",
        "app/models/",
        "app/models/__init__.py",
        "app/routes/",
        "app/routes/__init__.py",
        "app/routes/health.py",
        "app/services/",
        "app/services/__init__.py",
        "tests/",
        "tests/__init__.py",
        "tests/conftest.py",
        "Dockerfile",
        "docker-compose.yml",
        "pyproject.toml",
        "README.md",
        ".gitignore",
        ".editorconfig",
        ".env.example",
    ],
    "node-express": [
        "src/",
        "src/index.ts",
        "src/config.ts",
        "src/routes/",
        "src/routes/index.ts",
        "src/routes/health.ts",
        "src/middleware/",
        "src/middleware/index.ts",
        "src/services/",
        "src/services/index.ts",
        "src/models/",
        "src/models/index.ts",
        "tests/",
        "tests/health.test.ts",
        "Dockerfile",
        "docker-compose.yml",
        "package.json",
        "tsconfig.json",
        ".eslintrc.json",
        "README.md",
        ".gitignore",
        ".editorconfig",
        ".env.example",
    ],
    "node-nestjs": [
        "src/",
        "src/main.ts",
        "src/app.module.ts",
        "src/app.controller.ts",
        "src/app.service.ts",
        "src/config/",
        "src/config/configuration.ts",
        "src/health/",
        "src/health/health.controller.ts",
        "src/health/health.module.ts",
        "test/",
        "test/app.e2e-spec.ts",
        "test/jest-e2e.json",
        "Dockerfile",
        "docker-compose.yml",
        "package.json",
        "tsconfig.json",
        "tsconfig.build.json",
        "nest-cli.json",
        "README.md",
        ".gitignore",
        ".editorconfig",
        ".env.example",
    ],
    "go-gin": [
        "cmd/{project}/",
        "cmd/{project}/main.go",
        "internal/config/",
        "internal/config/config.go",
        "internal/handler/",
        "internal/handler/health.go",
        "internal/middleware/",
        "internal/middleware/logging.go",
        "internal/service/",
        "internal/service/service.go",
        "internal/model/",
        "internal/model/model.go",
        "pkg/",
        "tests/",
        "tests/health_test.go",
        "Dockerfile",
        "docker-compose.yml",
        "go.mod",
        "Makefile",
        "README.md",
        ".gitignore",
        ".editorconfig",
        ".env.example",
    ],
    "go-stdlib": [
        "cmd/{project}/",
        "cmd/{project}/main.go",
        "internal/config/",
        "internal/config/config.go",
        "internal/handler/",
        "internal/handler/health.go",
        "internal/handler/router.go",
        "internal/service/",
        "internal/service/service.go",
        "internal/model/",
        "internal/model/model.go",
        "pkg/",
        "tests/",
        "tests/health_test.go",
        "Dockerfile",
        "docker-compose.yml",
        "go.mod",
        "Makefile",
        "README.md",
        ".gitignore",
        ".editorconfig",
        ".env.example",
    ],
}

# -- Boilerplate code templates (compact) ------------------------------------

_BOILERPLATE: dict[str, dict[str, str]] = {
    "python-fastapi": {
        "main.py": (
            'from fastapi import FastAPI\n'
            'from {project}.config import settings\n'
            'from {project}.routes.health import router as health_router\n\n'
            'app = FastAPI(title=settings.app_name, version="0.1.0")\n'
            'app.include_router(health_router, prefix="/api")\n\n'
            'if __name__ == "__main__":\n'
            '    import uvicorn\n'
            '    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)\n'
        ),
        "health.py": (
            'from fastapi import APIRouter\n\n'
            'router = APIRouter(tags=["health"])\n\n'
            '@router.get("/health")\n'
            'async def health():\n'
            '    return {"status": "ok"}\n'
        ),
        "Dockerfile": (
            "FROM python:3.12-slim\n"
            "WORKDIR /app\n"
            "COPY pyproject.toml .\n"
            "RUN pip install --no-cache-dir .\n"
            "COPY src/ src/\n"
            'EXPOSE 8000\n'
            'CMD ["uvicorn", "{project}.main:app", "--host", "0.0.0.0", "--port", "8000"]\n'
        ),
    },
    "node-express": {
        "index.ts": (
            'import express from "express";\n'
            'import { healthRouter } from "./routes/health";\n\n'
            'const app = express();\n'
            'const PORT = process.env.PORT || 3000;\n\n'
            'app.use(express.json());\n'
            'app.use("/api", healthRouter);\n\n'
            'app.listen(PORT, () => console.log(`Server running on port ${PORT}`));\n'
        ),
        "health.ts": (
            'import { Router } from "express";\n\n'
            'export const healthRouter = Router();\n\n'
            'healthRouter.get("/health", (_req, res) => {\n'
            '  res.json({ status: "ok" });\n'
            '});\n'
        ),
    },
    "go-gin": {
        "main.go": (
            'package main\n\n'
            'import (\n'
            '\t"log"\n'
            '\t"github.com/gin-gonic/gin"\n'
            '\t"{module}/internal/handler"\n'
            ')\n\n'
            'func main() {\n'
            '\tr := gin.Default()\n'
            '\thandler.RegisterRoutes(r)\n'
            '\tlog.Fatal(r.Run(":8080"))\n'
            '}\n'
        ),
        "health.go": (
            'package handler\n\n'
            'import (\n'
            '\t"net/http"\n'
            '\t"github.com/gin-gonic/gin"\n'
            ')\n\n'
            'func HealthCheck(c *gin.Context) {\n'
            '\tc.JSON(http.StatusOK, gin.H{"status": "ok"})\n'
            '}\n\n'
            'func RegisterRoutes(r *gin.Engine) {\n'
            '\tapi := r.Group("/api")\n'
            '\tapi.GET("/health", HealthCheck)\n'
            '}\n'
        ),
    },
}

# -- Supported framework lookup ----------------------------------------------

_FRAMEWORK_ALIASES: dict[str, str] = {
    "fastapi": "python-fastapi",
    "flask": "python-flask",
    "express": "node-express",
    "nestjs": "node-nestjs",
    "nest": "node-nestjs",
    "gin": "go-gin",
    "go-stdlib": "go-stdlib",
    "stdlib": "go-stdlib",
}


class ScaffoldingAgent(BaseAgent):
    """
    Project scaffolding agent.

    Generates production-ready project structures for greenfield
    applications across multiple languages and frameworks.
    """

    SYSTEM_PROMPT = (
        "You are a senior software architect who sets up greenfield projects. "
        "Generate production-ready scaffolding: proper directory layout, "
        "health endpoints, Docker configuration, testing setup, and CI config. "
        "Prefer convention over configuration. Include security best practices "
        "from day one (non-root Docker user, env-based config, .env.example)."
    )

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="scaffolding",
            name="Scaffolding Agent",
            description="Generates initial project structure for greenfield projects",
            version="1.0.0",
            capabilities=[
                AgentCapability(
                    name="generate_project_structure",
                    description="Create full directory tree for a new project",
                    input_schema={"project_name": "str", "framework": "str"},
                    output_schema={"tree": "list", "files": "dict"},
                ),
                AgentCapability(
                    name="generate_boilerplate",
                    description="Generate starter code for the chosen framework",
                    input_schema={"project_name": "str", "framework": "str"},
                    output_schema={"files": "dict"},
                ),
                AgentCapability(
                    name="generate_configs",
                    description="Generate build, lint, test, and CI configs",
                    input_schema={"framework": "str"},
                    output_schema={"configs": "dict"},
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["scaffolding", "project", "greenfield", "boilerplate"],
        ))

    # -- execute --------------------------------------------------------------

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Execute scaffolding generation.

        ctx.input: project description or requirements
        ctx.params:
          - project_name: str  (default "myproject")
          - framework: str     (fastapi, flask, express, nestjs, gin, go-stdlib)
          - action: "structure" | "boilerplate" | "configs" | "full"
        """
        project_name = ctx.params.get("project_name", "myproject")
        raw_framework = ctx.params.get("framework", "fastapi")
        action = ctx.params.get("action", "full")

        framework = _FRAMEWORK_ALIASES.get(raw_framework.lower(), raw_framework.lower())
        if framework not in _PROJECT_TREES:
            framework = "python-fastapi"

        safe_name = re.sub(r"[^a-z0-9_]", "_", project_name.lower())

        # Pattern-based generation
        tree = self._build_tree(framework, safe_name)
        boilerplate = self._build_boilerplate(framework, safe_name)

        if action == "structure":
            return {
                "tree": tree,
                "project_name": safe_name,
                "framework": framework,
                "model_used": "template",
                "input_tokens": 0,
                "output_tokens": 0,
                "confidence": 0.95,
            }

        if action == "boilerplate":
            return {
                "files": boilerplate,
                "project_name": safe_name,
                "framework": framework,
                "model_used": "template",
                "input_tokens": 0,
                "output_tokens": 0,
                "confidence": 0.95,
            }

        # Full or configs: use LLM to customise
        prompt = self._build_scaffold_prompt(
            ctx.input, safe_name, framework, tree, boilerplate,
        )
        try:
            llm_response = await self.call_llm(ctx, prompt)
            customisations = llm_response.content
            model_used = llm_response.model
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        except Exception as exc:
            logger.warning("LLM unavailable for scaffolding customisation: %s", exc)
            customisations = ""
            model_used = "template-only"
            input_tokens = 0
            output_tokens = 0

        return {
            "tree": tree,
            "files": boilerplate,
            "project_name": safe_name,
            "framework": framework,
            "total_files": len(tree),
            "customisations": customisations,
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": 0.85 if model_used != "template-only" else 0.7,
        }

    # -- Tree builder ---------------------------------------------------------

    def _build_tree(self, framework: str, project_name: str) -> list[str]:
        """Resolve the directory tree template with the project name."""
        template = _PROJECT_TREES.get(framework, _PROJECT_TREES["python-fastapi"])
        return [path.format(project=project_name) for path in template]

    # -- Boilerplate builder --------------------------------------------------

    def _build_boilerplate(self, framework: str, project_name: str) -> dict[str, str]:
        """Resolve boilerplate templates with project name."""
        templates = _BOILERPLATE.get(framework, {})
        resolved: dict[str, str] = {}
        for filename, content in templates.items():
            resolved[filename] = content.format(
                project=project_name,
                module=f"github.com/org/{project_name}",
            )
        return resolved

    # -- LLM prompt -----------------------------------------------------------

    def _build_scaffold_prompt(
        self, description: str, project_name: str, framework: str,
        tree: list[str], boilerplate: dict[str, str],
    ) -> str:
        tree_str = "\n".join(f"  {p}" for p in tree)
        files_str = "\n".join(
            f"--- {name} ---\n{content}" for name, content in boilerplate.items()
        )
        return (
            f"I am scaffolding a new project called '{project_name}' "
            f"using the {framework} framework.\n\n"
            f"Project description: {description[:1500]}\n\n"
            f"Generated directory tree:\n{tree_str}\n\n"
            f"Generated boilerplate files:\n{files_str}\n\n"
            "Based on the project description, suggest:\n"
            "1. Additional files or directories needed\n"
            "2. Modifications to the boilerplate code\n"
            "3. Recommended third-party libraries\n"
            "4. Database and caching setup if appropriate\n"
            "5. Authentication / authorization strategy"
        )
