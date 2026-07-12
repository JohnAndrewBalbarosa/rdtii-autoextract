FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY data ./data
COPY run.py .

ENV PYTHONPATH=/app/src
ENV ZETARIX_GROUNDING=few_shot
ENV ZETARIX_LLM_BACKEND=local
ENV OLLAMA_MODEL=llama3.1:latest

EXPOSE 8000
CMD ["uvicorn", "zetarix.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
