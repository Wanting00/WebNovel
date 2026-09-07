from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import List, Optional
from uuid import uuid4


@dataclass
class SampleRecord:
    sample_id: str
    filename: str
    size_bytes: int
    created_at: str
    corpus_id: Optional[str] = None
    corpus_chunks: int = 0


class SampleStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.registry_path = directory / "samples.json"
        self._lock = Lock()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _read(self) -> List[SampleRecord]:
        if not self.registry_path.exists():
            return []
        try:
            items = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"样本区清单无法读取：{exc}") from exc
        return [
            SampleRecord(
                sample_id=item["sample_id"],
                filename=item["filename"],
                size_bytes=item["size_bytes"],
                created_at=item["created_at"],
                corpus_id=item.get("corpus_id"),
                corpus_chunks=item.get("corpus_chunks", 0),
            )
            for item in items
        ]

    def _write(self, records: List[SampleRecord]) -> None:
        temporary_path = self.registry_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps([asdict(record) for record in records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.registry_path)

    def list(self) -> List[SampleRecord]:
        with self._lock:
            return self._read()

    def get(self, sample_id: str) -> Optional[SampleRecord]:
        return next((record for record in self.list() if record.sample_id == sample_id), None)

    def add(self, filename: str, content: bytes) -> SampleRecord:
        sample_id = uuid4().hex
        record = SampleRecord(
            sample_id=sample_id,
            filename=filename,
            size_bytes=len(content),
            created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        )
        with self._lock:
            (self.directory / f"{sample_id}.txt").write_bytes(content)
            records = self._read()
            records.append(record)
            self._write(records)
        return record

    def read_content(self, sample_id: str) -> bytes:
        if self.get(sample_id) is None:
            raise ValueError("样本文件不存在或已经被删除。")
        try:
            return (self.directory / f"{sample_id}.txt").read_bytes()
        except OSError as exc:
            raise RuntimeError(f"样本文件无法读取：{exc}") from exc

    def set_corpus(self, sample_id: str, corpus_id: str, chunks: int) -> None:
        with self._lock:
            records = self._read()
            for record in records:
                if record.sample_id == sample_id:
                    record.corpus_id = corpus_id
                    record.corpus_chunks = chunks
                    self._write(records)
                    return
        raise ValueError("样本文件不存在或已经被删除。")

    def delete(self, sample_id: str) -> bool:
        with self._lock:
            records = self._read()
            remaining = [record for record in records if record.sample_id != sample_id]
            if len(remaining) == len(records):
                return False
            try:
                (self.directory / f"{sample_id}.txt").unlink(missing_ok=True)
            except OSError as exc:
                raise RuntimeError(f"样本文件删除失败：{exc}") from exc
            self._write(remaining)
            return True
