from app.services.llm_service import LLMService

class FrontendEngineerAgent:
    def __init__(self):
        self.llm = LLMService()

    async def generate_code(self, architecture_description: str) -> str:
        system_prompt = {
            "role": "system",
            "content": "You are a Frontend Engineer. Based on the architecture design, implement the frontend code."
        }
        messages = [
            system_prompt,
            {"role": "user", "content": f"Architecture Design:\n{architecture_description}\n\nPlease generate the frontend code."}
        ]
        code = await self.llm.chat(messages)
        return code