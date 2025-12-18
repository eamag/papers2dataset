import json
import threading
from collections import deque
from pathlib import Path
from typing import Optional


class BFSQueue:
    def __init__(self, path: Path = Path("bfs_queue.json")):
        self.path = path
        self.lock = threading.Lock()
        self.queue: deque[str] = deque()  # paper IDs in BFS order
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
        if not paper_id:
            return False
        with self.lock:
            if paper_id in self.processed or paper_id in self.skipped:
                return False
            if paper_id in self.queue:
                return False

            self.queue.append(paper_id)
            self._save()
            return True

    def add_many(self, paper_ids: list[str]) -> int:
        with self.lock:
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
        with self.lock:
            while self.queue:
                pid = self.queue.popleft()
                if pid not in self.processed and pid not in self.skipped:
                    self.in_progress.add(pid)
                    self._save()
                    return pid
            return None

    def peek(self) -> Optional[str]:
        with self.lock:
            for pid in self.queue:
                if pid not in self.processed and pid not in self.skipped:
                    return pid
            return None

    def mark_processed(self, paper_id: str):
        with self.lock:
            self.processed.add(paper_id)
            self.in_progress.discard(paper_id)
            self._save()

    def mark_skipped(self, paper_id: str, reason: str):
        with self.lock:
            self.skipped[paper_id] = reason
            self.in_progress.discard(paper_id)
            self._save()

    def mark_failed(self, paper_id: str, reason: str):
        with self.lock:
            self.failed[paper_id] = reason
            self.in_progress.discard(paper_id)
            self._save()

    def __len__(self) -> int:
        with self.lock:
            return len(self.queue) + len(self.processed) + len(self.skipped)

    def __contains__(self, paper_id: str) -> bool:
        with self.lock:
            return (
                paper_id in self.queue
                or paper_id in self.processed
                or paper_id in self.skipped
            )

    def __repr__(self) -> str:
        with self.lock:
            return f"In Progress: {list(self.in_progress)}\nNext 10 in Queue: {list(self.queue)[:10]}\nProcessed: {list(self.processed)}\nSkipped: {list(self.skipped)}"
