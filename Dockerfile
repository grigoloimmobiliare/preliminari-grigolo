FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRELIMINARI_DATI=/dati \
    HOME=/tmp \
    TZ=Europe/Rome

# Tesseract (OCR in italiano), LibreOffice Writer (conteggio pagine del Word generato)
# ed EB Garamond, usato al posto di Garamond per impaginare come in Word.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng \
        libreoffice-writer-nogui fonts-ebgaramond fontconfig tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY docker/garamond.conf /etc/fonts/conf.d/99-garamond.conf
RUN fc-cache -f

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY modelli ./modelli
COPY docs ./docs

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/salute')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
