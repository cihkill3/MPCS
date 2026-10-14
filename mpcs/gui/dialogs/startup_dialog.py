"""
MPCS — MALDI Polymer Composition Solver
GUI Dialogs: Startup Dialog

Q12: 처음 실행할 때 기존 프로젝트를 열 수 있도록 표시.
    - 최근 프로젝트 목록 표시
    - 새 프로젝트 시작
    - 기존 프로젝트 열기 (파일 탐색기)
"""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from mpcs.core.i18n import tr
from mpcs.gui.widgets import caption, role_label
from mpcs.infrastructure.config_manager import RecentProjectsManager
from mpcs.infrastructure.project_serializer import PROJECT_FILE_EXTENSION


class StartupDialog(QDialog):
    """
    애플리케이션 시작 화면 다이얼로그.

    Q12: 기존 프로젝트를 열거나 새 프로젝트를 시작할 수 있다.

    Result:
        - selected_path: 열 파일 경로 (None이면 새 프로젝트)
        - result() == QDialog.Accepted → selected_path 사용
        - result() == QDialog.Rejected → 앱 종료
    """

    def __init__(self, recent_manager: RecentProjectsManager, parent=None) -> None:
        super().__init__(parent)
        self.selected_path: str | None = None
        self._recent_manager = recent_manager
        self._setup_ui()
        self._load_recent()

    def _setup_ui(self) -> None:
        self.setWindowTitle("MALDI Polymer Composition Solver")
        self.setMinimumSize(560, 400)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 제목
        from mpcs.gui.icons import app_icon, app_pixmap

        self.setWindowIcon(app_icon())
        logo = QLabel()
        logo.setPixmap(app_pixmap(72))
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)
        title_label = role_label("MALDI Polymer Composition Solver", "dialogTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        sub_label = caption(tr("MALDI·LC-MS 고분자 피크의 조성을 계산합니다. 시작하려면 옵션을 선택하십시오."))
        sub_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub_label)

        # 최근 프로젝트 섹션
        layout.addWidget(role_label(tr("최근 프로젝트:"), "sectionTitle"))

        self._recent_list = QListWidget()
        self._recent_list.setAlternatingRowColors(True)
        self._recent_list.itemDoubleClicked.connect(self._open_recent)
        self._recent_list.setToolTip(tr("최근에 저장하거나 연 프로젝트 (.mpcs). 두 번 누르면 엽니다."))
        layout.addWidget(self._recent_list)

        # 버튼 행
        btn_layout = QHBoxLayout()

        self._open_recent_btn = QPushButton(tr("최근 프로젝트 열기"))
        self._open_recent_btn.setEnabled(False)
        self._open_recent_btn.clicked.connect(self._open_recent)

        browse_btn = QPushButton(tr("파일 찾아보기..."))
        browse_btn.setToolTip(tr("다른 위치의 프로젝트 파일(.mpcs)을 엽니다."))
        browse_btn.clicked.connect(self._browse_file)

        new_btn = QPushButton(tr("새 프로젝트"))
        new_btn.setObjectName("primaryButton")
        new_btn.setToolTip(tr("빈 프로젝트로 시작합니다 (기본 어덕트 [M+Na]+, 말단기 OH/OH)."))
        new_btn.setDefault(True)
        new_btn.clicked.connect(self._new_project)

        btn_layout.addWidget(self._open_recent_btn)
        btn_layout.addWidget(browse_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(new_btn)

        layout.addLayout(btn_layout)

        # 선택 변경 시 버튼 활성화
        self._recent_list.currentItemChanged.connect(self._on_selection_changed)

    def _load_recent(self) -> None:
        """최근 프로젝트 목록을 로드하여 리스트에 표시한다."""
        self._recent_list.clear()
        recent = self._recent_manager.get_valid()

        if not recent:
            placeholder = QListWidgetItem(tr("(최근 프로젝트 없음)"))
            placeholder.setFlags(Qt.NoItemFlags)
            self._recent_list.addItem(placeholder)
            return

        for filepath in recent:
            path = Path(filepath)
            item = QListWidgetItem()
            item.setText(f"{path.stem}  —  {path.parent}")
            item.setData(Qt.UserRole, filepath)
            item.setToolTip(filepath)
            self._recent_list.addItem(item)

    def _on_selection_changed(self, current: QListWidgetItem | None, _) -> None:
        has_valid = current is not None and current.data(Qt.UserRole) is not None
        self._open_recent_btn.setEnabled(has_valid)

    def _open_recent(self, item: QListWidgetItem | None = None) -> None:
        """선택된 최근 프로젝트를 연다."""
        target = item or self._recent_list.currentItem()
        if target is None:
            return
        filepath = target.data(Qt.UserRole)
        if filepath and Path(filepath).exists():
            self.selected_path = filepath
            self.accept()
        else:
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, tr("파일 없음"),
                tr("파일을 찾을 수 없습니다:\n{path}", path=filepath)
            )
            self._recent_manager.remove(filepath)
            self._load_recent()

    def _browse_file(self) -> None:
        """파일 탐색기로 프로젝트 파일을 선택한다."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            tr("프로젝트 파일 열기"),
            str(Path.home()),
            tr("MPCS 프로젝트") + f" (*{PROJECT_FILE_EXTENSION});;" + tr("모든 파일") + " (*.*)",
        )
        if filepath:
            self.selected_path = filepath
            self.accept()

    def _new_project(self) -> None:
        """새 프로젝트를 시작한다."""
        self.selected_path = None
        self.accept()
