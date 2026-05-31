class ArchitectureDesigner:
    def __call__(self, params: dict) -> dict:
        prd = params.get("prd", "")
        architecture = f"Architecture designed based on PRD: {prd[:50]}..."
        return {"architecture": architecture}