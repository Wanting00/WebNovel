from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 仅本地开发需要科学上网代理；服务器（如境外云主机）直接访问 Gemini，应保持 USE_PROXY=false
_use_proxy = os.getenv("USE_PROXY", "false").strip().lower() in ("1", "true", "yes")
_proxy_url = os.getenv("PROXY_URL", "").strip()
if _use_proxy and _proxy_url:
    os.environ.setdefault("HTTP_PROXY", _proxy_url)
    os.environ.setdefault("HTTPS_PROXY", _proxy_url)


@dataclass(frozen=True)
class Settings:
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "./models/paraphrase-multilingual-MiniLM-L12-v2",
    )
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    chroma_dir: Path = Path(os.getenv("CHROMA_DIR", "./data/chroma"))
    chroma_collection: str = os.getenv("CHROMA_COLLECTION", "web_novel_corpus_local")
    chroma_batch_size: int = int(os.getenv("CHROMA_BATCH_SIZE", "100"))
    samples_dir: Path = Path(os.getenv("SAMPLES_DIR", "./data/samples"))
    style_templates_file: Path = Path(
        os.getenv("STYLE_TEMPLATES_FILE", "./data/style_templates.json")
    )
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "900"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "5"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))

    def ensure_directories(self) -> None:
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.style_templates_file.parent.mkdir(parents=True, exist_ok=True)
        self.samples_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
