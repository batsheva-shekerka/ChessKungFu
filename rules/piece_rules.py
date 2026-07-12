from typing import Set
from model.position import Position
from model.board import Board

class PieceRules:
    @staticmethod
    def get_straight_moves(start: Position, board: Board) -> Set[Position]:
        """מחשב מהלכים חוקיים בקו ישר (צריח/מלכה) ומטפל בחסימות על הלוח."""
        moves = set()
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)] # ימין, שמאל, למטה, למעלה
        
        start_piece = board.get_piece(start)
        if not start_piece:
            return moves

        for dr, dc in directions:
            r, c = start.row + dr, start.col + dc
            while 0 <= r < 8 and 0 <= c < 8: # גבולות הלוח הסטנדרטי
                current_pos = Position(r, c)
                target_piece = board.get_piece(current_pos)
                
                if target_piece is None:
                    moves.add(current_pos)
                else:
                    # אם זה כלי של היריב, המהלך חוקי (הכאה), אך הדרך חסומה להמשך
                    if target_piece.color != start_piece.color:
                        moves.add(current_pos)
                    break
                r += dr
                c += dc
        return moves

    @staticmethod
    def get_diagonal_moves(start: Position, board: Board) -> Set[Position]:
        """מחשב מהלכים חוקיים באלכסון (רץ/מלכה) ומטפל בחסימות על הלוח."""
        moves = set()
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1)] # ארבעת האלכסונים
        
        start_piece = board.get_piece(start)
        if not start_piece:
            return moves

        for dr, dc in directions:
            r, c = start.row + dr, start.col + dc
            while 0 <= r < 8 and 0 <= c < 8:
                current_pos = Position(r, c)
                target_piece = board.get_piece(current_pos)
                
                if target_piece is None:
                    moves.add(current_pos)
                else:
                    if target_piece.color != start_piece.color:
                        moves.add(current_pos)
                    break
                r += dr
                c += dc
        return moves