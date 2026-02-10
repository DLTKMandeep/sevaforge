# Contributing to ForgeFlow

Thank you for your interest in contributing to ForgeFlow! This document provides guidelines and instructions for contributing.

---

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. Please be respectful and constructive in all interactions.

---

## Getting Started

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/forgeflow.git
cd forgeflow
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### 3. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

---

## Development Workflow

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/test_agents.py -v
```

### Code Quality

```bash
# Run linter
make lint

# Format code
make format

# Type checking
make typecheck
```

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`. To run manually:

```bash
pre-commit run --all-files
```

---

## Contribution Types

### Bug Reports

1. Search existing issues first
2. Use the bug report template
3. Include:
   - ForgeFlow version
   - Python version
   - Operating system
   - Steps to reproduce
   - Expected vs actual behavior
   - Error messages/logs

### Feature Requests

1. Search existing issues first
2. Use the feature request template
3. Describe the use case clearly
4. Explain why it would benefit users

### Pull Requests

1. Link to related issue(s)
2. Follow coding standards
3. Include tests for new features
4. Update documentation
5. Keep commits focused and atomic

---

## Adding a New Agent

To add a new agent to ForgeFlow:

### 1. Create Agent Class

```python
# agents/my_new_agent.py
from .base_agent import BaseAgent
from typing import Dict, Any

class MyNewAgent(BaseAgent):
    """Description of what this agent does."""

    def __init__(self):
        super().__init__(
            name="MyNewAgent",
            description="Does something useful"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = params.get("repo_path", ".")

        # Your business logic here
        result_data = self._do_something(repo_path)

        return self.create_result(
            status="success",
            summary="Successfully did something",
            data=result_data
        )

    def _do_something(self, path):
        # Implementation
        pass
```

### 2. Create MCP Server

```python
# mcp_servers/my_new_mcp/server.py
import sys
from pathlib import Path

root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))

from agents import MyNewAgent

agent = MyNewAgent()

def run(params: dict) -> dict:
    return agent.execute(params)
```

### 3. Register in Configuration

```yaml
# mcp-config.yaml
servers:
  my-new-mcp-server:
    command: "python3"
    args: ["mcp_servers/my_new_mcp/server.py"]
    capabilities: ["my_capability"]
    agent: "MyNewAgent"
    type: local

command_mapping:
  mycommand: "my-new-mcp-server"
```

### 4. Add CLI Command

```python
# cli/forgeflow.py

# Add to create_parser()
mycommand_parser = subparsers.add_parser("mycommand", help="Description")
mycommand_parser.add_argument("--path", "-p", default=".")

# Add to main()
elif args.command == "mycommand":
    result = mc.mycommand(path)
```

### 5. Add to Mission Control

```python
# core/mission_control.py

def mycommand(self, path: str) -> Dict:
    return self.orchestrator.call_mcp(
        "my-new-mcp-server",
        {"action": "mycommand", "repo_path": path}
    )
```

### 6. Write Tests

```python
# tests/test_my_new_agent.py
import pytest
from agents import MyNewAgent

class TestMyNewAgent:
    def test_execute_success(self, tmp_path):
        agent = MyNewAgent()
        result = agent.execute({"repo_path": str(tmp_path)})
        assert result["status"] == "success"
```

### 7. Update Documentation

- Add to `agents/__init__.py`
- Update README command table
- Update ARCHITECTURE.md

---

## Coding Standards

### Python Style

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use docstrings for classes and public methods

### Naming Conventions

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

### Documentation

```python
def my_function(param1: str, param2: int = 10) -> Dict[str, Any]:
    """Brief description of function.

    Args:
        param1: Description of param1
        param2: Description of param2 (default: 10)

    Returns:
        Dictionary containing result data

    Raises:
        ValueError: If param1 is empty
    """
    pass
```

---

## Pull Request Process

1. **Update your branch**
   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. **Run checks locally**
   ```bash
   make lint
   make test
   ```

3. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **PR Description**
   - Link to related issues
   - Describe changes
   - Note any breaking changes
   - Include testing steps

5. **Review Process**
   - Address reviewer feedback
   - Keep discussions constructive
   - Update based on suggestions

6. **Merge**
   - Squash commits if requested
   - Ensure CI passes
   - Get required approvals

---

## Questions?

- Open a [Discussion](https://github.com/forgeflow/forgeflow/discussions)
- Check existing [Issues](https://github.com/forgeflow/forgeflow/issues)
- Read the [Documentation](./)

Thank you for contributing! 🎉
