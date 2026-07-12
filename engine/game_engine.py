from model.board import Board
from model.position import Position
from model.piece import PieceStatus
from rules.rule_engine import RuleEngine
from realtime.real_time_arbiter import RealTimeArbiter

class GameEngine:
    def __init__(self, board: Board):
        self.board = board
        self.rule_engine = RuleEngine(board)
        self.arbiter = RealTimeArbiter()
        self.game_over = False
        self.winner = None

    def handle_move_request(self, start: Position, end: Position, duration_ms: int) -> bool:
        """
        מטפל בבקשת מהלך מהמשתמש (קליק/פקודה).
        מבצע בדיקות על-משחק ומפעיל את מנוע החוקים.
        """
        if self.game_over:
            return False

        # אם כלי כבר נמצא בתנועה באוויר, אין לבצע מהלך חדש
        if self.arbiter.has_active_motion():
            return False

        # שליפת הכלי ובדיקה שהוא קיים ונמצא במצב מנוחה
        piece = self.board.get_piece(start)
        if not piece or piece.status != PieceStatus.IDLE:
            return False

        # בדיקת חוקיות המהלך במנוע החוקים הסטטי
        if not self.rule_engine.is_move_legal(start, end):
            return False

        # אם הכל תקין, משגרים את הכלי לאוויר דרך בורר זמן האמת
        self.arbiter.start_motion(piece, start, end, duration_ms)
        return True

    def update_game_clock(self, ms: int) -> None:
        """
        מקדמת את שעון המשחק הכללי ומעדכנת את הלוח הפיזי
        עבור כל התנועות שהסתיימו בהצלחה בפעימה זו.
        """
        if self.game_over:
            return

        # קידום הזמן וקבלת התנועות שהסתיימו (ממוינות לפי סדר הגעה הנדסי)
        completed_motions = self.arbiter.advance_time(ms)

        for motion in completed_motions:
            # אם הכלי המיועד כבר נתפס או שונה בינתיים, התנועה מבוטלת
            if motion.piece.status == PieceStatus.CAPTURED:
                continue

            # בדיקה האם יש כלי ביעד (הכאה)
            target_piece = self.board.get_piece(motion.end)
            if target_piece:
                target_piece.status = PieceStatus.CAPTURED
                # בדיקה האם המשחק נגמר (הכאת מלך)
                if target_piece.piece_type == 'k':
                    self.game_over = True
                    self.winner = motion.piece.color

            # החזרת מצב הכלי לסטטי וביצוע ההזזה בפועל על הלוח
            motion.piece.status = PieceStatus.IDLE
            self.board.move_piece(motion.start, motion.end)
    
    def wait(self, ms: int):
    # האצלת קידום הזמן המדומה לבורר זמן-האמת
        self.arbiter.advance_time(ms)