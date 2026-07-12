import unittest
from model.board import Board
from model.position import Position
from model.piece import Piece
from rules.rule_engine import RuleEngine

class TestRulesLayer(unittest.TestCase):
    def setUp(self):
        self.board = Board()
        self.rule_engine = RuleEngine(self.board)

    def test_rook_straight_path_clear(self):
        """בדיקה שצריח יכול לזוז במסלול ישר ופתוח"""
        rook = Piece("w_r_1", "w", "r")
        start = Position(7, 0)
        end = Position(3, 0)
        self.board.set_piece(start, rook)
        self.assertTrue(self.rule_engine.is_move_legal(start, end))

    def test_rook_path_blocked_by_friendly(self):
        """בדיקה שצריח נחסם על ידי כלי ידידותי באותו מסלול"""
        rook = Piece("w_r_1", "w", "r")
        pawn = Piece("w_p_1", "w", "p")
        start = Position(7, 0)
        block = Position(5, 0)
        end = Position(3, 0)

        self.board.set_piece(start, rook)
        self.board.set_piece(block, pawn)
        self.assertFalse(self.rule_engine.is_move_legal(start, end))

    def test_friendly_fire_prevention(self):
        """ודאות שלא ניתן להכות כלי מאותו הצבע ביעד"""
        rook = Piece("w_r_1", "w", "r")
        knight = Piece("w_n_1", "w", "n")
        start = Position(7, 0)
        end = Position(7, 2)

        self.board.set_piece(start, rook)
        self.board.set_piece(end, knight)
        self.assertFalse(self.rule_engine.is_move_legal(start, end))

if __name__ == "__main__":
    unittest.main()