from typing import List
from realtime.motion import Motion
from model.piece import Piece, PieceStatus
from model.position import Position

class RealTimeArbiter:
    def __init__(self):
        self._active_motions: List[Motion] = []
        self._motion_counter = 0

    def start_motion(self, piece: Piece, start: Position, end: Position, duration_ms: int) -> None:
        """משחרר כלי לאוויר ומשנה את מצבו ל-MOVING."""
        self._motion_counter += 1
        piece.status = PieceStatus.MOVING
        
        new_motion = Motion(
            motion_id=self._motion_counter,
            piece=piece,
            start=start,
            end=end,
            remaining_time=duration_ms
        )
        self._active_motions.append(new_motion)

    def has_active_motion(self) -> bool:
        """מחזיר האם יש כרגע תנועה כלשהי באוויר."""
        return len(self._active_motions) > 0

    def advance_time(self, ms: int) -> List[Motion]:
        """
        מקדם את שעון המשחק ב-ms מילישניות.
        מפחית זמן מכל התנועות הפעילות ומחזיר רשימה ממוינת של תנועות שהסתיימו.
        """
        completed_motions: List[Motion] = []
        still_moving: List[Motion] = []

        for motion in self._active_motions:
            motion.remaining_time -= ms
            if motion.remaining_time <= 0:
                completed_motions.append(motion)
            else:
                still_moving.append(motion)

        self._active_motions = still_moving

        # 1. תחילה לפי מי שהגיע קודם
        # 2. אחר כך על פי מי שנשלח קודם על ידי ID
        completed_motions.sort(key=lambda m: (m.remaining_time, m.motion_id))
        
        return completed_motions
    
    