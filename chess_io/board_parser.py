from typing import List 
from model.board import Board
from model.position import Position
from model.piece import Piece
from exceptions import ChessValidationError

class BoardParser:
    @staticmethod
    def parse_initial_board(board_lines: List[str]) -> Board:
        
        if not board_lines:
            return Board(num_rows=0, num_cols=0)

        first_row_tokens = board_lines[0].strip().split()
        expected_cols = len(first_row_tokens)

        board = Board(num_rows=len(board_lines), num_cols=expected_cols)
        
        valid_pieces = {'K', 'Q', 'R', 'B', 'N', 'P', 'k', 'q', 'r', 'b', 'n', 'p'}
        for row_idx, line in enumerate(board_lines):
            tokens = line.strip().split()
            if len(tokens) != expected_cols:
                raise ChessValidationError("ERROR ROW_WIDTH_MISMATCH")
            for col_idx, token in enumerate(tokens):
                if token == '.':
                    continue
                
                if '_' in token:
                    parts = token.split('_')
                    color = parts[0]
                    piece_type = parts[1].lower()
                else:
                    if len(token) < 2:
                        raise ChessValidationError("ERROR UNKNOWN_TOKEN")
                    color = token[0].lower()
                    piece_type = token[1:].lower()

                if color not in ('w', 'b') or piece_type not in ('k', 'q', 'r', 'b', 'n', 'p'):
                    raise ChessValidationError("ERROR UNKNOWN_TOKEN")
                
                position = Position(row_idx, col_idx)
                piece = Piece(piece_id=token, color=color, piece_type=piece_type)
                board.set_piece(position, piece)
                    
        return board