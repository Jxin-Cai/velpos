from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import islice

from domain.team.acl.session_context_collector import SessionArtifact
from domain.team.model.card_execution import CardExecution
from domain.team.model.stage_output import StageOutput
from domain.team.model.wish_card import WishCard


@dataclass(frozen=True)
class _Section:
    heading: str
    body: str


class StageOutputBuilder:
    """Build a bounded, auditable handoff snapshot without copying a transcript."""

    _MAX_SUMMARY_CHARS = 8_000
    _MAX_ARTIFACTS = 50
    _COMPRESSION_METHOD = "goal_anchored_final_output_v1"
    _HEADING_PATTERN = re.compile(r"^#{1,4}\s+(.+?)\s*$", re.MULTILINE)
    _SENSITIVE_PATTERNS = (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
            r"(\s*[:=]\s*)([^\s,;]+)"
        ),
        re.compile(r"(?i)\b(bearer)(\s+)([a-z0-9._~+/=-]{12,})"),
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
            r"-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    )
    _SECTION_ALIASES = {
        "summary": ("阶段结论", "结论", "总结", "summary", "result"),
        "completed_work": ("已完成", "完成内容", "完成工作", "completed", "implemented"),
        "decisions": ("关键决策", "决策", "decisions"),
        "deliverables": ("产物", "交付物", "deliverables", "artifacts"),
        "validation": ("验证", "测试", "validation", "tests"),
        "unresolved_issues": ("待处理", "未解决", "遗留问题", "unresolved", "todo"),
        "risks": ("风险", "risks"),
        "next_stage_brief": ("下一步", "下阶段", "next steps", "next stage"),
    }

    @classmethod
    def build(
        cls,
        *,
        card: WishCard,
        execution: CardExecution,
        source_session_id: str,
        final_output: str,
        artifacts: Iterable[SessionArtifact] = (),
        previous_output_id: str | None = None,
        revision: int = 1,
    ) -> StageOutput:
        artifact_list = tuple(islice(artifacts, cls._MAX_ARTIFACTS))
        objective = card.title.strip()
        if card.description.strip():
            objective = f"{objective}\n\n{card.description.strip()}"
        objective = cls._redact_sensitive_text(objective)

        bounded_output = cls._compress_final_output(
            cls._redact_sensitive_text(final_output),
            objective,
        )
        sections = cls._parse_sections(bounded_output)
        content = {
            "objective": objective,
            "stage_summary": cls._section_text(sections, "summary") or bounded_output,
            "completed_work": cls._section_items(sections, "completed_work"),
            "decisions": cls._section_items(sections, "decisions"),
            "deliverables": cls._section_items(sections, "deliverables"),
            "validation": cls._section_items(sections, "validation"),
            "constraints": [],
            "unresolved_issues": cls._section_items(sections, "unresolved_issues"),
            "risks": cls._section_items(sections, "risks"),
            "next_stage_brief": cls._section_text(sections, "next_stage_brief"),
        }
        known_deliverables = {item for item in content["deliverables"]}
        for artifact in artifact_list:
            item = f"{artifact.path} — {artifact.description}"
            if item not in known_deliverables:
                content["deliverables"].append(item)
                known_deliverables.add(item)

        rendered = cls._render_markdown(content)
        checksum_payload = {
            "schema_version": 1,
            "content": content,
            "artifacts": [
                {
                    "path": artifact.path,
                    "description": artifact.description,
                    "artifact_type": artifact.artifact_type,
                }
                for artifact in artifact_list
            ],
        }
        checksum = hashlib.sha256(
            json.dumps(
                checksum_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        stage_output = StageOutput.create_ready(
            card_id=card.id,
            execution_id=execution.id,
            revision=revision,
            content=content,
            rendered_markdown=rendered,
            source_session_id=source_session_id,
            checksum=checksum,
            compression_method=cls._COMPRESSION_METHOD,
            previous_output_id=previous_output_id,
        )
        for artifact in artifact_list:
            stage_output.add_artifact(
                name=artifact.path.rsplit("/", 1)[-1],
                path=artifact.path,
                media_type=artifact.artifact_type,
            )
        return stage_output

    @classmethod
    def _compress_final_output(cls, final_output: str, objective: str) -> str:
        normalized = final_output.strip()
        if not normalized:
            return "本阶段已结束，但 Agent 没有提供可提取的最终输出。"
        if len(normalized) <= cls._MAX_SUMMARY_CHARS:
            return normalized

        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", normalized)
            if paragraph.strip()
        ]
        objective_terms = {
            term.lower()
            for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", objective)
        }
        priority_terms = (
            "完成",
            "实现",
            "修复",
            "决策",
            "验证",
            "测试",
            "风险",
            "待处理",
            "下一步",
            "completed",
            "implemented",
            "fixed",
            "decision",
            "test",
            "risk",
            "next",
        )

        def score(item: tuple[int, str]) -> tuple[int, int]:
            index, paragraph = item
            lowered = paragraph.lower()
            keyword_score = sum(3 for term in priority_terms if term in lowered)
            goal_score = sum(1 for term in objective_terms if term in lowered)
            heading_score = 4 if paragraph.startswith("#") else 0
            boundary_score = 2 if index in {0, len(paragraphs) - 1} else 0
            return keyword_score + goal_score + heading_score + boundary_score, -index

        selected: set[int] = set()
        size = 0
        for index, paragraph in sorted(enumerate(paragraphs), key=score, reverse=True):
            paragraph_size = len(paragraph) + 2
            if selected and size + paragraph_size > cls._MAX_SUMMARY_CHARS:
                continue
            selected.add(index)
            size += paragraph_size
            if size >= cls._MAX_SUMMARY_CHARS:
                break
        result = "\n\n".join(paragraphs[index] for index in sorted(selected))
        return result[: cls._MAX_SUMMARY_CHARS].rstrip()

    @classmethod
    def _redact_sensitive_text(cls, value: str) -> str:
        redacted = value
        for index, pattern in enumerate(cls._SENSITIVE_PATTERNS):
            if index == 0:
                redacted = pattern.sub(r"\1\2[REDACTED]", redacted)
            elif index == 1:
                redacted = pattern.sub(r"\1\2[REDACTED]", redacted)
            else:
                redacted = pattern.sub("[REDACTED PRIVATE KEY]", redacted)
        return redacted

    @classmethod
    def _parse_sections(cls, text: str) -> list[_Section]:
        matches = list(cls._HEADING_PATTERN.finditer(text))
        return [
            _Section(
                heading=match.group(1).strip().lower(),
                body=text[
                    match.end() : matches[index + 1].start()
                    if index + 1 < len(matches)
                    else len(text)
                ].strip(),
            )
            for index, match in enumerate(matches)
        ]

    @classmethod
    def _matching_bodies(cls, sections: list[_Section], key: str) -> list[str]:
        aliases = cls._SECTION_ALIASES[key]
        return [
            section.body
            for section in sections
            if any(alias in section.heading for alias in aliases)
            and section.body
        ]

    @classmethod
    def _section_text(cls, sections: list[_Section], key: str) -> str:
        return "\n\n".join(cls._matching_bodies(sections, key)).strip()

    @classmethod
    def _section_items(cls, sections: list[_Section], key: str) -> list[str]:
        items: list[str] = []
        for body in cls._matching_bodies(sections, key):
            candidates = [
                re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", line).strip()
                for line in body.splitlines()
                if line.strip()
            ]
            bullet_items = [
                candidate
                for line, candidate in zip(
                    (line for line in body.splitlines() if line.strip()),
                    candidates,
                    strict=True,
                )
                if re.match(r"^(?:[-*+]|\d+[.)])\s+", line.strip())
            ]
            items.extend(bullet_items or ([body.strip()] if body.strip() else []))
        return list(dict.fromkeys(items))

    @staticmethod
    def _render_markdown(content: dict[str, object]) -> str:
        parts = [
            "## 目标",
            str(content["objective"]),
            "## 本阶段结论",
            str(content["stage_summary"]),
        ]
        sections = (
            ("已完成", "completed_work"),
            ("关键决策", "decisions"),
            ("产物", "deliverables"),
            ("验证", "validation"),
            ("约束", "constraints"),
            ("待处理", "unresolved_issues"),
            ("风险", "risks"),
        )
        for heading, key in sections:
            values = content[key]
            if isinstance(values, list) and values:
                parts.extend((f"## {heading}", "\n".join(f"- {item}" for item in values)))
        next_stage = str(content["next_stage_brief"]).strip()
        if next_stage:
            parts.extend(("## 下一阶段建议", next_stage))
        return "\n\n".join(parts)
