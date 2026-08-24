"""IM 投递策略的环境变量注入测试."""

from __future__ import annotations

import pytest

from infr.config.im_delivery_config import ImDeliveryPolicy


def test_uses_defaults_when_env_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    for name in (
        "IM_DELIVERY_LEASE_SECONDS",
        "IM_DELIVERY_MAX_ATTEMPTS",
        "IM_DELIVERY_MAX_BACKOFF_SECONDS",
        "IM_INBOX_WORKERS",
        "IM_OUTBOX_WORKERS",
    ):
        monkeypatch.delenv(name, raising=False)

    # Act
    policy = ImDeliveryPolicy.from_env()

    # Assert
    assert policy == ImDeliveryPolicy()


def test_reads_value_when_env_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("IM_DELIVERY_MAX_ATTEMPTS", "3")

    # Act
    policy = ImDeliveryPolicy.from_env()

    # Assert
    assert policy.max_attempts == 3


def test_clamps_value_when_env_is_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("IM_OUTBOX_WORKERS", "999")

    # Act
    policy = ImDeliveryPolicy.from_env()

    # Assert
    assert policy.outbox_workers == 16


def test_falls_back_to_default_when_env_is_not_numeric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("IM_DELIVERY_LEASE_SECONDS", "not-a-number")

    # Act
    policy = ImDeliveryPolicy.from_env()

    # Assert
    assert policy.lease_seconds == ImDeliveryPolicy().lease_seconds
