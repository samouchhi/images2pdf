# Image to PDF Telegram Bot

A Telegram bot that collects photos from you and converts them into a single PDF.

## Features

- Send photos one by one or as albums — the bot collects them into a batch
- `/pdf` (or text `pdf` / `make pdf`) converts the batch to a PDF and sends it back
- A photo captioned `make pdf` converts immediately
- `/cancel` clears the current batch
- Lossless conversion via `img2pdf` (no re-compression of your images)

## Setup

1. Create a bot with **@BotFather** on Telegram and copy its token.
2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Create your config file:

   ```
   copy .env.example .env
   ```

   Then edit `.env` and set `BOT_TOKEN` to your bot's token.

4. Run the bot:

   ```
   python bot.py
   ```

The bot runs locally using long polling — it works while the script is running.

## Deploy on a VPS with Docker

Install Docker Engine and the Docker Compose plugin on your Linux VPS using
[Docker's installation guide](https://docs.docker.com/engine/install/).
Clone this repository (or upload it), then open its directory.

```sh
cp .env.example .env
chmod 600 .env
nano .env
```

Set `BOT_TOKEN` to the token from BotFather, save, then start:

```sh
docker compose up -d --build
docker compose logs -f --tail=100 bot
```

Press Ctrl+C to leave the logs; the bot keeps running. Docker restarts the bot
after crashes or a VPS reboot, provided the Docker service starts on boot.
No domain, HTTPS certificate, or inbound port is needed; allow outbound HTTPS
to Telegram. Run only one instance with the same bot token, including locally,
to avoid polling conflicts.

Useful commands:

```sh
# Check status
docker compose ps

# Update after pulling or uploading new code
docker compose up -d --build

# Stop and remove the container
docker compose down
```

The container runs as a non-root user. The token is passed at runtime and is
excluded from the image. Logs rotate at 10 MB with three files, using
[Docker's log rotation options](https://docs.docker.com/engine/logging/drivers/json-file/).
Pending batches are temporary and are lost when the bot restarts; no volume
is needed because batch state is held in memory.

## Usage

| You do | Bot does |
|---|---|
| `/start` | Shows usage instructions |
| Send photos (one or an album) | Adds them to your batch and confirms the count |
| `/pdf` or `pdf` / `make pdf` | Sends back a PDF of your batch |
| Photo captioned `make pdf` | Adds the photo and converts immediately |
| `/cancel` | Clears your batch |

Batches are held in memory, so restarting the bot clears any pending photos.
