# KungFu Chess — WebSocket game server
# Build from repo root:
#   docker build -t kungfu-chess-server .
# Run:
#   docker run --rm -p 8765:8765 kungfu-chess-server

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8765

WORKDIR /app

# Install dependencies first (better layer caching).
# --trusted-host: needed behind SSL-inspecting filters (e.g. NetFree).
COPY Server/requirements.txt /app/Server/requirements.txt
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    --trusted-host pypi.python.org \
    -r /app/Server/requirements.txt

# Server code + game engine packages it imports from project root
COPY Server/ /app/Server/
COPY engine/ /app/engine/
COPY model/ /app/model/
COPY rules/ /app/rules/
COPY realtime/ /app/realtime/
COPY chess_io/ /app/chess_io/
COPY controller/ /app/controller/
COPY exceptions.py /app/exceptions.py
COPY input.txt /app/input.txt

WORKDIR /app/Server

EXPOSE 8765

CMD ["python", "-u", "server.py"]
