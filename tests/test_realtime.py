import unittest
from model.position import Position
from model.piece import Piece, PieceStatus
from realtime.real_time_arbiter import RealTimeArbiter

class TestRealTimeLayer(unittest.TestCase):
    def setUp(self):
        self.arbiter = RealTimeArbiter()
        self.piece1 = Piece("w_r_1", "w", "r")
        self.piece2 = Piece("b_r_1", "b", "r")

    def test_motion_starts_correctly(self):
        """בדיקה ששיגור כלי משנה את מצבו ל-MOVING ומפעיל תנועה אקטיבית"""
        self.arbiter.start_motion(self.piece1, Position(7,0), Position(5,0), 1000)
        self.assertTrue(self.arbiter.has_active_motion())
        self.assertEqual(self.piece1.status, PieceStatus.MOVING)

    def test_tie_breaking_logic(self):
        """
        בדיקת מנגנון שבירת השוויון:
        כאשר שני כלים מגיעים באותה פעימה, מי שיש לו זמן נותר נמוך יותר
        (או מזהה פקודה מוקדם יותר) יופיע ראשון ברשימת התנועות שהסתיימו.
        """
        # כלי 1 מגיע בעוד 100 מילישניות
        self.arbiter.start_motion(self.piece1, Position(7,0), Position(5,0), 100)
        # כלי 2 מגיע בעוד 200 מילישניות
        self.arbiter.start_motion(self.piece2, Position(0,0), Position(2,0), 200)

        # קידום השעון ב-250 מילישניות (שניהם מסיימים)
        completed = self.arbiter.advance_time(250)
        
        self.assertEqual(len(completed), 2)
        # כלי 1 היה צריך להסתיים קודם לכן הוא ראשון ברשימה
        self.assertEqual(completed[0].piece, self.piece1)
        self.assertEqual(completed[1].piece, self.piece2)

if __name__ == "__main__":
    unittest.main()