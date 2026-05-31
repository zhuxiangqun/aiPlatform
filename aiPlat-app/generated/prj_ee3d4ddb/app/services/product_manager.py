from app.services.llm_service import LLMService
from typing import List, Dict, Any

class ProductManagerAgent:
    def __init__(self):
        self.llm = LLMService()
        self.conversation_history = []

    async def generate_prd(self, conversation_history: List[Dict[str, Any]]) -> str:
        self.conversation_history = conversation_history
        system_prompt = {
            "role": "system",
            "content": "You are a Product Manager. Guide the user through a multi-turn conversation to clarify requirements and generate a comprehensive PRD."
        }
        messages = [system_prompt] + self.conversation_history
        messages.append({
            "role": "user",
            "content": "Based on our conversation, please generate a complete PRD document."
        })
        prd_content = await self.llm.chat(messages)
        return prd_content