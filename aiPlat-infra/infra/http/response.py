from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional


@dataclass
class Response:
    status_code: int
    text: str
    headers: Dict[str, str]
    cookies: Dict[str, str]
    elapsed: timedelta
    _content: Optional[bytes] = None
    _json: Optional[Any] = None

    def json(self) -> Any:
        if self._json is None:
            import json

            self._json = json.loads(self.text)
        return self._json

    @property
    def content(self) -> bytes:
        if self._content is None:
            self._content = self.text.encode("utf-8")
        return self._content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(f"{self.status_code} {self.text}")


class HTTPError(Exception):
    pass
