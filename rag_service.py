from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import Settings, settings
from sample_store import SampleStore
from style_store import StyleTemplate, StyleTemplateStore


@dataclass
class IndexedDocument:
    document_id: str
    filename: str
    chunks: int


class RAGService:
    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings
        self._vectorstore: Optional[Chroma] = None
        self._llm: Optional[ChatGoogleGenerativeAI] = None
        self._sample_store = SampleStore(self.settings.samples_dir)
        self._style_store = StyleTemplateStore(self.settings.style_templates_file)

    def _require_api_key(self) -> str:
        api_key = self.settings.google_api_key
        if not api_key or not api_key.strip():
            raise RuntimeError("未配置 GOOGLE_API_KEY，请在 .env 中设置 Gemini API Key。")
        return api_key.strip()

    def _get_vectorstore(self) -> Chroma:
        if self._vectorstore is None:
            self.settings.ensure_directories()
            embedding_path = Path(self.settings.embedding_model)
            if not embedding_path.exists():
                raise RuntimeError(
                    f"本地 Embedding 模型不存在：{self.settings.embedding_model}。"
                    f"当前工作目录：{Path.cwd()}，请从项目根目录 d:\\WebNovel 启动程序。"
                )
            embeddings = HuggingFaceEmbeddings(
                model_name=self.settings.embedding_model,
                model_kwargs={"device": self.settings.embedding_device},
                encode_kwargs={"normalize_embeddings": True},
            )
            self._vectorstore = Chroma(
                collection_name=self.settings.chroma_collection,
                embedding_function=embeddings,
                persist_directory=str(self.settings.chroma_dir),
            )
        return self._vectorstore

    def _get_llm(self) -> ChatGoogleGenerativeAI:
        if self._llm is None:
            self._llm = ChatGoogleGenerativeAI(
                model=self.settings.gemini_model,
                google_api_key=self._require_api_key(),
                temperature=0.8,
                max_output_tokens=4096,
                transport="rest",  # 走 REST/requests 而非 gRPC，才能使用 HTTP(S)_PROXY
            )
        return self._llm

    def _get_raw_collection(self) -> Any:
        import chromadb

        client = chromadb.PersistentClient(path=str(self.settings.chroma_dir))
        return client.get_or_create_collection(name=self.settings.chroma_collection)

    @staticmethod
    def _decode(content: bytes) -> str:
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("TXT 文件无法按 UTF-8 或 GB18030 解码。")

    def index_text(self, filename: str, content: bytes) -> IndexedDocument:
        if not filename.lower().endswith(".txt"):
            raise ValueError("目前只支持 .txt 文件。")
        text = self._decode(content).strip()
        if not text:
            raise ValueError("上传的 TXT 文件没有可索引的正文。")

        document_id = uuid4().hex
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
        chunks = splitter.create_documents(
            [text],
            metadatas=[{"document_id": document_id, "filename": filename}],
        )
        ids = [f"{document_id}:{index}" for index in range(len(chunks))]
        vectorstore = self._get_vectorstore()
        batch_size = max(1, min(self.settings.chroma_batch_size, 166))
        try:
            for start in range(0, len(chunks), batch_size):
                vectorstore.add_documents(
                    chunks[start : start + batch_size],
                    ids=ids[start : start + batch_size],
                )
        except Exception:
            self._delete_document_chunks(document_id)
            raise
        return IndexedDocument(document_id=document_id, filename=filename, chunks=len(chunks))

    def list_documents(self) -> List[Dict[str, Any]]:
        result = self._get_raw_collection().get(include=["metadatas"])
        documents: Dict[str, Dict[str, Any]] = {}
        for metadata in result.get("metadatas", []):
            if not metadata or not metadata.get("document_id"):
                continue
            document_id = metadata["document_id"]
            item = documents.setdefault(
                document_id,
                {
                    "document_id": document_id,
                    "filename": metadata.get("filename", ""),
                    "name": Path(metadata.get("filename", "")).stem,
                    "chunks": 0,
                },
            )
            item["chunks"] += 1
        return list(documents.values())

    def _delete_document_chunks(self, document_id: str) -> None:
        collection = self._get_raw_collection()
        result = collection.get(where={"document_id": document_id}, include=["metadatas"])
        ids = result.get("ids") or []
        batch_size = max(1, min(self.settings.chroma_batch_size, 166))
        for start in range(0, len(ids), batch_size):
            collection.delete(ids=ids[start : start + batch_size])

    def delete_document(self, document_id: str) -> None:
        self._delete_document_chunks(document_id)

    def list_samples(self) -> List[Dict[str, Any]]:
        return [sample.__dict__.copy() for sample in self._sample_store.list()]

    def add_sample(self, filename: str, content: bytes) -> Dict[str, Any]:
        if not filename.lower().endswith(".txt"):
            raise ValueError("目前只支持 .txt 文件。")
        if not self._decode(content).strip():
            raise ValueError("上传的样本 TXT 文件没有可分析的正文。")
        return self._sample_store.add(filename, content).__dict__.copy()

    def index_sample(self, sample_id: str) -> Dict[str, Any]:
        sample = self._sample_store.get(sample_id)
        if sample is None:
            raise ValueError("样本文件不存在或已经被删除。")
        if sample.corpus_id:
            raise ValueError("这个样本已经生成过语料库，无需重复生成。")
        indexed = self.index_text(sample.filename, self._sample_store.read_content(sample_id))
        self._sample_store.set_corpus(sample_id, indexed.document_id, indexed.chunks)
        return {
            "sample_id": sample_id,
            "document_id": indexed.document_id,
            "filename": indexed.filename,
            "chunks": indexed.chunks,
        }

    def delete_sample(self, sample_id: str) -> None:
        if not self._sample_store.delete(sample_id):
            raise ValueError("样本文件不存在或已经被删除。")

    @staticmethod
    def _sample_text(text: str, target_chars: int = 18000) -> str:
        text = text.strip()
        if len(text) <= target_chars:
            return text
        window_count = 6
        window_size = target_chars // window_count
        max_start = len(text) - window_size
        starts = [round(max_start * index / (window_count - 1)) for index in range(window_count)]
        windows = []
        for start in starts:
            end = min(len(text), start + window_size)
            if start > 0:
                boundary = text.find("\n", start, min(end, start + 200))
                if boundary != -1:
                    start = boundary + 1
            windows.append(text[start:end].strip())
        return "\n\n--- 样本片段 ---\n\n".join(windows)

    def list_styles(self) -> List[Dict[str, Any]]:
        return [style.__dict__.copy() for style in self._style_store.list()]

    def delete_style(self, style_id: str) -> None:
        if not self._style_store.delete(style_id):
            raise ValueError("文风模板不存在或已经被删除。")

    def _get_document_text(self, document_id: str) -> Dict[str, str]:
        result = self._get_vectorstore()._collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        documents = result.get("documents") or []
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        if not documents:
            raise ValueError("找不到这份语料，可能已被删除。")

        parts = sorted(zip(ids, documents), key=lambda item: item[0])
        filename = next(
            (metadata.get("filename", "") for metadata in metadatas if metadata),
            "未知文件",
        )
        return {"filename": filename, "text": "\n\n".join(part[1] for part in parts)}

    @staticmethod
    def _parse_style_response(content: Any) -> Dict[str, str]:
        raw = content if isinstance(content, str) else str(content)
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("Gemini 没有返回可解析的文风模板。")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError("Gemini 返回的文风模板不是有效 JSON。") from exc
        required_fields = ("name", "description", "instructions")
        if any(not str(parsed.get(field, "")).strip() for field in required_fields):
            raise ValueError("文风模板缺少名称、描述或写作规则。")
        return {field: str(parsed[field]).strip() for field in required_fields}

    def extract_style(self, sample_id: str) -> Dict[str, Any]:
        sample_record = self._sample_store.get(sample_id)
        if sample_record is None:
            raise ValueError("样本文件不存在或已经被删除。")
        sample = self._sample_text(self._decode(self._sample_store.read_content(sample_id)))
        prompt = f"""你是一名中文网络小说文风分析师。请分析下面的小说原文，提炼出可复用的写作风格模板。

只返回一个 JSON 对象，不要 Markdown 代码块，不要额外解释。JSON 必须包含：
- name：简短、有辨识度的中文文风名称
- description：不超过 80 字的风格概述
- instructions：给后续写作者使用的具体写作规则，包含叙事视角、句式节奏、用词、对话、环境/心理描写等

样本文件名：{sample_record.filename}
原文样本：
{sample}
"""
        response = self._get_llm().invoke(prompt)
        parsed = self._parse_style_response(response.content)
        style = self._style_store.add(
            name=parsed["name"],
            description=parsed["description"],
            instructions=parsed["instructions"],
            source_sample_id=sample_id,
            source_filename=sample_record.filename,
        )
        return style.__dict__.copy()

    def generate(
        self,
        instruction: str,
        k: Optional[int] = None,
        style_id: Optional[str] = None,
        corpus_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("扩写指令不能为空。")

        style: Optional[StyleTemplate] = None
        if style_id:
            style = self._style_store.get(style_id)
            if style is None:
                raise ValueError("所选文风模板不存在或已经被删除。")

        search_kwargs: Dict[str, Any] = {"k": k or self.settings.retrieval_k}
        if corpus_id:
            search_kwargs["filter"] = {"document_id": corpus_id}
        documents = self._get_vectorstore().similarity_search(instruction, **search_kwargs)
        if not documents:
            raise ValueError("当前选择的语料库没有可用片段，请先上传或选择其他语料。")

        context = "\n\n--- 相关原文片段 ---\n\n".join(
            f"[{index + 1}] {document.page_content}"
            for index, document in enumerate(documents)
        )
        style_prompt = (
            f"当前文风模板：{style.name}\n{style.description}\n\n文风执行规则：\n{style.instructions}"
            if style
            else "当前未选择文风模板。请自然遵循检索原文的语言风格。"
        )
        prompt = f"""你是一名中文网络小说编辑和续写作者。请严格依据给出的原文片段，完成用户的情节扩写指令。

要求：
1. 保持人物性格、世界观、叙事视角和已有设定一致。
2. 不要编造与原文冲突的设定；如果信息不足，用自然的文学表达补足细节。
3. 输出连贯的小说正文，不要解释过程，不要列提纲，不要重复用户指令。
4. 适当补充动作、环境、对话和心理描写，让情节有推进。

{style_prompt}

用户的扩写指令：
{instruction}

检索到的原文片段：
{context}
"""
        response = self._get_llm().invoke(prompt)
        answer = response.content if isinstance(response.content, str) else str(response.content)
        sources = [
            {
                "filename": document.metadata.get("filename", "未知文件"),
                "document_id": document.metadata.get("document_id", ""),
                "preview": document.page_content[:160],
            }
            for document in documents
        ]
        return {"answer": answer, "sources": sources}
