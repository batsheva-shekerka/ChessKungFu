from typing import List  # <-- 1. להוסיף את השורה הזו בטופ של הקובץ!
from model.board import Board
from model.position import Position
from model.piece import Piece
from exceptions import ChessValidationError

class BoardParser:
    @staticmethod
    def parse_initial_board(board_lines: List[str]) -> Board:
        
        board = Board()
        if not board_lines:
            board.num_rows = 0
            board.num_cols = 0
            return board
        
        # שמירת אורך השורה הראשונה כבסיס להשוואה
        first_row_tokens = board_lines[0].strip().split()
        expected_cols = len(first_row_tokens)
        
        board.num_rows = len(board_lines)
        board.num_cols = expected_cols
        
        # רשימת סוגי הכלים המותרים בשחמט
        valid_pieces = {'K', 'Q', 'R', 'B', 'N', 'P', 'k', 'q', 'r', 'b', 'n', 'p'}
        for row_idx, line in enumerate(board_lines):
        # פיצול השורה לפי רווחים (מניח שהכלים מופרדים ברווח, למשל 'w_r_1' או '.')
            tokens = line.strip().split()
            if len(tokens) != expected_cols:
                raise ChessValidationError("ERROR ROW WIDTH MISMATCH")
            for col_idx, token in enumerate(tokens):
                if token == '.':
                    continue
                
                if '_' in token:
                    parts = token.split('_')
                    color = parts[0]
                    piece_type = parts[1]
                else:
                    if len(token) < 2:
                        raise ChessValidationError("ERROR UNKNOWN TOKEN")
                    color = token[0]
                    piece_type = token[1:]
                
                # בדיקה עבור Test 4: האם הצבע או סוג הכלי אינם חוקיים?
                if color not in ('w', 'b') or piece_type not in valid_pieces:
                    raise ChessValidationError("ERROR UNKNOWN TOKEN")
                
                position = Position(row_idx, col_idx)
                piece = Piece(piece_id=token, color=color, piece_type=piece_type)
                board.set_piece(position, piece)
                    
        return board