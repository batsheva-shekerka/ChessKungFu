from typing import Set
from model.position import Position
from model.piece import PieceStatus
from model.board import Board


class PieceRules:
    @staticmethod
    def _in_bounds(r: int, c: int, board: Board) -> bool:
        return 0 <= r < board.num_rows and 0 <= c < board.num_cols

    @staticmethod
    def get_straight_moves(start: Position, board: Board) -> Set[Position]:
        """מחשב מהלכים חוקיים בקו ישר (צריח/מלכה) ומטפל בחסימות על הלוח."""
        moves = set()
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

        start_piece = board.get_piece(start)
        if not start_piece:
            return moves

        for dr, dc in directions:
            r, c = start.row + dr, start.col + dc
            while PieceRules._in_bounds(r, c, board):
                current_pos = Position(r, c)
                target_piece = board.get_piece(current_pos)

                if target_piece is None or target_piece.status == PieceStatus.MOVING:
                    moves.add(current_pos)
                else:
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
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1)]

        start_piece = board.get_piece(start)
        if not start_piece:
            return moves

        for dr, dc in directions:
            r, c = start.row + dr, start.col + dc
            while PieceRules._in_bounds(r, c, board):
                current_pos = Position(r, c)
                target_piece = board.get_piece(current_pos)

                if target_piece is None or target_piece.status == PieceStatus.MOVING:
                    moves.add(current_pos)
                else:
                    if target_piece.color != start_piece.color:
                        moves.add(current_pos)
                    break
                r += dr
                c += dc
        return moves

    @staticmethod
    def get_knight_moves(start: Position, board: Board) -> Set[Position]:
        """מחשב מהלכים חוקיים לפרש (קפיצת L)."""
        moves = set()
        start_piece = board.get_piece(start)
        if not start_piece:
            return moves

        offsets = [(-2, -1), (-2, 1), (-1, -2), (-1, 2),
                   (1, -2),  (1,  2), (2, -1),  (2,  1)]
        for dr, dc in offsets:
            r, c = start.row + dr, start.col + dc
            if PieceRules._in_bounds(r, c, board):
                target = board.get_piece(Position(r, c))
                if target is None or target.color != start_piece.color:
                    moves.add(Position(r, c))
        return moves

    @staticmethod
    def get_king_moves(start: Position, board: Board) -> Set[Position]:
        """מחשב מהלכים חוקיים למלך (צעד אחד בכל כיוון)."""
        moves = set()
        start_piece = board.get_piece(start)
        if not start_piece:
            return moves

        offsets = [(-1, -1), (-1, 0), (-1, 1),
                   (0,  -1),          (0,  1),
                   (1,  -1), (1,  0), (1,  1)]
        for dr, dc in offsets:
            r, c = start.row + dr, start.col + dc
            if PieceRules._in_bounds(r, c, board):
                target = board.get_piece(Position(r, c))
                if target is None or target.color != start_piece.color:
                    moves.add(Position(r, c))
        return moves

    @staticmethod
    def get_pawn_moves(start: Position, board: Board) -> Set[Position]:
        """
        מחשב מהלכים חוקיים לרגלי.
        לבנים: זזים למעלה (row-1). שחורים: זזים למטה (row+1).
        צעד כפול מותר רק משורת ההתחלה (שורה 6 ללבן, שורה 1 לשחור).
        הכאה אלכסונית רק כשיש יריב ביעד.
        """
        moves = set()
        piece = board.get_piece(start)
        if not piece:
            return moves

        direction = -1 if piece.color == 'w' else 1
        start_row = board.num_rows - 2 if piece.color == 'w' else 1

        one_step = Position(start.row + direction, start.col)
        if PieceRules._in_bounds(one_step.row, one_step.col, board):
            if board.get_piece(one_step) is None:
                moves.add(one_step)
                two_step = Position(start.row + 2 * direction, start.col)
                if start.row == start_row and PieceRules._in_bounds(two_step.row, two_step.col, board):
                    if board.get_piece(two_step) is None:
                        moves.add(two_step)

        for dc in (-1, 1):
            cap = Position(start.row + direction, start.col + dc)
            if PieceRules._in_bounds(cap.row, cap.col, board):
                target = board.get_piece(cap)
                if target is not None and target.color != piece.color:
                    moves.add(cap)

        return moves