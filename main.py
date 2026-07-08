import sys

def main():
    lines = [line.strip() for line in sys.stdin if line.strip()]
    
    board_lines = []
    commands = []
    current_section = None
    
    for line in lines:
        if line.startswith("Board:"):
            current_section = "board"
            continue
        elif line.startswith("Commands:"):
            current_section = "commands"
            continue
        
        if current_section == "board":
            board_lines.append(line)
        elif current_section == "commands":
            commands.append(line)
            
    if not board_lines:
        return

    parsed_board = [row.split() for row in board_lines]
    
    expected_width = len(parsed_board[0])
    for row in parsed_board:
        if len(row) != expected_width:
            print("ERROR ROW_WIDTH_MISMATCH")
            return

   
    valid_pieces = {'K', 'Q', 'R', 'B', 'N', 'P'}
    
    for row in parsed_board:
        for token in row:
            if token == '.':
                continue
            if len(token) == 2 and token[0] in ('w', 'b') and token[1].upper() in valid_pieces:
                continue
            else:
                print("ERROR UNKNOWN_TOKEN")
                return

    for cmd in commands:
        if cmd == "print board":
            for row in parsed_board:
                print(" ".join(row))

if __name__ == "__main__":
    main()