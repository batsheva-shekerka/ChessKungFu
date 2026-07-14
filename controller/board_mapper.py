from model.position import Position
from model.board import Board

CELL_SIZE = 100  # כל תא הוא 100x100 פיקסלים


class BoardMapper:
    """
    ממיר קואורדינטות פיקסל (x, y) של קליק המשתמש למיקום (row, col) על הלוח.
    כל תא תופס CELL_SIZE x CELL_SIZE פיקסלים.
    """

    def __init__(self, board: Board):
        self._board = board

    def to_position(self, x: int, y: int) -> Position:
        """
        ממיר קואורדינטת פיקסל (x, y) לאובייקט Position.
        מחזיר None אם הקואורדינטות מחוץ לגבולות הלוח.
        """
        col = x // CELL_SIZE
        row = y // CELL_SIZE
        if 0 <= row < self._board.num_rows and 0 <= col < self._board.num_cols:
            return Position(row, col)
        return None
