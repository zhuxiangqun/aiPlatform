from app.services.llm_service import LLMService

class ProductManagerAgent:
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
    
    async def generate_prd(self, conversation_history: list) -> str:
        messages = [
            {"role": "system", "content": "You are a Product Manager. Guide the user through requirements gathering and generate a comprehensive PRD."}
        ] + conversation_history
        return await self.llm.chat_completion(messages)

class SystemArchitectAgent:
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
    
    async def generate_architecture(self, prd_content: str) -> dict:
        messages = [
            {"role": "system", "content": "You are a System Architect. Based on the PRD, generate system architecture design including diagrams and descriptions."},
            {"role": "user", "content": f"PRD Content:\n{prd_content}\n\nGenerate architecture design."}
        ]
        response = await self.llm.chat_completion(messages)
        return {
            "diagram": response,
            "description": f"Architecture generated from PRD: {prd_content[:100]}..."
        }

class FrontendEngineerAgent:
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
    
    async def generate_code(self, architecture_description: str) -> str:
        messages = [
            {"role": "system", "content": "You are a Frontend Engineer. Generate frontend code based on the architecture design."},
            {"role": "user", "content": f"Architecture:\n{architecture_description}\n\nGenerate frontend code."}
        ]
        return await self.llm.chat_completion(messages)

class BackendEngineerAgent:
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
    
    async def generate_code(self, architecture_description: str) -> str:
        messages = [
            {"role": "system", "content": "You are a Backend Engineer. Generate backend code based on the architecture design."},
            {"role": "user", "content": f"Architecture:\n{architecture_description}\n\nGenerate backend code."}
        ]
        return await self.llm.chat_completion(messages)