from __future__ import annotations

import os
import sys
from typing import Any, Optional

_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ROOT = os.path.abspath(os.path.join(_SERVER_DIR, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from application.ports import GameEngineFactory, GameEnginePort
from domain.models import PlayerRole
from engine.game_engine import GameEngine
from infrastructure.game.board_loader import InputTxtBoardLoader
from model.board import Board
from model.position import Position
from protocol import PieceSnapshot, StateMessage

MS_PER_CELL = 1000


def chebyshev_duration_ms(start: Position, end: Position) -> int:
    dr = abs(end.row - start.row)
    dc = abs(end.col - start.col)
    return max(dr, dc) * MS_PER_CELL


class KungFuEngineAdapter:
    """Infrastructure adapter: wraps root GameEngine behind GameEnginePort."""

    def __init__(self, board: Board):
        self._engine = GameEngine(board)

    def try_player_move(
        self,
        color: str,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> tuple[bool, str]:
        if self._engine.game_over:
            return False, "game already over"

        start_pos = Position(start[0], start[1])
        end_pos = Position(end[0], end[1])
        piece = self._engine.board.get_piece(start_pos)
        if piece is None or piece.color != color:
            return False, "not your piece"

        duration = chebyshev_duration_ms(start_pos, end_pos)
        ok = self._engine.handle_move_request(start_pos, end_pos, duration)
        if not ok:
            return False, "illegal move"
        return True, "ok"

    def update_game_clock(self, ms: int) -> None:
        self._engine.update_game_clock(ms)

    def has_active_motion(self) -> bool:
        return self._engine.arbiter.has_active_motion()

    def force_forfeit(self, winner_color: str) -> None:
        if self._engine.game_over:
            return
        self._engine.winner = winner_color
        self._engine.game_over = True

    def snapshot_state(self, room_id: str) -> dict[str, Any]:
        engine = self._engine
        pieces = [
            PieceSnapshot(
                row=pos.row,
                col=pos.col,
                color=piece.color,
                type=piece.piece_type,
                status=piece.status.name,
            )
            for pos, piece in engine.board.get_all_pieces().items()
        ]
        return StateMessage(
            pieces=pieces,
            score={
                PlayerRole.WHITE.value: engine.scoreboard.plaier1_score,
                PlayerRole.BLACK.value: engine.scoreboard.plaier2_score,
            },
            game_over=engine.game_over,
            winner=engine.winner,
            room_id=room_id,
        ).to_dict()

    @property
    def game_over(self) -> bool:
        return bool(self._engine.game_over)

    @property
    def winner(self) -> Optional[str]:
        return self._engine.winner


class KungFuEngineFactory:
    def __init__(self, board_loader: InputTxtBoardLoader):
        self._loader = board_loader

    def create(self) -> GameEnginePort:
        return KungFuEngineAdapter(self._loader.load())
