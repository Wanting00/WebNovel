# 织梦台：RAG AI 网文扩写工具

技术栈：Python 3.9、FastAPI、Streamlit、LangChain、Chroma、本地 Hugging Face Embeddings、Gemini API。

## 1. 安装

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，至少填写 `GOOGLE_API_KEY`。Gemini API Key 可从 Google AI Studio 创建。

## 2. 启动

在项目根目录打开两个终端：

```powershell
# 终端一：API
Set-Location d:\WebNovel
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 8000
```

```powershell
# 终端二：前端
Set-Location d:\WebNovel
.\.venv\Scripts\Activate.ps1
python -m streamlit run streamlit_app.py --server.port 8501
```

浏览器访问 <http://localhost:8501>。API 文档在 <http://localhost:8000/docs>。

Docker 部署时 Streamlit 不直接对外，由 nginx 监听 443 端口处理 HTTPS（自签名证书），详见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 3. 工作流

1. 在侧边栏样本区上传 `.txt` 文件，文件会保存到本地样本目录。
2. 选择样本后，可以点击“生成语料”将它切片、向量化并写入 `data/chroma`，也可以点击“生成文风”调用 Gemini 提炼模板。
3. 在“已入库文档”中选择当前语料库并删除它。
4. 输入情节指令，服务只在当前选中的语料库中用本地 Embeddings 检索相关片段。
5. 将检索片段连同写作约束发送给 Gemini，返回扩写正文和引用来源。

## 文风模板

在“样本区”上传用于模仿文风的原始 `.txt` 文件，选择样本后点击“生成文风模板”。系统会根据样本长度自动抽样：短文件使用全文，长文件从开头、前段、中段、后段和结尾均匀抽取多个窗口，再交给 Gemini 生成名称、风格概述和可执行的写作规则，并保存到 `data/style_templates.json`。

样本区和语料库相互独立：样本文件保存于 `data/samples`，只用于文风分析；语料库仍保存于 `data/chroma`，用于 RAG 检索。上传样本文件本身不调用 Gemini，也不会写入 Chroma。

语料库列表、选择、删除、语料切片和向量化都不需要调用 Gemini。语料上传时使用项目内 `models/paraphrase-multilingual-MiniLM-L12-v2` 生成向量并写入 Chroma；只有文风提炼和扩写需要 Gemini Key。

模型文件保存在项目内的 `models/paraphrase-multilingual-MiniLM-L12-v2`，运行时直接从本地目录加载，不再依赖 Hugging Face 网络访问。

模型、Chroma 和文风模板都使用相对路径；程序必须从 `d:\WebNovel` 项目根目录启动。模型路径 `./models/paraphrase-multilingual-MiniLM-L12-v2` 会相对于启动时的当前工作目录解析。

本地 Embedding 使用独立的 Chroma collection。旧版 Gemini Embeddings 生成的向量不能与新模型混用，需要用本地模型重新上传并索引语料。

扩写时可以在侧边栏下拉选择模板；模板会作为独立写作约束注入生成提示词。删除模板不会删除原始 TXT 的向量数据，删除原始文档也不会自动删除已经生成的模板。

## 配置项

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GEMINI_MODEL` | `gemini-2.5-flash` | 生成模型 |
| `EMBEDDING_MODEL` | `./models/paraphrase-multilingual-MiniLM-L12-v2` | 本地向量模型目录 |
| `EMBEDDING_DEVICE` | `cpu` | 本地向量化设备，可改为 `cuda` |
| `CHROMA_COLLECTION` | `web_novel_corpus_local` | 本地 Embedding 使用的 collection |
| `CHROMA_BATCH_SIZE` | `100` | Chroma 单批写入片段数，需低于版本限制 |
| `STYLE_TEMPLATES_FILE` | `./data/style_templates.json` | 文风模板持久化文件 |
| `CHUNK_SIZE` | `900` | 切片字符数 |
| `CHUNK_OVERLAP` | `150` | 切片重叠字符数 |
| `RETRIEVAL_K` | `5` | 默认检索数量 |
| `MAX_UPLOAD_MB` | `10` | 单文件上限 |


## 启动命令
后端：.venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
前端：.venv\Scripts\streamlit.exe run streamlit_app.py