from model.board import Board
from model.position import Position

class BoardPrinter:
    @staticmethod
    def print_board(board: Board) -> None:
        """מדפיס את מצב הלוח הנוכחי בפורמט טקסטואלי."""
        for r in range(board.num_rows):
            row_tokens = []
            for c in range(board.num_cols):
                piece = board.get_piece(Position(r, c))
                if piece:
                    row_tokens.append(piece.piece_id)
                else:
                    row_tokens.append(".")
            print(" ".join(row_tokens))