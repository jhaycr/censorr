# Censorr v2 — single Alpine image for both roles: `serve` (API) and `work` (pipeline worker).
# Validated 2026-07-16: all compiled deps (pydantic-core, rapidfuzz) ship musllinux wheels,
# so no build toolchain is needed in either stage; ffmpeg comes from apk.

# ---------- build: package the wheel ----------
FROM python:3.12-alpine AS build
WORKDIR /build
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md ./
COPY censorr ./censorr
RUN python -m build --wheel --outdir /dist

# ---------- runtime ----------
FROM python:3.12-alpine

# ffmpeg: worker's only system dependency. su-exec: drop root after fixing volume ownership.
RUN apk add --no-cache ffmpeg su-exec

RUN addgroup -g 1000 censorr && adduser -D -H -u 1000 -G censorr censorr

COPY --from=build /dist/*.whl /tmp/dist/
RUN pip install --no-cache-dir "$(ls /tmp/dist/*.whl)[serve]" && rm -rf /tmp/dist

RUN mkdir -p /app/queue /app/work /app/config && chown -R censorr:censorr /app
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["entrypoint.sh"]
CMD ["serve"]
