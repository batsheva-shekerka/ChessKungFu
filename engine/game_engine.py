from model.board import Board
from model.position import Position
from model.piece import PieceStatus
from rules.rule_engine import RuleEngine
from realtime.real_time_arbiter import RealTimeArbiter
from engine.scoreboard import Scoreboard

class GameEngine:
    def __init__(self, board: Board):
        self.board = board
        self.rule_engine = RuleEngine(board)
        self.arbiter = RealTimeArbiter()
        self.scoreboard=Scoreboard()
        self.game_over = False
        self.winner = None
        
    def handle_jump_request(self, position: Position) -> bool:
        if self.game_over:
            return False

        piece = self.board.get_piece(position)
        if not piece or piece.status != PieceStatus.IDLE:
            return False

        self.arbiter.start_jump(piece, position, 1000)
        move_text = f"{piece.piece_type.upper()} jump ({position.row},{position.col})"
        self.scoreboard.add_move(piece.color, move_text)
        return True
    def handle_move_request(self, start: Position, end: Position, duration_ms: int) -> bool:
        """
        מטפל בבקשת מהלך מהמשתמש (קליק/פקודה).
        מבצע בדיקות על-משחק ומפעיל את מנוע החוקים.
        """
        if self.game_over:
            return False

        piece = self.board.get_piece(start)
        if not piece or piece.status != PieceStatus.IDLE:
            return False

        if not self.rule_engine.is_move_legal(start, end):
            return False

        piece.status = PieceStatus.MOVING
        self.arbiter.start_motion(piece, start, end, duration_ms)
        move_text = f"{piece.piece_type.upper()} ({start.row},{start.col})->({end.row},{end.col})"
        self.scoreboard.add_move(piece.color, move_text)
        return True

    def update_game_clock(self, ms: int) -> None:
        """
        מקדמת את שעון המשחק הכללי ומעדכנת את הלוח הפיזי
        עבור כל התנועות שהסתיימו בהצלחה בפעימה זו.
        """
        if self.game_over:
            return

        completed_motions = self.arbiter.advance_time(ms)
        
        
        completed_motions.sort(
            key=lambda m: (m.remaining_time, m.original_duration, m.is_jump, -m.motion_id)
        )

        for motion in completed_motions:
            if motion.piece.status == PieceStatus.CAPTURED:
                continue
            if motion.is_jump:
                motion.piece.status = PieceStatus.IDLE
                continue
            jumper = self.board.get_piece(motion.end)
            if (jumper is not None
                    and jumper.status == PieceStatus.JUMPING
                    and jumper.color != motion.piece.color):
                motion.piece.status = PieceStatus.CAPTURED
                self.scoreboard.add_capture_points(jumper.color, motion.piece.piece_type)               
                if self.board.get_piece(motion.start) is motion.piece:
                    self.board.set_piece(motion.start, None)
                if motion.piece.piece_type == 'k':
                    self.game_over = True
                    self.winner = jumper.color
                continue
            target_piece = self.board.get_piece(motion.end)
            if target_piece and target_piece.status == PieceStatus.IDLE:
                if target_piece.color == motion.piece.color:
                    motion.piece.status = PieceStatus.IDLE
                    continue
                target_piece.status = PieceStatus.CAPTURED
                self.scoreboard.add_capture_points(motion.piece.color, target_piece.piece_type)
                self.board.set_piece(motion.end, None)
                if target_piece.piece_type == 'k':
                    self.game_over = True
                    self.winner = motion.piece.color

            motion.piece.status = PieceStatus.IDLE
            if self.board.get_piece(motion.start) is motion.piece:
                self.board.set_piece(motion.start, None)
            self.board.set_piece(motion.end, motion.piece)

            # if p in the last row
            if motion.piece.piece_type == 'p':
                promotion_row = 0 if motion.piece.color == 'w' else self.board.num_rows - 1
                if motion.end.row == promotion_row:
                    motion.piece.piece_type = 'q'
                    motion.piece.piece_id = f"{motion.piece.color}Q"
    
    def wait(self, ms: int):
        self.update_game_clock(ms)