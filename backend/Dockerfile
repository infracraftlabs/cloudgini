FROM python:3.12-slim
ARG EXTRAS=gcp,ai
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install ".[${EXTRAS}]" && useradd --uid 10001 --no-create-home cloudgini
COPY alembic.ini ./
COPY alembic ./alembic
USER 10001
EXPOSE 8000
# One worker: the rate limiter and the simulated estate live in process memory.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers"]
