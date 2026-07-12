from dataclasses import dataclass
from enum import Enum

class PieceStatus(Enum):
    IDLE = "idle"
    MOVING = "moving"
    CAPTURED = "captured"

@dataclass
class Piece:
    piece_id: str       # מזהה ייחודי (למשל 'w_rook_1')
    color: str          # 'w' או 'b'
    piece_type: str     # 'r', 'n', 'b', 'q', 'k', 'p'
    status: PieceStatus = PieceStatus.IDLE

    def __str__(self):
        return f"{self.color}{self.piece_type}({self.status.value})"