from model.position import Position
from model.board import Board
from rules.piece_rules import PieceRules

class RuleEngine:
    def __init__(self, board: Board):
        self.board = board

    def is_move_legal(self, start: Position, end: Position) -> bool:
        """
        פונקציית המעטפת הראשית לבדיקת חוקיות מהלך.
        מחזירה True אם המהלך תקין לחלוטין מבחינת חוקי המשחק.
        """
        if start == end:
            return False

        piece = self.board.get_piece(start)
        if not piece:
            return False

        # בדיקה שהיעד אינו מכיל כלי מאותו הצבע (מניעת אש ידידותית)
        target_piece = self.board.get_piece(end)
        if target_piece and target_piece.color == piece.color:
            return False

        # ניתוב הבדיקה לפי סוג הכלי
        if piece.piece_type == 'r':   # צריח
            return end in PieceRules.get_straight_moves(start, self.board)
        elif piece.piece_type == 'b': # רץ
            return end in PieceRules.get_diagonal_moves(start, self.board)
        elif piece.piece_type == 'q': # מלכה
            return (end in PieceRules.get_straight_moves(start, self.board) or
                    end in PieceRules.get_diagonal_moves(start, self.board))
        elif piece.piece_type == 'n': # פרש
            return end in PieceRules.get_knight_moves(start, self.board)
        elif piece.piece_type == 'k': # מלך
            return end in PieceRules.get_king_moves(start, self.board)
        elif piece.piece_type == 'p': # רגלי
            return end in PieceRules.get_pawn_moves(start, self.board)

        return False