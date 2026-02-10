#!/usr/bin/env python3
"""
AI Enhancer - Uses Claude to improve discovery and generation accuracy
Adds intelligent analysis on top of pattern-based detection
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional
import anthropic

logger = logging.getLogger("forgeflow.ai_enhancer")


class AIEnhancer:
    """
    AI-powered enhancement layer for ForgeFlow.
    Uses Claude 3 Haiku for intelligent code analysis and artifact generation.
    """
    
    def __init__(self):
        self.api_key = os.getenv('CLAUDE_API_KEY')
        self.client = None
        self.model = "claude-3-haiku-20240307"  # Available model
        
        if self.api_key:
            try:
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info("✅ AI Enhancer initialized with Claude 3 Haiku")
            except Exception as e:
                logger.warning(f"AI Enhancer unavailable: {e}")
                self.client = None
        else:
            logger.info("AI Enhancer disabled (CLAUDE_API_KEY not set)")
    
    def is_available(self) -> bool:
        """Check if AI enhancement is available."""
        return self.client is not None
    
    def enhance_discovery(self, 
                         repo_path: str,
                         basic_discovery: Dict[str, Any],
                         sample_files: Dict[str, str]) -> Dict[str, Any]:
        """
        Enhance basic discovery with AI analysis.
        
        Args:
            repo_path: Path to repository
            basic_discovery: Results from pattern-based discovery
            sample_files: Dictionary of {filename: content} for key files
            
        Returns:
            Enhanced discovery with AI insights
        """
        if not self.is_available():
            return basic_discovery
        
        try:
            # Build prompt with discovery context
            prompt = self._build_discovery_prompt(basic_discovery, sample_files)
            
            # Get AI analysis
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,  # Increased for enterprise-grade responses
                temperature=0.2,  # Lower temperature for precise technical output
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            analysis = response.content[0].text
            logger.info("✅ AI discovery enhancement completed")
            
            # Parse AI response and merge with basic discovery
            ai_insights = self._parse_discovery_analysis(analysis)
            
            return self._merge_discovery_results(basic_discovery, ai_insights)
            
        except Exception as e:
            logger.error(f"AI enhancement failed: {e}")
            return basic_discovery
    
    def enhance_dockerfile(self,
                          service_info: Dict[str, Any],
                          basic_dockerfile: str) -> str:
        """
        Enhance Dockerfile with AI-generated improvements.
        
        Args:
            service_info: Service metadata (language, framework, dependencies)
            basic_dockerfile: Template-generated Dockerfile
            
        Returns:
            Improved Dockerfile
        """
        if not self.is_available():
            return basic_dockerfile
        
        try:
            prompt = self._build_dockerfile_prompt(service_info, basic_dockerfile)
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,  # Enterprise Dockerfile with detailed comments
                temperature=0.1,  # Very precise for production code
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            improved = response.content[0].text
            logger.info(f"✅ AI Dockerfile enhancement for {service_info.get('name', 'service')}")
            
            # Extract Dockerfile content from response
            dockerfile = self._extract_dockerfile(improved)
            return dockerfile if dockerfile else basic_dockerfile
            
        except Exception as e:
            logger.error(f"Dockerfile AI enhancement failed: {e}")
            return basic_dockerfile
    
    def enhance_docker_compose(self,
                               services: List[Dict[str, Any]],
                               detected_dependencies: Dict[str, Any],
                               basic_compose: str) -> str:
        """
        Enhance docker-compose.yml with AI insights.
        
        Args:
            services: List of detected services
            detected_dependencies: Detected databases, caching, etc.
            basic_compose: Template-generated docker-compose
            
        Returns:
            Improved docker-compose.yml
        """
        if not self.is_available():
            return basic_compose
        
        try:
            prompt = self._build_compose_prompt(services, detected_dependencies, basic_compose)
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,  # Enterprise docker-compose with all services
                temperature=0.1,  # Very precise configuration
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            improved = response.content[0].text
            logger.info("✅ AI docker-compose enhancement")
            
            compose = self._extract_yaml(improved)
            return compose if compose else basic_compose
            
        except Exception as e:
            logger.error(f"Docker-compose AI enhancement failed: {e}")
            return basic_compose
    
    def detect_architecture(self,
                           directory_structure: Dict[str, Any],
                           dependency_files: Dict[str, str]) -> Dict[str, Any]:
        """
        Use AI to detect application architecture pattern.
        
        Args:
            directory_structure: Tree of directories and files
            dependency_files: Contents of package.json, requirements.txt, etc.
            
        Returns:
            Architecture analysis with services, databases, patterns
        """
        if not self.is_available():
            return {"type": "unknown", "services": []}
        
        try:
            prompt = self._build_architecture_prompt(directory_structure, dependency_files)
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,  # Detailed architecture analysis
                temperature=0.2,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            analysis = response.content[0].text
            logger.info("✅ AI architecture detection")
            
            return self._parse_architecture_analysis(analysis)
            
        except Exception as e:
            logger.error(f"Architecture detection failed: {e}")
            return {"type": "unknown", "services": [], "error": str(e)}
    
    # =========================================================================
    # Private Methods - Prompt Builders
    # =========================================================================
    
    def _build_discovery_prompt(self, 
                                basic_discovery: Dict[str, Any],
                                sample_files: Dict[str, str]) -> str:
        """Build prompt for discovery enhancement."""
        return f"""You are analyzing a code repository for ENTERPRISE-GRADE infrastructure generation.

**Basic Discovery Results:**
- Total files: {basic_discovery.get('total_files', 0)}
- Languages detected: {', '.join(basic_discovery.get('languages', {}).keys())}
- Components: {', '.join(basic_discovery.get('components', {}).keys())}

**Sample Files:**
{self._format_sample_files(sample_files)}

**ENTERPRISE ANALYSIS REQUIREMENTS**:

Analyze the codebase and provide detailed information for production-grade infrastructure:

1. **Frameworks & Versions**: Exact framework names and versions from dependencies
   - Web frameworks: FastAPI, Flask, Django, Express, NestJS, Spring Boot
   - Frontend: React, Vue, Angular, Next.js, Svelte
   - ORM/Database libs: SQLAlchemy, Prisma, TypeORM, Mongoose

2. **Data Layer**: Complete data infrastructure requirements
   - Databases: PostgreSQL, MySQL, MongoDB (with version requirements)
   - Vector DBs: ChromaDB, Pinecone, Weaviate, Milvus
   - Caching: Redis, Memcached (with persistence needs)
   - Message queues: RabbitMQ, Kafka, NATS
   - Object storage: S3, MinIO

3. **Architecture Pattern**: Identify the exact architecture
   - Monolith: Single deployable unit
   - Multi-service: Backend + Frontend separation
   - Microservices: Multiple independent services with API gateway
   - Serverless: FaaS with managed services
   - Event-driven: Message-based communication

4. **Services Detail**: For each service, provide:
   - Name, path, language, framework, version
   - HTTP port and optional metrics port
   - Entry point file
   - Environment variables needed (DB_URL, API_KEY, etc.)
   - Resource requirements (CPU, memory estimates)
   - Dependencies on other services
   - Health check endpoint

5. **Infrastructure Requirements**:
   - Container orchestration: Docker, Kubernetes, ECS
   - Reverse proxy/Load balancer: Nginx, Traefik, ALB
   - Service mesh: Istio, Linkerd (if microservices)
   - Observability stack: Prometheus, Grafana, ELK, Jaeger
   - Secrets management: Vault, AWS Secrets Manager

6. **Production Concerns**:
   - Authentication/Authorization: JWT, OAuth, SAML
   - Rate limiting requirements
   - CORS configuration
   - SSL/TLS termination
   - Backup and disaster recovery needs
   - Compliance requirements (GDPR, HIPAA, SOC2)

7. **CI/CD Requirements**:
   - Build tools: npm, pip, gradle, cargo
   - Test frameworks: pytest, jest, JUnit
   - Code quality: SonarQube, ESLint, black
   - Security scanning: Trivy, Snyk, OWASP
   - Deployment strategy: Blue-green, canary, rolling

Format as JSON:
```json
{{
  "frameworks": [
    {{"name": "FastAPI", "version": "0.100.0", "type": "web_framework"}},
    {{"name": "React", "version": "18.2.0", "type": "frontend_framework"}}
  ],
  "databases": [
    {{"type": "ChromaDB", "version": "latest", "persistence": true, "purpose": "vector_database"}},
    {{"type": "Redis", "version": "7.0", "persistence": false, "purpose": "caching"}}
  ],
  "architecture": "multi-service",
  "services": [
    {{
      "name": "backend",
      "path": "backend",
      "language": "Python",
      "framework": "FastAPI",
      "version": "3.11",
      "port": 8000,
      "metrics_port": 9090,
      "entry_point": "server.py",
      "health_check": "/healthz",
      "env_vars": ["DATABASE_URL", "REDIS_URL", "API_KEY"],
      "cpu_limit": "1000m",
      "memory_limit": "512Mi",
      "depends_on": ["redis", "chromadb"]
    }}
  ],
  "infrastructure": {{
    "container_orchestration": "kubernetes",
    "reverse_proxy": "nginx",
    "observability": ["prometheus", "grafana"],
    "secrets_management": "vault"
  }},
  "production_requirements": {{
    "authentication": "JWT",
    "rate_limiting": true,
    "cors_enabled": true,
    "ssl_required": true,
    "backup_strategy": "daily"
  }},
  "key_dependencies": {{"dependency": "purpose"}},
  "insights": ["Enterprise-grade insight 1", "Production readiness insight 2"]
}}
```"""
    
    def _build_dockerfile_prompt(self,
                                 service_info: Dict[str, Any],
                                 basic_dockerfile: str) -> str:
        """Build prompt for Dockerfile enhancement."""
        return f"""Generate an ENTERPRISE-GRADE Dockerfile for a {service_info.get('language', 'Unknown')} service using {service_info.get('framework', 'Unknown')}.

**Service Info:**
- Name: {service_info.get('name', 'app')}
- Language: {service_info.get('language', 'Unknown')}
- Framework: {service_info.get('framework', 'Unknown')}
- Port: {service_info.get('port', 8000)}
- Entry Point: {service_info.get('entry_point', 'main.py')}
- Key Dependencies: {', '.join(service_info.get('dependencies', [])[:5])}

**Current Dockerfile:**
```dockerfile
{basic_dockerfile}
```

**ENTERPRISE REQUIREMENTS** (MANDATORY):

1. **Security**:
   - Run as non-root user with specific UID/GID
   - Use official base images with specific versions (no 'latest')
   - Scan for vulnerabilities (add LABEL for scanning)
   - Minimize attack surface (distroless or alpine)
   - No secrets in build (use build args)
   - Read-only root filesystem where possible

2. **Multi-Stage Build**:
   - Builder stage (dependencies + compilation)
   - Production stage (runtime only, minimal layers)
   - Security scanning stage (optional)
   - Development stage for debugging

3. **Optimization**:
   - Leverage layer caching (dependencies before code)
   - Minimize image size (remove build tools in final stage)
   - Use .dockerignore patterns
   - Combine RUN commands to reduce layers

4. **Observability**:
   - Add LABELs (version, maintainer, git-commit, build-date)
   - Framework-specific health check with proper intervals
   - Add STOPSIGNAL for graceful shutdown
   - Expose metrics port if applicable

5. **Production Readiness**:
   - Set proper environment variables (LOG_LEVEL, WORKERS, TIMEOUT)
   - Use framework's production server (gunicorn, uvicorn, nginx)
   - Configure graceful shutdown
   - Add startup probe compatibility
   - Set working directory and volume mount points

6. **Framework-Specific**:
   - FastAPI: Use uvicorn with workers, set async workers
   - Flask: Use gunicorn with gevent workers
   - Express/Node: Use PM2 or multi-process mode
   - React: Nginx with gzip, caching headers, SPA routing
   - Go: Static binary, scratch base image

Return ONLY the production-ready Dockerfile with inline comments explaining enterprise features."""
    
    def _build_compose_prompt(self,
                              services: List[Dict[str, Any]],
                              dependencies: Dict[str, Any],
                              basic_compose: str) -> str:
        """Build prompt for docker-compose enhancement."""
        services_summary = "\n".join([
            f"  - {s.get('name', 'service')}: {s.get('language', 'Unknown')} ({s.get('framework', 'Unknown')}), port {s.get('port', 'unknown')}"
            for s in services
        ])
        
        return f"""Generate an ENTERPRISE-GRADE docker-compose.yml for production-ready local development.

**Services:**
{services_summary}

**Detected Dependencies:**
- Databases: {', '.join(dependencies.get('databases', []))}
- Caching: {', '.join(dependencies.get('caching', []))}
- Messaging: {', '.join(dependencies.get('messaging', []))}

**Current docker-compose.yml:**
```yaml
{basic_compose}
```

**ENTERPRISE REQUIREMENTS** (MANDATORY):

1. **Service Architecture**:
   - Include ONLY services actually needed (from detected dependencies)
   - Use correct service names matching repository structure
   - Define networks for service isolation (frontend, backend, data)
   - Add resource limits (cpu, memory) for stability

2. **Security**:
   - Use environment variables from .env file (no hardcoded secrets)
   - Run containers as non-root users
   - Use read_only root filesystem where possible
   - Add security_opt for AppArmor/SELinux
   - Restrict capabilities (drop ALL, add only needed)

3. **High Availability**:
   - Add health checks for ALL services with proper intervals
   - Use depends_on with service_healthy condition
   - Configure restart policies (restart: unless-stopped)
   - Add init: true for proper signal handling
   - Set stop_grace_period for graceful shutdown

4. **Data Persistence**:
   - Named volumes for databases (not bind mounts)
   - Tmpfs for temporary data
   - Volume labels for backup automation
   - Backup volumes for critical data

5. **Observability**:
   - Expose metrics ports for Prometheus
   - Add logging configuration (json-file with rotation)
   - Add labels for service discovery
   - Configure log aggregation

6. **Development Experience**:
   - Hot reload for development (watch mode)
   - Debug ports exposed conditionally
   - Volume mounts for code (development profile)
   - Seed data initialization

7. **Database-Specific**:
   - PostgreSQL: Set shared_buffers, max_connections, enable pg_stat_statements
   - MongoDB: Enable authentication, set replica set
   - Redis: Configure maxmemory, eviction policy, persistence
   - ChromaDB: Set persist directory, configure HNSW parameters

Return ONLY the production-ready docker-compose.yml with version 3.8+ and inline comments."""
    
    def _build_architecture_prompt(self,
                                   directory_structure: Dict[str, Any],
                                   dependency_files: Dict[str, str]) -> str:
        """Build prompt for architecture detection."""
        deps_summary = "\n".join([
            f"**{filename}:**\n```\n{content[:500]}...\n```"
            for filename, content in dependency_files.items()
        ])
        
        return f"""Analyze this repository structure and dependency files to determine the application architecture.

**Directory Structure:**
{json.dumps(directory_structure, indent=2)}

**Dependency Files:**
{deps_summary}

Determine:
1. Architecture type: monolith, backend-frontend, microservices, or serverless
2. All services: name, path, language, framework, port, entry point
3. All databases and data stores used
4. All caching layers used
5. API patterns (REST, GraphQL, gRPC)

Format as JSON:
```json
{{
  "architecture": "backend-frontend",
  "services": [
    {{
      "name": "backend",
      "path": "backend",
      "language": "Python",
      "framework": "FastAPI",
      "port": 8000,
      "entry_point": "server.py",
      "databases": ["chromadb"],
      "api_endpoints": ["/api/v1/..."]
    }},
    {{
      "name": "frontend",
      "path": "frontend",
      "language": "JavaScript",
      "framework": "React",
      "port": 3000,
      "entry_point": "src/index.js"
    }}
  ],
  "databases": ["chromadb"],
  "caching": ["redis"],
  "api_type": "REST"
}}
```"""
    
    # =========================================================================
    # Private Methods - Response Parsers
    # =========================================================================
    
    def _parse_discovery_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse AI discovery analysis response."""
        try:
            # Extract JSON from markdown code blocks
            if "```json" in analysis:
                start = analysis.find("```json") + 7
                end = analysis.find("```", start)
                json_str = analysis[start:end].strip()
            elif "```" in analysis:
                start = analysis.find("```") + 3
                end = analysis.find("```", start)
                json_str = analysis[start:end].strip()
            else:
                json_str = analysis
            
            return json.loads(json_str)
        except Exception as e:
            logger.warning(f"Failed to parse AI analysis: {e}")
            return {}
    
    def _parse_architecture_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse architecture analysis response."""
        return self._parse_discovery_analysis(analysis)
    
    def _extract_dockerfile(self, response: str) -> Optional[str]:
        """Extract Dockerfile content from AI response."""
        if "```dockerfile" in response:
            start = response.find("```dockerfile") + 13
            end = response.find("```", start)
            return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            return response[start:end].strip()
        return None
    
    def _extract_yaml(self, response: str) -> Optional[str]:
        """Extract YAML content from AI response."""
        if "```yaml" in response:
            start = response.find("```yaml") + 7
            end = response.find("```", start)
            return response[start:end].strip()
        elif "```yml" in response:
            start = response.find("```yml") + 6
            end = response.find("```", start)
            return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            return response[start:end].strip()
        return None
    
    def _merge_discovery_results(self,
                                 basic: Dict[str, Any],
                                 ai_insights: Dict[str, Any]) -> Dict[str, Any]:
        """Merge basic discovery with AI insights."""
        enhanced = basic.copy()
        
        # Add AI-detected information
        if 'frameworks' in ai_insights:
            enhanced['frameworks'] = ai_insights['frameworks']
        
        if 'databases' in ai_insights:
            enhanced['databases'] = ai_insights['databases']
        
        if 'architecture' in ai_insights:
            enhanced['architecture'] = ai_insights['architecture']
        
        if 'services' in ai_insights:
            enhanced['services'] = ai_insights['services']
        
        if 'key_dependencies' in ai_insights:
            enhanced['key_dependencies'] = ai_insights['key_dependencies']
        
        if 'insights' in ai_insights:
            enhanced['ai_insights'] = ai_insights['insights']
        
        return enhanced
    
    def _format_sample_files(self, sample_files: Dict[str, str]) -> str:
        """Format sample files for prompt."""
        formatted = []
        for filename, content in sample_files.items():
            # Limit content length
            content_preview = content[:1000] + ("..." if len(content) > 1000 else "")
            formatted.append(f"**{filename}:**\n```\n{content_preview}\n```")
        return "\n\n".join(formatted)


# Global singleton instance
_ai_enhancer = None

def get_ai_enhancer() -> AIEnhancer:
    """Get or create AI enhancer singleton."""
    global _ai_enhancer
    if _ai_enhancer is None:
        _ai_enhancer = AIEnhancer()
    return _ai_enhancer
