FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERRA_HOST=0.0.0.0 \
    SERRA_PORT=8765 \
    TZ=Europe/Madrid \
    SERRA_COOKIE_SECURE=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --create-home serra \
    && mkdir -p /app/data /app/logs \
    && chown -R serra:serra /app
COPY --chown=serra:serra local_training_app.py connect_chatgpt.py ./
COPY --chown=serra:serra app ./app
COPY container_entrypoint.py ./container_entrypoint.py
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8765')+'/api/health', timeout=2)"
CMD ["python", "container_entrypoint.py"]

