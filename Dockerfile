FROM python:3.12-slim

WORKDIR /workspace

# Andika (SIL), designed for children learning to read, is the typeface of the PDF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-sil-andika \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY config/ config/

EXPOSE 8502

CMD ["streamlit", "run", "app/main.py", "--server.port=8502", "--server.address=0.0.0.0", "--server.headless=true"]
