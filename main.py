
import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🎄 Malfred est réveillé : {bot.user}")

@bot.command()
async def malfred(ctx):
    await ctx.send(
        "🎄 HO HO HO ! Malfred est là ! "
        "Surveillez vos flocons, bande de pigeons ! 😈"
    )

bot.run(os.environ["DISCORD_TOKEN"])
