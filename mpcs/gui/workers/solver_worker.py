"""
MPCS — MALDI Polymer Composition Solver
GUI Workers: Solver QThread Worker

SRS §21 Performance:
    솔버는 GUI 스레드를 블로킹하지 않아야 한다.
    QThread를 통해 백그라운드에서 실행.
"""

from __future__ import annotations

from qtpy.QtCore import QThread, Signal

from mpcs.models.result import RankedResultSet
from mpcs.services.solver_service import SolverParams, SolverService


class SolverWorker(QThread):
    """
    백그라운드 솔버 QThread.

    Signals:
        progress(current, total): 진행 상황 업데이트
        finished(RankedResultSet): 솔버 완료
        error(str): 오류 발생
    """

    progress = Signal(int, int, int)   # (현재, 유효조합 수, 전체조합 수)
    finished = Signal(object)          # RankedResultSet
    error = Signal(str)                # 오류 메시지

    def __init__(
        self,
        solver: SolverService,
        params: SolverParams,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._solver = solver
        self._params = params
        self._cancelled = False

    def cancel(self) -> None:
        """솔버 실행을 취소한다."""
        self._cancelled = True

    def run(self) -> None:
        """솔버를 백그라운드에서 실행한다."""
        try:
            result = self._solver.solve(
                self._params,
                progress_callback=self._on_progress,
                cancel_flag=self._is_cancelled,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_progress(self, current: int, valid_total: int, all_total: int) -> None:
        self.progress.emit(current, valid_total, all_total)

    def _is_cancelled(self) -> bool:
        return self._cancelled


class BatchSolverWorker(QThread):
    """
    여러 피크 일괄 솔버 + 조성 계열 점수화 QThread.

    Signals:
        progress(processed, valid, total)
        finished(result_sets, families)
        error(str)
    """

    progress = Signal(object, object, object)   # 32비트 int 초과 조합 수 대응
    finished = Signal(object, object)   # list[RankedResultSet], list[CompositionFamily]
    error = Signal(str)

    def __init__(
        self,
        solver: SolverService,
        peaks: list[float],
        params: SolverParams,
        repeat_names: list[str],
        max_results: int = 1000,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._solver = solver
        self._peaks = peaks
        self._params = params
        self._repeat_names = repeat_names
        self._max_results = max_results
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from mpcs.services.series_analysis import score_families

        try:
            results = self._solver.solve_batch(
                self._peaks, self._params, self._max_results,
                progress_callback=lambda a, b, c: self.progress.emit(a, b, c),
                cancel_flag=lambda: self._cancelled,
            )
            families = score_families(results, self._repeat_names, self._params.tolerance_da)
            self.finished.emit(results, families)
        except Exception as exc:
            self.error.emit(str(exc))
