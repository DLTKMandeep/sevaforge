"""Tests for CLI module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCLI:
    """Tests for CLI functionality."""
    
    def test_cli_import(self):
        """Test CLI module can be imported."""
        from cli import forgeflow
        assert hasattr(forgeflow, 'main')
        assert hasattr(forgeflow, 'create_parser')
    
    def test_parser_creation(self):
        """Test argument parser creation."""
        from cli.forgeflow import create_parser
        
        parser = create_parser()
        assert parser is not None
    
    def test_parser_discover_command(self):
        """Test discover command parsing."""
        from cli.forgeflow import create_parser
        
        parser = create_parser()
        args = parser.parse_args(['discover', '--path', './test'])
        
        assert args.command == 'discover'
        assert args.path == './test'
    
    def test_parser_scan_command(self):
        """Test scan command parsing."""
        from cli.forgeflow import create_parser
        
        parser = create_parser()
        args = parser.parse_args(['scan', '--severity', 'high'])
        
        assert args.command == 'scan'
        assert args.severity == 'high'
    
    def test_parser_generate_command(self):
        """Test generate command parsing."""
        from cli.forgeflow import create_parser
        
        parser = create_parser()
        args = parser.parse_args(['generate', '--stack', 'kubernetes'])
        
        assert args.command == 'generate'
        assert args.stack == 'kubernetes'
    
    def test_parser_mode_flag(self):
        """Test mode flag parsing."""
        from cli.forgeflow import create_parser
        
        parser = create_parser()
        args = parser.parse_args(['--mode', 'hybrid', 'discover'])
        
        assert args.mode == 'hybrid'
        assert args.command == 'discover'
    
    def test_all_commands_exist(self):
        """Test all expected commands are defined."""
        from cli.forgeflow import create_parser
        
        parser = create_parser()
        
        commands = [
            'discover', 'normalize', 'scan', 'generate',
            'review', 'test', 'deploy', 'monitor',
            'docs', 'bridge', 'status', 'doctor',
            'audit', 'run-all'
        ]
        
        for cmd in commands:
            # Should not raise
            if cmd == 'run-all':
                args = parser.parse_args([cmd, './test'])
            else:
                args = parser.parse_args([cmd])
            assert args.command == cmd
