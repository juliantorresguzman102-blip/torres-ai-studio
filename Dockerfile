FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg espeak-ng fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server.py /app/server.py
RUN pip install --no-cache-dir 'Pillow>=10,<14'
ENV PORT=10000
EXPOSE 10000
CMD ["python", "-u", "server.py"]
