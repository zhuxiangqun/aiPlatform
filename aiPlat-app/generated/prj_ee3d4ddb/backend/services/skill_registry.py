class SkillRegistry:
    def __init__(self):
        self._skills = {}

    def register(self, name: str, skill_func):
        self._skills[name] = skill_func

    def execute(self, name: str, params: dict) -> dict:
        skill = self._skills.get(name)
        if not skill:
            return {"error": f"Skill {name} not found"}
        return skill(params)