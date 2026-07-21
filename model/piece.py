from dataclasses import dataclass
from enum import Enum

class PieceStatus(Enum):
    IDLE = "idle"
    MOVING = "moving"
    JUMPING = "jumping"
    CAPTURED = "captured"

@dataclass
class Piece:
    piece_id: str       
    color: str          
    piece_type: str     
    status: PieceStatus = PieceStatus.IDLE
    animation_time:int=1

    def __str__(self):
        return f"{self.color}{self.piece_type}({self.status.value})"