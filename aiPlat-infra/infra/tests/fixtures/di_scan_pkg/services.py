from infra.di import injectable


@injectable
class GreeterService:
    def hello(self, name: str) -> str:
        return f"hello {name}"

