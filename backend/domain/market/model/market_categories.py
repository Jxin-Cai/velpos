from __future__ import annotations

from enum import Enum


class EntrySource(str, Enum):
    """Where a market entry came from: created by hand or pulled from an open-source marketplace."""

    CUSTOM = "custom"
    MARKETPLACE = "marketplace"


class MarketplaceSort(str, Enum):
    """Sort order when browsing an open-source marketplace."""

    STARS = "stars"
    DOWNLOADS = "downloads"
    RECENT = "recent"


class McpTransport(str, Enum):
    """Transport protocol of an MCP server."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class McpCategory(str, Enum):
    """Category taxonomy for MCP server entries (aligned with awesome-mcp-servers)."""

    SEARCH = "search"
    BROWSER_AUTOMATION = "browser-automation"
    DATABASE = "database"
    DEVELOPER_TOOLS = "developer-tools"
    FILE_SYSTEM = "file-system"
    CLOUD_PLATFORM = "cloud-platform"
    COMMUNICATION = "communication"
    KNOWLEDGE_MEMORY = "knowledge-memory"
    MONITORING = "monitoring"
    SECURITY = "security"
    FINANCE = "finance"
    MEDIA = "media"
    PRODUCTIVITY = "productivity"
    AI_SERVICE = "ai-service"
    OTHER = "other"


class SkillCategory(str, Enum):
    """Category taxonomy for skill entries."""

    DOCUMENT = "document"
    DEVELOPMENT = "development"
    DATA_ANALYSIS = "data-analysis"
    CREATIVE_DESIGN = "creative-design"
    OFFICE_AUTOMATION = "office-automation"
    RESEARCH = "research"
    COMMUNICATION = "communication"
    OTHER = "other"
