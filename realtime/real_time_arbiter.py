from typing import List
from realtime.motion import Motion
from model.piece import Piece, PieceStatus
from model.position import Position


class RealTimeArbiter:
    def __init__(self):
        self._active_motions: List[Motion] = []
        self._motion_counter = 0
    def start_jump(self, piece: Piece, position: Position, duration_ms: int = 1000) -> None:
        self._motion_counter += 1
        piece.status = PieceStatus.JUMPING

        new_motion = Motion(
            motion_id=self._motion_counter,
            piece=piece,
            start=position,
            end=position,         
            remaining_time=duration_ms,
            original_duration=duration_ms,
            is_jump=True
        )
        self._active_motions.append(new_motion)
    def start_motion(self, piece: Piece, start: Position, end: Position, duration_ms: int) -> None:
        """משחרר כלי לאוויר ומשנה את מצבו ל-MOVING."""
        self._motion_counter += 1
        piece.status = PieceStatus.MOVING

        new_motion = Motion(
            motion_id=self._motion_counter,
            piece=piece,
            start=start,
            end=end,
            remaining_time=duration_ms,
            original_duration=duration_ms
        )
        self._active_motions.append(new_motion)

        # בדיקת התנגשות ראש-בראש עם תנועות קיימות ישנות יותר
        self._resolve_common_route_collision(new_motion)

    def _resolve_common_route_collision(self, new_motion: Motion) -> None:
        """
        לאחר שיגור תנועה חדשה, בודק אם היא נמצאת על מסלול ישיר (ראש-בראש)
        מול תנועה קיימת שהתחילה קודם.
        אם כן — התנועה החדשה מוסרת מיידית (הכלי הוותיק מנצח).
        """
        for existing in list(self._active_motions):
            if existing is new_motion:
                continue
            if self._are_on_collision_course(existing, new_motion):
                self._active_motions.remove(new_motion)
                return

    @staticmethod
    def _sign(x: int) -> int:
        return 1 if x > 0 else (-1 if x < 0 else 0)

    @staticmethod
    def _are_on_collision_course(motion_a: Motion, motion_b: Motion) -> bool:
        """
        בודק האם motion_b נמצא בנתיב הישיר של motion_a בכיוון ההפוך.
        מחזיר True אם:
          - שניהם נעים על אותו קו ישר (שורה / עמודה / אלכסון)
          - בכיוונים מנוגדים
          - נקודת המוצא של B נמצאת בתחום הנתיב של A (בין A.start ל-A.end)
        """
        s = RealTimeArbiter._sign

        dr_a = s(motion_a.end.row - motion_a.start.row)
        dc_a = s(motion_a.end.col - motion_a.start.col)
        dr_b = s(motion_b.end.row - motion_b.start.row)
        dc_b = s(motion_b.end.col - motion_b.start.col)

        if dr_a + dr_b != 0 or dc_a + dc_b != 0:
            return False
        if dr_a == 0 and dc_a == 0:
            return False

        diff_row = motion_b.start.row - motion_a.start.row
        diff_col = motion_b.start.col - motion_a.start.col
        end_row  = motion_a.end.row   - motion_a.start.row
        end_col  = motion_a.end.col   - motion_a.start.col

        if dr_a == 0: 
            if diff_row != 0:
                return False
            if dc_a > 0:
                return 0 < diff_col <= end_col
            else:
                return end_col <= diff_col < 0

        elif dc_a == 0:  
            if diff_col != 0:
                return False
            if dr_a > 0:
                return 0 < diff_row <= end_row
            else:
                return end_row <= diff_row < 0

        else:  
            if diff_row == 0 or diff_col == 0:
                return False
            if abs(diff_row) != abs(diff_col):
                return False
            if s(diff_row) != dr_a or s(diff_col) != dc_a:
                return False
            steps = abs(diff_row)
            total  = abs(end_row)
            return 0 < steps <= total

    def has_active_motion(self) -> bool:
        """מחזיר האם יש כרגע תנועה כלשהי באוויר."""
        return len(self._active_motions) > 0
    
    def get_active_motions(self):
        return list(self._active_motions)
    
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

        completed_motions.sort(key=lambda m: (m.remaining_time, m.motion_id))

        return completed_motions
