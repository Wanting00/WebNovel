from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import settings
from rag_service import RAGService

app = FastAPI(title="AI 网文扩写工具", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "https://lalabots.com",
        "https://www.lalabots.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
service = RAGService()


class GenerateRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=5000)
    k: Optional[int] = Field(default=None, ge=1, le=20)
    style_id: Optional[str] = None
    corpus_id: Optional[str] = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "gemini_configured": bool(settings.google_api_key)}


@app.get("/documents")
def documents() -> dict:
    try:
        return {"documents": service.list_documents()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择 TXT 文件。")
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="目前只支持 .txt 文件。")

    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb} MB。")
    try:
        indexed = service.index_text(file.filename, content)
        return {"document_id": indexed.document_id, "filename": indexed.filename, "chunks": indexed.chunks}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"索引失败：{exc}") from exc


@app.get("/samples")
def samples() -> dict:
    try:
        return {"samples": service.list_samples()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取样本区失败：{exc}") from exc


@app.post("/samples/upload")
async def upload_sample(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择 TXT 样本文件。")
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="目前只支持 .txt 文件。")
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb} MB。")
    try:
        return service.add_sample(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存样本失败：{exc}") from exc


@app.post("/samples/{sample_id}/index")
def index_sample(sample_id: str) -> dict:
    try:
        return service.index_sample(sample_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成语料失败：{exc}") from exc


@app.delete("/samples/{sample_id}")
def delete_sample(sample_id: str) -> dict:
    try:
        service.delete_sample(sample_id)
        return {"deleted": True, "sample_id": sample_id}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除样本失败：{exc}") from exc


@app.delete("/documents/{document_id}")
def delete_document(document_id: str) -> dict:
    try:
        service.delete_document(document_id)
        return {"deleted": True, "document_id": document_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除失败：{exc}") from exc


@app.get("/styles")
def styles() -> dict:
    try:
        return {"styles": service.list_styles()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取文风模板失败：{exc}") from exc


@app.post("/styles/extract/{sample_id}")
def extract_style(sample_id: str) -> dict:
    try:
        return service.extract_style(sample_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文风提炼失败：{exc}") from exc


@app.delete("/styles/{style_id}")
def delete_style(style_id: str) -> dict:
    try:
        service.delete_style(style_id)
        return {"deleted": True, "style_id": style_id}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除文风模板失败：{exc}") from exc


@app.post("/generate")
def generate(request: GenerateRequest) -> dict:
    try:
        return service.generate(
            request.instruction,
            request.k,
            request.style_id,
            request.corpus_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"扩写失败：{exc}") from exc
