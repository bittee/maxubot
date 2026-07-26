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
- 📉 Автоматично знижує якість відео, щоб вміститись у ліміт Telegram (50 МБ)

## Швидкий старт

### 1. Створи бота

1. Напиши [@BotFather](https://t.me/BotFather) → `/newbot` → отримай токен.
2. Для роботи в групах: `/setprivacy` → **Disable** (щоб бот бачив усі
   повідомлення в групі, а не тільки команди).

### 2. Запуск через Docker (рекомендовано)

```bash
git clone https://github.com/bittee/maxubot.git
cd maxubot
cp .env.example .env   # встав свій BOT_TOKEN
docker compose up -d --build
```

### 3. Запуск без Docker

Потрібні Python 3.11+ і [ffmpeg](https://ffmpeg.org/) у PATH.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # встав свій BOT_TOKEN
python -m bot.main
```

## Налаштування (.env)

| Змінна | Обовʼязкова | Опис |
|---|---|---|
| `BOT_TOKEN` | ✅ | токен від @BotFather |
| `COOKIES_FILE` | — | шлях до `cookies.txt` (потрібен для Instagram, приватних постів, вікових обмежень) |
| `MAX_FILE_MB` | — | ліміт розміру файлу, за замовчуванням 49 |
| `MAX_CONCURRENT_DOWNLOADS` | — | одночасних завантажень, за замовчуванням 3 |

### Instagram і cookies

Instagram часто вимагає авторизацію. Експортуй cookies свого акаунта
розширенням браузера (наприклад, «Get cookies.txt LOCALLY»), збережи як
`cookies.txt` у корені проєкту і вкажи `COOKIES_FILE=cookies.txt` у `.env`
(у Docker — розкоментуй volume у `docker-compose.yml`).

## Використання

- **У приваті:** просто скинь лінк.
- **У групі:** додай бота учасником — він відповість на будь-яке повідомлення
  з підтримуваним посиланням.
- **Тільки музика:** `/audio https://…` або кнопка «🎵 Музика» під відео.

## Обмеження

- Bot API дозволяє ботам надсилати файли до **50 МБ** — довгі відео бот
  спробує завантажити в нижчій якості; якщо не влазить — повідомить.
- Приватні/видалені пости недоступні без cookies.
- У каруселях надсилається до 10 елементів на альбом.

## Структура проєкту

```
bot/
├── main.py               # точка входу (long polling)
├── config.py             # конфіг з .env
├── handlers/
│   ├── commands.py       # /start, /help
│   ├── links.py          # обробка лінків + /audio
│   └── callbacks.py      # кнопка «🎵 Музика»
├── services/
│   ├── extractor.py      # пошук/класифікація лінків у тексті
│   ├── downloader.py     # yt-dlp + gallery-dl
│   └── sender.py         # відправка відео/альбомів/аудіо
└── utils/
    ├── text.py           # підписи до медіа
    └── tokens.py         # токени для callback-кнопок
```

## Тести

```bash
pip install pytest
pytest
```
