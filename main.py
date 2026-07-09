# Git Repository URL: https://github.com/batsheva-shekerka/ChessKungFu.git

from parser import BoardParser
from board import Board
from exceptions import BoardValidationError

def main():
    try:
        grid, commands = BoardParser.parse_from_stdin()
        if not grid:
            return
        
        board = Board(grid)
        
        for cmd in commands:
            parts = cmd.split()
            if not parts:
                continue
                
            command_type = parts[0]
            
            if command_type == "click" and len(parts) == 3:
                x, y = int(parts[1]), int(parts[2])
                board.handle_click(x, y)
                
            elif command_type == "wait" and len(parts) == 2:
                ms = int(parts[1])
                board.handle_wait(ms)
                
            elif cmd == "print board":
                board.display()
                
    except BoardValidationError as e:
        print(f"{e}")

if __name__ == "__main__":
    main()