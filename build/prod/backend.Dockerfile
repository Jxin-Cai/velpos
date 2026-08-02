ARG BACKEND_BASE_IMAGE=velpos-backend-base:local
FROM ${BACKEND_BASE_IMAGE}

COPY --chown=appuser:appuser . .

USER appuser
ENV HOME=/home/appuser
ENV PATH="/app/.venv/bin:/home/appuser/.local/bin:$PATH"

EXPOSE 8083

CMD ["sh", "-c", "\
  if [ ! -f \"$HOME/.claude/plugins/known_marketplaces.json\" ]; then \
    timeout 15 claude plugin list 2>/dev/null || true; \
    timeout 10 claude plugin marketplace add anthropics/claude-plugins-official 2>/dev/null || true; \
    timeout 10 claude plugin marketplace add anthropics/skills 2>/dev/null || true; \
  fi && \
  exec uv run uvicorn main:app --host 0.0.0.0 --port 8083 --log-level info"]
