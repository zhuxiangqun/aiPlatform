from typing import Dict, Any
import openai
import os

class FrontendEngineerAgent:
    def __init__(self):
        self.llm_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def generate_frontend_code(self, architecture: Dict[str, Any]) -> str:
        """Generate frontend code based on architecture"""
        messages = [
            {"role": "system", "content": "You are a Frontend Engineer. Generate React/Vue frontend code based on the architecture."},
            {"role": "user", "content": f"Generate frontend code for architecture: {architecture.get('diagram', '')}"}
        ]
        
        response = self.llm_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )
        
        return response.choices[0].message.content