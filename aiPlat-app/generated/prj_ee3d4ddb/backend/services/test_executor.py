class TestExecutor:
    def __call__(self, params: dict) -> dict:
        test_cases = params.get("test_cases", [])
        results = []
        for tc in test_cases:
            results.append({"description": tc["description"], "result": "passed"})
        return {"results": results}