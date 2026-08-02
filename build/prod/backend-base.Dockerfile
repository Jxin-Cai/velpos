FROM nikolaik/python-nodejs:python3.12-nodejs22-slim

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN npm config set registry https://registry.npmmirror.com \
    && npm install -g @anthropic-ai/claude-code

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && install -m 0755 /root/.local/bin/uv /usr/local/bin/uv

RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser \
    && mkdir -p /app /home/appuser/velpos /home/appuser/.claude /home/appuser/.ssh \
    && chown -R appuser:appuser /app /home/appuser/velpos /home/appuser/.claude /home/appuser/.ssh \
    && chmod 700 /home/appuser/.ssh

USER appuser
ENV HOME=/home/appuser
WORKDIR /app

COPY --chown=appuser:appuser pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --index-url https://pypi.tuna.tsinghua.edu.cn/simple

ENV PATH="/app/.venv/bin:/home/appuser/.local/bin:$PATH"

RUN git config --global user.name "Velpos" \
    && git config --global user.email "velpos@local"
