class BugFixer:
    def __call__(self, params: dict) -> dict:
        bug_description = params.get("bug_description", "")
        fix = f"Fixed bug: {bug_description}"
        return {"fix": fix}