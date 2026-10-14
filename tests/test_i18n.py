"""
다국어 검사: 코드의 모든 tr() 키에 영어가 있고, 자리표시자가 같으며, GUI에 tr() 밖 한국어가 없다.
이온 표기 위첨자 변환도 확인한다.
"""

from __future__ import annotations

import ast
import json
import re
import string
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DICT = json.loads((ROOT / "mpcs/assets/i18n/dictionary.json").read_text(encoding="utf-8"))
KOR = re.compile(r"[가-힣]")


def _py_files(sub: str) -> list[Path]:
    return sorted((ROOT / sub).rglob("*.py"))


def _tr_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    for f in _py_files("mpcs") + [ROOT / "main.py"]:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    keys.setdefault(a.value, f"{f.relative_to(ROOT)}:{node.lineno}")
    return keys


def _fields(s: str) -> set[tuple[str, str]]:
    return {(n, spec or "") for _l, n, spec, _c in string.Formatter().parse(s) if n is not None}


def test_every_tr_key_has_english():
    missing = {k: where for k, where in _tr_keys().items() if not DICT.get(k, {}).get("en")}
    assert not missing, f"영어 번역 없음 {len(missing)}개: {list(missing.items())[:10]}"


def test_dictionary_placeholders_match():
    bad = [k for k, v in DICT.items() if v.get("en") and _fields(k) != _fields(v["en"])]
    assert not bad, bad[:10]


# tr() 밖에 남아도 되는 한국어 (사용자에게 보이지 않거나 번역 대상이 아님)
_ALLOWED = (
    "가-힣",          # 이름 검증 정규식
    "한국어",         # 언어 메뉴: 각 언어 고유 이름
)


def test_gui_has_no_untranslated_korean():
    found = []
    for f in _py_files("mpcs/gui") + [ROOT / "main.py"]:
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        skip = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr":
                skip.update(id(n) for n in ast.walk(node))
            if isinstance(node, ast.Expr) and isinstance(node.value, (ast.Constant, ast.JoinedStr)):
                skip.update(id(n) for n in ast.walk(node))      # docstring / 속성 설명
        for node in ast.walk(tree):
            if id(node) in skip or not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if KOR.search(node.value) and not any(a in node.value for a in _ALLOWED):
                if f.name == "theme.py":           # QSS 안의 주석
                    continue
                found.append(f"{f.relative_to(ROOT)}:{node.lineno}: {node.value[:40]!r}")
    assert not found, found


def test_english_translation_applies():
    from mpcs.core.i18n import I18nManager, tr

    mgr = I18nManager.get_instance()
    old = mgr.lang
    try:
        mgr.set_language("en")
        assert tr("솔버 실행") == "Run solver"
        assert tr("피크 {n}개 검출", n=3) == "Peaks detected: 3"
        mgr.set_language("ko")
        assert tr("피크 {n}개 검출", n=3) == "피크 3개 검출"
    finally:
        mgr.set_language(old)


@pytest.mark.parametrize("raw, shown", [
    ("[M+Na]+", "[M+Na]⁺"),
    ("[M+2H]2+", "[M+2H]²⁺"),
    ("[M+NH4]+", "[M+NH₄]⁺"),
    ("[M-H]-", "[M-H]⁻"),
    ("EO n=15–59 · LA5 · [M+Na]+ (+1 iso)", "EO n=15–59 · LA5 · [M+Na]⁺ (+1 iso)"),
])
def test_ion_text_superscript(raw, shown):
    from mpcs.core.formatting import ion_text

    assert ion_text(raw) == shown
