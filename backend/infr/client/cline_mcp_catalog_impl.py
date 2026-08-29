from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

from domain.market.acl.marketplace_catalog import (
    McpMarketplaceCatalog,
    RemoteMcpServer,
    RemoteMcpServerPage,
)
from domain.market.model.market_categories import MarketplaceSort, McpTransport
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)

_DEFAULT_MARKETPLACE_URL = "https://api.cline.bot/v1/mcp/marketplace"
_DEFAULT_REGISTRY_URL = "https://registry.modelcontextprotocol.io"
_CACHE_TTL_SECONDS = 600
_REQUEST_TIMEOUT_SECONDS = 30.0


class ClineMcpMarketplaceCatalog(McpMarketplaceCatalog):
    """Browses the open-source Cline MCP marketplace (github stars + download counts).

    The marketplace API returns the full curated catalog in one call, so keyword
    filtering, popularity sorting and pagination happen locally over a TTL cache.
    Install config (command/args or remote url) is not part of the marketplace
    payload; `get_server` best-effort derives it from the official MCP Registry.
    """

    def __init__(self, marketplace_url: str | None = None, registry_url: str | None = None) -> None:
        self._marketplace_url = (
            marketplace_url or os.environ.get("MCP_MARKETPLACE_URL") or _DEFAULT_MARKETPLACE_URL
        )
        self._registry_url = (
            registry_url or os.environ.get("MCP_REGISTRY_URL") or _DEFAULT_REGISTRY_URL
        ).rstrip("/")
        self._cache: tuple[float, tuple[RemoteMcpServer, ...]] | None = None
        self._lock = asyncio.Lock()

    async def search(
        self,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 30,
        sort: MarketplaceSort = MarketplaceSort.STARS,
    ) -> RemoteMcpServerPage:
        catalog = await self._load_catalog()
        if keyword:
            needle = keyword.lower()
            catalog = [
                server
                for server in catalog
                if needle in server.name.lower()
                or needle in server.display_name.lower()
                or needle in server.description.lower()
                or needle in server.author.lower()
            ]
        if sort is MarketplaceSort.DOWNLOADS:
            catalog = sorted(catalog, key=lambda s: s.downloads, reverse=True)
        elif sort is MarketplaceSort.STARS:
            catalog = sorted(catalog, key=lambda s: s.stars, reverse=True)
        page = max(page, 1)
        start = (page - 1) * limit
        return RemoteMcpServerPage(
            items=tuple(catalog[start : start + limit]),
            total=len(catalog),
            has_next=start + limit < len(catalog),
        )

    async def get_server(self, ref: str) -> RemoteMcpServer | None:
        for server in await self._load_catalog():
            if server.ref == ref:
                transport, config = await self._derive_install_config(server)
                if not config:
                    return server
                return RemoteMcpServer(
                    ref=server.ref,
                    name=server.name,
                    display_name=server.display_name,
                    description=server.description,
                    version=server.version,
                    transport=transport,
                    server_config=config,
                    repo_url=server.repo_url,
                    homepage_url=server.homepage_url,
                    author=server.author,
                    logo_url=server.logo_url,
                    category=server.category,
                    stars=server.stars,
                    downloads=server.downloads,
                )
        return None

    async def _load_catalog(self) -> tuple[RemoteMcpServer, ...]:
        async with self._lock:
            if self._cache is not None and self._cache[0] > time.monotonic():
                return self._cache[1]
            try:
                async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                    response = await client.get(self._marketplace_url)
                    response.raise_for_status()
                    payload = response.json()
            except (httpx.HTTPError, ValueError):
                logger.warning("MCP marketplace request failed: %s", self._marketplace_url, exc_info=True)
                raise BusinessException("MCP marketplace is unavailable, please retry later")
            if not isinstance(payload, list):
                raise BusinessException("MCP marketplace returned an unexpected response")
            catalog = tuple(
                server
                for item in payload
                if isinstance(item, dict) and (server := self._to_remote_server(item)) is not None
            )
            self._cache = (time.monotonic() + _CACHE_TTL_SECONDS, catalog)
            return catalog

    @staticmethod
    def _to_remote_server(item: dict) -> RemoteMcpServer | None:
        ref = str(item.get("mcpId") or "")
        if not ref:
            return None
        name = ref.rsplit("/", 1)[-1]
        return RemoteMcpServer(
            ref=ref,
            name=name,
            display_name=str(item.get("name") or name),
            description=str(item.get("description") or ""),
            version="",
            transport=McpTransport.STDIO,
            server_config={},
            repo_url=str(item.get("githubUrl") or ""),
            homepage_url="",
            author=str(item.get("author") or ""),
            logo_url=str(item.get("logoUrl") or ""),
            category=str(item.get("category") or ""),
            stars=int(item.get("githubStars") or 0),
            downloads=int(item.get("downloadCount") or 0),
        )

    async def _derive_install_config(self, server: RemoteMcpServer) -> tuple[McpTransport, dict]:
        """Look the server up in the official MCP Registry to derive a runnable config."""
        owner_repo = server.repo_url.rstrip("/").removeprefix("https://github.com/")
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{self._registry_url}/v0/servers",
                    params={"search": owner_repo.rsplit("/", 1)[-1], "version": "latest", "limit": 20},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "MCP registry lookup failed, importing without install config: %s",
                server.ref,
                exc_info=True,
            )
            return McpTransport.STDIO, {}
        for raw in payload.get("servers", []) if isinstance(payload, dict) else []:
            detail = raw.get("server") or {}
            repository_url = str((detail.get("repository") or {}).get("url") or "").rstrip("/")
            if repository_url.removeprefix("https://github.com/").lower() == owner_repo.lower():
                return self._derive_client_config(detail)
        return McpTransport.STDIO, {}

    @staticmethod
    def _derive_client_config(server: dict) -> tuple[McpTransport, dict]:
        """Derive a runnable .mcp.json server object from registry packages/remotes metadata."""
        for package in server.get("packages") or []:
            registry_type = str(package.get("registryType") or "")
            identifier = str(package.get("identifier") or "")
            if not identifier:
                continue
            version = str(package.get("version") or "")
            env_vars = {
                str(var.get("name")): str(var.get("default") or "")
                for var in package.get("environmentVariables") or []
                if var.get("name")
            }
            config: dict | None = None
            if registry_type == "npm":
                spec = f"{identifier}@{version}" if version else identifier
                config = {"command": "npx", "args": ["-y", spec]}
            elif registry_type == "pypi":
                config = {"command": "uvx", "args": [identifier]}
            elif registry_type == "oci":
                config = {"command": "docker", "args": ["run", "-i", "--rm", identifier]}
            if config is not None:
                if env_vars:
                    config["env"] = env_vars
                return McpTransport.STDIO, config

        for remote in server.get("remotes") or []:
            url = str(remote.get("url") or "")
            if not url:
                continue
            remote_type = str(remote.get("type") or "")
            if remote_type == "sse":
                return McpTransport.SSE, {"url": url}
            return McpTransport.HTTP, {"url": url}

        return McpTransport.STDIO, {}
