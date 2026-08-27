# Cloud Run image for the governed fleet demo.
#
# Why this file exists rather than `adk deploy cloud_run`
# -------------------------------------------------------
# `adk deploy cloud_run` generates a Dockerfile at deploy time and hands it to
# Cloud Build. That is convenient, but the generated file makes three choices
# that are wrong for this project:
#
#   1. `FROM python:3.11-slim`. This package requires Python 3.12, so pip
#      refuses to install it — the build fails before anything runs.
#   2. `ENV GOOGLE_CLOUD_LOCATION=<--region>`. It reuses the Cloud Run region as
#      the Vertex location, so deploying to us-central1 sets the Vertex location
#      to us-central1 — where `gemini-3.5-flash` returns HTTP 404. The service
#      would deploy green and fail on the first message.
#   3. `pip install -r requirements.txt` in a slim image, which has no git, so a
#      `git+https://` dependency cannot resolve.
#
# Writing the image directly fixes all three and removes the network fetch of
# our own package entirely: the source is copied in and installed from disk.

FROM python:3.12-slim

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

# Vertex, not the Gemini API. `global` is not interchangeable with the Cloud Run
# region: gemini-3.5-flash resolves only on `global` and 404s in us-central1,
# while gemini-2.5-flash works in both — so getting this wrong fails late.
ENV GOOGLE_GENAI_USE_ENTERPRISE=true \
    GOOGLE_CLOUD_LOCATION=global \
    ADK_HARNESS_WORKSPACE=/workspace \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir ".[tracing]"

# ADK expects an agents directory holding one folder per agent. Both are
# served by one container: /fleet governs coding harnesses, /workspace
# governs Google Calendar. Same gate, same audit trail.
COPY --chown=appuser:appuser examples/fleet/ /app/agents/fleet/
COPY --chown=appuser:appuser examples/workspace/ /app/agents/workspace/

USER appuser

# Cloud Run supplies PORT; 8080 is its default and the local fallback.
ENV PORT=8080
EXPOSE 8080

CMD exec adk api_server --with_ui --host=0.0.0.0 --port=${PORT} \
    --session_service_uri=memory:// --artifact_service_uri=memory:// \
    --trace_to_cloud /app/agents
