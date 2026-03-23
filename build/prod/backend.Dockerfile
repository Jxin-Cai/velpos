FROM nikolaik/python-nodejs:python3.12-nodejs22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv lock && uv sync --frozen --no-dev

COPY . .

# Non-root user — Claude CLI refuses --dangerously-skip-permissions as root
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser \
    && chown -R appuser:appuser /app \
    && mkdir -p /data/projects /home/appuser/.claude /home/appuser/.ssh \
    && chown -R appuser:appuser /data/projects /home/appuser/.claude /home/appuser/.ssh \
    && chmod 700 /home/appuser/.ssh
USER appuser
ENV HOME=/home/appuser
ENV PATH="/app/.venv/bin:/home/appuser/.local/bin:$PATH"

# Default git identity so commits work out-of-the-box
RUN git config --global user.name "Velpos" && git config --global user.email "velpos@local"

EXPOSE 8083

CMD ["sh", "-c", "\
  if [ ! -f \"$HOME/.claude/plugins/known_marketplaces.json\" ]; then \
    claude plugin list 2>&1 || true; \
    claude plugin marketplace add anthropics/claude-plugins-official || true; \
    claude plugin marketplace add anthropics/skills || true; \
  fi && \
  exec uv run uvicorn main:app --host 0.0.0.0 --port 8083 --log-level info"]
