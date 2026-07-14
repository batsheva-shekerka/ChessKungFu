from dataclasses import dataclass
from model.position import Position
from model.piece import Piece

@dataclass
class Motion:
    motion_id: int        # מזהה ייחודי רציף המשמש לשבירת שוויון (מי ששוגר קודם)
    piece: Piece          # הכלי שזז
    start: Position       # משבצת המקור
    end: Position         # משבצת היעד
    remaining_time: int   # הזמן שנותר לסיום התנועה במילישניות (ms)
    original_duration: int  # משך התנועה המקורי (ms) — משמש לשבירת שוויון לפי מהירות פיזית