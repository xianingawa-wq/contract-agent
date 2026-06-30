FROM python:3.12-slim AS builder

WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml README.md ./
COPY contract_agent ./contract_agent

RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AGENT_GRPC_PORT=50051 \
    VECTOR_BACKEND=faiss \
    KNOWLEDGE_VECTOR_STORE_DIR=/app/knowledge/ingested/laws_faiss

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY knowledge ./knowledge

RUN chown -R app:app /app
USER app

EXPOSE 50051

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, socket; port=int(os.environ.get('AGENT_GRPC_PORT', '50051')); s=socket.create_connection(('127.0.0.1', port), timeout=3); s.close()"

CMD ["python", "-m", "contract_agent.agent_rpc.server"]
