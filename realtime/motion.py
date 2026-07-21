from dataclasses import dataclass
from model.position import Position
from model.piece import Piece

@dataclass
class Motion:
    motion_id: int        
    piece: Piece          
    start: Position        
    end: Position          
    remaining_time: int  
    original_duration: int 
    is_jump: bool = False