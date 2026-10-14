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

import os
import sys

os.environ.setdefault("QT_API", "pyqt5")

from qtpy.QtCore import Qt  # noqa: E402
from qtpy.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mpcs.core.i18n import I18nManager, tr  # noqa: E402
from mpcs.gui.dialogs.startup_dialog import StartupDialog  # noqa: E402
from mpcs.gui.icons import app_icon  # noqa: E402
from mpcs.gui.main_window import MainWindow, install_qt_translator  # noqa: E402
from mpcs.gui.theme import apply_theme  # noqa: E402
from mpcs.infrastructure.config_manager import AppConfigManager, RecentProjectsManager  # noqa: E402
from mpcs.infrastructure.project_serializer import (  # noqa: E402
    ProjectDeserializeError,
    ProjectSerializer,
)


def _set_windows_app_id() -> None:
    """Windows 작업 표시줄이 python.exe 대신 MPCS 아이콘으로 묶어 보이도록 앱 ID를 정한다."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MPCS.MALDIPolymerCompositionSolver")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    """애플리케이션 진입점."""
    _set_windows_app_id()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("MALDI Polymer Composition Solver")
    app.setApplicationVersion("1.3")
    app.setOrganizationName("MPCS")
    app.setWindowIcon(app_icon())      # 모든 창(시작 화면·메인·대화상자)의 제목 표시줄·작업 표시줄 아이콘

    # 언어 (창을 만들기 전에) + Qt 표준 대화상자 번역
    app_config = AppConfigManager()
    lang = app_config.get_language()
    I18nManager.get_instance().set_language(lang)
    install_qt_translator(lang)

    # 테마 (Fusion + 토큰 팔레트 + 맑은 고딕 + QSS)
    apply_theme(app)

    recent_manager = RecentProjectsManager()
    serializer = ProjectSerializer()

    # Q12: 시작 화면 표시
    startup = StartupDialog(recent_manager)
    if startup.exec() != StartupDialog.Accepted:
        return 0

    project = None
    current_filepath: str | None = None
    if startup.selected_path:
        try:
            project = serializer.load(startup.selected_path)
            current_filepath = startup.selected_path
            recent_manager.add(startup.selected_path)
        except ProjectDeserializeError as exc:
            QMessageBox.critical(
                None, tr("파일 열기 실패"),
                tr("프로젝트를 불러올 수 없습니다:\n{e}\n\n새 프로젝트로 시작합니다.", e=exc),
            )
            project = None

    window = MainWindow(project=project, recent_manager=recent_manager)
    if current_filepath:
        window._current_filepath = current_filepath
        window._update_title()
    app._mpcs_window = window      # 언어 전환 시 새 창으로 바뀐다
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
