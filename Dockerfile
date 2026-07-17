FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-cache --no-dev --no-install-project --compile-bytecode
COPY api /app/api
COPY app.py /app/app.py
COPY log_config.yaml /app/log_config.yaml
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-dev

FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer-nogui \
    libreoffice-impress-nogui \
    fonts-dejavu-core \
    fonts-liberation \
  # Clean up apt caches and unused files
  #https://docs.docker.com/build/building/best-practices/#run
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/* /usr/share/locale/*

# Remove help files, galleries, and config XMLs to reduce size
#https://github.com/linuxserver/docker-libreoffice
RUN find /usr/lib/libreoffice/share -type d -name "help*" -exec rm -rf {} + || true \
 && find /usr/lib/libreoffice/share -type d -name "gallery" -exec rm -rf {} + || true \
 && find /usr/lib/libreoffice/share/config/ -type f -name "*.xcu" -delete || true

RUN mkdir -p /tmp && chmod 777 /tmp
ENV JAVA_HOME=""
COPY setup.sh /setup.sh
RUN chmod +x /setup.sh && /setup.sh
RUN groupadd --system --gid 1000 nonroot \
  && useradd --system --uid 1000 --gid nonroot --create-home nonroot
COPY --from=builder --chown=nonroot:nonroot /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER nonroot
WORKDIR /app
EXPOSE 8000
CMD ["python", "app.py"]
