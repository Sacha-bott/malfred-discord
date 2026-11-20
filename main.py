import os
import random
import sqlite3
from datetime import datetime, timezone

import discord
from discord.ext import commands

DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/malfred.db")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def connexion():
    directory = os.path.dirname(DATABASE_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=20)
    db.execute("PRAGMA busy_timeout=20000")
    return db


def initialiser_base():
    with connexion() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS joueurs (
            user_id INTEGER PRIMARY KEY,
            flocons INTEGER NOT NULL DEFAULT 20,
            dernier_cadeau TEXT
        )""")


def creer_joueur(db, user_id):
    db.execute("INSERT OR IGNORE INTO joueurs (user_id, flocons, dernier_cadeau) VALUES (?, 20, NULL)", (user_id,))


@bot.event
async def on_ready():
    print(f"🎄 Malfred est réveillé : {bot.user}")


@bot.command()
async def malfred(ctx):
    await ctx.send("🎄 HO HO HO ! Malfred est là ! Surveillez vos flocons, bande de pigeons ! 😈")


@bot.command(aliases=["flocon"])
async def flocons(ctx):
    with connexion() as db:
        creer_joueur(db, ctx.author.id)
        solde = db.execute("SELECT flocons FROM joueurs WHERE user_id = ?", (ctx.author.id,)).fetchone()[0]
    await ctx.send(f"❄️ {ctx.author.mention}, tu possèdes **{solde} flocons** !")


@bot.command()
async def cadeau(ctx):
    await ctx.send(
        "🎁 **CHOISIS TON POISON, PETIT PIGEON !**\n"
        "1️⃣ **Paquet du lâche** — 70 % de gagner (+2 à +5), sinon −1 à −3 ❄️\n"
        "2️⃣ **Coffre du filou** — 50 % de gagner (+5 à +12), sinon −4 à −8 ❄️\n"
        "3️⃣ **Cadeau du démon** — 30 % de gagner (+15 à +30), sinon −8 à −15 ❄️\n\n"
        "Tape **!ouvrir 1**, **!ouvrir 2** ou **!ouvrir 3**. Un seul cadeau par jour ! 😈"
    )


@bot.command()
async def ouvrir(ctx, choix: int = 0):
    cadeaux = {
        1: (70, (2, 5), (1, 3), "Paquet du lâche"),
        2: (50, (5, 12), (4, 8), "Coffre du filou"),
        3: (30, (15, 30), (8, 15), "Cadeau du démon"),
    }
    if choix not in cadeaux:
        await ctx.send("🎁 Choisis **1**, **2** ou **3**, génie du mal.")
        return

    jour = datetime.now(timezone.utc).date().isoformat()
    chance, gains, pertes, nom = cadeaux[choix]
    with connexion() as db:
        db.execute("BEGIN IMMEDIATE")
        creer_joueur(db, ctx.author.id)
        solde, dernier = db.execute(
            "SELECT flocons, dernier_cadeau FROM joueurs WHERE user_id = ?", (ctx.author.id,)
        ).fetchone()
        if dernier == jour:
            await ctx.send("🎄 Doucement, petit pigeon ! Tu as déjà ouvert ton cadeau aujourd'hui. Reviens demain ! 😈")
            return

        victoire = random.randint(1, 100) <= chance
        montant = random.randint(*(gains if victoire else pertes))
        nouveau_solde = solde + montant if victoire else max(0, solde - montant)
        difference = nouveau_solde - solde
        db.execute(
            "UPDATE joueurs SET flocons = ?, dernier_cadeau = ? WHERE user_id = ?",
            (nouveau_solde, jour, ctx.author.id),
        )

    if victoire:
        phrase = random.choice([
            "QUOI ?! Tu as gagné ?! Mon comptable va me tuer !",
            "Profite, petit insolent. La chance tourne.",
            "J'ai dû emballer le mauvais cadeau... 😤",
        ])
        resultat = f"🎉 **+{difference} flocons !**"
    else:
        phrase = random.choice([
            "HAHAHA ! Merci pour les flocons, pigeon !",
            "C'est Noël pour MOI, visiblement. 😈",
            "Tu aurais dû lire les petites lignes. Elles n'existent pas.",
        ])
        resultat = f"💀 **{difference} flocons !**"

    await ctx.send(
        f"🎁 {ctx.author.mention} ouvre **{nom}** !\n"
        f"{resultat}\n{phrase}\n❄️ Nouveau solde : **{nouveau_solde} flocons**."
    )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("🎁 Tape **!ouvrir 1**, **!ouvrir 2** ou **!ouvrir 3**.")
        return
    raise error


if __name__ == "__main__":
    initialiser_base()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("La variable DISCORD_TOKEN manque sur Railway.")
    bot.run(token)
