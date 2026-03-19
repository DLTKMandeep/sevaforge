"""Pytest configuration and fixtures."""
import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository structure for testing."""
    # Create basic structure
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    
    # Create some Python files
    (tmp_path / "src" / "main.py").write_text("""
def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")
    
    (tmp_path / "src" / "utils.py").write_text("""
def helper():
    return "helper"
""")
    
    # Create test file
    (tmp_path / "tests" / "test_main.py").write_text("""
def test_main():
    assert True
""")
    
    # Create config files
    (tmp_path / "requirements.txt").write_text("pytest>=7.0\n")
    (tmp_path / "README.md").write_text("# Test Project\n")
    
    return tmp_path


@pytest.fixture
def temp_repo_with_issues(tmp_path):
    """Create a temporary repository with security issues for testing."""
    # Create source with issues
    (tmp_path / "src").mkdir()
    
    (tmp_path / "src" / "insecure.py").write_text("""
import os
import subprocess

# Hardcoded secret
password = "super_secret_123"
api_key = "sk-12345678901234567890"

def run_command(user_input):
    # Command injection
    os.system("ls " + user_input)
    subprocess.call(user_input, shell=True)

def query_db(user_input):
    # SQL injection
    query = f"SELECT * FROM users WHERE id = {user_input}"
    return query
""")
    
    # Create .env file (should be detected)
    (tmp_path / ".env").write_text("SECRET_KEY=abc123\n")
    
    return tmp_path


@pytest.fixture
def empty_repo(tmp_path):
    """Create an empty repository for testing."""
    return tmp_path
