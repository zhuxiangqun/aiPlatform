from app.services.llm_service import LLMService
from app.services.agent_engine import AgentEngine

llm_service = LLMService()
agent_engine = AgentEngine(llm_service)