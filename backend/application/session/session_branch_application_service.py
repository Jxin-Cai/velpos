from __future__ import annotations

import asyncio
import subprocess
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.model.session import Session
from domain.session.model.session_branch import SessionBranch
from domain.session.model.session_snapshot import SessionSnapshot
from domain.session.model.session_status import SessionStatus
from domain.session.model.usage import Usage
from domain.shared.async_utils import safe_create_task
from application.session.command.run_query_command import RunQueryCommand
from domain.session.repository.session_branch_repository import SessionBranchRepository
from domain.session.repository.session_repository import SessionRepository
from domain.session.repository.session_snapshot_repository import SessionSnapshotRepository
from domain.shared.business_exception import BusinessException


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BranchSessionResult:
    branches: list[SessionBranch]
    sessions: list[Session]


class SessionBranchApplicationService:

    def __init__(
        self,
        session_repository: SessionRepository,
        branch_repository: SessionBranchRepository,
        snapshot_repository: SessionSnapshotRepository,
        delete_session_fn: Callable[[str], Awaitable[bool]] | None = None,
        session_service_factory: Callable[[], Awaitable[Any]] | None = None,
        connection_manager: Any = None,
        cleanup_branch_group_fn: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._session_repository = session_repository
        self._branch_repository = branch_repository
        self._snapshot_repository = snapshot_repository
        self._delete_session_fn = delete_session_fn
        self._session_service_factory = session_service_factory
        self._connection_manager = connection_manager
        self._cleanup_branch_group_fn = cleanup_branch_group_fn

    async def create_branch(
        self,
        source_session_id: str,
        message_index: int,
        name: str = "",
        branch_count: int = 1,
        worktree_enabled: bool = False,
    ) -> BranchSessionResult:
        source = await self._get_session(source_session_id)
        if source.is_running or source.is_compacting:
            raise BusinessException("Cannot branch a running session")
        if branch_count < 1 or branch_count > 8:
            raise BusinessException("Branch count must be between 1 and 8")
        if source.messages:
            messages = self._messages_until(source, message_index)
        elif source.sdk_session_id:
            messages = []
        else:
            raise BusinessException("Cannot branch before the session has context")
        root_session_id = await self._root_session_id(source.session_id)
        group_id = uuid.uuid4().hex[:8]
        base_name = name.strip() or source.name or source.session_id
        base_branch = await self._current_git_branch(source.project_dir) if worktree_enabled else ""
        branches: list[SessionBranch] = []
        sessions: list[Session] = []
        source_fork_marker = self._fork_marker(source.sdk_session_id)
        for sequence_no in range(1, branch_count + 1):
            seed = Session.create(model=source.model, project_id=source.project_id, project_dir=source.project_dir)
            branch_name = f"{base_name}-{sequence_no}"
            project_dir, actual_worktree_path = await self._create_worktree(
                source.project_dir,
                seed.session_id,
                sequence_no,
                worktree_enabled,
            )
            branch_session = Session.reconstitute(
                session_id=seed.session_id,
                model=source.model,
                status=SessionStatus.IDLE,
                messages=messages,
                usage=Usage.zero(),
                continue_conversation=bool(messages) or bool(source_fork_marker),
                project_id=source.project_id,
                project_dir=project_dir,
                name=branch_name,
                sdk_session_id=source_fork_marker,
                last_input_tokens=0,
            )
            branch = SessionBranch.create(
                source_session_id=source.session_id,
                branch_session_id=branch_session.session_id,
                source_message_index=message_index,
                name=branch_session.name,
                root_session_id=root_session_id,
                group_id=group_id,
                sequence_no=sequence_no,
                worktree_enabled=bool(actual_worktree_path),
                worktree_path=actual_worktree_path,
                base_branch=base_branch,
            )
            await self._session_repository.save(branch_session)
            await self._branch_repository.save(branch)
            branches.append(branch)
            sessions.append(branch_session)
        snapshot = self._create_snapshot(source.session_id, message_index, messages)
        await self._snapshot_repository.save(snapshot)
        await self._session_repository.commit()
        return BranchSessionResult(branches=branches, sessions=sessions)

    async def apply_vb_reviews(
        self,
        source_session_id: str,
        file_path: str,
        reviews: list[dict[str, Any]],
    ) -> dict[str, str]:
        source = await self._get_session(source_session_id)
        if source.is_running or source.is_compacting:
            raise BusinessException("Cannot apply VB while session is running")
        if not source.messages and not source.sdk_session_id:
            raise BusinessException("Cannot apply VB before the session has context")
        if not reviews:
            raise BusinessException("VB reviews are required")
        if self._session_service_factory is None or self._connection_manager is None:
            raise BusinessException("VB executor is not configured", "VB_NOT_CONFIGURED")

        message_index = max(source.message_count - 1, 0)
        result = await self.create_branch(source_session_id, message_index, "VB", 1, False)
        branch = result.branches[0]
        branch_session = result.sessions[0]
        job_id = uuid.uuid4().hex[:8]
        safe_create_task(self._run_vb_job(
            job_id=job_id,
            source_session_id=source_session_id,
            branch_session_id=branch_session.session_id,
            branch_group_id=branch.group_id,
            file_path=file_path,
            reviews=reviews,
        ))
        return {"job_id": job_id, "branch_session_id": branch_session.session_id}

    async def _run_vb_job(
        self,
        job_id: str,
        source_session_id: str,
        branch_session_id: str,
        branch_group_id: str,
        file_path: str,
        reviews: list[dict[str, Any]],
    ) -> None:
        await self._broadcast_vb(source_session_id, "vb_started", {
            "job_id": job_id,
            "branch_session_id": branch_session_id,
            "file_path": file_path,
        })
        error_message = ""
        try:
            service = await self._session_service_factory()
            try:
                await service.set_permission_mode(branch_session_id, "bypassPermissions")
                await service.run_claude_query(RunQueryCommand(
                    session_id=branch_session_id,
                    prompt=self._build_vb_prompt(file_path, reviews),
                ))
            finally:
                await service.close()
            await self._broadcast_vb(source_session_id, "vb_completed", {
                "job_id": job_id,
                "branch_session_id": branch_session_id,
                "file_path": file_path,
            })
        except Exception as exc:
            error_message = str(exc)
            logger.warning("VB job failed: job=%s source=%s branch=%s", job_id, source_session_id, branch_session_id, exc_info=True)
            await self._broadcast_vb(source_session_id, "vb_failed", {
                "job_id": job_id,
                "branch_session_id": branch_session_id,
                "file_path": file_path,
                "message": error_message or "VB failed",
            })
        finally:
            await self._cleanup_vb_branch(branch_session_id, branch_group_id)

    async def _broadcast_vb(self, source_session_id: str, event: str, payload: dict[str, Any]) -> None:
        await self._connection_manager.broadcast(source_session_id, {"event": event, **payload})

    async def _cleanup_vb_branch(self, branch_session_id: str, branch_group_id: str) -> None:
        try:
            await self._delete_session(branch_session_id)
            if self._cleanup_branch_group_fn is not None and branch_group_id:
                await self._cleanup_branch_group_fn(branch_group_id)
        except Exception:
            logger.warning("Failed to cleanup VB branch session %s", branch_session_id, exc_info=True)

    @staticmethod
    def _build_vb_prompt(file_path: str, reviews: list[dict[str, Any]]) -> str:
        review_lines = []
        for index, review in enumerate(reviews, start=1):
            start = review.get("start_line")
            end = review.get("end_line")
            selected_text = review.get("selected_text", "")
            comment = review.get("comment", "")
            text_block = f"\n   选中文本: {selected_text}" if selected_text else ""
            review_lines.append(f"{index}. 行 {start}-{end}:{text_block}\n   评语: {comment}")
        return (
            "你正在执行文件 VB 修改任务。请基于当前会话上下文和下面的行级评价，直接修改指定文件。\n"
            "只修改目标文件，保持无关代码和格式不变；完成后不要创建提交。\n\n"
            f"目标文件: {file_path}\n\n"
            "评价列表:\n"
            + "\n".join(review_lines)
        )

    async def compare_sessions(self, source_session_id: str, target_session_id: str) -> dict[str, Any]:
        left = await self._get_session(source_session_id)
        right = await self._get_session(target_session_id)
        left_messages = left.messages
        right_messages = right.messages
        common = 0
        for left_msg, right_msg in zip(left_messages, right_messages):
            if left_msg.message_type == right_msg.message_type and left_msg.content == right_msg.content:
                common += 1
            else:
                break
        code_diff = await self._build_code_diff(left, right)
        result = {
            "left_session_id": left.session_id,
            "right_session_id": right.session_id,
            "common_prefix_count": common,
            "left_only_count": max(len(left_messages) - common, 0),
            "right_only_count": max(len(right_messages) - common, 0),
            "left_message_count": len(left_messages),
            "right_message_count": len(right_messages),
            "left_only": [self._message_to_dict(m) for m in left_messages[common:]],
            "right_only": [self._message_to_dict(m) for m in right_messages[common:]],
            "code_diff": code_diff,
        }
        result["analysis_prompt"] = self._build_analysis_prompt(result)
        return result

    async def list_branches(self, session_id: str) -> list[SessionBranch]:
        branch = await self._branch_repository.find_by_branch_session_id(session_id)
        if branch is not None:
            if branch.group_id:
                return await self._branch_repository.find_by_group_id(branch.group_id)
            return await self._branch_repository.find_by_root_session_id(branch.root_session_id or branch.source_session_id)
        branches = await self._branch_repository.find_by_source_session_id(session_id)
        if branches:
            root_branches = await self._branch_repository.find_by_root_session_id(branches[0].root_session_id or session_id)
            return root_branches or branches
        return []

    async def converge_branches(self, current_session_id: str, target_session_id: str) -> dict[str, Any]:
        branches = await self.list_branches(current_session_id)
        if not branches:
            raise BusinessException("No parallel branches found")
        branch_by_session_id = {branch.branch_session_id: branch for branch in branches}
        target_branch = branch_by_session_id.get(target_session_id)
        base_project_dir = ""
        if target_branch and target_branch.worktree_enabled:
            base_project_dir = await self._merge_worktree_target(target_branch)
            await self._move_session_to_project_dir(target_session_id, base_project_dir)
        deleted_sessions: list[str] = []
        cleanup_errors: list[str] = []
        for branch in branches:
            if branch.branch_session_id == target_session_id:
                continue
            if branch.worktree_path:
                error = await self._remove_worktree(branch.worktree_path)
                if error:
                    cleanup_errors.append(error)
            await self._delete_session(branch.branch_session_id)
            deleted_sessions.append(branch.branch_session_id)
        if target_branch and target_branch.worktree_path:
            error = await self._remove_worktree(target_branch.worktree_path)
            if error:
                cleanup_errors.append(error)
        await self._branch_repository.remove_by_group_id(branches[0].group_id)
        await self._session_repository.commit()
        return {
            "target_session_id": target_session_id,
            "deleted_session_ids": deleted_sessions,
            "merged": bool(target_branch and target_branch.worktree_enabled),
            "cleanup_errors": cleanup_errors,
        }

    async def _merge_worktree_target(self, branch: SessionBranch) -> str:
        target = await self._get_session(branch.branch_session_id)
        base = await self._get_session(branch.root_session_id or branch.source_session_id)
        if await self._has_uncommitted_changes(target.project_dir):
            raise BusinessException("Target worktree has uncommitted changes. Commit them before converging.")
        target_branch_name = await self._current_git_branch(target.project_dir)
        if not target_branch_name:
            raise BusinessException("Target worktree branch not found")
        base_branch = branch.base_branch or await self._current_git_branch(base.project_dir)
        if not base_branch:
            raise BusinessException("Base branch not found")
        await self._run_git_checked(base.project_dir, ["checkout", base_branch], "Failed to checkout base branch")
        if await self._has_uncommitted_changes(base.project_dir):
            raise BusinessException("Base working tree has uncommitted changes. Clean it before converging.")
        await self._run_git_checked(base.project_dir, ["merge", target_branch_name], "Failed to merge target branch")
        return base.project_dir

    async def _move_session_to_project_dir(self, session_id: str, project_dir: str) -> None:
        session = await self._get_session(session_id)
        moved = Session.reconstitute(
            session_id=session.session_id,
            model=session.model,
            status=session.status,
            messages=session.messages,
            usage=session.usage,
            continue_conversation=session.continue_conversation,
            project_id=session.project_id,
            project_dir=project_dir,
            name=session.name,
            sdk_session_id=session.sdk_session_id,
            last_input_tokens=session.last_input_tokens,
            pending_request_context=session.pending_request_context,
            queued_command=session.queued_command,
            cancel_requested=session.cancel_requested,
            updated_time=session.updated_time,
        )
        await self._session_repository.save(moved)


    async def _has_uncommitted_changes(self, project_dir: str) -> bool:
        output = await self._git_output(project_dir, ["status", "--porcelain"])
        return bool(output.strip())

    async def _run_git_checked(self, project_dir: str, args: list[str], message: str) -> None:
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", project_dir, *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise BusinessException(f"{message}: {detail}" if detail else message) from exc

    async def _remove_worktree(self, worktree_path: str) -> str:
        if not worktree_path or not Path(worktree_path).exists():
            return ""
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", worktree_path, "worktree", "remove", worktree_path],
                check=True,
                capture_output=True,
                text=True,
            )
            return ""
        except subprocess.CalledProcessError as exc:
            return (exc.stderr or exc.stdout or str(exc)).strip()

    async def _delete_session(self, session_id: str) -> None:
        if self._delete_session_fn is not None:
            await self._delete_session_fn(session_id)
            return
        await self._session_repository.remove(session_id)

    async def _build_code_diff(self, left: Session, right: Session) -> dict[str, Any]:
        left_branch = await self._current_git_branch(left.project_dir)
        right_branch = await self._current_git_branch(right.project_dir)
        result = {
            "left_branch": left_branch,
            "right_branch": right_branch,
            "changed_files": [],
            "diff_stat": "",
            "patch_excerpt": "",
            "truncated": False,
        }
        if not left_branch or not right_branch or left.project_dir == right.project_dir:
            return result
        range_expr = f"{left_branch}..{right_branch}"
        result["changed_files"] = [
            line for line in (await self._git_output(left.project_dir, ["diff", "--name-only", range_expr])).splitlines()
            if line.strip()
        ]
        result["diff_stat"] = await self._git_output(left.project_dir, ["diff", "--stat", range_expr])
        patch = await self._git_output(left.project_dir, ["diff", "--patch", "--unified=3", range_expr])
        max_patch_len = 12000
        result["patch_excerpt"] = patch[:max_patch_len]
        result["truncated"] = len(patch) > max_patch_len
        return result

    async def _git_output(self, project_dir: str, args: list[str]) -> str:
        if not project_dir:
            return ""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", project_dir, *args],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    @staticmethod
    def _build_analysis_prompt(compare_result: dict[str, Any]) -> str:
        code_diff = compare_result.get("code_diff") or {}
        changed_files = "\n".join(f"- {path}" for path in code_diff.get("changed_files", [])) or "- 无代码文件差异或无法读取"
        left_only = compare_result.get("left_only_count", 0)
        right_only = compare_result.get("right_only_count", 0)
        return (
            "请比较这两个会话分支的方案与代码差异，并给出推荐选择。\n\n"
            f"左侧会话: {compare_result.get('left_session_id', '')}\n"
            f"右侧会话: {compare_result.get('right_session_id', '')}\n"
            f"公共消息前缀: {compare_result.get('common_prefix_count', 0)}\n"
            f"左侧独有消息数: {left_only}\n"
            f"右侧独有消息数: {right_only}\n\n"
            f"左侧 Git 分支: {code_diff.get('left_branch', '')}\n"
            f"右侧 Git 分支: {code_diff.get('right_branch', '')}\n"
            f"变更文件:\n{changed_files}\n\n"
            f"Diff stat:\n{code_diff.get('diff_stat', '')}\n\n"
            f"Patch 摘要:\n{code_diff.get('patch_excerpt', '')}\n\n"
            "请从实现思路、风险、代码影响面、可维护性、测试建议五个角度分析，并明确推荐保留哪个分支。"
        )

    async def _root_session_id(self, session_id: str) -> str:
        branch = await self._branch_repository.find_by_branch_session_id(session_id)
        return branch.root_session_id if branch else session_id

    async def _current_git_branch(self, project_dir: str) -> str:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", project_dir, "rev-parse", "--abbrev-ref", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    async def _create_worktree(
        self,
        project_dir: str,
        session_id: str,
        sequence_no: int,
        enabled: bool,
    ) -> tuple[str, str]:
        if not enabled or not project_dir:
            return project_dir, ""
        project_path = Path(project_dir)
        worktree_path = project_path / ".claude" / "worktrees" / session_id
        branch_name = f"velpos/{session_id}-{sequence_no}"
        try:
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", project_dir, "worktree", "add", "-b", branch_name, str(worktree_path), "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            return str(worktree_path), str(worktree_path)
        except Exception:
            return project_dir, ""

    async def _get_session(self, session_id: str) -> Session:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")
        return session

    @staticmethod
    def _fork_marker(sdk_session_id: str) -> str:
        if not sdk_session_id:
            return ""
        if sdk_session_id.startswith("fork:"):
            return sdk_session_id
        return f"fork:{sdk_session_id}"

    @staticmethod
    def _messages_until(session: Session, message_index: int) -> list[Message]:
        messages = session.messages
        if message_index < 0:
            raise BusinessException("Message index must be >= 0")
        if message_index >= len(messages):
            raise BusinessException("Message index out of range")
        return messages[:message_index + 1]

    @staticmethod
    def _message_to_dict(message: Message) -> dict[str, Any]:
        return {"type": message.message_type.value, "content": message.content}

    def _create_snapshot(
        self,
        session_id: str,
        message_index: int,
        messages: list[Message],
    ) -> SessionSnapshot:
        return SessionSnapshot.create(
            session_id=session_id,
            message_index=message_index,
            messages=[self._message_to_dict(message) for message in messages],
        )
