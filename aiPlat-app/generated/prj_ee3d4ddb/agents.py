import openai
import os
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

class LLMService:
    @staticmethod
    def chat(messages, model="gpt-4"):
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content

class ProductManagerAgent:
    def __init__(self):
        self.llm = LLMService()
    
    def generate_prd(self, conversation_history):
        system_prompt = {
            "role": "system",
            "content": "You are a Product Manager. Based on the conversation, generate a comprehensive PRD document."
        }
        messages = [system_prompt] + conversation_history
        content = self.llm.chat(messages)
        return content
    
    def confirm_prd(self, prd_content):
        return True

class SystemArchitectAgent:
    def __init__(self):
        self.llm = LLMService()
    
    def generate_architecture(self, prd_content):
        system_prompt = {
            "role": "system",
            "content": "You are a System Architect. Based on the PRD, generate a detailed architecture design including diagram and description."
        }
        messages = [
            system_prompt,
            {"role": "user", "content": f"Generate architecture for: {prd_content}"}
        ]
        content = self.llm.chat(messages)
        diagram = content
        description = content
        return diagram, description

class FrontendEngineerAgent:
    def __init__(self):
        self.llm = LLMService()
    
    def generate_code(self, architecture_description):
        system_prompt = {
            "role": "system",
            "content": "You are a Frontend Engineer. Generate frontend code based on the architecture design."
        }
        messages = [
            system_prompt,
            {"role": "user", "content": f"Generate frontend code for: {architecture_description}"}
        ]
        return self.llm.chat(messages)

class BackendEngineerAgent:
    def __init__(self):
        self.llm = LLMService()
    
    def generate_code(self, architecture_description):
        system_prompt = {
            "role": "system",
            "content": "You are a Backend Engineer. Generate backend code based on the architecture design."
        }
        messages = [
            system_prompt,
            {"role": "user", "content": f"Generate backend code for: {architecture_description}"}
        ]
        return self.llm.chat(messages)