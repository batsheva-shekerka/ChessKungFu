from model.board import Board
from model.position import Position

class BoardPrinter:
    @staticmethod
    def print_board(board: Board) -> None:
        """מדפיס את מצב הלוח הנוכחי בפורמט טקסטואלי."""
        for r in range(8):
            row_tokens = []
            for c in range(8):
                piece = board.get_piece(Position(r, c))
                if piece:
                    row_tokens.append(piece.piece_id)
                else:
                    row_tokens.append(".")
            print(" ".join(row_tokens))