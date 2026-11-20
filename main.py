import os
import sqlite3
import random
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB_PATH = Path("/data/malfred.db")


def connexion():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def initialiser():
    with connexion() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS joueurs (
                user_id INTEGER PRIMARY KEY,
                flocons INTEGER NOT NULL DEFAULT 20,
                dernier_cadeau TEXT
            )
        """)


def creer_joueur(db, user_id):
    db.execute(
        "INSERT OR IGNORE INTO joueurs (user_id) VALUES (?)",
        (user_id,)
    )


@bot.event
async def on_ready():
    initialiser()
    print(f"🎄 Malfred est réveillé : {bot.user}")


@bot.command()
async def malfred(ctx):
    await ctx.send(
        "🎄 HO HO HO ! Malfred est là ! "
        "Surveillez vos flocons, bande de pigeons ! 😈"
    )


@bot.command()
async def flocons(ctx):
    with connexion() as db:
        creer_joueur(db, ctx.author.id)
        solde = db.execute(
            "SELECT flocons FROM joueurs WHERE user_id = ?",
            (ctx.author.id,)
        ).fetchone()[0]

    await ctx.send(
        f"❄️ {ctx.author.mention}, tu possèdes "
        f"**{solde} flocons** !"
    )


@bot.command()
async def cadeau(ctx):
    aujourd_hui = datetime.now(timezone.utc).date().isoformat()

    with connexion() as db:
        db.execute("BEGIN IMMEDIATE")
        creer_joueur(db, ctx.author.id)

        solde, dernier = db.execute(
            "SELECT flocons, dernier_cadeau FROM joueurs WHERE user_id = ?",
            (ctx.author.id,)
        ).fetchone()

        if dernier == aujourd_hui:
            message = (
                "🎁 Doucement, petit pigeon ! "
                "Tu as déjà ouvert ton cadeau aujourd'hui !"
            )
        else:
            gain = random.randint(2, 8)
            nouveau_solde = solde + gain

            db.execute(
                """UPDATE joueurs
                   SET flocons = ?, dernier_cadeau = ?
                   WHERE user_id = ?""",
                (nouveau_solde, aujourd_hui, ctx.author.id)
            )

            message = (
                f"🎁 {ctx.author.mention}, Malfred t'accorde "
                f"**{gain} flocons** ! ❄️\n"
                f"Tu possèdes maintenant **{nouveau_solde} flocons**. "
                "Profites-en, ça ne durera pas ! 😈"
            )

    await ctx.send(message)


initialiser()
bot.run(os.environ["DISCORD_TOKEN"])
