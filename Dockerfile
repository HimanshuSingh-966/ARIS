FROM python:3.11-slim

WORKDIR /app

# No .pyc written into the image layer, and stdout unbuffered so uvicorn's logs
# reach `docker logs` as they happen instead of sitting in a pipe buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# gcc used to be apt-installed here. Every dependency in requirements.txt ships a
# manylinux wheel, so nothing is compiled from source and the toolchain was pure
# image weight. If a future dependency has no wheel for this platform, pip fails
# with "command 'gcc' failed" — that, and only that, is the signal to restore:
#   RUN apt-get update && apt-get install -y --no-install-recommends gcc \
#       && rm -rf /var/lib/apt/lists/*

# Requirements before source: this layer is cached and re-runs only when the file
# itself changes, rather than on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# .dockerignore keeps .git, .venv and the three multi-MB master PDFs out of this —
# they were ~18MB of build context that the API never reads.
COPY . .

EXPOSE 8000

# No --reload. This is the production entrypoint, and reload runs a file-watching
# supervisor that restarts the app on any touch of the bind-mounted tree. Local
# development gets it from docker-compose's `command:` override instead.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
