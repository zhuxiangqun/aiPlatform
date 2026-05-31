```python
from typing import List, Dict, Any, Optional
import openai
import os

class LLMService:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        openai.api_key = self.api_key
    
    async def generate_response(
        self,
        system_prompt: str,
        conversation: List[Dict[str, str]],
        temperature: float = 0.7
    ) -> str:
        """Generate response using OpenAI GPT-4"""
        try:
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(conversation)
            
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=messages,
                temperature=temperature
            )
            
            return response.choices[0].message.content
        except Exception as e:
            # Fallback response for development/testing
            return f"Simulated LLM response for: {system_prompt[:50]}..."
```