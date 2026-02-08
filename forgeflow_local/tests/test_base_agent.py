"""Tests for BaseAgent."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent


class ConcreteAgent(BaseAgent):
    """Concrete implementation for testing."""
    
    def execute(self, params):
        return self.create_result(
            status="success",
            summary="Test executed",
            data={"test": True}
        )


class TestBaseAgent:
    """Tests for BaseAgent class."""
    
    def test_agent_initialization(self):
        """Test agent initialization."""
        agent = ConcreteAgent(name="TestAgent", description="A test agent")
        
        assert agent.name == "TestAgent"
        assert agent.description == "A test agent"
    
    def test_create_result(self):
        """Test result creation."""
        agent = ConcreteAgent(name="TestAgent")
        
        result = agent.create_result(
            status="success",
            summary="Test summary",
            data={"key": "value"},
            findings=["finding1"]
        )
        
        assert result["status"] == "success"
        assert result["summary"] == "Test summary"
        assert result["data"] == {"key": "value"}
        assert result["findings"] == ["finding1"]
        assert "timestamp" in result
    
    def test_execute(self):
        """Test execute method."""
        agent = ConcreteAgent(name="TestAgent")
        result = agent.execute({})
        
        assert result["status"] == "success"
        assert result["data"]["test"] is True
    
    def test_save_and_get_results(self):
        """Test result storage."""
        agent = ConcreteAgent(name="TestAgent")
        
        result1 = agent.execute({})
        agent.save_result(result1)
        
        result2 = agent.execute({})
        agent.save_result(result2)
        
        results = agent.get_results()
        assert len(results) == 2
