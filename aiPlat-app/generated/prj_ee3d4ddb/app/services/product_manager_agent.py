from app.services.llm_service import LLMService
from typing import List, Dict, Any

class ProductManagerAgent:
    def __init__(self):
        self.llm = LLMService()
    
    def generate_prd(self, conversation_history: List[Dict[str, str]]) -> str:
        system_prompt = """You are a Product Manager Agent. Your role is to analyze user requirements 
        and generate a comprehensive Product Requirements Document (PRD). 
        Based on the conversation history, create a detailed PRD that includes:
        1. Product Overview
        2. User Stories
        3. Functional Requirements
        4. Non-Functional Requirements
        5. Acceptance Criteria
        
        Output the PRD in a structured markdown format."""
        
        return self.llm.chat(conversation_history, system_prompt)
    
    def confirm_prd(self, prd_content: str) -> bool:
        # Simulated confirmation logic - in production, would involve user feedback
        return True