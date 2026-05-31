from typing import Dict, Any
import openai
import os

class BackendEngineerAgent:
    def __init__(self):
        self.llm_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def generate_backend_code(self, architecture: Dict[str, Any]) -> str:
        """Generate backend code based on architecture"""
        messages = [
            {"role": "system", "content": "You are a Backend Engineer. Generate Python/FastAPI backend code based on the architecture."},
            {"role": "user", "content": f"Generate backend code for architecture: {architecture.get('diagram', '')}"}
        ]
        
        response = self.llm_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )
        
        return response.choices[0].message.content