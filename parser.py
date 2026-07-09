import sys

class BoardParser:
    """אחראית אך ורק על קריאת הקלט מה-stdin ופירוקו לסעיפים"""
    @staticmethod
    def parse_from_stdin():
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

        grid = [row.split() for row in board_lines]
        return grid, commands