from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0:
            raise ValueError("input_tokens must be >= 0")
        if self.output_tokens < 0:
            raise ValueError("output_tokens must be >= 0")

    @classmethod
    def zero(cls) -> Usage:
        """Create a zero-value Usage object (input_tokens=0, output_tokens=0)."""
        return cls(input_tokens=0, output_tokens=0)

    def add(self, input_tokens: int, output_tokens: int) -> Usage:
        """Return a new Usage object with accumulated token counts.

        Both input_tokens and output_tokens must be >= 0.
        """
        if input_tokens < 0:
            raise ValueError("input_tokens must be >= 0")
        if output_tokens < 0:
            raise ValueError("output_tokens must be >= 0")
        return Usage(
            input_tokens=self.input_tokens + input_tokens,
            output_tokens=self.output_tokens + output_tokens,
        )
