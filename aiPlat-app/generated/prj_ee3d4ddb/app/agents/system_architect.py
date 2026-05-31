import os
from openai import OpenAI

class SystemArchitectAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
    def generate_architecture(self, prd_content: str) -> dict:
        system_prompt = """You are a System Architect Agent. Your role is to:
1. Analyze PRD documents to design system architecture
2. Generate detailed architecture diagrams (text-based)
3. Provide comprehensive architecture descriptions

Generate a system architecture design based on the PRD content. Include:
- Architecture Overview
- Component Diagram (text-based)
- Data Flow
- API Design
- Technology Stack Recommendations
- Deployment Architecture"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Based on this PRD, generate a system architecture design:\n\n{prd_content}"}
        ]
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=2500
        )
        
        architecture_content = response.choices[0].message.content
        
        return {
            "diagram": architecture_content,
            "description": architecture_content
        }