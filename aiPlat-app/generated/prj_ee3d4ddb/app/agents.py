import openai
import os
from typing import List, Dict, Any

openai.api_key = os.getenv("OPENAI_API_KEY", "sk-your-key")

class ProductManagerAgent:
    @staticmethod
    def generate_prd(conversation_history: List[Dict[str, Any]]) -> str:
        messages = [
            {"role": "system", "content": "You are a product manager. Based on the conversation, generate a detailed PRD."}
        ] + conversation_history
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content

class SystemArchitectAgent:
    @staticmethod
    def generate_architecture(prd_content: str) -> Dict[str, str]:
        messages = [
            {"role": "system", "content": "You are a system architect. Based on the PRD, generate system architecture design."},
            {"role": "user", "content": f"PRD: {prd_content}\n\nGenerate architecture diagram (Mermaid format) and description."}
        ]
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=0.5
        )
        content = response.choices[0].message.content
        return {
            "diagram": content,
            "description": content
        }