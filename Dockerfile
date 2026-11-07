# Ballast runner: Linux image with Pi (Node) + Python runtime.
FROM node:24-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-venv python-is-python3 git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

# Idle by default; jobs run via `fly ssh console -C` or `fly machine run ... -- <cmd>`.
CMD ["sleep", "infinity"]
