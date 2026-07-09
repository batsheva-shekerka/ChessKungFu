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
                return False
            curr_row += step_row
            curr_col += step_col

        return True

    def _is_move_legal(self, selected_token, from_row, from_col, to_row, to_col):
        """מיישמת את דפוסי התנועה עבור כל כלי המשחק (כולל חייל פשוט)"""
        team = selected_token[0]
        piece_type = selected_token[1].upper()

        # חישוב מרחקים מוחלטים (עבור הכלים הרגילים)
        dr_abs = abs(to_row - from_row)
        dc_abs = abs(to_col - from_col)

        # לוגיקה ייחודית עבור חייל (Pawn)
        if piece_type == 'P':
            dr_signed = to_row - from_row
            
            # 1. בדיקת כיוון התנועה לפי צבע החייל (לבן עולה למעלה, שחור יורד למטה)
            if team == 'w' and dr_signed != -1:
                return False
            if team == 'b' and dr_signed != 1:
                return False

            target_token = self._grid[to_row][to_col]

            # 2. תנועה ישר קדימה: מותרת רק למשבצת ריקה (אסור לתפוס קדימה)
            if dc_abs == 0:
                return target_token == EMPTY_CELL
                
            # 3. תנועה באלכסון: מותרת רק אם יש שם כלי אויב (תפיסה באלכסון)
            elif dc_abs == 1:
                return target_token != EMPTY_CELL

            return False

        # לוגיקה עבור שאר הכלים (מאיטרציות קודמות)
        if piece_type == 'K':    # מלך
            return dr_abs <= 1 and dc_abs <= 1

        elif piece_type == 'N':  # פרש
            return (dr_abs == 2 and dc_abs == 1) or (dr_abs == 1 and dc_abs == 2)

        elif piece_type == 'R':  # צריח
            if dr_abs == 0 or dc_abs == 0:
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        elif piece_type == 'B':  # רץ
            if dr_abs == dc_abs:
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        elif piece_type == 'Q':  # מלכה
            if (dr_abs == 0 or dc_abs == 0) or (dr_abs == dc_abs):
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        return False

    def handle_click(self, x: int, y: int):
        """מטפלת בלחיצות עכבר, בחירת כלים ותנועה חוקית בהתאם לסוג הכלי"""
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
        
        # בדיקה האם מדובר בכלי ידידותי אחר (מוציא מכלל אפשרות לחיצה על עצמו)
        is_friendly = (clicked_token != EMPTY_CELL and 
                       clicked_token[0] == selected_token[0] and 
                       (row, col) != self._selected_cell)

        if is_friendly:
            self._selected_cell = (row, col)
        else:
            # שליחת ה-token המלא לבדיקת חוקיות המהלך
            if self._is_move_legal(selected_token, sel_row, sel_col, row, col):
                self._grid[row][col] = selected_token
                self._grid[sel_row][sel_col] = EMPTY_CELL
                self._selected_cell = None
            else:
                # מהלך לא חוקי -> מתעלמים
                pass

    def handle_wait(self, ms: int):
        self._game_clock_ms += ms

    def display(self):
        for row in self._grid:
            print(" ".join(row))