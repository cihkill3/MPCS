"""
MPCS — MALDI Polymer Composition Solver
Infrastructure Layer: Recent Projects Manager

Q12: 처음 실행할 때 기존 프로젝트를 열 수 있도록 표시.
최근 프로젝트 목록을 JSON 파일로 관리한다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Final

# 최근 프로젝트 최대 저장 수
MAX_RECENT_PROJECTS: Final[int] = 10

# 설정 저장 위치: 사용자 홈 디렉토리의 .mpcs 폴더 (테스트는 MPCS_CONFIG_DIR로 바꾼다)
def _config_dir() -> Path:
    return Path(os.environ.get("MPCS_CONFIG_DIR") or (Path.home() / ".mpcs"))


class RecentProjectsManager:
    """
    최근 사용한 프로젝트 파일 경로를 관리한다.

    Q12 구현:
    - 최근 프로젝트 목록 저장 (최대 10개)
    - 존재하지 않는 파일은 목록에서 자동 제거
    - 앱 시작 시 시작 화면에서 최근 프로젝트 표시

    저장 위치:
        Windows: C:\\Users\\<username>\\.mpcs\\recent_projects.json
    """

    def __init__(self) -> None:
        self._file = _config_dir() / "recent_projects.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._recent: list[str] = self._load()

    def add(self, filepath: str | Path) -> None:
        """
        파일 경로를 최근 목록 맨 앞에 추가한다.
        이미 존재하면 기존 항목을 제거하고 맨 앞으로 이동.
        최대 MAX_RECENT_PROJECTS개 유지.
        """
        path_str = str(Path(filepath).resolve())

        # 기존 항목 제거
        if path_str in self._recent:
            self._recent.remove(path_str)

        self._recent.insert(0, path_str)
        self._recent = self._recent[:MAX_RECENT_PROJECTS]
        self._save()

    def remove(self, filepath: str | Path) -> None:
        """특정 파일을 최근 목록에서 제거한다."""
        path_str = str(Path(filepath).resolve())
        if path_str in self._recent:
            self._recent.remove(path_str)
            self._save()

    def get_valid(self) -> list[str]:
        """
        존재하는 파일만 필터링하여 반환한다.
        존재하지 않는 파일은 목록에서 자동 제거.
        """
        valid = [p for p in self._recent if Path(p).exists()]
        if len(valid) != len(self._recent):
            self._recent = valid
            self._save()
        return list(valid)

    def clear(self) -> None:
        """최근 목록을 초기화한다."""
        self._recent = []
        self._save()

    def _load(self) -> list[str]:
        """JSON 파일에서 최근 목록을 로드한다."""
        if not self._file.exists():
            return []
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self) -> None:
        """최근 목록을 JSON 파일에 저장한다."""
        try:
            self._file.write_text(
                json.dumps(self._recent, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # 설정 저장 실패는 앱 동작에 영향 없음



class AppConfigManager:
    """
    다국어(Language) 및 UI 테마 등의 전역 애플리케이션 설정을 관리합니다.
    """
    def __init__(self) -> None:
        self._file = _config_dir() / "app_config.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self.config: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._file.exists():
            return {"language": "ko"}
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {"language": "ko"}
        except Exception:
            return {"language": "ko"}

    def _save(self) -> None:
        try:
            self._file.write_text(
                json.dumps(self.config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def get_language(self) -> str:
        return self.config.get("language", "ko")

    def set_language(self, lang: str) -> None:
        self.config["language"] = lang
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        """임의 설정값 (창 크기, 패널 접힘 등)."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self._save()
