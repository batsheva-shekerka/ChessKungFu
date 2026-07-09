from constants import VALID_PIECES, VALID_TEAMS, EMPTY_CELL, CELL_SIZE, MS_PER_CELL
from exceptions import BoardValidationError

class Board:
    """מחלקה המייצגת את לוח המשחק ומנהלת תנועה סימולטנית וחסימת מסלולים משותפים"""
    def __init__(self, grid):
        self._grid = grid
        self._validate_board()
        
        self._rows = len(grid)
        self._cols = len(grid[0]) if self._rows > 0 else 0
        
        self._selected_cell = None
        self._game_clock_ms = 0
        
        # שדרוג לרשימה כדי לתמוך בתנועה של כמה כלים במקביל
        self._pending_moves = []

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
        """בודקת האם הדרך בין שתי משבצות פנויה מכלי חסימה על הלוח"""
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
        """מיישמת את דפוסי התנועה עבור כל כלי המשחק"""
        team = selected_token[0]
        piece_type = selected_token[1].upper()

        dr_abs = abs(to_row - from_row)
        dc_abs = abs(to_col - from_col)

        # לוגיקה עבור חייל (Pawn)
        if piece_type == 'P':
            dr_signed = to_row - from_row
            if team == 'w' and dr_signed != -1:
                return False
            if team == 'b' and dr_signed != 1:
                return False

            target_token = self._grid[to_row][to_col]
            if dc_abs == 0:
                return target_token == EMPTY_CELL
            elif dc_abs == 1:
                return target_token != EMPTY_CELL
            return False

        # לוגיקה עבור שאר הכלים
        if piece_type == 'K':
            return dr_abs <= 1 and dc_abs <= 1

        elif piece_type == 'N':
            return (dr_abs == 2 and dc_abs == 1) or (dr_abs == 1 and dc_abs == 2)

        elif piece_type == 'R':
            if dr_abs == 0 or dc_abs == 0:
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        elif piece_type == 'B':
            if dr_abs == dc_abs:
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        elif piece_type == 'Q':
            if (dr_abs == 0 or dc_abs == 0) or (dr_abs == dc_abs):
                return self._is_path_clear(from_row, from_col, to_row, to_col)
            return False

        return False

    def handle_click(self, x: int, y: int):
        """מטפלת בלחיצות עכבר, מנהלת חסימות רדירקט ומסלולים משותפים בין יריבים"""
        col = x // CELL_SIZE
        row = y // CELL_SIZE

        if not (0 <= row < self._rows and 0 <= col < self._cols):
            return

        # שומר סף: מניעת הסטה (Redirect) של כלי שנמצא כרגע בתנועה
        for pm in self._pending_moves:
            if (row, col) == pm['from']:
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
                
                # בדיקת חסימת מסלול משותף (Common Route) מול כלי יריב בתנועה
                has_route_conflict = False
                for pm in self._pending_moves:
                    # אם זה כלי של הקבוצה היריבה
                    if pm['token'][0] != selected_token[0]:
                        # בודקים אם יש שורה משותפת או עמודה משותפת במסלולים שלהם
                        pm_rows = {pm['from'][0], pm['to'][0]}
                        pm_cols = {pm['from'][1], pm['to'][1]}
                        new_rows = {sel_row, row}
                        new_cols = {sel_col, col}
                        
                        if (pm_rows & new_rows) or (pm_cols & new_cols):
                            has_route_conflict = True
                            break
                
                # אם יש התנגשות מסלולים עם כלי יריב - מתעלמים מהמהלך לחלוטין!
                if has_route_conflict:
                    self._selected_cell = None
                    return

                # חישוב מרחק וזמן הגעה דינמי
                distance = max(abs(row - sel_row), abs(col - sel_col))
                duration = distance * MS_PER_CELL
                arrival_time = self._game_clock_ms + duration
                
                # הוספת המהלך לרשימת המהלכים הפעילים
                self._pending_moves.append({
                    'from': (sel_row, sel_col),
                    'to': (row, col),
                    'token': selected_token,
                    'arrival_time': arrival_time
                })
                self._selected_cell = None
            else:
                pass

    def handle_wait(self, ms: int):
        """מקדמת את השעון ומבצעת את כל המהלכים שהגיע זמן הגעתם לפי הסדר"""
        self._game_clock_ms += ms

        remaining_moves = []
        
        # נמיין לפי זמן הגעה כדי שהכלים יגיעו בסדר כרונולוגי נכון
        self._pending_moves.sort(key=lambda x: x['arrival_time'])

        for pm in self._pending_moves:
            if self._game_clock_ms >= pm['arrival_time']:
                from_r, from_c = pm['from']
                to_r, to_c = pm['to']
                token = pm['token']

                # ביצוע המהלך בפועל על הלוח
                self._grid[to_r][to_c] = token
                self._grid[from_r][from_c] = EMPTY_CELL
            else:
                remaining_moves.append(pm)

        self._pending_moves = remaining_moves

    def display(self):
        for row in self._grid:
            print(" ".join(row))