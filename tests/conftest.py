"""테스트 공통 설정: 사용자 설정 폴더(~/.mpcs)를 건드리지 않도록 임시 폴더로 바꾸고, Qt는 offscreen으로."""

import os
import tempfile

os.environ.setdefault("QT_API", "pyqt5")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MPCS_CONFIG_DIR"] = tempfile.mkdtemp(prefix="mpcs_test_cfg_")
