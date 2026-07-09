from constants import VALID_PIECES, VALID_TEAMS, EMPTY_CELL, CELL_SIZE
from exceptions import BoardValidationError

class Board:
    """מחלקה המייצגת את לוח המשחק ומנהלת את מצבו הדינמי (State)"""
    def __init__(self, grid):
        self._grid = grid
        self._validate_board()
        
        # הגדרת מימדי הלוח
        self._rows = len(grid)
        self._cols = len(grid[0]) if self._rows > 0 else 0
        
        # ניהול מצב המשחק (State)
        self._selected_cell = None  # ישמור טופל של (row, col) או None
        self._game_clock_ms = 0     # שעון המשחק במילישניות

    def _validate_board(self):
        """בדיקות תקינות ללוח (מאיטרציה קודמת)"""
        if not self._grid:
            return
        expected_width = len(self._grid[0])
        for row in self._grid:
            if len(row) != expected_width:
                raise BoardValidationError("ERROR ROW_WIDTH_MISMATCH")
        for row in self._grid:
            for token in row:
                if token == EMPTY_CELL:
                    continue
                if len(token) != 2 or token[0] not in VALID_TEAMS or token[1].upper() not in VALID_PIECES:
                    raise BoardValidationError("ERROR UNKNOWN_TOKEN")

    def handle_click(self, x: int, y: int):
        """מפענחת לחיצת עכבר בפיקסלים ומעדכנת את מצב הלוח"""
        # תרגום פיקסלים למשבצת (x קובע עמודה, y קובע שורה)
        col = x // CELL_SIZE
        row = y // CELL_SIZE

        # 1. התעלמות בלחיצה מחוץ לגבולות הלוח
        if not (0 <= row < self._rows and 0 <= col < self._cols):
            return

        clicked_token = self._grid[row][col]

        # 2. תרחיש א': אין כרגע כלי נבחר
        if self._selected_cell is None:
            if clicked_token != EMPTY_CELL:
                self._selected_cell = (row, col)  # בחירת הכלי
            return

        # 3. תרחיש ב': כבר יש כלי נבחר בזיכרון
        sel_row, sel_col = self._selected_cell
        selected_token = self._grid[sel_row][sel_col]

        # בדיקה האם לחצו על כלי אחר של אותה הקבוצה (Friendly Piece)
        is_friendly = (clicked_token != EMPTY_CELL and clicked_token[0] == selected_token[0])

        if is_friendly:
            self._selected_cell = (row, col)  # החלפת הבחירה לכלי החדש
        else:
            # בקשת תנועה (Move Request) - הזזת הכלי ועידכון הלוח
            self._grid[row][col] = selected_token
            self._grid[sel_row][sel_col] = EMPTY_CELL
            self._selected_cell = None  # איפוס הבחירה לאחר התנועה

    def handle_wait(self, ms: int):
        """קידום שעון המשחק"""
        self._game_clock_ms += ms

    def display(self):
        """הדפסת הלוח במצבו הנוכחי"""
        for row in self._grid:
            print(" ".join(row))