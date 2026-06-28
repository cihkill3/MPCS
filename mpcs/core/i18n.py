"""
MPCS — I18n (다국어 지원)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

# 기본 사전 경로
_DICT_PATH = Path(__file__).parent.parent / "assets" / "i18n" / "dictionary.json"


class I18nManager:
    """
    단어 사전(JSON)을 기반으로 다국어 번역을 제공하는 싱글톤 매니저.
    기본 한국어 텍스트를 키(Key)로 사용합니다.
    """
    _instance: I18nManager | None = None

    def __init__(self) -> None:
        self.lang = "ko"  # 기본 언어
        self.dictionary: dict[str, dict[str, str]] = {}
        self._load_dictionary()

    @classmethod
    def get_instance(cls) -> I18nManager:
        if cls._instance is None:
            cls._instance = I18nManager()
        return cls._instance

    def _load_dictionary(self) -> None:
        if not _DICT_PATH.exists():
            logging.warning(f"사전 파일을 찾을 수 없습니다: {_DICT_PATH}")
            return
        try:
            data = json.loads(_DICT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.dictionary = data
        except Exception as e:
            logging.error(f"사전 파일 로드 중 오류: {e}")

    def set_language(self, lang: str) -> None:
        if lang in ["ko", "en"]:
            self.lang = lang

    def translate(self, text: str, **kwargs: Any) -> str:
        """
        주어진 텍스트(한국어 기준)를 현재 언어로 번역하여 반환합니다.
        키가 없으면 원본 텍스트를 그대로 반환합니다.
        kwargs가 주어지면 Python format 문자열로 취급하여 포맷팅합니다.
        """
        # 한국어면 원본 그대로 반환 (포맷팅은 수행)
        if self.lang == "ko":
            translated = text
        else:
            # 영어일 경우 사전에서 탐색
            entry = self.dictionary.get(text)
            if entry and self.lang in entry:
                translated = entry[self.lang]
            else:
                translated = text  # 번역이 없으면 원본 반환
        
        if kwargs:
            try:
                return translated.format(**kwargs)
            except Exception:
                return translated
        return translated


def tr(text: str, **kwargs: Any) -> str:
    """I18nManager의 translate 편의 함수."""
    return I18nManager.get_instance().translate(text, **kwargs)
