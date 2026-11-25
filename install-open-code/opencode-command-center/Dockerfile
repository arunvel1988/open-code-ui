FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates bash git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m -u 10001 appuser && mkdir -p /app/data /workspace && chown -R appuser:appuser /app /workspace
USER appuser
ENV HOME=/home/appuser PYTHONUNBUFFERED=1
EXPOSE 5000
CMD ["gunicorn","--bind","0.0.0.0:5000","--workers","1","--threads","8","--timeout","240","app:app"]
