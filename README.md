# KungFu Chess

משחק שחמט בזמן אמת (KungFu Chess) — שחקנים יכולים להזיז כלים במקביל, בלי תורות קלאסיים.  
הפרויקט כולל מנוע משחק מקומי, שרת רשת (WebSocket) וממשק גרפי (OpenCV) להתחברות ולמשחק אונליין.

---

## מה מיוחד במשחק?

- **זמן אמת** — אין המתנה לתור; כלים נעים באוויר לפי משך תנועה
- **אנימציות** — תנועת כלים על הלוח בזמן אמת
- **משחק מרובה משתתפים** — שני שחקנים דרך שרת משותף
- **Elo** — דירוג שמתעדכן בסוף משחק
- **חדרים ו-Matchmaking** — חיפוש יריב או יצירת/הצטרפות לחדר

---

## דרישות מערכת

- Python 3.10+ (מומלץ)
- חבילות עיקריות:
  - `websockets`
  - `opencv-python` (`cv2`)
  - `numpy`

התקנה לדוגמה:

```bash
py -3 -m pip install websockets opencv-python numpy
```

---

## איך מריצים?

### 1. הפעלת השרת

מתיקיית `Server`:

```bash
cd Server
py -3 server.py
```

אמור להופיע משהו כמו:

```text
WebSocket server listening on ws://localhost:8765
```

השאירו את הטרמינל הזה פתוח.

### הרצה עם Docker Compose (מומלץ לגרסת הלימוד)

דורש Docker Desktop פתוח. מתיקיית השורש:

```bash
docker compose up --build
```

זה מריץ:
- **ws-gateway** על פורט `8765` (WebSocket + auth)
- **game-server-1** / **game-server-2** (שני shards של מנוע authoritative; ה-Allocator בוחר)
- **matchmaker** (שידוך דרך Redis + Game Allocator)
- **Redis** על פורט `6379`
- **Postgres** על פורט `5432`

Health / metrics (בדפדפן או `curl`):
- Gateway: http://localhost:18080/health · http://localhost:18080/metrics
- Matchmaker: http://localhost:18081/health · http://localhost:18081/metrics
- Game-1: http://localhost:18082/health · http://localhost:18082/metrics
- Game-2: http://localhost:18083/health · http://localhost:18083/metrics

ב-`/metrics` תראו למשל חיבורי WS, אורך תור matchmaking, rooms לכל shard, ו-latency של move→ack.

עצירה:

```bash
docker compose down
```

הקליינט הגרפי רץ מקומית כמו קודם (`py -3 Design/board/main_design.py`) ומתחבר ל-`ws://localhost:8765`.

> Sessions → **Redis** (`REDIS_URL`).  
> Users / Elo → **PostgreSQL** (`DATABASE_URL`).  
> בלי המשתנים האלה השרת נופל חזרה ל-SQLite (פיתוח מקומי).

### 2. הפעלת הגרפיקה (קליינט)

מתיקיית השורש של הפרויקט, בטרמינל נפרד:

```bash
py -3 Design/board/main_design.py
```

למשחק של שני שחקנים — הריצו את הפקודה **פעמיים** (שני חלונות), עם **שני משתמשים שונים**.  
אין צורך בשרת שני.

### 3. קליינט טרמינל (אופציונלי)

לדיבוג בלבד:

```bash
cd Server
py -3 client.py
```

---

## איך משחקים בממשק הגרפי?

### התחברות (Login)

1. הזינו **Username** ו-**Password** (הקלדה בחלון)
2. לחצו **Enter** או על כפתור **Login**
3. משתמש חדש נוצר אוטומטית בהרשמה ראשונה; בהמשך נדרשת אותה סיסמה

### לובי (Lobby)

| כפתור | מה הוא עושה |
|--------|-------------|
| **Play (matchmaking)** | מחפש יריב עם Elo קרוב (±100) |
| **Cancel queue** | יוצא מתור החיפוש |
| **Create room** | יוצר חדר ומציג `room_id` |
| **Join room** | מצטרף לחדר לפי מזהה |

**חשוב ל-Play:** שני השחקנים חייבים ללחוץ Play כששניהם בלובי (לא בתוך חדר).  
אם רק אחד בתור — אחרי כ־60 שניות תופיע הודעת timeout.

**Create + Join:** שחקן א יוצר חדר; שחקן ב מזין את ה-`room_id` ולוחץ Enter.

### במהלך המשחק

- קליק ראשון — בחירת כלי שלכם
- קליק שני — יעד (המהלך נשלח לשרת)
- כלים בתנועה לא ניתנים לבחירה עד סיום האנימציה
- **ESC** — יציאה מהחלון
- בסיום משחק — **Back to lobby** / מקש **B**

---

## מבנה הפרויקט

```text
chess/
├── Design/board/          # ממשק גרפי + חיבור לשרת
│   ├── main_design.py     # נקודת כניסה ל-UI
│   ├── game_controller.py # מסכים, קליקים, אנימציות מקומיות
│   ├── network_client.py  # WebSocket לקליינט הגרפי
│   └── chessRender.py     # ציור לוח / תפריטים
├── Server/                # שרת רשת
│   ├── server.py          # הפעלת השרת
│   ├── protocol.py        # פרוטוקול JSON בין קליינט לשרת
│   ├── client.py          # קליינט טרמינל
│   ├── application/       # לוגיקת משחק, לובי, auth
│   ├── transport/         # WebSocket, ניתוב הודעות
│   └── domain/            # מודלים, Elo
├── engine/                # מנוע המשחק
├── rules/                 # חוקי כלים
├── realtime/              # תנועות ואנימציה בזמן אמת
├── model/                 # לוח, כלים, מיקומים
├── controller/            # קלט מקומי (מצב offline ישן)
├── tests/                 # בדיקות
├── input.txt              # מצב לוח התחלתי
└── Server_Design.md       # מפרט עיצוב ענן (בקנה מידה רחב)
```

---

## ארכיטקטורה בקצרה

```text
[גרפיקה OpenCV]  --WebSocket JSON-->  [Server]
       |                                    |
  ציור + אנימציה                      מנוע + חדרים
  login / lobby / moves               Elo + matchmaking
```

- השרת הוא **מקור האמת** לחוקיות מהלכים ולמצב המשחק
- הגרפיקה שולחת פקודות (`login`, `play`, `move`…) ומציגה `state` / אנימציה מקומית אחרי `ack`
- פרוטוקול ההודעות מוגדר ב-`Server/protocol.py`

---

## בדיקות

מתיקיית השורש:

```bash
py -3 -m pytest tests/
```

---

## פתרון בעיות נפוצות

| בעיה | פתרון |
|------|--------|
| `Could not connect` / לא מתחבר | ודאו שהשרת רץ על `ws://localhost:8765` |
| `Looking for opponent...` ואז timeout | הריצו קליינט שני עם משתמש אחר ולחצו Play גם שם |
| כפתורים לא מגיבים | לחצו על חלון המשחק כדי לתת לו פוקוס |
| סיסמה שגויה | אותו username דורש את הסיסמה המקורית שנרשמה |

---

## רישיון / הערות

פרויקט לימודי במסגרת Kamatech — KungFu Chess.
