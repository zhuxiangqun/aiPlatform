from typing import Dict, Any
import openai
import os

class SystemArchitectAgent:
    def __init__(self):
        self.llm_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def generate_architecture(self, prd_content: str) -> Dict[str, str]:
        """Generate system architecture based on PRD"""
        messages = [
            {"role": "system", "content": "You are a System Architect. Design a detailed system architecture based on the PRD."},
            {"role": "user", "content": f"Design architecture for: {prd_content}"}
        ]
        
        response = self.llm_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )
        
        architecture_text = response.choices[0].message.content
        
        return {
            "diagram": architecture_text,
            "description": "Generated system architecture"
        }