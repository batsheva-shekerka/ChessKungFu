import sys
from texttests.script_runner import ScriptRunner

def main():
    raw_input = sys.stdin.read()
    
    runner = ScriptRunner()
    runner.run_script(raw_input)

if __name__ == "__main__":
    main()