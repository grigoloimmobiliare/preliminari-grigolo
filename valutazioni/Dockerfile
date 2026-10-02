FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VALUTAZIONI_DATI=/dati \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/tmp \
    TZ=Europe/Rome

WORKDIR /app
COPY requirements.txt .
# Chromium (con le sue librerie) serve per la ricerca sul sito OMI e la schermata del risultato
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata fonts-dejavu-core tesseract-ocr tesseract-ocr-ita \
    && pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*
COPY app ./app
COPY modelli ./modelli

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/salute')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
