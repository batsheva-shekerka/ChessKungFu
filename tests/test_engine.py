import unittest
from model.board import Board
from model.position import Position
from model.piece import Piece, PieceStatus
from engine.game_engine import GameEngine

class TestEngineLayer(unittest.TestCase):
    def setUp(self):
        self.board = Board()
        self.engine = GameEngine(self.board)

    def test_no_move_while_motion_in_progress(self):
        """חוק קונג-פו: בדיקה שלא ניתן לבצע מהלך חדש כשיש כלי באוויר"""
        rook1 = Piece("w_r_1", "w", "r")
        rook2 = Piece("w_r_2", "w", "r")
        
        self.board.set_piece(Position(7, 0), rook1)
        self.board.set_piece(Position(7, 7), rook2)

        # שיגור כלי ראשון
        self.engine.handle_move_request(Position(7, 0), Position(5, 0), 1000)
        
        # ניסיון שיגור כלי שני בזמן שהראשון באוויר - חייב להידחות
        accepted = self.engine.handle_move_request(Position(7, 7), Position(5, 7), 1000)
        self.assertFalse(accepted)

    def test_king_capture_ends_game(self):
        """בדיקה שהכאת מלך מעבירה את המשחק למצב גמור ומגדירה מנצח"""
        attacker = Piece("w_r_1", "w", "r")
        king = Piece("b_k_1", "b", "k")
        
        start = Position(7, 0)
        target = Position(0, 0)
        
        self.board.set_piece(start, attacker)
        self.board.set_piece(target, king)

        # ביצוע מהלך והרצת הזמן לסיומו
        self.engine.handle_move_request(start, target, 500)
        self.engine.update_game_clock(500)

        # וידוא חוקי סיום משחק
        self.assertTrue(self.engine.game_over)
        self.assertEqual(self.engine.winner, "w")
        self.assertEqual(king.status, PieceStatus.CAPTURED)

if __name__ == "__main__":
    unittest.main()