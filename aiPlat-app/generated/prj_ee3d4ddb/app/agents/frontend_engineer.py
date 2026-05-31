import os
from openai import OpenAI

class FrontendEngineerAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
    def generate_code(self, architecture: dict, component: str = "frontend") -> str:
        system_prompt = f"""You are a Frontend Engineer Agent. Your role is to:
1. Analyze architecture designs to implement frontend code
2. Generate production-ready React/Vue/Angular components
3. Follow best practices for frontend development

Generate {component} code based on the architecture design. Include:
- Component structure
- State management
- API integration
- UI/UX implementation
- Responsive design"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Based on this architecture, generate the {component} code:\n\nArchitecture Diagram: {architecture.get('diagram', '')}\n\nArchitecture Description: {architecture.get('description', '')}"}
        ]
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=3000
        )
        
        return response.choices[0].message.content