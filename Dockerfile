FROM python:3.12-slim

WORKDIR /workspace

# DejaVu Sans gives the PDF export full Unicode coverage; Comic Neue is the friendlier face used
# for titles and captions in the coloring book.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-comic-neue \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY config/ config/

EXPOSE 8502

CMD ["streamlit", "run", "app/main.py", "--server.port=8502", "--server.address=0.0.0.0", "--server.headless=true"]
