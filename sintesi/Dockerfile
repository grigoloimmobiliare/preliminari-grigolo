# Immagine del programma "Sintesi immobili".
# Si costruisce dalla cartella principale del repository (usa anche i moduli di app/):
#     docker compose -f sintesi/docker-compose.yml up -d --build   (oppure sintesi/installa.sh)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SINTESI_DATI=/dati \
    HOME=/tmp \
    TZ=Europe/Rome

# Tesseract serve solo se arriva un PDF scansionato (senza testo); DejaVu per gli accenti nel PDF
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-ita fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /programma
COPY sintesi/requirements.txt ./requirements-sintesi.txt
RUN pip install --no-cache-dir -r requirements-sintesi.txt
COPY app ./app
COPY sintesi ./sintesi

EXPOSE 8081
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/salute')"
CMD ["uvicorn", "sintesi.main:app", "--host", "0.0.0.0", "--port", "8081"]
