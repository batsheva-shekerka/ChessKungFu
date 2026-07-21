from typing import Optional
from model.position import Position
from engine.game_engine import GameEngine
from controller.board_mapper import BoardMapper

MS_PER_CELL = 1000  # seconds per pieces


class Controller:
    """
    שכבת הקונטרולר: מקבל אירועי קליק מהמשתמש, ממיר אותם לפקודות על המנוע.

    זרימה:
      קליק ראשון  → בחירת כלי מקור  (selection)
      קליק שני    → בחירת יעד ושיגור (move request)

    משך התנועה מחושב לפי מרחק Chebyshev (מקסימום מבין הפרש השורות והפרש העמודות).
    """

    def __init__(self, engine: GameEngine):
        self._engine = engine
        self._mapper = BoardMapper(engine.board)
        self._selected: Optional[Position] = None
    
    @property
    def selected(self):
        """
        הגשר: מאפשר לכל העולם החיצוני לקבל את המיקום הנבחר כ-Tuple פשוט.
        """
        if self._selected is None:
            return None
        return (self._selected.row, self._selected.col)

    @staticmethod
    def _duration(start: Position, end: Position) -> int:
        """מחשב את משך הטיסה במילישניות לפי מרחק Chebyshev."""
        dr = abs(end.row - start.row)
        dc = abs(end.col - start.col)
        return max(dr, dc) * MS_PER_CELL

    def click(self, x: int, y: int) -> None:
        """מטפל בקליק יחיד של המשתמש."""
        position = self._mapper.to_position(x, y)
        if position is None:
            return

        if self._selected is None:
            # first click
            if self._engine.board.get_piece(position) is not None:
                self._selected = position
        else:
            #second click
            clicked_piece = self._engine.board.get_piece(position)
            selected_piece = self._engine.board.get_piece(self._selected)
            if position == self._selected:
                self._engine.handle_jump_request(self._selected)
                self._selected = None
                return
            if (clicked_piece is not None
                    and selected_piece is not None
                    and clicked_piece.color == selected_piece.color):
                self._selected = position
            else:
                if selected_piece is not None:
                    #calculate the duration by the num of the pieces at the way
                    duration = self._duration(self._selected, position)
                    self._engine.handle_move_request(
                        self._selected, position, duration
                    )
                self._selected = None
