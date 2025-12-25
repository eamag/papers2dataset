"""BFS Queue for paper processing - Reference Implementation.

This is a reference implementation. Agents can use this directly with Python
or implement equivalent logic in their preferred language.

Usage:
    from bfs_queue import BFSQueue

    q = BFSQueue(Path("bfs_queue.json"))
    q.add_many(["W123", "W456"])

    while paper_id := q.pop():
        # process paper...
        q.mark_processed(paper_id)
"""

import json
from collections import deque
from pathlib import Path
from typing import Optional


class BFSQueue:
    """Persistent BFS queue for paper processing with stop/resume support."""

    def __init__(self, path: Path = Path("bfs_queue.json")):
        self.path = path
        self.queue: deque[str] = deque()
        self.processed: set[str] = set()
        self.skipped: dict[str, str] = {}
        self.in_progress: set[str] = set()
        self.failed: dict[str, str] = {}
        self._load_if_exists()

    def _load_if_exists(self):
        if self.path.exists():
            with open(self.path) as f:
                data = json.load(f)
            self.queue = deque(data.get("queue", []))
            self.processed = set(data.get("processed", []))
            self.skipped = data.get("skipped", {})
            self.failed = data.get("failed", {})

    def _save(self):
        data = {
            "queue": list(self.queue),
            "processed": list(self.processed),
            "skipped": self.skipped,
            "failed": self.failed,
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, paper_id: str) -> bool:
        """Add a single paper ID to the queue."""
        if not paper_id:
            return False
        if paper_id in self.processed or paper_id in self.skipped:
            return False
        if paper_id in self.queue:
            return False
        self.queue.append(paper_id)
        self._save()
        return True

    def add_many(self, paper_ids: list[str]) -> int:
        """Add multiple paper IDs, skipping duplicates. Returns count added."""
        existing = (
            set(self.queue)
            | self.processed
            | set(self.skipped.keys())
            | set(self.failed.keys())
        )
        added = 0
        for pid in paper_ids:
            if pid and pid not in existing:
                self.queue.append(pid)
                existing.add(pid)
                added += 1
        if added > 0:
            self._save()
        return added

    def pop(self) -> Optional[str]:
        """Pop the next paper ID from the queue."""
        while self.queue:
            pid = self.queue.popleft()
            if pid not in self.processed and pid not in self.skipped:
                self.in_progress.add(pid)
                self._save()
                return pid
        return None

    def mark_processed(self, paper_id: str):
        """Mark a paper as successfully processed."""
        self.processed.add(paper_id)
        self.in_progress.discard(paper_id)
        self._save()

    def mark_skipped(self, paper_id: str, reason: str):
        """Mark a paper as skipped (not relevant)."""
        self.skipped[paper_id] = reason
        self.in_progress.discard(paper_id)
        self._save()

    def mark_failed(self, paper_id: str, reason: str):
        """Mark a paper as failed (couldn't process)."""
        self.failed[paper_id] = reason
        self.in_progress.discard(paper_id)
        self._save()

    def status(self) -> dict:
        """Return current queue status."""
        return {
            "pending": len(self.queue),
            "processed": len(self.processed),
            "skipped": len(self.skipped),
            "failed": len(self.failed),
            "in_progress": len(self.in_progress),
        }

    def __repr__(self) -> str:
        return f"BFSQueue(pending={len(self.queue)}, processed={len(self.processed)}, skipped={len(self.skipped)}, failed={len(self.failed)})"
