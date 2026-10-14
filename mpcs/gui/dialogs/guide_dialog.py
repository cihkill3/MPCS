"""
MPCS — GUI Dialog: Guide Dialog
이용 안내 (도움말 > 이용 안내, F1)
"""

from __future__ import annotations

from qtpy.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from mpcs.core.i18n import tr
from mpcs.gui import theme


def _section(title: str, items: list[tuple[str, str]], intro: str = "") -> str:
    body = f"<p>{intro}</p>" if intro else ""
    body += "<ul>" + "".join(f"<li><b>{k}</b> {v}</li>" for k, v in items) + "</ul>"
    return f"<h3>{title}</h3>{body}"


def guide_html() -> str:
    t = theme
    css = (f"<style>h2{{color:{t.TEXT};}} h3{{color:{t.ACCENT}; margin-top:14px;}} "
           f"li{{margin-bottom:4px;}} code{{background:{t.BG};}}</style>")
    parts = [
        css,
        f"<h2>{tr('MALDI Polymer Composition Solver (MPCS) 이용 안내')}</h2>",
        f"<p>{tr('MPCS는 고분자 MALDI-TOF·LC-MS 피크의 질량으로부터 어떤 모노머가 몇 개 결합했는지(조성)를 계산하고, 주기적으로 나타나는 피크에서 반복 수가 연속되는 조성 계열을 찾아 가능성이 높은 조성을 알려줍니다.')}</p>",
        _section(tr("화면 구성"), [
            (tr("명령 막대:"), tr("맨 위 한 줄. [파일·분석·도움말] 메뉴, 프로젝트 열기/저장, 스펙트럼 열기, [솔버 실행] (F5), 중단, 내보내기, 화면 언어(KO/EN).")),
            (tr("입력 패널 (왼쪽):"), tr("모노머 / 제약식 / 말단기·어덕트 / 데이터·설정 / 중합 계산기 탭. Ctrl+B 또는 [입력 패널] 버튼으로 접어 결과 화면을 넓게 쓸 수 있습니다.")),
            (tr("결과 (오른쪽):"), tr("요약 띠(최상위 조성 계열) → 스펙트럼 → 피크 목록 → 후보 조성 / 조성 계열 / KMD / 메시지 탭.")),
        ]),
        _section(tr("1단계: 모노머 등록"), [
            (tr("일반 모노머:"), tr("이름과 분자식(예: LA, C3H4O2)을 입력하면 정밀질량과 평균질량을 자동 계산합니다.")),
            (tr("질량 직접 입력:"), tr("분자식을 모르면 분자식 칸에 질량을 숫자로 입력합니다 (예: 100.5). 이 경우 후보의 분자식은 표시되지 않습니다.")),
            (tr("블록(Block):"), tr("여러 성분이 묶인 반복 단위(예: PLA-PEG-PLA)는 유형을 블록으로 추가한 뒤, 블록을 선택한 상태에서 하위 성분을 추가합니다.")),
            (tr("최소값/최대값:"), tr("솔버가 탐색할 개수 범위입니다. 범위가 좁을수록 빠릅니다. 중합 계산기로 예상 범위를 자동으로 채울 수 있습니다.")),
        ]),
        _section(tr("2단계: 말단기·어덕트"), [
            (tr("말단기:"), tr("사슬 양 끝 원자단을 '/'로 구분해 고릅니다 (예: H/OH = H₂O, 기본값 OH/OH = H₂O₂).")),
            (tr("어덕트:"), tr("이온화될 때 붙는 이온([M+Na]⁺, [M+K]⁺, [M+H]⁺ …)을 체크합니다. 체크한 어덕트마다 후보를 계산합니다.")),
        ]),
        _section(tr("3단계: 제약식 (선택)"), [
            (tr("등식:"), tr("<code>HDI = PLA + SMA - 1</code> 처럼 '이름 = 식'이면 그 모노머 개수를 식으로 계산해 탐색을 크게 줄입니다.")),
            (tr("부등식·질량 참조:"), tr("<code>LA &gt;= 10</code>, <code>EO * EO.mw &lt;= 3000</code> 처럼 범위를 제한할 수 있습니다.")),
        ]),
        _section(tr("4단계: 피크 입력"), [
            (tr("질량값 목록:"), tr("오른쪽 피크 목록에 m/z를 직접 입력하거나, 엑셀에서 복사해 [붙여넣기], 또는 [가져오기]로 xlsx/csv를 읽습니다.")),
            (tr("원본 스펙트럼:"), tr("[데이터/설정] 탭에서 mzXML을 열고 측정 모드 프리셋(Reflectron·LC-MS / Linear)을 고른 뒤 [피크 검출]을 누릅니다. 프리셋은 질량 기준과 허용 오차도 맞춥니다.")),
            (tr("주기 시리즈:"), tr("모노머 질량 간격으로 이어지는 피크는 시리즈(S1, S2 …)로 색이 표시됩니다. [주기 시리즈 피크만]을 켜면 시리즈 피크만 솔버에 씁니다.")),
        ]),
        _section(tr("5단계: 솔버 실행과 결과 해석"), [
            (tr("실행:"), tr("[솔버 실행] (F5)을 누르면 목록의 모든 피크를 한 번에 계산합니다.")),
            (tr("피크 선택:"), tr("피크 목록의 행이나 스펙트럼의 피크를 누르면 [후보 조성]에 그 피크의 후보가 나옵니다.")),
            (tr("확률과 조성 계열:"), tr("같은 계열(한 모노머만 1개씩 늘고 나머지 조성·어덕트가 같은 후보)이 많은 피크를 연속으로, 작은 오차로 설명할수록 확률이 높습니다. 후보를 고르면 같은 계열 피크가 스펙트럼에 ▲와 반복 수로 표시됩니다.")),
            (tr("동위원소 패턴:"), tr("후보 행을 두 번 누르면 그 이온의 이론 동위원소 패턴을 볼 수 있습니다.")),
            (tr("내보내기:"), tr("[내보내기] → 전체 결과는 피크 요약·전체 후보·조성 계열을 엑셀 시트로 저장합니다.")),
        ]),
        _section(tr("측정 모드별 권장 설정"), [
            (tr("Reflectron / 고분해능 LC-MS:"), tr("질량 기준 모노이소토픽(Exact), 허용 오차 0.01–0.05 Da, 동위원소 정리 '모노이소토픽만'.")),
            (tr("Linear (동위원소 미분리):"), tr("질량 기준 평균 질량(Average), 허용 오차 0.5–2 Da. 거의 같은 질량의 다른 조성(예: Na⁺ vs K⁺−O)은 확률이 나뉘어 표시됩니다.")),
        ]),
    ]
    return "".join(parts)


class GuideDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("이용 안내"))
        self.resize(780, 620)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(guide_html())
        layout.addWidget(browser)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
