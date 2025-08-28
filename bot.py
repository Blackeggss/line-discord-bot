import os
import threading
import asyncio
import discord
from discord.ext import commands
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# ===== 環境変数 =====
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID"))
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# ===== Discord Bot 設定 =====
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== LINE Bot 設定 =====
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ===== Flask サーバー =====
app = Flask(__name__)

# ===== LINE → Discord =====
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    display_name = "Unknown"

    try:
        if event.source.type == "user":
            profile = line_bot_api.get_profile(event.source.user_id)
            display_name = profile.display_name
        elif event.source.type == "group":
            profile = line_bot_api.get_group_member_profile(event.source.group_id, event.source.user_id)
            display_name = profile.display_name
        elif event.source.type == "room":
            profile = line_bot_api.get_room_member_profile(event.source.room_id, event.source.user_id)
            display_name = profile.display_name
    except Exception as e:
        print("プロフィール取得失敗:", e)

    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if channel:
        asyncio.run_coroutine_threadsafe(
            channel.send(f"📲 LINE({display_name}): {user_message}"),
            bot.loop
        )


# ===== Discord → LINE =====
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id == DISCORD_CHANNEL_ID:
        line_bot_api.push_message(
            LINE_USER_ID,
            TextSendMessage(text=f"💻 Discord({message.author.display_name}): {message.content}")
        )
    await bot.process_commands(message)


# ===== 並列実行 =====
def run_flask():
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(DISCORD_TOKEN)
