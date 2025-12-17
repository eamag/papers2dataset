"""Data models for the papers pipeline."""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class Paper:
    """Represents a paper in the BFS queue."""

    # Identifiers (at least one should be present)
    doi: Optional[str] = None
    openalex_id: Optional[str] = None

    # Metadata
    title: Optional[str] = None

    # BFS metadata
    source: str = "edison"  # edison, cited, citing, related
    depth: int = 0

    # Additional metadata from OpenAlex (populated after fetch)
    publication_year: Optional[int] = None
    cited_by_count: Optional[int] = None

    @property
    def id(self) -> str:
        """Returns a unique identifier for deduplication."""
        return self.doi or self.openalex_id or self.title or ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Paper":
        return cls(**data)
