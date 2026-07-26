# 🚂 Деплой на Railway — покроковий план

Railway не запускає `docker-compose.yml` напряму як прод-конфіг — кожен сервіс
(бот, telegram-bot-api, Redis) деплоїться окремо в межах одного проєкту й
спілкується через приватну мережу Railway (`*.railway.internal`). План нижче
йде від найпростішого робочого варіанту до повного (2 ГБ + кеш).

---

## Крок 0 — що підготувати заздалегідь

- Обліковий запис на [railway.app](https://railway.app) (прив'язаний до GitHub).
- Токен бота від [@BotFather](https://t.me/BotFather) + `/setprivacy` → **Disable**.
- Репозиторій уже на GitHub (`bittee/maxubot`) — Railway деплоїть з нього напряму,
  нічого зливати вручну не треба.
- (Для 2 ГБ) `api_id`/`api_hash` з [my.telegram.org](https://my.telegram.org) →
  API development tools.
- (Опційно) `cookies.txt` для Instagram — про перенесення на Railway див. крок 5.
- Встанови [Railway CLI](https://docs.railway.com/guides/cli) — знадобиться для
  `railway logs` і, якщо треба, `railway ssh` (крок 5): `npm i -g @railway/cli`.

**Порада:** роби це поетапно й перевіряй кожен крок в логах, перш ніж додавати
наступний сервіс — так простіше знайти, що саме зламалось.

---

## Етап A — мінімальний бот (хмарний API, ліміт 50 МБ)

Мета — переконатись, що образ збирається і бот взагалі стартує на Railway,
перш ніж ускладнювати.

1. **New Project** → **Deploy from GitHub repo** → обери `bittee/maxubot`.
   Railway сам знайде `Dockerfile` у корені й збере образ.
2. Сервіс отримає назву типу `maxubot`. Відкрий **Variables** і додай:
   ```
   BOT_TOKEN=<токен від BotFather>
   ```
3. **Settings → Networking**: нічого не чіпай — публічний домен НЕ потрібен.
   Бот працює через long polling (сам ініціює зʼєднання з Telegram), порт не слухає.
4. Задеплой (Railway зробить це автоматично після додавання variables).
   Перевір логи: `railway logs` або вкладка **Deployments → View Logs** — має бути
   `Бот запущено (polling): @твій_бот`.
5. Напиши боту в Telegram лінк на TikTok/YouTube — має відповісти файлом
   (до 50 МБ, кеш — в памʼяті процесу, зникає при рестарті).

Якщо цього достатньо — можна зупинитись тут. Далі — прискорення й 2 ГБ.

---

## Етап B — додати Redis (кеш file_id, миттєві повтори)

1. У проєкті: **+ New** → **Database** → **Add Redis**.
   Railway підніме керований Redis і сам створить змінну підключення.
2. У сервісі `maxubot` → **Variables** → додай через **Add Reference**
   (не хардкодь вручну — так значення оновиться, якщо Railway його змінить):
   ```
   REDIS_URL=${{Redis.REDIS_URL}}
   ```
   (назва референсу залежить від того, як Railway назвав сервіс Redis —
   зазвичай `Redis`; підстав актуальну зі списку автодоповнення `${{ }}`).
3. Redeploy сервісу `maxubot`. У логах має зʼявитись
   `Кеш file_id: Redis підключено (...)`.

---

## Етап C — самохостнутий Bot API сервер (файли до 2 ГБ)

1. **+ New** → **Empty Service** (або **Docker Image**) → вкажи образ
   `aiogram/telegram-bot-api:latest`. Назви сервіс, наприклад, `telegram-bot-api`.
2. **Variables** для цього сервісу:
   ```
   TELEGRAM_API_ID=<api_id з my.telegram.org>
   TELEGRAM_API_HASH=<api_hash з my.telegram.org>
   TELEGRAM_LOCAL=1
   ```
3. **Settings → Volumes** → **+ New Volume** → mount path `/var/lib/telegram-bot-api`.
   Без volume дані (сесії) губляться при кожному редеплої/рестарті.
4. **Settings → Networking**: публічний домен НЕ додавай — цей сервіс має
   бути доступний лише всередині проєкту (там же лежить твій `api_hash`).
   Приватна мережа увімкнена за замовчуванням; внутрішня адреса матиме вигляд
   `telegram-bot-api.railway.internal` (сервіс слухає порт `8081`).
5. **Важливо, разова дія:** якщо бот раніше вже приймав апдейти через хмарний
   Bot API, Telegram не пустить той самий токен на локальний сервер, поки
   не «розлогінити» його з хмари:
   ```
   curl https://api.telegram.org/bot<ТВІЙ_ТОКЕН>/logOut
   ```
   Виконай це один раз (з будь-якого місця — це просто HTTP-запит) **перед**
   тим, як бот у Railway вперше підключиться через `BOT_API_URL`.
6. У сервісі `maxubot` → **Variables** додай:
   ```
   BOT_API_URL=http://telegram-bot-api.railway.internal:8081
   ```
   (заміни `telegram-bot-api` на реальну назву сервісу, якщо назвав інакше —
   Railway показує внутрішню адресу в **Settings → Networking** цього сервісу).
7. Redeploy `maxubot`. У логах: `Локальний Bot API: http://telegram-bot-api.railway.internal:8081 (ліміт 1950 МБ)`.
8. Перевір: скинь боту довге відео (>50 МБ) — має завантажитись і надіслатись.

---

## Крок 5 — cookies для Instagram (опційно)

Railway не має простого веб-аплоаду файлів у контейнер. Найчистіший спосіб:

1. Додай сервісу `maxubot` **Volume**, напр. mount path `/app/data`.
2. Задай `COOKIES_FILE=/app/data/cookies.txt`.
3. Підключись до контейнера й запиши файл напряму:
   ```
   railway link            # прив'язати CLI до проєкту (один раз)
   railway ssh -s maxubot
   cat > /app/data/cookies.txt <<'EOF'
   # встав тут вміст свого cookies.txt (формат Netscape)
   EOF
   exit
   ```
4. Redeploy не обов'язковий — файл уже на volume; за потреби перезапусти сервіс.

Для кількох профілів (ротація при бані) — постав кілька файлів на той самий
volume і вкажи `COOKIES_FILE=/app/data/cookies1.txt,/app/data/cookies2.txt`.

---

## Підсумкова карта сервісів у проєкті Railway

| Сервіс | Джерело | Публічний домен | Volume | Ключові змінні |
|---|---|---|---|---|
| `maxubot` | GitHub repo (Dockerfile) | ні (polling) | опційно, для cookies | `BOT_TOKEN`, `BOT_API_URL`, `REDIS_URL`, `ADMIN_IDS` |
| `telegram-bot-api` | Docker image `aiogram/telegram-bot-api` | ні (приватна мережа) | так, обов'язково | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_LOCAL=1` |
| `Redis` | Railway managed database | — | керується Railway | — |

---

## Нюанси й типові помилки

- **«Unauthorized» після переходу на BOT_API_URL** — забув крок `logOut`
  (п.5 етапу C), або URL/порт вказано неправильно.
- **Бот «засинає»/рестартиться** — Railway може приспати сервіс на дешевих
  планах при відсутності HTTP-трафіку; long-polling воркер без публічного
  домену зазвичай працює 24/7 без проблем, але звір план на Hobby/Pro, якщо
  бачиш несподівані рестарти.
- **`/var/lib/telegram-bot-api` без volume** — після кожного редеплою
  telegram-bot-api сервіс «забуде» сесію й може тимчасово відмовляти в запитах
  одразу після старту (кілька секунд). З volume таке не повторюється.
- **Вартість** — три сервіси (бот + telegram-bot-api + Redis), що працюють
  безперервно, споживають план Railway цілодобово. Redis-плагін і volume теж
  тарифікуються. Для тесту можна зупинитись на Етапі A (без Redis і без
  локального Bot API) — і рахунок буде мінімальним.
- **Webhook замість polling** — якщо захочеш перейти на webhook (нижча
  латентність), увімкни публічний домен для `maxubot` у Networking і задай
  `WEBHOOK_URL=https://<домен-railway>`; порт бот візьме автоматично з
  Railway-змінної `PORT` (це вже враховано в конфізі бота).
- **Оновлення коду** — Railway передеплоює сервіс `maxubot` автоматично на
  кожен push у гілку, яку він відстежує (перевір **Settings → Source** —
  яка гілка підключена).
