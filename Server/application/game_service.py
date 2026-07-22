from __future__ import annotations

from typing import Any, Callable, Optional

from application.dto import MoveOutcome
from application.ports import (
    AppLogger,
    EventPublisher,
    GameEngineFactory,
    GameEnginePort,
    UserStore,
)
from application.room_service import RoomService
from domain.elo import calc_elo
from domain.events import EventType
from domain.models import PlayerRole


BroadcastFn = Callable[[str, str], Any]  # room_id, encoded_message


class GameService:
    TICK_MS = 50

    def __init__(
        self,
        users: UserStore,
        bus: EventPublisher,
        logger: AppLogger,
        rooms: RoomService,
        engine_factory: GameEngineFactory,
        get_room_players: Callable[
            [str], tuple[Optional[str], Optional[str], Optional[str], Optional[str]]
        ],
        is_elo_updated: Callable[[str], bool],
        mark_elo_updated: Callable[[str], None],
        broadcast_room: BroadcastFn,
    ):
        self._users = users
        self._bus = bus
        self._logger = logger
        self._rooms = rooms
        self._engine_factory = engine_factory
        self._engines: dict[str, GameEnginePort] = {}
        self._get_room_players = get_room_players
        self._is_elo_updated = is_elo_updated
        self._mark_elo_updated = mark_elo_updated
        self._broadcast_room = broadcast_room

    def create_engine_for_room(self, room_id: str) -> GameEnginePort:
        engine = self._engine_factory.create()
        self._engines[room_id] = engine
        return engine

    def get_engine(self, room_id: str) -> Optional[GameEnginePort]:
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
        return engine.try_player_move(color, start, end)

    async def submit_move(
        self,
        user_id: str,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> MoveOutcome:
        room_id = self._rooms.room_id_for_user(user_id)
        if room_id is None:
            return MoveOutcome(ok=False, reason="not in a room")

        role = self._rooms.member_role(room_id, user_id)
        if role is None or role == PlayerRole.VIEWER:
            return MoveOutcome(ok=False, reason="viewers cannot move")

        color = (
            PlayerRole.WHITE.value
            if role == PlayerRole.WHITE
            else PlayerRole.BLACK.value
        )
        ok, reason = self.handle_move(room_id, user_id, color, start, end)
        if not ok:
            return MoveOutcome(ok=False, reason=reason)

        await self._bus.publish(
            EventType.PLAYER_MOVE.value,
            room_id=room_id,
            user_id=user_id,
            start=start,
            end=end,
        )

        room = self._rooms.get_room(room_id)
        member_ids = list(room.members.keys()) if room else []
        return MoveOutcome(
            ok=True,
            room_id=room_id,
            start=start,
            end=end,
            member_ids=member_ids,
        )

    def build_state_dict(self, room_id: str) -> dict[str, Any]:
        return self._engines[room_id].snapshot_state(room_id)

    async def tick_all(self, encode_fn, make_game_over_fn) -> None:
        for room_id, engine in list(self._engines.items()):
            had_motions = engine.has_active_motion()
            engine.update_game_clock(self.TICK_MS)
            finished_now = had_motions and not engine.has_active_motion()
            if finished_now:
                await self._broadcast_room(
                    room_id, encode_fn(self.build_state_dict(room_id))
                )

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
            winner = PlayerRole.BLACK.value
        elif loser_user_id == black_id:
            winner = PlayerRole.WHITE.value
        else:
            return
        engine.force_forfeit(winner)
        await self._apply_elo(room_id, engine, encode_fn, make_game_over_fn)

    async def _apply_elo(
        self,
        room_id: str,
        engine: GameEnginePort,
        encode_fn,
        make_game_over_fn,
    ) -> None:
        if self._is_elo_updated(room_id):
            return
        if engine.winner not in (PlayerRole.WHITE.value, PlayerRole.BLACK.value):
            return

        white_id, black_id, white_name, black_name = self._get_room_players(room_id)
        if not white_id or not black_id or not white_name or not black_name:
            return

        white_user = self._users.get_by_id(white_id)
        black_user = self._users.get_by_id(black_id)
        if white_user is None or black_user is None:
            return

        if engine.winner == PlayerRole.WHITE.value:
            new_white, new_black = calc_elo(white_user.elo, black_user.elo)
        else:
            new_black, new_white = calc_elo(black_user.elo, white_user.elo)

        self._users.set_elo(white_id, new_white)
        self._users.set_elo(black_id, new_black)
        self._mark_elo_updated(room_id)

        ratings = {white_name: new_white, black_name: new_black}
        payload = make_game_over_fn(engine.winner, ratings, room_id=room_id)
        await self._broadcast_room(room_id, encode_fn(payload))
        await self._bus.publish(
            EventType.GAME_OVER.value,
            room_id=room_id,
            winner=engine.winner,
            ratings=ratings,
        )
        self._logger.info("ELO updated", room_id=room_id, ratings=ratings)
