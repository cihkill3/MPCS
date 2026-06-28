"""
MPCS — Core: Formatting
"""

import re
from qtpy.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle
from qtpy.QtGui import QTextDocument, QAbstractTextDocumentLayout
from qtpy.QtCore import Qt, QSize, QRectF

def format_formula_html(formula: str) -> str:
    """분자식 문자열(예: 'C458H755') 내의 숫자를 HTML 아래첨자로 변환."""
    if not formula:
        return formula
    # 양수 및 음수 숫자 매칭
    return re.sub(r'([0-9]+)', r'<sub><font size="+1">\1</font></sub>', formula)

def format_adduct_html(adduct: str) -> str:
    """
    어덕트 텍스트(예: '[M+NH4]+' 또는 '[M+2H]2+')를 HTML 첨자로 변환.
    - '[...]' 내부의 숫자는 아래첨자로 변환(단, 원소 앞의 숫자는 제외 가능하지만 여기서는 NH4처럼 대문자 뒤의 숫자를 아래첨자로)
    - 닫는 괄호 ']' 뒤의 전하 기호(+, 2+, 3+, -, 2- 등)는 위첨자로 변환.
    """
    if not adduct:
        return adduct

    # 1. 괄호 뒤의 전하를 위첨자로 변환
    # ] 뒤에 오는 +, -, 숫자+, 숫자- 등
    adduct = re.sub(r'\]([0-9]*[+-]+)$', r']<sup><font size="+1">\1</font></sup>', adduct)

    # 2. 내부 숫자를 아래첨자로 (주로 NH4, Na, K 등 뒤에 붙는 숫자)
    # 간단히 알파벳(대소문자) 바로 뒤에 붙는 숫자를 아래첨자로 처리
    # '[M+2H]'의 '2'는 알파벳 앞이므로 매치 안 되도록 하려면 (?<=[A-Za-z]) 사용
    adduct = re.sub(r'(?<=[A-Za-z])([0-9]+)', r'<sub><font size="+1">\1</font></sub>', adduct)
    
    return adduct

def to_unicode_subsup(text: str) -> str:
    """
    일반 UI 위젯(QCheckBox 등)을 위해 분자식 및 전하 기호를 유니코드 첨자로 변환.
    """
    if not text:
        return text
    
    subscripts = {'0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
                  '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉'}
    superscripts = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
                    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
                    '+': '⁺', '-': '⁻'}
    
    # 1. ']' 뒤의 전하 기호를 위첨자로
    def sup_repl(m):
        return ']' + ''.join(superscripts.get(c, c) for c in m.group(1))
    text = re.sub(r'\]([0-9]*[+-]+)$', sup_repl, text)
    
    # 2. 내부 숫자를 아래첨자로
    def sub_repl(m):
        return ''.join(subscripts.get(c, c) for c in m.group(1))
    text = re.sub(r'(?<=[A-Za-z])([0-9]+)', sub_repl, text)
    
    return text

class HtmlDelegate(QStyledItemDelegate):
    """
    QTableWidget/QTreeWidget 등에서 HTML 텍스트를 렌더링하는 델리게이트.
    편집 시에는 원래 문자열(ASCII)을 유지함.
    """
    def __init__(self, parent=None, formatter=None):
        super().__init__(parent)
        self.formatter = formatter or (lambda x: x)

    def paint(self, painter, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)

        painter.save()
        doc = QTextDocument()
        doc.setDocumentMargin(2)
        doc.setDefaultFont(options.font)
        
        # 원본 텍스트를 포매터로 변환
        raw_text = options.text
        html_text = self.formatter(raw_text) if isinstance(raw_text, str) and not raw_text.startswith("~") else raw_text
        doc.setHtml(html_text)

        options.text = ""
        style = options.widget.style() if options.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, options, painter, options.widget)

        # 텍스트 수직 중앙 정렬 조정
        ctx = QAbstractTextDocumentLayout.PaintContext()
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, options, options.widget)
        painter.translate(text_rect.left(), text_rect.top() + (text_rect.height() - doc.size().height()) / 2)
        clip = QRectF(0, 0, text_rect.width(), text_rect.height())
        doc.drawContents(painter, clip)
        painter.restore()

    def sizeHint(self, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        doc = QTextDocument()
        doc.setDefaultFont(options.font)
        doc.setDocumentMargin(2)
        raw_text = options.text
        html_text = self.formatter(raw_text) if isinstance(raw_text, str) and not raw_text.startswith("~") else raw_text
        doc.setHtml(html_text)
        return QSize(int(doc.idealWidth()), int(doc.size().height()))