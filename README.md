# 📥 MaxuBot — Telegram-бот-завантажувач

Бот, який завантажує контент за посиланням — у приватному чаті або в групі.
Скидаєш лінк → отримуєш відео/фото/карусель, опис поста і музику.

## Що вміє

- 🎬 **Відео** — TikTok, Instagram Reels, YouTube (Shorts і звичайні), X (Twitter),
  Facebook, Reddit, Pinterest, Vimeo, VK, Threads, Snapchat та [сотні інших сайтів](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
- 🖼 **Фото і каруселі** — Instagram, X, Threads, Pinterest (до 10 елементів, надсилає альбомом)
- 📝 **Опис** — заголовок, текст поста і автор додаються підписом до медіа
- 🎵 **Музика** — кнопка «🎵 Музика» під відео витягує аудіодоріжку в mp3;
  або одразу `/audio <лінк>`
- 👥 **Групи** — додай бота в чат, і він сам реагуватиме на повідомлення
  з підтримуваними посиланнями (на решту повідомлень мовчить)
- 📦 **Файли до 2 ГБ** — через самохостнутий Bot API сервер (у docker-compose
  з коробки); без нього — до 50 МБ зі зниженням якості
- ⚡ **Швидкість** — кеш file_id у Redis (повторний лінк віддається < 1 с без
  завантаження), aria2c (багатопотокове скачування), дедуплікація одночасних
  завантажень, вибір формату за метаданими, tmpfs, uvloop, прогрес у
  статусному повідомленні
- 🎚 **Вибір якості** — для довгих YouTube-відео (15+ хв) бот питає якість
  кнопками: 480p / 720p / 1080p / максимальна
- 🧾 **Зрозумілі помилки** — приватний пост, геоблок, вікове обмеження чи
  видалений контент — бот скаже, в чому справа
- 📈 **/stats** — статистика для адмінів (`ADMIN_IDS` у .env)

## Швидкий старт

### 1. Створи бота

1. Напиши [@BotFather](https://t.me/BotFather) → `/newbot` → отримай токен.
2. Для роботи в групах: `/setprivacy` → **Disable** (щоб бот бачив усі
   повідомлення в групі, а не тільки команди).

### 2. Отримай API_ID і API_HASH

Потрібні для самохостнутого Bot API сервера (файли до 2 ГБ):
[my.telegram.org](https://my.telegram.org) → **API development tools** →
створи застосунок → скопіюй `api_id` і `api_hash`.

### 3. Запуск через Docker (рекомендовано)

```bash
git clone https://github.com/bittee/maxubot.git
cd maxubot
cp .env.example .env   # встав BOT_TOKEN, API_ID, API_HASH
docker compose up -d --build
```

Підніметься три контейнери: бот, `telegram-bot-api` (ліміт 2 ГБ) і Redis (кеш).

> ⚠️ Якщо бот раніше працював через хмарний Bot API, перед першим запуском
> на локальному сервері виконай разово:
> `curl https://api.telegram.org/bot<ТОКЕН>/logOut`
> (інакше локальний сервер не прийме токен).

### 4. Запуск без Docker (простий режим, до 50 МБ)

Потрібні Python 3.11+ і [ffmpeg](https://ffmpeg.org/) у PATH
(опційно aria2 — для швидшого скачування).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # встав свій BOT_TOKEN
python -m bot.main
```

Без `BOT_API_URL` бот працює через хмарний Bot API (ліміт 50 МБ),
без `REDIS_URL` — кеш file_id тримається в памʼяті процесу.

## Налаштування (.env)

| Змінна | Обовʼязкова | Опис |
|---|---|---|
| `BOT_TOKEN` | ✅ | токен від @BotFather |
| `API_ID`, `API_HASH` | для Docker | з [my.telegram.org](https://my.telegram.org), для telegram-bot-api сервера |
| `COOKIES_FILE` | — | шлях до `cookies.txt` (потрібен для Instagram, приватних постів, вікових обмежень) |
| `MAX_FILE_MB` | — | ліміт розміру файлу; за замовчуванням 1950 з локальним Bot API, 49 без |
| `MAX_CONCURRENT_DOWNLOADS` | — | одночасних завантажень, за замовчуванням 4 |
| `BOT_API_URL` | — | адреса самохостнутого telegram-bot-api (у Docker задається автоматично) |
| `REDIS_URL` | — | Redis для кешу file_id (у Docker задається автоматично) |
| `ADMIN_IDS` | — | Telegram ID адмінів через кому — доступ до `/stats` |
| `WEBHOOK_URL` | — | публічний HTTPS-URL для webhook-режиму; без нього — long polling |
| `WEBHOOK_PORT` | — | порт webhook-сервера, за замовчуванням 8080 |

### Instagram і cookies

Instagram часто вимагає авторизацію. Експортуй cookies свого акаунта
розширенням браузера (наприклад, «Get cookies.txt LOCALLY»), збережи як
`cookies.txt` у корені проєкту і вкажи `COOKIES_FILE=cookies.txt` у `.env`
(у Docker — розкоментуй volume у `docker-compose.yml`).

Можна вказати кілька профілів через кому
(`COOKIES_FILE=cookies1.txt,cookies2.txt`) — бот ротуватиме їх між
завантаженнями і перемикатиметься на інший профіль при відмові авторизації.

## Використання

- **У приваті:** просто скинь лінк.
- **У групі:** додай бота учасником — він відповість на будь-яке повідомлення
  з підтримуваним посиланням.
- **Тільки музика:** `/audio https://…` або кнопка «🎵 Музика» під відео.

## Обмеження

- З локальним Bot API сервером (Docker) — файли до **2 ГБ**; через хмарний
  Bot API — до **50 МБ** (бот автоматично знижує якість, щоб вміститись).
- Приватні/видалені пости недоступні без cookies.
- У каруселях надсилається до 10 елементів на альбом.

## Структура проєкту

```
bot/
├── main.py               # точка входу (polling/webhook, локальний Bot API, uvloop)
├── config.py             # конфіг з .env
├── handlers/
│   ├── commands.py       # /start, /help, /stats
│   ├── links.py          # обробка лінків + /audio (кеш → дедуп → завантаження)
│   └── callbacks.py      # кнопки «🎵 Музика» і вибір якості
├── services/
│   ├── extractor.py      # пошук/класифікація лінків у тексті
│   ├── downloader.py     # yt-dlp (+aria2c) + gallery-dl, прогрес, помилки
│   ├── cache.py          # нормалізація URL, кеш file_id (Redis), дедуплікація
│   ├── sender.py         # відправка відео/альбомів/аудіо + з кешу
│   └── stats.py          # статистика для /stats
└── utils/
    ├── text.py           # підписи до медіа
    └── tokens.py         # токени для callback-кнопок
```

Докладніше про архітектуру і подальші плани — у [PLAN.md](PLAN.md).

## Тести

```bash
pip install pytest
pytest
```
