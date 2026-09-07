from __future__ import annotations

import json
from datetime import datetime
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional
from uuid import uuid4


@dataclass
class StyleTemplate:
    style_id: str
    name: str
    description: str
    instructions: str
    source_sample_id: str
    source_filename: str
    created_at: str


class StyleTemplateStore:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = Lock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> List[StyleTemplate]:
        if not self.file_path.exists():
            return []
        try:
            raw_items = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"文风模板文件无法读取：{exc}") from exc
        templates = []
        for item in raw_items:
            if "source_sample_id" not in item:
                item["source_sample_id"] = item.pop("source_document_id", "")
            templates.append(StyleTemplate(**item))
        return templates

    def _write(self, templates: List[StyleTemplate]) -> None:
        temporary_path = self.file_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps([asdict(template) for template in templates], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.file_path)

    def list(self) -> List[StyleTemplate]:
        with self._lock:
            return self._read()

    def get(self, style_id: str) -> Optional[StyleTemplate]:
        return next((template for template in self.list() if template.style_id == style_id), None)

    def add(
        self,
        name: str,
        description: str,
        instructions: str,
        source_sample_id: str,
        source_filename: str,
    ) -> StyleTemplate:
        template = StyleTemplate(
            style_id=uuid4().hex,
            name=name.strip() or "未命名文风",
            description=description.strip(),
            instructions=instructions.strip(),
            source_sample_id=source_sample_id,
            source_filename=source_filename,
            created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        )
        with self._lock:
            templates = self._read()
            templates.append(template)
            self._write(templates)
        return template

    def delete(self, style_id: str) -> bool:
        with self._lock:
            templates = self._read()
            remaining = [template for template in templates if template.style_id != style_id]
            if len(remaining) == len(templates):
                return False
            self._write(remaining)
            return True
