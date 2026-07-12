import unittest
from model.position import Position
from model.piece import Piece, PieceStatus
from model.board import Board

class TestModelLayer(unittest.TestCase):
    def test_position_immutability(self):
        """ודאות שמיקום הוא אובייקט ערך תקין שומר נתונים"""
        pos = Position(row=7, col=0)
        self.assertEqual(pos.row, 7)
        self.assertEqual(pos.col, 0)

    def test_piece_initialization(self):
        """בדיקה שהכלי נוצר עם מצב תחילי מנוחה"""
        piece = Piece(piece_id="w_r_1", color="w", piece_type="r")
        self.assertEqual(piece.status, PieceStatus.IDLE)

    def test_board_manipulation(self):
        """בדיקה שהלוח יודע להציב, לשלוף ולהזיז כלים באופן לוגי טהור"""
        board = Board()
        pos_start = Position(7, 0)
        pos_end = Position(5, 0)
        piece = Piece(piece_id="w_r_1", color="w", piece_type="r")

        # הצבה ושליפה
        board.set_piece(pos_start, piece)
        self.assertEqual(board.get_piece(pos_start), piece)

        # הזזה
        board.move_piece(pos_start, pos_end)
        self.assertIsNone(board.get_piece(pos_start))
        self.assertEqual(board.get_piece(pos_end), piece)

if __name__ == "__main__":
    unittest.main()