"""response：模块接口。"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional


@dataclass
class Response:
    """Response。"""
    status_code: int
    text: str
    headers: Dict[str, str]
    cookies: Dict[str, str]
    elapsed: timedelta
    _content: Optional[bytes] = None
    _json: Optional[Any] = None

    def json(self) -> Any:
        """json。
        """
        if self._json is None:
            import json

            self._json = json.loads(self.text)
        return self._json

    @property
    def content(self) -> bytes:
        """content。
        """
        if self._content is None:
            self._content = self.text.encode("utf-8")
        return self._content

    def raise_for_status(self) -> None:
        """raise_for_status。
        """
        if self.status_code >= 400:
            raise HTTPError(f"{self.status_code} {self.text}")


class HTTPError(Exception):
    """HTTPError。"""
    pass
