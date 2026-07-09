from constants import VALID_PIECES, VALID_TEAMS, EMPTY_CELL, CELL_SIZE, MS_PER_CELL
from exceptions import BoardValidationError

class Board:
    """מחלקה המייצגת את לוח המשחק ומנהלת תנועה, התנגשויות ומצב סיום משחק (Game Over)"""
    def __init__(self, grid):
        self._grid = grid
        self._validate_board()
        
        self._rows = len(grid)
        self._cols = len(grid[0]) if self._rows > 0 else 0
        
        self._selected_cell = None
        self._game_clock_ms = 0
        self._pending_moves = []
        self._game_over = False  # משתנה בוליאני חדש למעקב אחר סטטוס המשחק

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

    def _is_cell_occupied_dynamic(self, r, c):
        """בדיקה דינמית: האם תא חסום כרגע על ידי כלי סטטי או כלי שבדרך אליו"""
        for pm in self._pending_moves:
            if pm['to'] == (r, c):
                return True
        if self._grid[r][c] != EMPTY_CELL:
            is_moving_away = any(pm['from'] == (r, c) for pm in self._pending_moves)
            if not is_moving_away:
                return True
        return False

    def _is_path_clear(self, from_row, from_col, to_row, to_col):
        """בודקת האם הדרך פנויה (לוקחת בחשבון כלים בתנועה)"""
        if to_row > from_row: step_row = 1
        elif to_row < from_row: step_row = -1
        else: step_row = 0

        if to_col > from_col: step_col = 1
        elif to_col < from_col: step_col = -1
        else: step_col = 0

        curr_row = from_row + step_row
        curr_col = from_col + step_col

        while (curr_row, curr_col) != (to_row, to_col):
            if self._is_cell_occupied_dynamic(curr_row, curr_col):
                return False
            curr_row += step_row
            curr_col += step_col

        return True

    def _is_move_legal(self, selected_token, from_row, from_col, to_row, to_col):
        """מיישמת את דפוסי התנועה עבור כל כלי המשחק"""
        team = selected_token[0]
        piece_type = selected_token[1].upper()

        dr_abs = abs(to_row - from_row)
        dc_abs = abs(to_col - from_col)

        if piece_type == 'P':
            dr_signed = to_row - from_row
            if team == 'w' and dr_signed != -1: return False
            if team == 'b' and dr_signed != 1: return False

            target_token = self._grid[to_row][to_col]
            if dc_abs == 0:
                return target_token == EMPTY_CELL
            elif dc_abs == 1:
                return target_token != EMPTY_CELL
            return False

        if piece_type == 'K': return dr_abs <= 1 and dc_abs <= 1
        elif piece_type == 'N': return (dr_abs == 2 and dc_abs == 1) or (dr_abs == 1 and dc_abs == 2)
        elif piece_type == 'R':
            if dr_abs == 0 or dc_abs == 0: return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False
        elif piece_type == 'B':
            if dr_abs == dc_abs: return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False
        elif piece_type == 'Q':
            if (dr_abs == 0 or dc_abs == 0) or (dr_abs == dc_abs): return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        return False

    def handle_click(self, x: int, y: int):
        """מטפלת בלחיצות עכבר ומסננת קלטים אם המשחק נגמר"""
        # בדיקה האם המשחק נגמר - אם כן, מתעלמים מהלחיצה לחלוטין
        if self._game_over:
            return

        col = x // CELL_SIZE
        row = y // CELL_SIZE

        if not (0 <= row < self._rows and 0 <= col < self._cols):
            return

        for pm in self._pending_moves:
            if (row, col) == pm['from'] or (row, col) == pm['to']:
                return

        clicked_token = self._grid[row][col]

        if self._selected_cell is None:
            if clicked_token != EMPTY_CELL:
                self._selected_cell = (row, col)
            return

        sel_row, sel_col = self._selected_cell
        selected_token = self._grid[sel_row][sel_col]
        
        is_friendly = (clicked_token != EMPTY_CELL and 
                       clicked_token[0] == selected_token[0] and 
                       (row, col) != self._selected_cell)

        if is_friendly:
            self._selected_cell = (row, col)
        else:
            if self._is_move_legal(selected_token, sel_row, sel_col, row, col):
                for pm in self._pending_moves:
                    if pm['to'] == (row, col) and pm['token'][0] == selected_token[0]:
                        self._selected_cell = None
                        return

                distance = max(abs(row - sel_row), abs(col - sel_col))
                duration = distance * MS_PER_CELL
                arrival_time = self._game_clock_ms + duration
                
                self._pending_moves.append({
                    'from': (sel_row, sel_col),
                    'to': (row, col),
                    'token': selected_token,
                    'arrival_time': arrival_time
                })
                self._selected_cell = None

    def handle_wait(self, ms: int):
        """מקדמת שעון, מבצעת לכידות ובודקת השתלטות על מלך האויב"""
        # בדיקה האם המשחק כבר נגמר - אם כן, מתעלמים מפקודות המתנה נוספות
        if self._game_over:
            return

        self._game_clock_ms += ms
        self._pending_moves.sort(key=lambda x: x['arrival_time'])
        remaining_moves = []

        for pm in self._pending_moves:
            if self._game_clock_ms >= pm['arrival_time']:
                from_r, from_c = pm['from']
                to_r, to_c = pm['to']
                token = pm['token']

                if self._grid[from_r][from_c] != token:
                    continue

                self._grid[from_r][from_c] = EMPTY_CELL
                
                # בדיקה האם משבצת היעד מכילה מלך (של האויב או בכלל)
                target_token = self._grid[to_r][to_c]
                if target_token != EMPTY_CELL and target_token[1].upper() == 'K':
                    self._game_over = True

                # ביצוע המהלך (ההשתלטות) בפועל על הלוח
                self._grid[to_r][to_c] = token
                
                # אם המלך נלכד, עוצרים מיד את הלולאה ומרוקנים מהלכים עתידיים
                if self._game_over:
                    self._pending_moves = []
                    return
            else:
                remaining_moves.append(pm)

        self._pending_moves = remaining_moves

    def display(self):
        for row in self._grid:
            print(" ".join(row))