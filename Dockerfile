FROM denoland/deno:bin AS deno
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    HOME=/home/karaoke \
    PYGAME_HIDE_SUPPORT_PROMPT=1 \
    KARAOKE_DATA_DIR=/data \
    IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=deno /deno /usr/local/bin/deno

WORKDIR /app
COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt 'yt-dlp[default]'
COPY karaoke_terminal.py karaoke_web.py studio_store.py media_store.py ./
RUN useradd --create-home karaoke && mkdir /data && chown karaoke:karaoke /data
# psycopg-binary bundles OpenSSL, which may not locate Debian's CA bundle automatically.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
EXPOSE 8000
# shortcut: una instancia con disco compartido local; usar object storage antes de escalar a varios servidores.
CMD ["sh", "-c", "mkdir -p \"$KARAOKE_DATA_DIR\" && chown karaoke:karaoke \"$KARAOKE_DATA_DIR\" && python studio_store.py && exec gunicorn --bind 0.0.0.0:${PORT:-8000} --user karaoke --group karaoke --workers 1 --threads 4 --timeout 900 --access-logfile - --error-logfile - karaoke_web:app"]
