import os
from openai import OpenAI
from typing import List, Dict, Any

class ProductManagerAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.conversation_history = []
        
    def generate_prd(self, conversation_history: List[Dict[str, str]]) -> str:
        self.conversation_history = conversation_history
        
        system_prompt = """You are a Product Manager Agent. Your role is to:
1. Guide users through multi-turn conversations to clarify requirements
2. Generate comprehensive PRD documents based on user input
3. Ensure all requirements are well-defined and unambiguous

Generate a detailed PRD based on the conversation history. Include:
- Project Overview
- Target Users
- Functional Requirements
- Non-Functional Requirements
- User Stories
- Acceptance Criteria"""

        messages = [
            {"role": "system", "content": system_prompt},
            *conversation_history,
            {"role": "user", "content": "Based on our conversation, please generate a comprehensive PRD document."}
        ]
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )
        
        return response.choices[0].message.content