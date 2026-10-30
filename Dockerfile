FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Keep the SQLite file in a volume-friendly folder and run as a non-root user.
RUN mkdir -p /data && useradd --create-home appuser && chown -R appuser /data /srv
ENV DATABASE=/data/monitor.db
USER appuser

EXPOSE 5000

# One worker on purpose: the collector thread is started once per process,
# so multiple workers would collect duplicate samples.
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:5000", "run:app"]
