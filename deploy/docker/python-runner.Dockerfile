# Build from the repository root. PYTHON_BASE_IMAGE must be an immutable digest ref.
ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONNOUSERSITE=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    HOME=/tmp

WORKDIR /workspace

COPY requirements.txt /tmp/evo-agent-requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      -r /tmp/evo-agent-requirements.txt \
      pytest==8.3.5 \
    && rm -f /tmp/evo-agent-requirements.txt

# Runtime invocation overrides the user explicitly, but the image itself is non-root too.
USER 65532:65532
ENTRYPOINT []
