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

# ===== LINE 送信先IDキャッシュ =====
line_targets = set()  # 1:1, グループ, ルームのIDをすべて格納

# ===== LINE → Discord =====
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    print("LINE callback received")  # デバッグ用

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 送信対象IDを自動で登録
    target_id = None
    if event.source.type == "user":
        target_id = event.source.user_id
    elif event.source.type == "group":
        target_id = event.source.group_id
    elif event.source.type == "room":
        target_id = event.source.room_id

    if target_id:
        line_targets.add(target_id)

    # 送信者の名前を取得
    display_name = "Unknown"
    try:
        if event.source.type == "user":
            display_name = line_bot_api.get_profile(event.source.user_id).display_name
        elif event.source.type == "group":
            display_name = line_bot_api.get_group_member_profile(event.source.group_id, event.source.user_id).display_name
        elif event.source.type == "room":
            display_name = line_bot_api.get_room_member_profile(event.source.room_id, event.source.user_id).display_name
    except Exception as e:
        print("プロフィール取得失敗:", e)

    # Discordに送信
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if channel:
        bot.loop.create_task(
            channel.send(f"📲 LINE({display_name}): {event.message.text}")
        )
    else:
        print("Discord channel not found")


# ===== Discord → LINE =====
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id == DISCORD_CHANNEL_ID:
        # 保存済みのLINE送信先すべてに送信
        for target_id in line_targets:
            try:
                line_bot_api.push_message(
                    target_id,
                    TextSendMessage(text=f"💻 Discord({message.author.display_name}): {message.content}")
                )
            except Exception as e:
                print(f"LINE送信失敗 {target_id}: {e}")
    await bot.process_commands(message)

# ===== 並列実行 (Flask + Discord) =====
def run_flask():
    port = int(os.environ.get("PORT", 5000))  # RenderのPORTを使用
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(DISCORD_TOKEN)
