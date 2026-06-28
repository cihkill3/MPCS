"""
MPCS — GUI Dialog: Guide Dialog
이용 안내 메뉴
"""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
)

from mpcs.core.i18n import tr


class GuideDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("이용 안내 (User Guide)"))
        self.resize(700, 500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)

        guide_html = f"""
        <h2>{tr("MALDI Polymer Composition Solver - 이용 안내")}</h2>
        
        <h3>{tr("1. 모노머 정의 탭 (Monomers)")}</h3>
        <ul>
            <li><b>{tr("일반 모노머:")}</b> {tr("분자식을 입력하면 자동으로 정확한 질량이 계산됩니다. 질량을 직접 입력하려면 분자식 칸에 '~'로 시작하는 숫자(예: ~100.5)를 입력하세요.")}</li>
            <li><b>{tr("블록(Block) 공중합체:")}</b> {tr("여러 모노머/말단기가 결합된 하나의 단위를 정의합니다. 블록 내의 최소/최대 개수도 설정할 수 있습니다.")}</li>
            <li><b>{tr("최소/최대 개수:")}</b> {tr("솔버가 이 모노머를 조합할 때 탐색할 개수의 범위를 지정합니다.")}</li>
        </ul>

        <h3>{tr("2. 중합 계산기 탭 (Polymer Calculator)")}</h3>
        <ul>
            <li>{tr("고분자 중합 이론(Carothers Equation)에 따라 각 성분의 반응비, 분자량, 중량 분율 등을 계산합니다.")}</li>
            <li>{tr("'모노머 탭에서 가져오기'를 통해 입력된 모노머를 바로 불러와 계산할 수 있으며, 계산된 통계적 개수를 다시 '최솟값/최댓값에 반영'할 수 있습니다.")}</li>
        </ul>

        <h3>{tr("3. 제약식 및 설정")}</h3>
        <ul>
            <li><b>{tr("제약식 (Constraints):")}</b> {tr("특정 모노머의 개수가 다른 모노머의 개수에 종속되도록 수식을 설정할 수 있습니다. (예: M1 = M2 * 2)")}</li>
            <li><b>{tr("말단기 (End Group):")}</b> {tr("양 끝단에 결합하는 화학 성분을 지정합니다.")}</li>
            <li><b>{tr("어덕트 (Adducts):")}</b> {tr("이온화 과정에서 추가로 붙는 이온(예: [M+Na]+)을 설정합니다.")}</li>
        </ul>

        <h3>{tr("4. MALDI MS 입력 및 솔버 실행")}</h3>
        <ul>
            <li>{tr("분석하고자 하는 피크의 m/z 값을 입력하고 오차 허용 범위(Da)를 설정합니다.")}</li>
            <li>{tr("솔버를 실행하면 설정한 범위 내에서 가능한 모든 조합을 탐색하여 결과를 테이블에 보여줍니다.")}</li>
            <li>{tr("결과 테이블의 행을 <b>더블 클릭</b>하면 해당 조합의 <b>동위원소 패턴 스펙트럼(Isotope Pattern)</b>을 확인할 수 있습니다.")}</li>
        </ul>
        """
        browser.setHtml(guide_html)
        layout.addWidget(browser)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)
