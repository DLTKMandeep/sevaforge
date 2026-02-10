#!/usr/bin/env python3
"""
ForgeFlow API Server

REST API interface for ForgeFlow commands, enabling containerized/cloud deployment.

Endpoints:
    POST /api/v1/discover     - Run discover on repository
    POST /api/v1/normalize    - Run normalize
    POST /api/v1/scan         - Run security scan
    POST /api/v1/docs         - Generate documentation
    POST /api/v1/generate     - Generate infrastructure
    POST /api/v1/review       - Code review
    POST /api/v1/test         - Run tests
    POST /api/v1/bridge       - Push to GitHub
    POST /api/v1/run-all      - Full pipeline
    GET  /api/v1/status       - Service status
    GET  /health              - Health check
"""
import os
import sys
import tempfile
import shutil
import subprocess
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import asynccontextmanager
from functools import wraps

from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Add parent directory to path for imports
root_dir = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(root_dir))

from core.mission_control import MissionControl


# ============================================================================
# Configuration
# ============================================================================

class Settings(BaseSettings):
    """API Configuration from environment variables."""
    api_key: str = Field(default="", env="FORGEFLOW_API_KEY")
    api_key_required: bool = Field(default=True, env="FORGEFLOW_API_KEY_REQUIRED")
    mode: str = Field(default="local", env="FORGEFLOW_MODE")
    max_repo_size_mb: int = Field(default=100, env="FORGEFLOW_MAX_REPO_SIZE_MB")
    task_timeout: int = Field(default=300, env="FORGEFLOW_TASK_TIMEOUT")
    temp_dir: str = Field(default="/tmp/forgeflow", env="FORGEFLOW_TEMP_DIR")
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Task storage (in production, use Redis)
task_store: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Request/Response Models
# ============================================================================

class RepoRequest(BaseModel):
    """Base request with repository path or git URL."""
    path: Optional[str] = Field(default=None, description="Local path to repository")
    git_url: Optional[str] = Field(default=None, description="Git URL to clone")
    
class DiscoverRequest(RepoRequest):
    """Discover command request."""
    pass

class NormalizeRequest(RepoRequest):
    """Normalize command request."""
    pass

class ScanRequest(RepoRequest):
    """Security scan request."""
    severity: str = Field(default="medium", description="Minimum severity threshold")

class DocsRequest(RepoRequest):
    """Documentation generation request."""
    pass

class GenerateRequest(RepoRequest):
    """Infrastructure generation request."""
    stack: str = Field(default="auto", description="Deployment stack: auto, docker, kubernetes, terraform, helm")

class ReviewRequest(RepoRequest):
    """Code review request."""
    pass

class TestRequest(RepoRequest):
    """Test execution request."""
    pass

class BridgeRequest(RepoRequest):
    """GitHub bridge request."""
    repo: Optional[str] = Field(default=None, description="GitHub repository (owner/repo)")
    branch: Optional[str] = Field(default=None, description="Branch name")
    operation: str = Field(default="status", description="Operation: init, push, pr, branch, status")
    message: str = Field(default="Update from ForgeFlow", description="Commit message")
    pr_title: Optional[str] = Field(default=None, description="Pull request title")
    pr_body: Optional[str] = Field(default=None, description="Pull request body")

class RunAllRequest(RepoRequest):
    """Full pipeline request."""
    include_post_merge: bool = Field(default=False, description="Include post-merge stages (deploy, monitor)")
    async_execution: bool = Field(default=False, description="Run asynchronously and return task ID")

class TaskResponse(BaseModel):
    """Response for async task submission."""
    task_id: str
    status: str
    message: str

class CommandResponse(BaseModel):
    """Standard command response."""
    status: str
    command: str
    summary: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    findings: Optional[List[Dict[str, Any]]] = None
    timestamp: str
    execution_time_ms: Optional[int] = None

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    mode: str
    timestamp: str

class StatusResponse(BaseModel):
    """Service status response."""
    status: str
    version: str
    mode: str
    active_tasks: int
    uptime_seconds: float
    config: Dict[str, Any]


# ============================================================================
# Application Lifecycle
# ============================================================================

start_time = datetime.utcnow()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Startup
    os.makedirs(settings.temp_dir, exist_ok=True)
    print(f"ForgeFlow API starting in {settings.mode} mode...")
    yield
    # Shutdown
    print("ForgeFlow API shutting down...")
    # Cleanup temp files
    if os.path.exists(settings.temp_dir):
        shutil.rmtree(settings.temp_dir, ignore_errors=True)

app = FastAPI(
    title="ForgeFlow API",
    description="REST API for ForgeFlow - AI Platform Engineering CLI",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Authentication
# ============================================================================

async def verify_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Verify API key if required."""
    if not settings.api_key_required:
        return True
    if not settings.api_key:
        return True  # No key configured, allow all
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True


# ============================================================================
# Helper Functions
# ============================================================================

async def prepare_repo(request: RepoRequest) -> str:
    """Prepare repository path from request (clone if git URL provided)."""
    if request.git_url:
        # Clone repository to temp directory
        temp_path = tempfile.mkdtemp(dir=settings.temp_dir)
        try:
            process = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", request.git_url, temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=60
            )
            if process.returncode != 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to clone repository: {stderr.decode()}"
                )
            return temp_path
        except asyncio.TimeoutError:
            shutil.rmtree(temp_path, ignore_errors=True)
            raise HTTPException(status_code=408, detail="Repository clone timed out")
    elif request.path:
        if not os.path.isdir(request.path):
            raise HTTPException(status_code=400, detail=f"Path not found: {request.path}")
        return request.path
    else:
        raise HTTPException(status_code=400, detail="Either 'path' or 'git_url' must be provided")


def run_command(func):
    """Decorator to wrap command execution with timing and error handling."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = datetime.utcnow()
        try:
            result = await func(*args, **kwargs)
            end = datetime.utcnow()
            execution_time = int((end - start).total_seconds() * 1000)
            
            return CommandResponse(
                status=result.get("status", "success"),
                command=func.__name__.replace("_", "-"),
                summary=result.get("summary"),
                data=result.get("data"),
                findings=result.get("findings"),
                timestamp=end.isoformat(),
                execution_time_ms=execution_time
            )
        except HTTPException:
            raise
        except Exception as e:
            return CommandResponse(
                status="error",
                command=func.__name__.replace("_", "-"),
                summary=str(e),
                data=None,
                findings=None,
                timestamp=datetime.utcnow().isoformat(),
                execution_time_ms=None
            )
    return wrapper


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint for container orchestration."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        mode=settings.mode,
        timestamp=datetime.utcnow().isoformat()
    )


@app.get("/api/v1/status", response_model=StatusResponse, tags=["Status"])
async def service_status(authorized: bool = Depends(verify_api_key)):
    """Get service status and configuration."""
    uptime = (datetime.utcnow() - start_time).total_seconds()
    return StatusResponse(
        status="running",
        version="0.1.0",
        mode=settings.mode,
        active_tasks=len([t for t in task_store.values() if t.get("status") == "running"]),
        uptime_seconds=uptime,
        config={
            "api_key_required": settings.api_key_required,
            "max_repo_size_mb": settings.max_repo_size_mb,
            "task_timeout": settings.task_timeout
        }
    )


# ============================================================================
# ForgeFlow Command Endpoints
# ============================================================================

@app.post("/api/v1/discover", response_model=CommandResponse, tags=["Commands"])
async def discover(request: DiscoverRequest, authorized: bool = Depends(verify_api_key)):
    """Run discovery on repository to analyze structure and components."""
    repo_path = await prepare_repo(request)
    mc = MissionControl(mode=settings.mode)
    result = mc.discover(repo_path)
    
    return CommandResponse(
        status=result.get("status", "success"),
        command="discover",
        summary=result.get("summary"),
        data=result.get("data"),
        findings=result.get("findings"),
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/api/v1/normalize", response_model=CommandResponse, tags=["Commands"])
async def normalize(request: NormalizeRequest, authorized: bool = Depends(verify_api_key)):
    """Normalize and standardize repository structure."""
    repo_path = await prepare_repo(request)
    mc = MissionControl(mode=settings.mode)
    result = mc.normalize(repo_path)
    
    return CommandResponse(
        status=result.get("status", "success"),
        command="normalize",
        summary=result.get("summary"),
        data=result.get("data"),
        findings=result.get("findings"),
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/api/v1/scan", response_model=CommandResponse, tags=["Commands"])
async def scan(request: ScanRequest, authorized: bool = Depends(verify_api_key)):
    """Run security vulnerability scan on repository."""
    repo_path = await prepare_repo(request)
    mc = MissionControl(mode=settings.mode)
    result = mc.scan(repo_path, request.severity)
    
    return CommandResponse(
        status=result.get("status", "success"),
        command="scan",
        summary=result.get("summary"),
        data=result.get("data"),
        findings=result.get("findings"),
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/api/v1/docs", response_model=CommandResponse, tags=["Commands"])
async def docs(request: DocsRequest, authorized: bool = Depends(verify_api_key)):
    """Generate documentation and diagrams."""
    repo_path = await prepare_repo(request)
    mc = MissionControl(mode=settings.mode)
    result = mc.docs(repo_path)
    
    return CommandResponse(
        status=result.get("status", "success"),
        command="docs",
        summary=result.get("summary"),
        data=result.get("data"),
        findings=result.get("findings"),
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/api/v1/generate", response_model=CommandResponse, tags=["Commands"])
async def generate(request: GenerateRequest, authorized: bool = Depends(verify_api_key)):
    """Generate deployment infrastructure artifacts."""
    repo_path = await prepare_repo(request)
    mc = MissionControl(mode=settings.mode)
    result = mc.generate(repo_path, request.stack)
    
    return CommandResponse(
        status=result.get("status", "success"),
        command="generate",
        summary=result.get("summary"),
        data=result.get("data"),
        findings=result.get("findings"),
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/api/v1/review", response_model=CommandResponse, tags=["Commands"])
async def review(request: ReviewRequest, authorized: bool = Depends(verify_api_key)):
    """Run code review and quality analysis."""
    repo_path = await prepare_repo(request)
    mc = MissionControl(mode=settings.mode)
    result = mc.review(repo_path)
    
    return CommandResponse(
        status=result.get("status", "success"),
        command="review",
        summary=result.get("summary"),
        data=result.get("data"),
        findings=result.get("findings"),
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/api/v1/test", response_model=CommandResponse, tags=["Commands"])
async def test(request: TestRequest, authorized: bool = Depends(verify_api_key)):
    """Run tests via CI/CD pipeline."""
    repo_path = await prepare_repo(request)
    mc = MissionControl(mode=settings.mode)
    result = mc.test(repo_path)
    
    return CommandResponse(
        status=result.get("status", "success"),
        command="test",
        summary=result.get("summary"),
        data=result.get("data"),
        findings=result.get("findings"),
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/api/v1/bridge", response_model=CommandResponse, tags=["Commands"])
async def bridge(request: BridgeRequest, authorized: bool = Depends(verify_api_key)):
    """Bridge to GitHub (push, PR, sync)."""
    mc = MissionControl(mode=settings.mode)
    result = mc.bridge(
        repo=request.repo,
        branch=request.branch,
        operation=request.operation,
        message=request.message,
        pr_title=request.pr_title,
        pr_body=request.pr_body
    )
    
    return CommandResponse(
        status=result.get("status", "success"),
        command="bridge",
        summary=result.get("summary"),
        data=result.get("data"),
        findings=result.get("findings"),
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/api/v1/run-all", response_model=CommandResponse, tags=["Commands"])
async def run_all(
    request: RunAllRequest,
    background_tasks: BackgroundTasks,
    authorized: bool = Depends(verify_api_key)
):
    """Run full pipeline: discover → normalize → docs → generate → review → test → scan → bridge."""
    repo_path = await prepare_repo(request)
    
    if request.async_execution:
        # Async execution - return task ID
        import uuid
        task_id = str(uuid.uuid4())
        task_store[task_id] = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "result": None
        }
        
        async def run_pipeline():
            try:
                mc = MissionControl(mode=settings.mode)
                result = mc.run_all(repo_path, include_post_merge=request.include_post_merge)
                task_store[task_id]["status"] = "completed"
                task_store[task_id]["result"] = result
            except Exception as e:
                task_store[task_id]["status"] = "failed"
                task_store[task_id]["error"] = str(e)
        
        background_tasks.add_task(run_pipeline)
        
        return CommandResponse(
            status="accepted",
            command="run-all",
            summary=f"Pipeline started with task ID: {task_id}",
            data={"task_id": task_id},
            findings=None,
            timestamp=datetime.utcnow().isoformat()
        )
    else:
        # Synchronous execution
        mc = MissionControl(mode=settings.mode)
        result = mc.run_all(repo_path, include_post_merge=request.include_post_merge)
        
        return CommandResponse(
            status=result.get("status", "success"),
            command="run-all",
            summary=result.get("summary"),
            data=result.get("data"),
            findings=result.get("findings"),
            timestamp=datetime.utcnow().isoformat()
        )


@app.get("/api/v1/tasks/{task_id}", response_model=Dict[str, Any], tags=["Tasks"])
async def get_task_status(task_id: str, authorized: bool = Depends(verify_api_key)):
    """Get status of an async task."""
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_store[task_id]


# ============================================================================
# File Upload Endpoint
# ============================================================================

@app.post("/api/v1/upload", response_model=Dict[str, str], tags=["Upload"])
async def upload_repo(
    file: UploadFile = File(...),
    authorized: bool = Depends(verify_api_key)
):
    """Upload a repository as a zip/tar archive."""
    if not file.filename.endswith(('.zip', '.tar.gz', '.tgz')):
        raise HTTPException(
            status_code=400,
            detail="Only .zip, .tar.gz, or .tgz archives are supported"
        )
    
    temp_dir = tempfile.mkdtemp(dir=settings.temp_dir)
    archive_path = os.path.join(temp_dir, file.filename)
    
    # Save uploaded file
    with open(archive_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Extract archive
    extract_dir = os.path.join(temp_dir, "repo")
    os.makedirs(extract_dir)
    
    if file.filename.endswith('.zip'):
        import zipfile
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
    else:
        import tarfile
        with tarfile.open(archive_path, 'r:gz') as tar_ref:
            tar_ref.extractall(extract_dir)
    
    # Find the actual repo root (handle single directory in archive)
    entries = os.listdir(extract_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
        repo_path = os.path.join(extract_dir, entries[0])
    else:
        repo_path = extract_dir
    
    return {
        "status": "uploaded",
        "path": repo_path,
        "message": "Repository uploaded successfully. Use this path in subsequent API calls."
    }


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error": exc.detail,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
