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

        self.engine.handle_move_request(Position(7, 0), Position(5, 0), 1000)
        
        # ניסיון שיגור כלי שני בזמן שהראשון באוויר - חייב להידחות
        accepted = self.engine.handle_move_request(Position(7, 7), Position(5, 7), 1000)
        self.assertFalse(accepted)

    def test_friendly_piece_blocks_late_arrival(self):
        """כששני כלים ידידותיים מגיעים לאותו ריבוע, הראשון נשאר והשני לא אוכל אותו"""
        bishop = Piece("w_b_1", "w", "b")
        queen = Piece("w_q_1", "w", "q")
        pawn = Piece("b_p_1", "b", "p")

        bishop_start = Position(2, 4)
        queen_start = Position(5, 5)
        target = Position(1, 5)

        self.board.set_piece(bishop_start, bishop)
        self.board.set_piece(queen_start, queen)
        self.board.set_piece(target, pawn)

        self.engine.handle_move_request(queen_start, target, 4000)
        self.engine.handle_move_request(bishop_start, target, 1000)
        self.engine.update_game_clock(1000)

        self.assertEqual(pawn.status, PieceStatus.CAPTURED)
        self.assertEqual(bishop.status, PieceStatus.IDLE)
        self.assertEqual(self.board.get_piece(target), bishop)

        self.engine.update_game_clock(3000)

        self.assertEqual(queen.status, PieceStatus.IDLE)
        self.assertEqual(self.board.get_piece(queen_start), queen)
        self.assertEqual(self.board.get_piece(target), bishop)

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