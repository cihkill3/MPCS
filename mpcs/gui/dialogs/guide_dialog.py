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
        <h2>{tr("MALDI Polymer Composition Solver (MPCS) - 초보자 가이드")}</h2>
        <p>{tr("MPCS는 복잡한 고분자의 MALDI-TOF MS(질량분석) 데이터를 분석하여, 어떤 모노머가 몇 개 결합했는지 정확한 조합을 찾아주는 프로그램입니다. 아래 순서대로 따라해 보세요!")}</p>
        
        <h3>{tr("1단계: 모노머(단량체) 등록하기 🧱")}</h3>
        <p>{tr("분석할 고분자를 구성하는 기본 블록(모노머)들을 등록합니다.")}</p>
        <ul>
            <li><b>{tr("일반 모노머:")}</b> {tr("예를 들어 젖산(LA, C3H4O2)을 분석하려면, 이름과 화학 분자식을 입력하세요. 프로그램이 정확한 질량을 자동으로 계산합니다.")}</li>
            <li><b>{tr("질량 직접 입력:")}</b> {tr("분자식을 정확히 모르고 질량만 안다면, 분자식 입력칸에 '~' 기호와 함께 질량을 적어주세요. (예: ~100.5)")}</li>
            <li><b>{tr("블록(Block) 공중합체:")}</b> {tr("여러 성분이 미리 결합된 거대한 블록(예: PLA-PEG)이 있다면 '유형'을 Block으로 바꾸고 하위 성분들을 추가해 묶을 수 있습니다.")}</li>
            <li><b>{tr("최소값/최대값:")}</b> {tr("각 모노머가 결합될 수 있는 대략적인 개수 범위를 지정합니다. 범위를 좁게 잡을수록 솔버가 정답을 더 빨리 찾습니다.")}</li>
        </ul>

        <h3>{tr("2단계: 부가 정보 설정하기 (말단기 & 어덕트) 🧪")}</h3>
        <ul>
            <li><b>{tr("말단기 (End Group):")}</b> {tr("고분자 양 끝에 붙어있는 화학 성분입니다. 기본적으로 물(H2O)이 들어있지만, 분석 샘플에 맞게 수정하세요.")}</li>
            <li><b>{tr("어덕트 (Adducts):")}</b> {tr("질량분석기에서 이온화될 때 달라붙는 이온(예: 나트륨 Na, 칼륨 K)입니다. 사용하는 매트릭스와 염(Salt)에 따라 체크박스를 선택하세요.")}</li>
        </ul>

        <h3>{tr("3단계: 제약식(Constraints) 활용하기 (선택 사항) ⚙️")}</h3>
        <p>{tr("특정 성분들 사이에 수학적 규칙이 있다면 제약식으로 지정할 수 있습니다.")}</p>
        <ul>
            <li>{tr("예를 들어, A 모노머와 B 모노머가 항상 1:1로 결합한다면 <code>A = B</code> 라고 입력해 탐색 시간을 대폭 줄일 수 있습니다.")}</li>
            <li>{tr("특정 모노머의 질량을 참조하고 싶다면 <code>A.mw</code> 처럼 입력하세요. (예: <code>A * A.mw <= 1000</code>)")}</li>
        </ul>

        <h3>{tr("4단계: 솔버 실행 및 결과 분석 🔍")}</h3>
        <ul>
            <li><b>{tr("m/z 입력:")}</b> {tr("스펙트럼에서 발견한 피크의 질량(m/z) 값을 입력 칸에 넣고 오차 허용 범위(Da)를 설정합니다.")}</li>
            <li><b>{tr("계산 시작:")}</b> {tr("[솔버 실행] 버튼을 누르면 조건에 맞는 모든 경우의 수를 탐색해 가장 오차가 적은 순서대로 결과를 보여줍니다.")}</li>
            <li><b>{tr("동위원소 패턴 확인:")}</b> {tr("결과 테이블의 행을 <b>더블 클릭</b>하면, 해당 조합이 실제 스펙트럼에서 어떤 동위원소 패턴(그래프)으로 나타나는지 시각적으로 확인할 수 있습니다. 실제 측정된 그래프와 모양이 일치하는지 비교해 보세요!")}</li>
        </ul>

        <hr/>
        <h3>{tr("💡 팁: 중합 계산기 (Polymer Calculator)")}</h3>
        <p>{tr("고분자 합성 레시피(Feed Ratio)나 전환율을 알고 계신가요? <b>[중합 계산기]</b> 탭에서 이를 입력하면 통계적으로 예상되는 모노머의 평균 개수를 미리 계산해 줍니다. 계산된 값을 '최소값/최대값에 반영' 버튼으로 가져오면, 수동으로 범위를 정하는 수고를 덜 수 있습니다.")}</p>
        """
        browser.setHtml(guide_html)
        layout.addWidget(browser)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)
