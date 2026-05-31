class CodeGenerator:
    def __call__(self, params: dict) -> dict:
        architecture = params.get("architecture", "")
        code = f"# Code generated based on architecture\n# {architecture[:50]}...\nprint('Hello World')"
        return {"code": code}