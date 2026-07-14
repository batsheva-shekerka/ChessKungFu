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

        # שליפת הכלי ובדיקה שהוא קיים ונמצא במצב מנוחה (לא כבר באוויר)
        piece = self.board.get_piece(start)
        if not piece or piece.status != PieceStatus.IDLE:
            return False

        # בדיקת חוקיות המהלך במנוע החוקים הסטטי
        if not self.rule_engine.is_move_legal(start, end):
            return False

        # מסמנים את הכלי כ-MOVING לפני השיגור כדי שכלים אחרים לא יאכלו אותו מהלוח
        piece.status = PieceStatus.MOVING
        self.arbiter.start_motion(piece, start, end, duration_ms)
        return True

    def update_game_clock(self, ms: int) -> None:
        """
        מקדמת את שעון המשחק הכללי ומעדכנת את הלוח הפיזי
        עבור כל התנועות שהסתיימו בהצלחה בפעימה זו.
        """
        if self.game_over:
            return

        # קידום הזמן וקבלת התנועות שהסתיימו
        completed_motions = self.arbiter.advance_time(ms)

        # מיון לפי סדר נחיתה פיזי:
        # 1. remaining_time (שלילי יותר = הגיע מוקדם יותר בתוך הטיק הנוכחי) → נוחת ראשון
        # 2. original_duration (קצר יותר = מהיר יותר → נוחת ראשון בשוויון זמן)
        # 3. -motion_id (ותיק יותר = היה באוויר מוקדם יותר → נוחת אחרון ואוכל את מי שנחת לפניו)
        completed_motions.sort(
            key=lambda m: (m.remaining_time, m.original_duration, -m.motion_id)
        )

        for motion in completed_motions:
            # אם הכלי המיועד כבר נתפס או שונה בינתיים, התנועה מבוטלת
            if motion.piece.status == PieceStatus.CAPTURED:
                continue

            # בדיקה האם יש כלי IDLE ביעד (רק כלי יציב נתפס, לא כלי מעופף)
            target_piece = self.board.get_piece(motion.end)
            if target_piece and target_piece.status == PieceStatus.IDLE:
                target_piece.status = PieceStatus.CAPTURED
                if target_piece.piece_type == 'k':
                    self.game_over = True
                    self.winner = motion.piece.color

            # נחיתה: אם הכלי עדיין נמצא בנקודת המוצא בגריד, מסירים אותו משם
            motion.piece.status = PieceStatus.IDLE
            if self.board.get_piece(motion.start) is motion.piece:
                self.board.set_piece(motion.start, None)
            self.board.set_piece(motion.end, motion.piece)

            # קידום רגלי: אם רגלי הגיע לשורה הראשונה/אחרונה, הוא הופך למלכה
            if motion.piece.piece_type == 'p':
                promotion_row = 0 if motion.piece.color == 'w' else self.board.num_rows - 1
                if motion.end.row == promotion_row:
                    motion.piece.piece_type = 'q'
                    motion.piece.piece_id = f"{motion.piece.color}Q"
    
    def wait(self, ms: int):
        self.update_game_clock(ms)