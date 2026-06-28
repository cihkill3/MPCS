# 전체적인 UI 세련화, 다국어 지원, 이용 안내 메뉴 구현 계획

사용자 요청 사항 3가지를 구현하기 위한 세부 계획입니다.

## 1. UI 세련화 (Modern Theming)
- `mpcs/gui/theme.py`를 신규 생성하여 모던하고 세련된 QSS (Qt Style Sheet)를 작성합니다.
- Flat 디자인, 둥근 모서리(Border-radius), 세련된 색상 조합(Primary Color: Blue/Indigo), 뚜렷한 여백과 그림자 효과를 적용합니다.
- `main.py`에서 애플리케이션 시작 시 해당 테마를 전역으로 적용합니다.
- 스플리터, 버튼, 그룹박스, 스크롤바, 테이블 뷰 등의 스타일을 현대적으로 변경합니다.

## 2. 언어 변경(다국어 지원) 및 단어 사전 구현
- **사전 파일 (`mpcs/assets/i18n/dictionary.json`)**: 
  향후 확장이 용이하도록 JSON 기반의 단어 사전을 만듭니다. 구조는 다음과 같습니다:
  ```json
  {
      "menu_file": {"ko": "파일(&F)", "en": "File(&F)"},
      "menu_settings": {"ko": "설정(&O)", "en": "Settings(&O)"},
      ...
  }
  ```
- **번역 모듈 (`mpcs/core/i18n.py`)**: 
  앱 내 어디서든 `from mpcs.core.i18n import tr`를 통해 손쉽게 번역된 텍스트를 가져올 수 있는 유틸리티를 구현합니다.
- **설정 저장 (`mpcs/infrastructure/config_manager.py`)**:
  선택된 언어 상태(ko/en)를 파일에 저장하여 다음 실행 시 유지되도록 합니다.
- **UI 리팩토링**:
  주요 텍스트를 모두 `tr()` 함수로 감싸 다국어가 지원되도록 수정합니다. 언어 변경 시 프로그램 재시작을 요구하는 안내를 표시하고 상태를 저장합니다.

## 3. 도움말 > 이용 안내 다이얼로그 추가
- `mpcs/gui/dialogs/guide_dialog.py`를 생성합니다.
- 다이얼로그 내부에 QTextBrowser를 사용하여 자세한 사용법(모노머 탭, 중합 계산기, 솔버 등)을 마크다운/HTML 형태로 가독성 있게 제공합니다.
- `main_window.py`의 도움말 메뉴에 "이용 안내(&G) / User Guide" 액션을 추가하여 연결합니다.

## User Review Required
> [!IMPORTANT]  
> 다국어 지원을 위해 UI 코드 내 수백 개의 하드코딩된 한국어 문자열(버튼 이름, 라벨, 테이블 헤더 등)을 일일이 식별하여 사전 파일에 등록하고 코드에서 `tr()`로 교체하는 작업이 수반됩니다.
> UI 텍스트 전면 교체 과정에서 대규모 코드 수정이 발생함을 양지해주시기 바랍니다.

## Open Questions
> [!NOTE]  
> 1. 테마 적용 시 선호하시는 컬러(예: 다크 모드, 라이트 모드(기본), 특정 포인트 컬러)가 있으신가요? 기본적으로는 밝고 세련된 라이트 모드(푸른 계열의 Accent Color)로 설계할 예정입니다.
> 2. 언어 변경은 구조상 런타임에 즉시 모든 텍스트를 바꾸기 어려워 **"언어 변경 후 앱 재시작(Restart)"** 을 요구하는 방식으로 구현하는 것이 일반적인데, 이 방식이 괜찮으신가요?

## Proposed Changes

### Configuration & Core
#### [NEW] `mpcs/assets/i18n/dictionary.json`
- 모든 UI 문자열의 ko, en 매핑 데이터 저장
#### [NEW] `mpcs/core/i18n.py`
- 언어 설정 로드 및 `tr(key)` 번역 함수 제공
#### [MODIFY] `mpcs/infrastructure/config_manager.py`
- 현재 선택된 언어를 저장/불러오는 기능 추가

### UI Design (Theming)
#### [NEW] `mpcs/gui/theme.py`
- 모던 QSS 테마 정의
#### [MODIFY] `main.py`
- 전역 QSS 테마 및 언어(i18n) 모듈 초기화 로직 추가

### GUI Refactoring (Applying i18n & Adding Guide)
#### [NEW] `mpcs/gui/dialogs/guide_dialog.py`
- 이용 안내 정보를 보여주는 다이얼로그 위젯
#### [MODIFY] `mpcs/gui/main_window.py`
- 다국어 `tr()` 적용 및 "이용 안내" 메뉴 연결, 언어 변경 메뉴 로직 수정 (재시작 알림)
#### [MODIFY] `mpcs/gui/panels/monomer_panel.py` 외 기타 Panel/Dialog 7개
- 하드코딩된 한국어 텍스트들을 전부 `tr()`로 교체

## Verification Plan
1. 애플리케이션을 실행하여 전반적인 테마(버튼, 테이블, 그룹박스 스타일)가 세련되게 적용되었는지 시각적으로 확인합니다.
2. '설정 -> 언어'에서 언어를 변경하고, 설정 파일(config)에 저장되는지 확인한 뒤 재시작하여 텍스트가 영어/한국어로 제대로 바뀌는지 검증합니다.
3. '도움말 -> 이용 안내'를 클릭하여 사용 방법 가이드가 표시되는지 확인합니다.
