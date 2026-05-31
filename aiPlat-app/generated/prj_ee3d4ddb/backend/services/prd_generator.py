class PRDGenerator:
    def __call__(self, params: dict) -> dict:
        requirements = params.get("requirements", "")
        prd_content = f"PRD generated based on: {requirements}"
        return {"prd": prd_content}