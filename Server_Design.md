# Server Design — KungFu Chess (Scalable Real-Time)

## סקירה כללית

מסמך זה מתאר את עיצוב צד השרת למשחק KungFu Chess מרובה משתתפים בזמן אמת.

**יעד סקייל (ייצור מלא):** עד ~100M משתמשים רשומים ו-~10M שחקנים פעילים בו-זמנית.  
**יעד לימודי עכשיו:** גרסה קטנה שעובדת (Docker Compose) עם אותה חלוקת אחריות — בלי לבנות את כל הענן בבת אחת.

### עקרון יסוד (Single Source of Truth)

* ה-**Client לא מחליט** על חוקי המשחק.
* ה-**Gateway לא מחליט** על חוקי המשחק.
* רק ה-**GameEngine** בתוך **Game Server Shard** הוא authoritative: מהלכים חוקיים, מצב לוח, סיום משחק.

הקליינט שולח כוונות (`move`, `play`, `join`); השרת מאמת ומפיץ `ack` / `state` / `game_over`.

---

## 1. רכיבי המערכת

| רכיב | אחריות | מה הוא *לא* עושה |
|------|--------|-------------------|
| **API Gateway** | פעולות שאינן זמן-אמת: `login`, ניהול rooms (יצירה/מידע), היסטוריית משחקים, פרופיל / Elo | לא מריץ לוח, לא מאשר מהלכים |
| **WebSocket Gateway** | מחזיק חיבורים חיים מול הלקוח; מאמת session/token; מנתב הודעות real-time; דוחף state updates ללקוח | לא מריץ GameEngine; לא בוחר חוקים |
| **Matchmaker** | מחבר שחקנים לפי Elo / זמן המתנה; מוציא זוג מוכן למשחק | לא מריץ את המשחק עצמו |
| **Game Allocator** | מחליט **באיזה Game Server Shard** ירוץ כל `room` (לפי עומס / hash / זמינות) ורושם `room_id → shard` | לא משחק את המהלכים |
| **Game Server Shards** | מריצים rooms ב-RAM; כל shard מחזיק GameEngine authoritative + tick | לא שומרים כל מהלך ל-DB בזמן אמת |
| **Observability** | logs, metrics, health checks, עומסי בדיקה (load tests) | לא חלק מלוגיקת המשחק |

### מיפוי לקוד הנוכחי (מונולית שעובד)

כיום רוב התפקידים רצים בתהליך שרת אחד (`Server/`), עם חלוקה לוגית בתוך הקוד:

| רכיב ב-Design | מימוש נוכחי (בקירוב) |
|---------------|----------------------|
| API + WS Gateway | `ws-gateway` service (`server.py` / `app.py`) |
| Matchmaker | `matchmaker` service + Redis queue (`infrastructure/matchmaking/`) |
| Game Allocator | `GameAllocator` בתוך matchmaker (רושם `room → shard` ב-Redis) |
| Game Server | `game-server` service (`game_main.py`) — מנוע authoritative |
| Persistence | PostgreSQL למשתמשים + Redis לסשנים/תור (SQLite כ-fallback מקומי) |

המונולית נשאר נקודת התחלה תקינה; ה-Design מגדיר לאן מפרקים כשעוברים לסקייל.

---

## 2. דיאגרמת אחריות (Logical)

```text
                    ┌─────────────────┐
                    │     Client      │
                    │ (גרפיקה / WS)   │
                    └────────┬────────┘
              HTTP/REST      │      WebSocket
                             │
         ┌───────────────────┴───────────────────┐
         ▼                                       ▼
┌─────────────────┐                   ┌─────────────────────┐
│  API Gateway    │                   │ WebSocket Gateway   │
│ login, rooms,   │                   │ חיבורים חיים,       │
│ history         │                   │ ניתוב + state push  │
└────────┬────────┘                   └──────────┬──────────┘
         │                                       │
         │              ┌────────────────────────┤
         │              │                        │
         ▼              ▼                        ▼
┌──────────────┐  ┌─────────────┐      ┌──────────────────┐
│ PostgreSQL   │  │ Matchmaker  │      │ Game Allocator   │
│ users, games │  │ שידוך Elo   │─────▶│ room → shard     │
│ results      │  └─────────────┘      └────────┬─────────┘
└──────────────┘                                │
                                                ▼
                                     ┌──────────────────────┐
                                     │ Game Server Shards   │
                                     │ GameEngine (truth)   │
                                     └──────────┬───────────┘
                                                │
                     Redis (sessions, queue,    │  NATS / Redis PubSub
                     room→shard, reconnect) ◀───┴──▶ fan-out ל-WS Gateway
```

---

## 3. טכנולוגיות מומלצות

| טכנולוגיה | שימוש |
|-----------|--------|
| **NATS / Redis PubSub** | תקשורת פנימית בין Gateway ↔ Matchmaker ↔ Allocator ↔ Game Shards (נתיב חם) |
| **Redis** | מידע זמני: sessions, active rooms, reconnect, תור matchmaking, מיפוי `room_id → shard` |
| **PostgreSQL** | מידע קבוע: users, games, results, move history (אחרי סיום / נתיב קר) |
| **Docker Compose** | הרצת גרסה קטנה מקומית של המערכת |
| **Kubernetes / K3s** | הרצה מנוהלת ו-scale של containers בסביבת ייצור / מעבדה מתקדמת |

### למה לא SQLite בסקייל?

SQLite נועל קובץ יחיד לכתיבות. תחת עומס מקבילי גבוה (הרשמה, סשנים, Elo) זה הופך לצוואר בקבוק. בלימוד אפשר להשאיר SQLite במונולית; ב-Compose/סקייל — PostgreSQL.

### נתיב חם מול נתיב קר

* **חם:** מהלכים / ack / state — דרך PubSub או RPC קצר, **בלי** לכתוב כל מהלך ל-PostgreSQL.
* **קר:** `game_over`, עדכון Elo, היסטוריה — אסינכרוני ל-PostgreSQL (תור / worker).

---

## 4. זרימות עיקריות

### 4.1 Login

1. Client → **API Gateway** (`login`)
2. אימות / יצירת משתמש מול **PostgreSQL**
3. יצירת session ב-**Redis** + token ללקוח
4. Client מתחבר ל-**WebSocket Gateway** עם token

### 4.2 Matchmaking

1. Client שולח `play` דרך WS Gateway
2. **Matchmaker** מכניס לתור ב-Redis (חלון Elo)
3. כשנמצא זוג → נוצר `room_id`
4. **Game Allocator** בוחר shard ורושם `room_id → shard` ב-Redis
5. שני הלקוחות מקבלים `match_found` (+ צבע) דרך WS Gateway
6. ה-shard יוצר GameEngine ל-room

### 4.3 מהלך במשחק

1. Client שולח `move` ל-WS Gateway
2. Gateway מאתר את ה-shard לפי Redis ומעביר את הבקשה
3. **GameEngine** בודק חוקיות ומעדכן מצב ב-RAM
4. `ack` / בהמשך `state` חוזרים ללקוחות בחדר דרך WS Gateway
5. **לא** נשמר snapshot מלא ל-DB בכל מהלך

### 4.4 סיום משחק

1. GameEngine קובע `game_over` + מנצח
2. פרסום תוצאה לנתיב קר → עדכון Elo / היסטוריה ב-PostgreSQL
3. Cleanup: שחרור room מה-shard + מחיקת מיפוי ב-Redis

### 4.5 Reconnect

* Session / `room_id` ב-Redis מאפשרים חזרה תוך חלון חסד
* WS Gateway מאמת token ומשייך מחדש לחדר הפעיל ב-shard

---

## 5. Game Allocator — למה רכיב נפרד?

בלי Allocator, Matchmaker או Gateway עלולים "להדביק" rooms לשרת קבוע ולהפוך ל-SPOF או לעומס לא מאוזן.

ה-Allocator:

* בוחר shard פחות עמוס / לפי hash על `room_id`
* מעדכן directory ב-Redis
* מאפשר להוסיף shards בלי לשנות את הלקוח

בגרסת Compose קטנה: Allocator יכול להיות פונקציה פשוטה (או שירות מינימלי) שבוחר בין `game-server-1` ל-`game-server-2`.

---

## 6. Observability

| סוג | דוגמאות |
|-----|---------|
| **Logs** | login, match_found, move rejected, game_over, disconnect grace (כבר קיים בסיס ב-`Server/logs`) |
| **Metrics** | חיבורי WS פעילים, אורך תור matchmaking, rooms לכל shard, latency של move→ack |
| **Health** | `/health` לכל שירות ב-Compose (process up + תלות Redis/Postgres) |
| **Load tests** | סימולציית לקוחות (login + play + moves) מול Compose לפני K8s |

בלי observability קשה לדעת אם פיצול השירותים באמת מחזיק עומס.

---

## 7. גרסה קטנה שעובדת (Docker Compose) — יעד המימוש הבא

עקרון: **עדיף משהו קטן שעובד** מאשר לבנות את כל הסקייל ולא לסיים.

### הרכב מוצע ל-Compose

```text
services:
  postgres
  redis
  api-gateway          # login / rooms / history (HTTP)
  ws-gateway           # WebSocket ללקוח
  matchmaker
  game-allocator       # יכול להיות חלק קטן / שירות דק
  game-server-1        # shard עם GameEngine
  # game-server-2      # אופציונלי להדגמת הקצאה
```

תקשורת פנימית ראשונית: **Redis PubSub** (פשוט יותר מ-NATS ללימוד).  
K8s / K3s — רק אחרי ש-`docker compose up` מאפשר לשני קליינטים להתחבר ולשחק end-to-end.

### שלבי מימוש מומלצים

1. ~~שרת בסיסי עובד + קליינט גרפי~~ (קיים)
2. עדכון Design זה (מסמך נוכחי)
3. Docker Compose מינימלי (אריזת השרת + Redis/Postgres)
4. פיצול הדרגתי ל-WS Gateway / Matchmaker / Game Shard לפי הצורך

---

## 8. שיקולי סקייל (ייצור מלא)

### האם שרת אחד מספיק ל-10M בו-זמנית?

**לא.** שרת יחיד הוא SPOF ומוגבל בחיבורי WebSocket, CPU של tick, ורוחב פס. נדרשים Gateways ו-Shards רבים מאחורי load balancing.

### איך כולם משחקים עם כולם?

אין חובה ששני השחקנים יהיו על אותו תהליך פיזי:

1. Matchmaker יוצר `room_id`
2. Allocator רושם ב-Redis איזה shard מחזיק את החדר
3. כל Client מתחבר ל-WS Gateway (יכול להיות Gateway אחר)
4. הודעות `move` מנותבות ל-shard הרשום

### הערכת תעבורה (סדר גודל)

* ~10M פעילים, ~0.5 מהלכים/שנייה למשתמש → ~5M הודעות מהלך/שנייה נכנסות
* ~200B למהלך → סדר גודל של Gbps ברמת datacenter (לא פר משתמש ביתי)
* לכן מפזרים על Gateways ו-Shards רבים — לא NIC אחד

### מחזור חיים קצר של משחק (עשרות שניות–דקות)

* Rooms זמניים על **shards ארוכי חיים** (לא container חדש לכל משחק)
* מצב משחק ב-RAM בלבד בזמן המשחק
* Persist רק בסוף (Elo / תוצאה)
* Cleanup חובה אחרי `game_over` כדי למנוע דליפת זיכרון

---

## 9. החלטות שאנחנו עומדות מאחוריהן

1. **GameEngine הוא מקור האמת** — Client ו-Gateway הם transport / UX בלבד.
2. **הפרדת API (לא real-time) מ-WebSocket (real-time)** — מקלה על scale ועל אבטחת session.
3. **Matchmaker נפרד מ-Game Shard** — שידוך לא חוסם tick של משחקים.
4. **Allocator מפורש** — כדי לא לקבע rooms לשרת אחד כשמוסיפים shards.
5. **Redis לזמני, PostgreSQL לקבוע** — בלי לכתוב כל מהלך ל-DB.
6. **Compose קודם, K8s אחר כך** — גרסה קטנה שעובדת לפני תשתית מלאה.

---

## 10. סיכום

| שכבה | מצב |
|------|-----|
| שרת בסיסי + פרוטוקול + גרפיקה | קיים ועובד |
| Design לפי רכיבי הסקיילביליות | מסמך זה |
| Docker Compose קטן | הצעד הבא למימוש |
| פיצול מלא + K8s | שלב מתקדם אחרי Compose יציב |
