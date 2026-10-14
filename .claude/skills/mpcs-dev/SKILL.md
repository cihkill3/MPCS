---
name: mpcs-dev
description: Use when writing, testing, or running code in the MPCS (MALDI Polymer Composition Solver) repo — how to run pytest and the GUI with the project venv, the layer layout (models/services/infrastructure/gui), and the coding conventions (qtpy, tr() i18n, Korean docstrings with SRS refs) new code must follow.
---

# MPCS development workflow

## Environment
- Python venv: `.venv2` (Python 3.12). Always call `.venv2/Scripts/python.exe`, never the system `python` (it is 3.14 and lacks deps).
- Qt binding: PyQt5 through `qtpy`. Set `QT_API=pyqt5` before any Qt import. Do not add direct `PyQt5`/`PySide6` imports; import from `qtpy`. Plots use `pyqtgraph`.

## Commands (Git Bash)
```bash
# tests (fast, no GUI)
QT_API=pyqt5 .venv2/Scripts/python.exe -m pytest -q
# single file / keyword
QT_API=pyqt5 .venv2/Scripts/python.exe -m pytest tests/test_solver_service.py -q -k batch
# launch GUI
QT_API=pyqt5 .venv2/Scripts/python.exe main.py      # or run.bat
# install a new dependency, then add it to requirements.txt
.venv2/Scripts/python.exe -m pip install scipy
```

## Layer rules
| Layer | Path | May import |
|---|---|---|
| core (pure calc, formula, i18n) | `mpcs/core/` | stdlib, numpy, molmass |
| models (dataclasses, validate()) | `mpcs/models/` | core |
| services (solver, constraints, spectrum processing, scoring) | `mpcs/services/` | core, models. **Never Qt.** |
| infrastructure (file I/O, serializer, config) | `mpcs/infrastructure/` | core, models |
| gui (panels, views, dialogs, QThread workers) | `mpcs/gui/` | everything |

- Put numeric and algorithmic code in `services/` so it can be unit-tested without Qt. GUI workers only adapt progress/cancel callbacks to Qt signals (see `mpcs/gui/workers/solver_worker.py`).
- `AdductPanel` and `SolverControlPanel` (solver settings form, shown at the top of the Data/Settings tab) live in `mpcs/gui/panels/end_group_panel.py` (same-named files are re-export shims). Give new panels their own module.
- Analysis flow: `SpectrumPanel` (left tab: mzXML → `pick_peaks`) → `AnalysisView` (right: peak list master ↔ spectrum plot ↔ candidate/family/KMD tabs) → `BatchSolverWorker` (`solve_batch` + `score_families`).
- Screenshots offscreen: `QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts` (without FONTDIR no text renders). Demo data: `examples/make_demo_data.py`.
- `Project` changes require matching updates to `infrastructure/project_serializer.py`, kept backward-compatible with existing `.mpcs` files (bump the format version and default any missing keys).

## Conventions
- Module docstring header: `MPCS — MALDI Polymer Composition Solver` / `<Layer>: <Name>`, with SRS section refs where relevant.
- Docstrings and comments in Korean, identifiers in English, type hints with `from __future__ import annotations`.
- All user-visible strings go through `tr("한국어 원문", name=value)` from `mpcs.core.i18n` — whole sentences with `{placeholders}`, never concatenated fragments. Add the English entry to `mpcs/assets/i18n/dictionary.json` (placeholders must match). `tests/test_i18n.py` fails on any missing key or untranslated Korean literal in `mpcs/gui`.
- Language switches instantly (command bar KO/EN): `MainWindow.request_language_change` rebuilds the window and moves state via `_capture_state`/`_apply_state` (panels expose `get_state`/`set_state`). New stateful widgets must join that path.
- UI kit (copied from PepLCMS, maintained independently): `mpcs/gui/theme.py` tokens + `apply_theme`, `icons.py` (Lucide SVG in `mpcs/assets/icons`), `command_bar.py`, `side_rail.py`, `widgets.py` (`caption`, `set_role`, `set_header_tooltips`, `fit_header`). No hex colors in view code — use theme tokens / QSS role names. Every input and table column gets a tooltip.
- Ion labels shown to users go through `formatting.ion_text()` (charge as superscript: [M+Na]⁺); keep raw ASCII labels in data and exports.
- Tests use `tests/conftest.py` (offscreen Qt, temporary `MPCS_CONFIG_DIR`) so the real `~/.mpcs` settings are never touched. Build: `build_exe.bat`.
- Long work runs in a `QThread` worker with `progress`/`finished`/`error` signals and a cancel flag. Never block the GUI thread.
- Multiprocessing on Windows: worker functions must be top-level (picklable), and `main.py` must call `multiprocessing.freeze_support()` (PyInstaller build via `MPCS.spec`).

## Before finishing a change
1. Run pytest (all green).
2. If the solver changed, run the `mpcs-solver-bench` skill (equivalence + timing).
3. If the GUI changed, launch the app and exercise the feature.
