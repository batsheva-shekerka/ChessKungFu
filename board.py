from constants import VALID_PIECES, VALID_TEAMS, EMPTY_CELL, CELL_SIZE
from exceptions import BoardValidationError

class Board:
    """מחלקה המייצגת את לוח המשחק ומנהלת את חוקי התנועה (State + Rules)"""
    def __init__(self, grid):
        self._grid = grid
        self._validate_board()
        
        self._rows = len(grid)
        self._cols = len(grid[0]) if self._rows > 0 else 0
        
        self._selected_cell = None
        self._game_clock_ms = 0

    def _validate_board(self):
        """בדיקות תקינות ללוח"""
        if not self._grid:
            return
        expected_width = len(self._grid[0])
        for row in self._grid:
            if len(row) != expected_width:
                raise BoardValidationError("ROW WIDTH MISMATCH")
        for row in self._grid:
            for token in row:
                if token == EMPTY_CELL:
                    continue
                if len(token) != 2 or token[0] not in VALID_TEAMS or token[1].upper() not in VALID_PIECES:
                    raise BoardValidationError("UNKNOWN TOKEN")

    def _is_path_clear(self, from_row, from_col, to_row, to_col):
        """בודקת האם הדרך בין שתי משבצות פנויה מכלי חסימה (לא כולל משבצת היעד)"""
        if to_row > from_row: step_row = 1
        elif to_row < from_row: step_row = -1
        else: step_row = 0

        if to_col > from_col: step_col = 1
        elif to_col < from_col: step_col = -1
        else: step_col = 0

        curr_row = from_row + step_row
        curr_col = from_col + step_col

        while (curr_row, curr_col) != (to_row, to_col):
            if self._grid[curr_row][curr_col] != EMPTY_CELL:
                return False  # נמצאה חסימה בדרך!
            curr_row += step_row
            curr_col += step_col

        return True

    def _is_move_legal(self, piece_type, from_row, from_col, to_row, to_col):
        """מיישמת את דפוסי התנועה עבור כל כלי (כולל מהלך למקום)"""
        dr = abs(to_row - from_row)
        dc = abs(to_col - from_col)

        if piece_type == 'K':    # מלך
            return dr <= 1 and dc <= 1

        elif piece_type == 'N':  # פרש (יכול לקפוץ, אין בדיקת מסלול)
            return (dr == 2 and dc == 1) or (dr == 1 and dc == 2)

        elif piece_type == 'R':  # צריח
            if dr == 0 or dc == 0:
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        elif piece_type == 'B':  # רץ
            if dr == dc:
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        elif piece_type == 'Q':  # מלכה
            if (dr == 0 or dc == 0) or (dr == dc):
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        return False

    def handle_click(self, x: int, y: int):
        """מטפלת בלחיצות עכבר, בחירת כלים, חסימות ואכילת אויב"""
        col = x // CELL_SIZE
        row = y // CELL_SIZE

        if not (0 <= row < self._rows and 0 <= col < self._cols):
            return

        clicked_token = self._grid[row][col]

        # תרחיש א': אין כלי נבחר כרגע
        if self._selected_cell is None:
            if clicked_token != EMPTY_CELL:
                self._selected_cell = (row, col)
            return

        # תרחיש ב': יש כלי נבחר
        sel_row, sel_col = self._selected_cell
        selected_token = self._grid[sel_row][sel_col]
        
        # כלי הוא ידידותי רק אם הוא מאותו צבע וזה *לא* אותו כלי שנבחר כרגע (מאפשר קפיצה למקום)
        is_friendly = (clicked_token != EMPTY_CELL and 
                       clicked_token[0] == selected_token[0] and 
                       (row, col) != self._selected_cell)

        if is_friendly:
            self._selected_cell = (row, col)
        else:
            piece_type = selected_token[1].upper()
            
            if self._is_move_legal(piece_type, sel_row, sel_col, row, col):
                # המהלך חוקי -> מזיזים (או אוכלים את האויב) ומאפסים בחירה
                self._grid[row][col] = selected_token
                self._grid[sel_row][sel_col] = EMPTY_CELL
                self._selected_cell = None
            else:
                # מהלך לא חוקי (כולל ניסיון דילוג מעל חוסם) -> מתעלמים
                pass

    def handle_wait(self, ms: int):
        self._game_clock_ms += ms

    def display(self):
        for row in self._grid:
            print(" ".join(row))