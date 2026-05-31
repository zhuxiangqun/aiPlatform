class TestCaseGenerator:
    def __call__(self, params: dict) -> dict:
        code = params.get("code", "")
        test_cases = [{"description": f"Test for {code[:30]}...", "status": "pending"}]
        return {"test_cases": test_cases}