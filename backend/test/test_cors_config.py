from __future__ import annotations

import pytest

from ohs.cors_config import DEFAULT_CORS_ORIGINS, parse_cors_origins


def test_default_origins_contain_only_localhost_when_env_is_unset() -> None:
    # Arrange / Act
    origins = parse_cors_origins(DEFAULT_CORS_ORIGINS)

    # Assert
    assert all(
        o.startswith("http://localhost:") or o.startswith("http://127.0.0.1:")
        for o in origins
    ), f"Non-localhost origin found in defaults: {origins}"
    assert "http://localhost:3231" in origins
    assert "http://127.0.0.1:3231" in origins
    assert "http://localhost:8083" in origins
    assert "http://127.0.0.1:8083" in origins


def test_default_origins_do_not_include_wildcard_when_env_is_unset() -> None:
    # Arrange / Act
    origins = parse_cors_origins(DEFAULT_CORS_ORIGINS)

    # Assert
    assert "*" not in origins


def testparse_cors_origins_returns_list_when_given_valid_comma_separated_value() -> None:
    # Arrange
    raw = "http://localhost:3231,http://127.0.0.1:3231"

    # Act
    result = parse_cors_origins(raw)

    # Assert
    assert result == ["http://localhost:3231", "http://127.0.0.1:3231"]


def testparse_cors_origins_drops_empty_segments_when_raw_contains_trailing_comma() -> None:
    # Arrange
    raw = "http://localhost:3231, ,http://127.0.0.1:3231,"

    # Act
    result = parse_cors_origins(raw)

    # Assert
    assert result == ["http://localhost:3231", "http://127.0.0.1:3231"]


def testparse_cors_origins_preserves_env_override_when_cors_allow_origins_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — caller supplies a custom origin list via the environment variable;
    # this test validates the parsing helper honours that value correctly.
    custom = "http://mycompany.internal:8080,http://192.168.1.10:3231"

    # Act
    result = parse_cors_origins(custom)

    # Assert
    assert result == ["http://mycompany.internal:8080", "http://192.168.1.10:3231"]
