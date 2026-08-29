# Cloud Run demo: install local sources with Python 3.12.

FROM python:3.12-slim

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

# Keep the Vertex model location separate from the Cloud Run region.
ENV GOOGLE_GENAI_USE_ENTERPRISE=true \
    GOOGLE_CLOUD_LOCATION=global \
    ADK_HARNESS_WORKSPACE=/workspace \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY plugins/antigravity/ ./plugins/antigravity/
# The wheel takes the generated approval bundle from here.
COPY ui/approval/ ./ui/approval/
RUN pip install --no-cache-dir "."

# ADK loads one agent per directory.
COPY --chown=appuser:appuser examples/agents/workspace/ /app/agents/workspace/

USER appuser

# Cloud Run supplies PORT; 8080 is its default and the local fallback.
ENV PORT=8080
EXPOSE 8080

CMD exec adk api_server --with_ui --host=0.0.0.0 --port=${PORT} \
    --session_service_uri=memory:// --artifact_service_uri=memory:// \
    --trace_to_cloud /app/agents
