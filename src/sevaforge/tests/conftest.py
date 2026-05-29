"""
Shared test fixtures and configuration.
"""

import os
import sys

# Ensure the src directory is on the path for test imports
src_dir = os.path.join(os.path.dirname(__file__), "..", "..")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Set test environment
os.environ.setdefault("SEVAFORGE_ENVIRONMENT", "development")
os.environ.setdefault("SEVAFORGE_DEBUG", "true")
os.environ.setdefault("SEVAFORGE_LOG_LEVEL", "WARNING")
