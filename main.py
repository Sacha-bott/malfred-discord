
import os
import sqlite3
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB_PATH = os.getenv("DB_PATH", "malfred.db")

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS joueurs (
                user_id INTEGER PRIMARY KEY,
                flocons INTEGER NOT NULL DEFAULT 20
            )
        """)

def obtenir_solde(user_id):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT OR IGNORE INTO joueurs (user_id) VALUES (?)",
            (user_id,)
        )
        return db.execute(
            "SELECT flocons FROM joueurs WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

@bot.event
async def on_ready():
    print(f"🎄 Malfred est réveillé : {bot.user}")

@bot.command()
async def malfred(ctx):
    await ctx.send(
        "🎄 HO HO HO ! Malfred est là ! "
        "Surveillez vos flocons, bande de pigeons ! 😈"
    )

@bot.command()
async def solde(ctx):
    flocons = obtenir_solde(ctx.author.id)
    await ctx.send(
        f"❄️ {ctx.author.mention}, tu possèdes "
        f"**{flocons} flocons** !\n"
        "😈 Profites-en, ça ne durera pas !"
    )

init_db()
bot.run(os.environ["DISCORD_TOKEN"])
