import openai
import os
from dotenv import load_dotenv

load_dotenv()

class LLMService:
    def __init__(self):
        openai.api_key = os.getenv("OPENAI_API_KEY", "sk-placeholder")
        self.model = os.getenv("LLM_MODEL", "gpt-4")
    
    async def chat_completion(self, messages: list, temperature: float = 0.7) -> str:
        try:
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"LLM Error: {str(e)}"