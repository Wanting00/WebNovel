import os
from typing import Any, Dict

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="织梦台 · AI 网文扩写", page_icon="✦", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #f6f3ed; }
    .block-container { max-width: 1180px; padding-top: 2rem; }
    h1, h2, h3 { color: #18251f; letter-spacing: -0.02em; }
    .hero { padding: 1.2rem 0 1.5rem; border-bottom: 1px solid #d8d2c5; margin-bottom: 1.5rem; }
    .hero p { color: #617067; font-size: 1.05rem; }
    .source { border-left: 3px solid #b87945; padding: .4rem .8rem; margin: .5rem 0; background: #fffdf9; }
    </style>
    """,
    unsafe_allow_html=True,
)


def request_json(method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=120, **kwargs)
        data = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"无法连接后端 {API_URL}：{exc}") from exc
    if not response.ok:
        raise RuntimeError(data.get("detail", response.text))
    return data


st.markdown(
    '<div class="hero"><h1>织梦台</h1><p>把已有世界观交给检索，把下一幕交给灵感。</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    selected_sample_id = None
    st.subheader("样本区")
    sample_file = st.file_uploader("上传 TXT 样本", type=["txt"], key="sample-uploader")
    if sample_file is not None and st.button("保存到样本区", use_container_width=True):
        try:
            result = request_json(
                "POST",
                "/samples/upload",
                files={"file": (sample_file.name, sample_file.getvalue(), "text/plain")},
            )
            st.success(f"已保存样本：{result['filename']}")
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))

    try:
        samples = request_json("GET", "/samples").get("samples", [])
        if samples:
            sample_options = {
                f"{sample['filename']} · {sample['size_bytes'] / 1024:.1f} KB": sample["sample_id"]
                for sample in samples
            }
            selected_sample_name = st.selectbox("选择样本文件", list(sample_options.keys()))
            selected_sample_id = sample_options[selected_sample_name]
            selected_sample = next(
                sample for sample in samples if sample["sample_id"] == selected_sample_id
            )
            sample_col1, sample_col2, sample_col3 = st.columns(3)
            if sample_col1.button(
                "生成语料",
                type="primary",
                use_container_width=True,
                disabled=bool(selected_sample.get("corpus_id")),
            ):
                try:
                    result = request_json("POST", f"/samples/{selected_sample_id}/index")
                    st.success(f"已生成语料：{result['chunks']} 段")
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
            if sample_col2.button("生成文风", type="primary", use_container_width=True):
                try:
                    request_json("POST", f"/styles/extract/{selected_sample_id}")
                    st.success("文风模板已保存")
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
            if sample_col3.button("删除样本", use_container_width=True):
                try:
                    request_json("DELETE", f"/samples/{selected_sample_id}")
                    st.success("样本已删除")
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
        else:
            st.caption("上传 TXT 后，在这里选择并生成语料或文风")
    except RuntimeError as exc:
        st.error(str(exc))

    st.divider()
    st.subheader("语料库")
    selected_style_id = None
    selected_corpus_id = None
    st.caption(f"后端地址：{API_URL}")
    try:
        health = request_json("GET", "/health")
        st.success("后端在线")
        if not health.get("gemini_configured"):
            st.warning("后端尚未配置 GOOGLE_API_KEY")
    except RuntimeError as exc:
        st.error(str(exc))

    st.subheader("已入库文档")
    try:
        documents = request_json("GET", "/documents").get("documents", [])
        if not documents:
            st.caption("还没有语料")
        else:
            corpus_options = {
                f"{document['name']} · {document['chunks']} 段 · {document['document_id'][:8]}": document["document_id"]
                for document in documents
            }
            selected_corpus_name = st.selectbox("选择当前语料库", list(corpus_options.keys()))
            selected_corpus_id = corpus_options[selected_corpus_name]
            selected_corpus = next(
                document
                for document in documents
                if document["document_id"] == selected_corpus_id
            )
            st.caption("后续检索和文风提炼只使用当前选中的语料库")
            if st.button("删除语料库", use_container_width=True):
                try:
                    request_json("DELETE", f"/documents/{selected_corpus_id}")
                    st.success(f"已删除 {selected_corpus['filename']}")
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
    except RuntimeError as exc:
        st.error(str(exc))

    st.subheader("文风模板")
    try:
        styles = request_json("GET", "/styles").get("styles", [])
        style_options = {"不指定文风": None}
        for style in styles:
            style_options[f"{style['name']} · {style['source_filename']}"] = style["style_id"]
        selected_style_name = st.selectbox("选择扩写文风", list(style_options.keys()))
        selected_style_id = style_options[selected_style_name]
        selected_style = next(
            (style for style in styles if style["style_id"] == selected_style_id),
            None,
        )
        if selected_style:
            st.caption(selected_style["description"])
            if st.button("删除当前文风模板", key="delete-selected-style"):
                request_json("DELETE", f"/styles/{selected_style_id}")
                st.rerun()
        if not styles:
            st.caption("上传语料后点击“生成文风模板”")
    except RuntimeError as exc:
        st.error(str(exc))

st.subheader("下一幕写什么？")
instruction = st.text_area(
    "情节指令",
    height=180,
    placeholder="例如：沈砚在雨夜回到旧宅，发现墙上的家族画像少了一个人。请扩写这一幕，约 800 字，保持第三人称限知视角。",
    label_visibility="collapsed",
)
col1, col2 = st.columns([1, 5])
with col1:
    retrieval_k = st.number_input("检索片段数", min_value=1, max_value=20, value=5)
with col2:
    st.write("")
    generate_clicked = st.button("开始扩写", type="primary", use_container_width=True)

if generate_clicked:
    if not selected_corpus_id:
        st.warning("请先选择一个语料库。")
    elif not instruction.strip():
        st.warning("请先输入情节指令。")
    else:
        with st.spinner("正在检索世界观并续写..."):
            try:
                result = request_json(
                    "POST",
                    "/generate",
                    json={
                        "instruction": instruction,
                        "k": retrieval_k,
                        "style_id": selected_style_id,
                        "corpus_id": selected_corpus_id,
                    },
                )
                st.divider()
                st.subheader("扩写结果")
                st.write(result["answer"])
                with st.expander("查看本次引用的原文片段"):
                    for source in result.get("sources", []):
                        st.markdown(
                            f"<div class='source'><strong>{source['filename']}</strong><br>{source['preview']}</div>",
                            unsafe_allow_html=True,
                        )
            except RuntimeError as exc:
                st.error(str(exc))
