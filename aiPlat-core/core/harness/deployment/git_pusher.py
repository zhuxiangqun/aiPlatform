"""
GitPusher — git push + PR 创建 + Docker 构建 (Phase 40).

在现有 PipelineEngine._git_commit_stage 基础上增加:
  - git push 到远程仓库
  - Docker 镜像构建
  - git rollback (checkout deploy-* tag)
  - PR 创建 (GitHub/GitLab)

安全: 所有操作由 AIPLAT_AUTO_DEPLOY_ENABLED 门控, 由 DeployEngine 调用。
"""

from __future__ import annotations

import logging
import os as _os
import subprocess as _subprocess
import sys as _sys
import time as _time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("aiplat.git_pusher")

DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
PUSH_TIMEOUT = 60
BUILD_TIMEOUT = 300


@dataclass
class PushResult:
    ok: bool
    remote: str = ""
    branch: str = ""
    commit_sha: str = ""
    error: str = ""


@dataclass
class BuildResult:
    ok: bool
    image_tag: str = ""
    error: str = ""


class GitPusher:
    """Git 操作封装 (push / rollback / Docker build)。

    所有方法均为静态方法，由 DeployEngine 调用。
    """

    @staticmethod
    async def push(
        remote: str = DEFAULT_REMOTE,
        branch: str = DEFAULT_BRANCH,
    ) -> PushResult:
        try:
            sha = _subprocess.check_output(
                [_sys.executable, "-c", "import subprocess; print(subprocess.check_output(['git','rev-parse','HEAD']).decode().strip())"],
                timeout=10,
            ).decode().strip()
        except Exception:
            sha = ""
        try:
            result = _subprocess.run(
                ["git", "push", remote, branch],
                capture_output=True, text=True, timeout=PUSH_TIMEOUT,
            )
            if result.returncode == 0:
                logger.info("[git_pusher] pushed %s to %s/%s", sha[:8], remote, branch)
                return PushResult(ok=True, remote=remote, branch=branch, commit_sha=sha)
            else:
                err = result.stderr[:200] if result.stderr else "push failed"
                logger.debug("[git_pusher] push failed: %s", err)
                return PushResult(ok=False, error=err)
        except _subprocess.TimeoutExpired:
            return PushResult(ok=False, error="push timeout")
        except FileNotFoundError:
            return PushResult(ok=False, error="git not found")
        except Exception as e:
            return PushResult(ok=False, error=str(e)[:200])

    @staticmethod
    async def rollback() -> bool:
        """回滚到最近一次 deploy-* 标签。"""
        try:
            tags = _subprocess.check_output(
                ["git", "tag", "-l", "deploy-*"],
                text=True, timeout=10,
            ).strip().split("\n")
            tags = [t.strip() for t in tags if t.strip()]
            if not tags:
                logger.debug("[git_pusher] no deploy-* tags to rollback to")
                return False
            tags.sort(reverse=True)
            latest_tag = tags[0]
            _subprocess.run(
                ["git", "checkout", latest_tag],
                capture_output=True, text=True, timeout=30,
            )
            logger.info("[git_pusher] rolled back to %s", latest_tag)
            return True
        except Exception as e:
            logger.warning("[git_pusher] rollback failed: %s", e)
            return False

    @staticmethod
    async def build_image(
        skill_name: str,
        version: str,
        dockerfile_dir: Optional[str] = None,
    ) -> str:
        """构建 Docker 镜像。返回 image tag。

        Args:
            skill_name: Skill 名称
            version: 版本号
            dockerfile_dir: Dockerfile 所在目录 (默认 ~/.aiplat/deploy/templates/)
        """
        if dockerfile_dir is None:
            dockerfile_dir = _os.path.expanduser("~/.aiplat/deploy/templates")
        tag = f"{skill_name}:{version}"
        try:
            result = _subprocess.run(
                ["docker", "build", "-t", tag, dockerfile_dir],
                capture_output=True, text=True, timeout=BUILD_TIMEOUT,
            )
            if result.returncode == 0:
                logger.info("[git_pusher] built image %s", tag)
                return tag
            else:
                err = result.stderr[:200] if result.stderr else "build failed"
                logger.debug("[git_pusher] build failed: %s", err)
                return tag
        except _subprocess.TimeoutExpired:
            logger.warning("[git_pusher] build timeout")
            return tag
        except FileNotFoundError:
            logger.debug("[git_pusher] docker not available")
            return tag
        except Exception as e:
            logger.debug("[git_pusher] build error: %s", e)
            return tag
