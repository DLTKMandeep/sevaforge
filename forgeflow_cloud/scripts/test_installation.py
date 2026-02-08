#!/usr/bin/env python3
"""ForgeFlow Installation Test Script

Run this script to verify that ForgeFlow is correctly installed.
"""

import sys
import os

def test_python_version():
    """Check Python version >= 3.9"""
    print(f"Python version: {sys.version}")
    if sys.version_info < (3, 9):
        print("❌ Python 3.9+ required")
        return False
    print("✅ Python version OK")
    return True

def test_dependencies():
    """Check required dependencies"""
    deps = ['yaml', 'click', 'rich']
    all_ok = True
    for dep in deps:
        try:
            __import__(dep)
            print(f"✅ {dep} installed")
        except ImportError:
            print(f"❌ {dep} NOT installed")
            all_ok = False
    return all_ok

def test_forgeflow_imports():
    """Check ForgeFlow modules can be imported"""
    # Add project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)
    
    try:
        from agents import DiscoveryAgent, SecurityAgent, BaseAgent
        print("✅ ForgeFlow agents import OK")
    except ImportError as e:
        print(f"❌ Agent import failed: {e}")
        return False
    
    try:
        from core.orchestrator import MCPOrchestrator
        print("✅ Orchestrator import OK")
    except ImportError as e:
        print(f"❌ Orchestrator import failed: {e}")
        return False
    
    return True

def test_config_exists():
    """Check mcp-config.yaml exists"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, 'mcp-config.yaml')
    if os.path.exists(config_path):
        print("✅ mcp-config.yaml found")
        return True
    print("❌ mcp-config.yaml not found")
    return False

def main():
    print("\n" + "="*50)
    print("ForgeFlow Installation Test")
    print("="*50 + "\n")
    
    results = [
        test_python_version(),
        test_dependencies(),
        test_forgeflow_imports(),
        test_config_exists()
    ]
    
    print("\n" + "="*50)
    if all(results):
        print("✅ All tests passed! ForgeFlow is ready to use.")
        print("\nTry running: python3 cli/forgeflow.py --help")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
