FROM nikolaik/python-nodejs:python3.12-nodejs22-slim

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI
RUN npm config set registry https://registry.npmmirror.com && npm install -g @anthropic-ai/claude-code

# uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Non-root user — Claude CLI refuses --dangerously-skip-permissions as root
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser \
    && chown -R appuser:appuser /app \
    && mkdir -p /home/appuser/velpos /home/appuser/.claude /home/appuser/.ssh \
    && chown -R appuser:appuser /home/appuser/velpos /home/appuser/.claude /home/appuser/.ssh \
    && chmod 700 /home/appuser/.ssh
USER appuser
ENV HOME=/home/appuser
ENV PATH="/app/.venv/bin:/home/appuser/.local/bin:$PATH"

# Default git identity so commits work out-of-the-box
RUN git config --global user.name "Velpos" && git config --global user.email "velpos@local"

EXPOSE 8083

CMD ["sh", "-c", "\
  if [ ! -f \"$HOME/.claude/plugins/known_marketplaces.json\" ]; then \
    timeout 15 claude plugin list 2>/dev/null || true; \
    timeout 10 claude plugin marketplace add anthropics/claude-plugins-official 2>/dev/null || true; \
    timeout 10 claude plugin marketplace add anthropics/skills 2>/dev/null || true; \
  fi && \
  exec uv run uvicorn main:app --host 0.0.0.0 --port 8083 --log-level info"]
