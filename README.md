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

## Usage

| You do | Bot does |
|---|---|
| `/start` | Shows usage instructions |
| Send photos (one or an album) | Adds them to your batch and confirms the count |
| `/pdf` or `pdf` / `make pdf` | Sends back a PDF of your batch |
| Photo captioned `make pdf` | Adds the photo and converts immediately |
| `/cancel` | Clears your batch |

Batches are held in memory, so restarting the bot clears any pending photos.
