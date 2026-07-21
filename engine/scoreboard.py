PIECE_VALUES = {
    'p': 1,
    'n': 3, 'b': 3,
    'r': 5,
    'q': 9,
    'k': 0,
}
PLAYER1='w'
PLAYER2='b'
class Scoreboard:
    def __init__(self):
        self.plaier1_score = 0
        self.plaier2_score = 0
        self.plaier1_moves = []
        self.plaier2_moves = []

    def add_move(self,color,move_text):
        current_moves=[]
        if color == PLAYER1:
            self.plaier1_moves.append(move_text)
            current_moves=self.plaier1_moves
        else:
            self.plaier2_moves.append(move_text)
            current_moves=self.plaier2_moves
        return current_moves
    def add_capture_points(self,capturer_color,captured_piece_type):
        current_score=0
        if capturer_color==PLAYER1:
            self.plaier1_score+=PIECE_VALUES[captured_piece_type]
            current_score=self.plaier1_score
        else:
            self.plaier2_score+=PIECE_VALUES[captured_piece_type]
            current_score=self.plaier2_score
        return current_score

