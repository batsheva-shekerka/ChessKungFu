import sys
from texttests.script_runner import ScriptRunner

def main():
    # קריאת כל הקלט שמגיע ממריץ הבדיקות בבת אחת
    raw_input = sys.stdin.read()
    
    # הפעלת הראנר האחראי על הפירוק וההרצה
    runner = ScriptRunner()
    runner.run_script(raw_input)

if __name__ == "__main__":
    main()