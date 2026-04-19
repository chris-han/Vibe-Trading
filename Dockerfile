# ============================================================================
# Stage 1: Use prebuilt frontend assets from the local repo context
# ============================================================================
FROM scratch AS frontend-build

COPY frontend/dist/ /app/frontend/dist/

# ============================================================================
# Stage 2: Python runtime
# ============================================================================
FROM python:3.11-slim AS runtime

# System proxy configuration (uses build args for mirror/proxy support)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PIP_DEFAULT_TIMEOUT=1000 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    no_proxy=${NO_PROXY}

WORKDIR /app

ENV VIRTUAL_ENV=/app/agent/.venv \
    PATH="/app/agent/.venv/bin:${PATH}"

# Python deps (install before copying code for layer caching)
RUN mkdir -p /app/agent && python -m venv /app/agent/.venv
COPY agent/requirements.txt agent/requirements.txt
RUN pip install --no-cache-dir --trusted-host ${PIP_TRUSTED_HOST} \
    $(if [ -n "$HTTP_PROXY" ]; then echo "--proxy=$HTTP_PROXY"; fi) \
    -r agent/requirements.txt

# Copy project
COPY pyproject.toml LICENSE README.md ./
COPY agent/.hermes/ /app/bootstrap/hermes/
COPY agent/ agent/
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh && mkdir -p /app/agent/.hermes /app/workspaces/public

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist frontend/dist

# Install CLI entrypoint
RUN pip install --no-cache-dir -e .

# Default port
EXPOSE 8899

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8899/health')" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run API server (serves frontend/dist as static files)
CMD ["vibe-trading", "serve", "--host", "0.0.0.0", "--port", "8899"]
