from typing import List, Dict

class AgentManager:
    def __init__(self):
        self.agents = {}

    def register_agent(self, name: str, agent_instance):
        self.agents[name] = agent_instance

    def get_agent(self, name: str):
        return self.agents.get(name)

    def execute_skill(self, agent_name: str, skill_name: str, context: dict) -> dict:
        agent = self.get_agent(agent_name)
        if not agent:
            return {"error": f"Agent {agent_name} not found"}
        return agent.execute(skill_name, context)