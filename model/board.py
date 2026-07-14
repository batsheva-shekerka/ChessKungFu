from typing import Dict, Optional
from model.position import Position
from model.piece import Piece

class Board:
    def __init__(self, num_rows: int = 8, num_cols: int = 8):
        self.num_rows = num_rows
        self.num_cols = num_cols
        self._grid: Dict[Position, Piece] = {}

    def get_piece(self, position: Position) -> Optional[Piece]:
        """מחזיר את הכלי שנמצא במיקום הנתון, או None אם המשבצת ריקה."""
        return self._grid.get(position)

    def set_piece(self, position: Position, piece: Optional[Piece]) -> None:
        """מציב כלי במיקום מסוים או מוחק אותו מהמשבצת אם הועבר None."""
        if piece is None:
            self._grid.pop(position, None)
        else:
            self._grid[position] = piece

    def move_piece(self, start: Position, end: Position) -> None:
        """
        מבצע הזזה של כלי ממיקום המקור ליעד.
        אך ורק לאחר שחוקיות המהלך וודאתה.
        """
        piece = self.get_piece(start)
        if piece:
            self.set_piece(start, None)
            self.set_piece(end, piece)

    def get_all_pieces(self) -> Dict[Position, Piece]:
        """מחזיר העתק של מצב הלוח הנוכחי."""
        return self._grid.copy()