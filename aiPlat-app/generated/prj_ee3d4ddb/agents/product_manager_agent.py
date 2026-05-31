from typing import List, Dict, Any
import openai
import os

class ProductManagerAgent:
    def __init__(self):
        self.llm_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def generate_prd(self, conversation_history: List[Dict[str, str]]) -> str:
        """Generate PRD based on conversation history with user"""
        messages = [
            {"role": "system", "content": "You are a Product Manager. Generate a detailed PRD based on the conversation."},
            *conversation_history
        ]
        
        response = self.llm_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )
        
        return response.choices[0].message.content