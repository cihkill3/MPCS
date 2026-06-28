"""
MPCS — GUI Theme
모던 UI 스타일(QSS)
"""

def get_modern_theme() -> str:
    """
    애플리케이션 전체에 적용할 모던 QSS를 반환합니다.
    """
    return """
    /* 기본 윈도우 배경 및 폰트 */
    QWidget {
        background-color: #f8f9fa;
        color: #212529;
        font-family: "Segoe UI", "맑은 고딕", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        font-size: 13px;
    }

    /* 그룹박스 스타일링 */
    QGroupBox {
        font-weight: bold;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        margin-top: 14px;
        background-color: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        color: #495057;
        left: 10px;
    }

    /* 버튼 스타일링 */
    QPushButton {
        background-color: #f1f3f5;
        border: 1px solid #ced4da;
        border-radius: 4px;
        padding: 5px 12px;
        color: #495057;
    }
    QPushButton:hover {
        background-color: #e9ecef;
        border-color: #adb5bd;
    }
    QPushButton:pressed {
        background-color: #dee2e6;
    }
    QPushButton:disabled {
        background-color: #f8f9fa;
        color: #adb5bd;
        border: 1px solid #e9ecef;
    }

    /* Primary 버튼 (강조) - 예: "▶ 계산", "솔버 실행" 등은 objectName 기반으로 적용 */
    QPushButton#primaryButton {
        background-color: #339af0;
        color: white;
        border: 1px solid #228be6;
        font-weight: bold;
    }
    QPushButton#primaryButton:hover {
        background-color: #228be6;
        border-color: #1c7ed6;
    }
    QPushButton#primaryButton:pressed {
        background-color: #1c7ed6;
    }

    /* 입력 폼 스타일링 */
    QLineEdit, QSpinBox, QDoubleSpinBox {
        border: 1px solid #ced4da;
        border-radius: 4px;
        padding: 4px 6px;
        background-color: #ffffff;
        selection-background-color: #339af0;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #339af0;
    }

    /* 테이블 뷰 스타일링 */
    QTableWidget, QTableView {
        background-color: #ffffff;
        alternate-background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 4px;
        gridline-color: #e9ecef;
        selection-background-color: #e7f5ff;
        selection-color: #1864ab;
    }
    QHeaderView::section {
        background-color: #f1f3f5;
        color: #495057;
        padding: 4px;
        border: none;
        border-right: 1px solid #dee2e6;
        border-bottom: 1px solid #dee2e6;
        font-weight: bold;
    }

    /* 스플리터 핸들 스타일링 */
    QSplitter::handle {
        background-color: #dee2e6;
        margin: 1px;
    }
    QSplitter::handle:horizontal {
        width: 3px;
    }
    QSplitter::handle:vertical {
        height: 3px;
    }

    /* 탭 위젯 스타일링 */
    QTabWidget::pane {
        border: 1px solid #dee2e6;
        border-radius: 4px;
        background-color: #ffffff;
        top: -1px;
    }
    QTabBar::tab {
        background-color: #f1f3f5;
        border: 1px solid #ced4da;
        border-bottom-color: #dee2e6;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        padding: 6px 14px;
        margin-right: 2px;
        color: #495057;
    }
    QTabBar::tab:selected {
        background-color: #ffffff;
        border-bottom-color: #ffffff;
        color: #339af0;
        font-weight: bold;
    }
    QTabBar::tab:hover:!selected {
        background-color: #e9ecef;
    }

    /* 스크롤바 바 꾸미기 */
    QScrollBar:vertical {
        border: none;
        background: #f1f3f5;
        width: 10px;
        margin: 0px 0px 0px 0px;
    }
    QScrollBar::handle:vertical {
        background: #ced4da;
        min-height: 20px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background: #adb5bd;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    /* 상태바 표시 */
    QStatusBar {
        background-color: #f1f3f5;
        border-top: 1px solid #dee2e6;
        color: #495057;
    }
    """
