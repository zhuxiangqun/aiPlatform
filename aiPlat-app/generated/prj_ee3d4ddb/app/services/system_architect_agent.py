from app.services.llm_service import LLMService

class SystemArchitectAgent:
    def __init__(self):
        self.llm = LLMService()
    
    def generate_architecture(self, prd_content: str) -> dict:
        system_prompt = """You are a System Architect Agent. Based on the PRD, generate:
        1. Component diagram (ASCII/PlantUML)
        2. System architecture description
        3. Technology stack recommendations
        4. Data flow design
        
        Output in JSON format with 'diagram' and 'description' fields."""
        
        response = self.llm.chat(
            [{"role": "user", "content": f"Generate architecture based on this PRD:\n\n{prd_content}"}],
            system_prompt
        )
        
        # Parse response - simplified for example
        return {
            "diagram": response,
            "description": "System architecture generated based on PRD requirements"
        }