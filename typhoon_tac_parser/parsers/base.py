from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseParser(ABC):
    supported_headers: tuple[str, ...] = ()

    def supports(self, normalized: str) -> bool:
        first = normalized[:11]
        return first in self.supported_headers

    @abstractmethod
    def parse(self, raw: str) -> dict[str, Any]:
        raise NotImplementedError
