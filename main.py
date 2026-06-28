"""
MPCS — MALDI Polymer Composition Solver
Application Entry Point

Q12: 시작 화면에서 최근 프로젝트를 열거나 새 프로젝트를 시작할 수 있다.

실행 방법:
    python main.py
    또는
    python -m mpcs
"""

from __future__ import annotations

import sys
from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication, QMessageBox

from mpcs.gui.dialogs.startup_dialog import StartupDialog
from mpcs.gui.main_window import MainWindow
from mpcs.infrastructure.config_manager import RecentProjectsManager, AppConfigManager
from mpcs.infrastructure.project_serializer import (
    ProjectDeserializeError,
    ProjectSerializer,
)
from mpcs.core.i18n import I18nManager
from mpcs.gui.theme import get_modern_theme


def main() -> int:
    """애플리케이션 진입점."""
    app = QApplication(sys.argv)
    app.setApplicationName("MALDI Polymer Composition Solver")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("MPCS")

    # 폰트 및 DPI 설정 (Windows 11)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # 전역 설정 로드 및 i18n 초기화
    app_config = AppConfigManager()
    i18n = I18nManager.get_instance()
    i18n.set_language(app_config.get_language())

    # 모던 테마 적용
    app.setStyleSheet(get_modern_theme())

    recent_manager = RecentProjectsManager()
    serializer = ProjectSerializer()

    # Q12: 시작 화면 표시
    startup = StartupDialog(recent_manager)
    result = startup.exec()

    if result != StartupDialog.Accepted:
        return 0  # 사용자가 다이얼로그를 닫음

    project = None
    current_filepath: str | None = None

    if startup.selected_path:
        # 기존 프로젝트 열기
        try:
            project = serializer.load(startup.selected_path)
            current_filepath = startup.selected_path
            recent_manager.add(startup.selected_path)
        except ProjectDeserializeError as exc:
            QMessageBox.critical(
                None, "파일 열기 실패",
                f"프로젝트를 불러올 수 없습니다:\n{exc}\n\n새 프로젝트로 시작합니다."
            )
            project = None

    # 메인 윈도우 생성
    window = MainWindow(project=project, recent_manager=recent_manager)
    if current_filepath:
        window._current_filepath = current_filepath
        window._update_title()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
