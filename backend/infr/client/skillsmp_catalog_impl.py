from __future__ import annotations

import logging
import os
import re
import time

import httpx

from domain.market.acl.marketplace_catalog import (
    RemoteSkill,
    RemoteSkillPage,
    SkillMarketplaceCatalog,
)
from domain.market.model.market_categories import MarketplaceSort
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)

_DEFAULT_SEARCH_URL = "https://skillsmp.com/api/v1/skills/search"
# SkillsMP requires a non-empty keyword; "a" matches virtually every skill, so
# combined with sortBy it approximates a "browse most popular" listing.
_BROWSE_ALL_KEYWORD = "a"
_CACHE_TTL_SECONDS = 300
_CACHE_MAX_KEYS = 64
_REQUEST_TIMEOUT_SECONDS = 20.0
_GITHUB_TREE_URL = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:tree|blob)/(?P<rest>.+)$"
)


class SkillsmpCatalog(SkillMarketplaceCatalog):
    """Browses the open-source SkillsMP marketplace (aggregated GitHub SKILL.md files).

    Search results carry repository star counts; the SKILL.md content itself is
    fetched from raw.githubusercontent.com on `get_skill`.
    """

    def __init__(self, search_url: str | None = None) -> None:
        self._search_url = search_url or os.environ.get("SKILL_MARKETPLACE_URL") or _DEFAULT_SEARCH_URL
        self._cache: dict[tuple, tuple[float, RemoteSkillPage]] = {}

    async def search(
        self,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 30,
        sort: MarketplaceSort = MarketplaceSort.STARS,
    ) -> RemoteSkillPage:
        cache_key = (keyword or "", page, limit, sort.value)
        cached = self._cache.get(cache_key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]

        params = {
            "q": keyword or _BROWSE_ALL_KEYWORD,
            "page": max(page, 1),
            "limit": min(limit, 50),
            "sortBy": "recent" if sort is MarketplaceSort.RECENT else "stars",
        }
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS, headers=self._headers()) as client:
                response = await client.get(self._search_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("Skill marketplace request failed: %s", self._search_url, exc_info=True)
            raise BusinessException("Skill marketplace is unavailable, please retry later")

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise BusinessException("Skill marketplace returned an unexpected response")
        pagination = data.get("pagination") or {}
        result = RemoteSkillPage(
            items=tuple(
                skill
                for item in data.get("skills", [])
                if isinstance(item, dict) and (skill := self._to_remote_skill(item)) is not None
            ),
            total=int(pagination.get("total") or 0),
            has_next=bool(pagination.get("hasNext")),
        )
        if len(self._cache) >= _CACHE_MAX_KEYS:
            self._cache.clear()
        self._cache[cache_key] = (time.monotonic() + _CACHE_TTL_SECONDS, result)
        return result

    async def get_skill(self, ref: str) -> RemoteSkill | None:
        raw_url = self._to_raw_content_url(ref)
        if raw_url is None:
            return None
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = await client.get(raw_url)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                content = response.text
        except httpx.HTTPError:
            logger.warning("Skill content fetch failed: %s", raw_url, exc_info=True)
            raise BusinessException("Skill marketplace is unavailable, please retry later")
        frontmatter = self._parse_frontmatter(content)
        name = frontmatter.get("name") or ref.rstrip("/").rsplit("/", 1)[-1].removesuffix(".md")
        return RemoteSkill(
            ref=ref,
            name=name,
            display_name=name,
            description=frontmatter.get("description", ""),
            content=content,
            repo_url=ref,
            author=ref.removeprefix("https://github.com/").split("/", 1)[0],
        )

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {"Accept": "application/json"}
        api_key = os.environ.get("SKILLSMP_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def _to_remote_skill(item: dict) -> RemoteSkill | None:
        github_url = str(item.get("githubUrl") or "")
        name = str(item.get("name") or "")
        if not github_url or not name:
            return None
        return RemoteSkill(
            ref=github_url,
            name=name,
            display_name=name,
            description=str(item.get("description") or ""),
            content="",
            repo_url=github_url,
            author=str(item.get("author") or ""),
            stars=int(item.get("stars") or 0),
        )

    @staticmethod
    def _to_raw_content_url(ref: str) -> str | None:
        match = _GITHUB_TREE_URL.match(ref.rstrip("/"))
        if match is None:
            return None
        rest = match.group("rest")
        if not rest.endswith("SKILL.md"):
            rest = f"{rest}/SKILL.md"
        return f"https://raw.githubusercontent.com/{match.group('owner')}/{match.group('repo')}/{rest}"

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, str]:
        """Extract single-line 'key: value' pairs from a leading YAML frontmatter block."""
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}
        fields: dict[str, str] = {}
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, separator, value = line.partition(":")
            if separator and key.strip() and not key.startswith((" ", "\t")):
                fields[key.strip()] = value.strip().strip("'\"")
        return fields
