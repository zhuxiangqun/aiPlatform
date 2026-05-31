from typing import Dict, Callable

class SkillRegistry:
    def __init__(self):
        self.skills: Dict[str, Callable] = {}

    def register(self, name: str, func: Callable):
        self.skills[name] = func

    def execute(self, name: str, **kwargs):
        skill = self.skills.get(name)
        if not skill:
            raise ValueError(f"Skill {name} not found")
        return skill(**kwargs)