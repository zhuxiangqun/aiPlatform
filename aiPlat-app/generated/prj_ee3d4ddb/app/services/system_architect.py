from app.services.llm_service import LLMService

class SystemArchitectAgent:
    def __init__(self):
        self.llm = LLMService()

    async def generate_architecture(self, prd_content: str) -> dict:
        system_prompt = {
            "role": "system",
            "content": "You are a System Architect. Based on the PRD, generate a detailed system architecture design including diagram and description."
        }
        messages = [
            system_prompt,
            {"role": "user", "content": f"PRD Content:\n{prd_content}\n\nPlease generate a system architecture design."}
        ]
        response = await self.llm.chat(messages)
        return {
            "diagram": response,
            "description": response
        }