FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FASTEMBED_CACHE_PATH=/app/.fastembed
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py ./
COPY src ./src
COPY data/*.json ./data/
COPY chroma_db ./chroma_db
COPY .streamlit ./.streamlit
# 임베딩 모델을 이미지에 미리 받아 첫 기동 지연 제거
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit","run","app.py","--server.port=8501","--server.address=0.0.0.0"]
