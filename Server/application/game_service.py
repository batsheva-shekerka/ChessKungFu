from __future__ import annotations

import os
import sys
from typing import Any, Callable, Optional

# Ensure project root is importable for GameEngine
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_SERVER_DIR, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from controller.controller import Controller
from chess_io.board_parser import BoardParser
from domain import events
from engine.game_engine import GameEngine
from infrastructure.async_event_bus import AsyncEventBus
from infrastructure.db.user_repository import UserRepository
from infrastructure.logging.error_logger import ServerLogger
from model.position import Position


BroadcastFn = Callable[[str, str], Any]  # room_id, encoded_message


def _load_board_from_input(root: str):
    input_path = os.path.join(root, "input.txt")
    with open(input_path, encoding="utf-8") as f:
        lines = f.readlines()

    board_lines = []
    in_board = False
    for line in lines:
        cleaned = line.strip()
        if cleaned == "Board:":
            in_board = True
            continue
        if cleaned.startswith("Commands:"):
            break
        if in_board and cleaned:
            board_lines.append(line)
    return BoardParser.parse_initial_board(board_lines)


class GameService:
    TICK_MS = 50

    def __init__(
        self,
        project_root: str,
        users: UserRepository,
        bus: AsyncEventBus,
        logger: ServerLogger,
        get_room_players: Callable[[str], tuple[Optional[str], Optional[str], Optional[str], Optional[str]]],
        is_elo_updated: Callable[[str], bool],
        mark_elo_updated: Callable[[str], None],
        broadcast_room: BroadcastFn,
    ):
        self._root = project_root
        self._users = users
        self._bus = bus
        self._logger = logger
        self._engines: dict[str, GameEngine] = {}
        self._get_room_players = get_room_players
        self._is_elo_updated = is_elo_updated
        self._mark_elo_updated = mark_elo_updated
        self._broadcast_room = broadcast_room

    def create_engine_for_room(self, room_id: str) -> GameEngine:
        board = _load_board_from_input(self._root)
        engine = GameEngine(board)
        self._engines[room_id] = engine
        return engine

    def get_engine(self, room_id: str) -> Optional[GameEngine]:
        return self._engines.get(room_id)

    def remove_engine(self, room_id: str) -> None:
        self._engines.pop(room_id, None)

    def handle_move(
        self,
        room_id: str,
        user_id: str,
        color: str,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> tuple[bool, str]:
        engine = self._engines.get(room_id)
        if engine is None:
            return False, "no active game"
        if engine.game_over:
            return False, "game already over"

        start_pos = Position(start[0], start[1])
        end_pos = Position(end[0], end[1])
        piece = engine.board.get_piece(start_pos)
        if piece is None or piece.color != color:
            return False, "not your piece"

        duration = Controller._duration(start_pos, end_pos)
        ok = engine.handle_move_request(start_pos, end_pos, duration)
        if not ok:
            return False, "illegal move"
        return True, "ok"

    def build_state_dict(self, room_id: str) -> dict[str, Any]:
        engine = self._engines[room_id]
        pieces = []
        for pos, piece in engine.board.get_all_pieces().items():
            pieces.append({
                "row": pos.row,
                "col": pos.col,
                "color": piece.color,
                "type": piece.piece_type,
                "status": piece.status.name,
            })
        return {
            "type": "state",
            "room_id": room_id,
            "pieces": pieces,
            "score": {
                "w": engine.scoreboard.plaier1_score,
                "b": engine.scoreboard.plaier2_score,
            },
            "game_over": engine.game_over,
            "winner": engine.winner,
        }

    async def tick_all(self, encode_fn, make_game_over_fn) -> None:
        for room_id, engine in list(self._engines.items()):
            had_motions = engine.arbiter.has_active_motion()
            engine.update_game_clock(self.TICK_MS)
            finished_now = had_motions and not engine.arbiter.has_active_motion()
            if finished_now:
                await self._broadcast_room(room_id, encode_fn(self.build_state_dict(room_id)))

            if engine.game_over and not self._is_elo_updated(room_id):
                await self._apply_elo(room_id, engine, encode_fn, make_game_over_fn)

    async def force_forfeit(
        self,
        room_id: str,
        loser_user_id: str,
        encode_fn,
        make_game_over_fn,
    ) -> None:
        engine = self._engines.get(room_id)
        if engine is None or engine.game_over:
            return
        white_id, black_id, _, _ = self._get_room_players(room_id)
        if loser_user_id == white_id:
            engine.winner = "b"
        elif loser_user_id == black_id:
            engine.winner = "w"
        else:
            return
        engine.game_over = True
        await self._apply_elo(room_id, engine, encode_fn, make_game_over_fn)

    async def _apply_elo(self, room_id: str, engine: GameEngine, encode_fn, make_game_over_fn) -> None:
        if self._is_elo_updated(room_id):
            return
        if engine.winner not in ("w", "b"):
            return

        white_id, black_id, white_name, black_name = self._get_room_players(room_id)
        if not white_id or not black_id or not white_name or not black_name:
            return

        white_user = self._users.get_by_id(white_id)
        black_user = self._users.get_by_id(black_id)
        if white_user is None or black_user is None:
            return

        if engine.winner == "w":
            new_white, new_black = UserRepository.calc_elo(white_user.elo, black_user.elo)
        else:
            new_black, new_white = UserRepository.calc_elo(black_user.elo, white_user.elo)

        self._users.set_elo(white_id, new_white)
        self._users.set_elo(black_id, new_black)
        self._mark_elo_updated(room_id)

        ratings = {white_name: new_white, black_name: new_black}
        payload = make_game_over_fn(engine.winner, ratings)
        payload["room_id"] = room_id
        await self._broadcast_room(room_id, encode_fn(payload))
        await self._bus.publish(
            events.GAME_OVER,
            room_id=room_id,
            winner=engine.winner,
            ratings=ratings,
        )
        self._logger.info("ELO updated", room_id=room_id, ratings=ratings)
