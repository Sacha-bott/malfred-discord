import os
import random
import sqlite3
from datetime import datetime, timezone

import discord
from discord.ext import commands

DATABASE_PATH = os.getenv('DATABASE_PATH', '/data/malfred.db')
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

OBJETS = {
    'bouclier': ('🛡️ Bouclier givré', 25, 'Annule la prochaine perte de flocons.'),
    'trefle': ('🍀 Trèfle douteux', 15, '+15 points de chance sur le prochain cadeau ouvert.'),
    'boule': ('🔮 Boule à neige', 30, 'Donne droit à une rencontre supplémentaire avec !rencontre.'),
    'paquet': ('🎁 Paquet suspect', 20, 'Rapporte immédiatement 0 à 30 flocons.'),
    'canard': ('🦆 Canard de contrebande', 15, 'Objet de collection totalement inutile.'),
}


def connexion():
    dossier = os.path.dirname(DATABASE_PATH)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=20)
    db.execute('PRAGMA busy_timeout=20000')
    return db


def initialiser_base():
    with connexion() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS joueurs (
            user_id INTEGER PRIMARY KEY,
            flocons INTEGER NOT NULL DEFAULT 20,
            dernier_cadeau TEXT
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS boutique_joueurs (
            user_id INTEGER PRIMARY KEY,
            dernier_achat TEXT
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS inventaire (
            user_id INTEGER NOT NULL,
            objet TEXT NOT NULL,
            quantite INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (user_id, objet)
        )''')


def creer_joueur(db, user_id):
    db.execute('INSERT OR IGNORE INTO joueurs (user_id, flocons, dernier_cadeau) VALUES (?, 20, NULL)', (user_id,))


def possede(db, user_id, objet):
    return db.execute('SELECT 1 FROM inventaire WHERE user_id=? AND objet=?', (user_id, objet)).fetchone() is not None


def retirer_objet(db, user_id, objet):
    db.execute('DELETE FROM inventaire WHERE user_id=? AND objet=?', (user_id, objet))


def jour_utc():
    return datetime.now(timezone.utc).date().isoformat()


@bot.event
async def on_ready():
    print(f'🎄 Malfred est réveillé : {bot.user}')


@bot.command()
async def malfred(ctx):
    await ctx.send('🎄 HO HO HO ! Malfred est là ! Surveillez vos flocons, bande de pigeons ! 😈')


@bot.command(aliases=['flocon'])
async def flocons(ctx):
    with connexion() as db:
        creer_joueur(db, ctx.author.id)
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (ctx.author.id,)).fetchone()[0]
    await ctx.send(f'❄️ {ctx.author.mention}, tu possèdes **{solde} flocons** !')


@bot.command()
async def cadeau(ctx):
    await ctx.send(
        '🎁 **CHOISIS TON POISON, PETIT PIGEON !**\n'
        '1️⃣ **Paquet du lâche** — 70 % de gagner (+2 à +5), sinon −1 à −3 ❄️\n'
        '2️⃣ **Coffre du filou** — 50 % de gagner (+5 à +12), sinon −4 à −8 ❄️\n'
        '3️⃣ **Cadeau du démon** — 30 % de gagner (+15 à +30), sinon −8 à −15 ❄️\n\n'
        'Tape **!ouvrir 1**, **!ouvrir 2** ou **!ouvrir 3**. Un seul cadeau par jour ! 😈'
    )


@bot.command()
async def ouvrir(ctx, choix: int = 0):
    cadeaux = {
        1: (70, (2, 5), (1, 3), 'Paquet du lâche'),
        2: (50, (5, 12), (4, 8), 'Coffre du filou'),
        3: (30, (15, 30), (8, 15), 'Cadeau du démon'),
    }
    if choix not in cadeaux:
        await ctx.send('🎁 Choisis **1**, **2** ou **3**, génie du mal.')
        return

    chance, gains, pertes, nom = cadeaux[choix]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, ctx.author.id)
        solde, dernier = db.execute(
            'SELECT flocons, dernier_cadeau FROM joueurs WHERE user_id=?', (ctx.author.id,)
        ).fetchone()
        if dernier == jour_utc():
            reponse = '🎄 Doucement, petit pigeon ! Tu as déjà ouvert ton cadeau aujourd’hui. Reviens demain ! 😈'
        else:
            bonus = 15 if possede(db, ctx.author.id, 'trefle') else 0
            if bonus:
                retirer_objet(db, ctx.author.id, 'trefle')
            victoire = random.randint(1, 100) <= chance + bonus
            montant = random.randint(*(gains if victoire else pertes))
            protege = not victoire and possede(db, ctx.author.id, 'bouclier')
            if protege:
                retirer_objet(db, ctx.author.id, 'bouclier')
            nouveau = solde + montant if victoire else (solde if protege else max(0, solde - montant))
            db.execute('UPDATE joueurs SET flocons=?, dernier_cadeau=? WHERE user_id=?',
                       (nouveau, jour_utc(), ctx.author.id))
            if victoire:
                phrase = random.choice([
                    'QUOI ?! Tu as gagné ?! Mon comptable va me tuer !',
                    'Profite, petit insolent. La chance tourne.',
                    'J’ai dû emballer le mauvais cadeau... 😤',
                ])
                resultat = f'🎉 **+{nouveau - solde} flocons !**'
            elif protege:
                phrase = '🛡️ Ton Bouclier givré a absorbé la perte et s’est brisé. Voleur de victoire !'
                resultat = '❄️ **0 flocon perdu !**'
            else:
                phrase = random.choice([
                    'HAHAHA ! Merci pour les flocons, pigeon !',
                    'C’est Noël pour MOI, visiblement. 😈',
                    'Tu aurais dû lire les petites lignes. Elles n’existent pas.',
                ])
                resultat = f'💀 **{nouveau - solde} flocons !**'
            reponse = (f'🎁 {ctx.author.mention} ouvre **{nom}** !\n{resultat}\n{phrase}\n'
                       f'❄️ Nouveau solde : **{nouveau} flocons**.'
                       + (' 🍀 Trèfle utilisé !' if bonus else ''))
    await ctx.send(reponse)


def afficher_boutique():
    embed = discord.Embed(title='🛒 LA BOUTIQUE DE MALFRED', description='Le marché noir du pôle Nord\n« Même mes promotions sont des arnaques, petits pigeons ! » 😈', color=discord.Color.green())
    for code, (nom, prix, description) in OBJETS.items():
        embed.add_field(name=f'{nom} — {prix} ❄️', value=description, inline=False)
    embed.set_footer(text='1 achat par jour • 1 exemplaire par objet • Aucun échange')
    return embed


def afficher_inventaire(user):
    with connexion() as db:
        creer_joueur(db, user.id)
        objets = db.execute('SELECT objet FROM inventaire WHERE user_id=? ORDER BY objet', (user.id,)).fetchall()
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user.id,)).fetchone()[0]
    contenu = '\n'.join(OBJETS[code][0] for (code,) in objets if code in OBJETS)
    return discord.Embed(title=f'🎒 Inventaire de {user.display_name}', description=(contenu or 'Vide ! Même les mites ont déménagé. 😈') + f'\n\n❄️ **{solde} flocons**', color=discord.Color.gold())


def effectuer_achat(user_id, objet):
    nom, prix, _ = OBJETS[objet]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]
        ancien = db.execute('SELECT dernier_achat FROM boutique_joueurs WHERE user_id=?', (user_id,)).fetchone()
        if ancien and ancien[0] == jour_utc():
            return '🛒 Un seul achat par jour, petit pigeon ! Reviens demain. 😈'
        if possede(db, user_id, objet):
            return '🎒 Tu possèdes déjà cet objet ! Un exemplaire maximum, avare !'
        if solde < prix:
            return f'💸 **{prix} flocons** nécessaires, tu n’en as que **{solde}** !'
        db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?', (prix, user_id))
        db.execute('INSERT INTO boutique_joueurs (user_id, dernier_achat) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET dernier_achat=excluded.dernier_achat', (user_id, jour_utc()))
        if objet != 'paquet':
            db.execute('INSERT INTO inventaire (user_id, objet, quantite) VALUES (?, ?, 1)', (user_id, objet))
        gain = random.randint(0, 30) if objet == 'paquet' else 0
        if gain:
            db.execute('UPDATE joueurs SET flocons=flocons+? WHERE user_id=?', (gain, user_id))
        reponse = f'🛒 Tu achètes **{nom}** pour **{prix} flocons** !\n'
        if objet == 'paquet':
            reponse += f'🎁 Le paquet contenait **{gain} flocons** !\n'
        return reponse + f'❄️ Solde : **{solde - prix + gain} flocons**. 😈'


class ChoixObjet(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=nom.split(' ', 1)[1], value=code, description=f'{prix} flocons — {description[:65]}', emoji=nom.split(' ', 1)[0]) for code, (nom, prix, description) in OBJETS.items()]
        super().__init__(placeholder='Choisis un objet à acheter…', options=options, custom_id='malfred:choix_objet')

    async def callback(self, interaction):
        objet = self.values[0]
        nom, prix, description = OBJETS[objet]
        await interaction.response.send_message(f'🛒 **{nom}** — **{prix} ❄️**\n{description}\nTu confirmes cet achat ?', view=ConfirmerAchat(objet), ephemeral=True)


class ConfirmerAchat(discord.ui.View):
    def __init__(self, objet):
        super().__init__(timeout=120)
        self.objet = objet

    @discord.ui.button(label='Confirmer mon achat', style=discord.ButtonStyle.success, emoji='💰')
    async def confirmer(self, interaction, button):
        resultat = effectuer_achat(interaction.user.id, self.objet)
        await interaction.response.edit_message(content=resultat, view=None)

    @discord.ui.button(label='Annuler', style=discord.ButtonStyle.secondary)
    async def annuler(self, interaction, button):
        await interaction.response.edit_message(content='Achat annulé. Malfred boude. 😤', view=None)


class BoutiqueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ChoixObjet())

    @discord.ui.button(label='Mon inventaire', emoji='🎒', style=discord.ButtonStyle.primary, custom_id='malfred:inventaire')
    async def inventaire_bouton(self, interaction, button):
        await interaction.response.send_message(embed=afficher_inventaire(interaction.user), ephemeral=True)

    @discord.ui.button(label='Mes flocons', emoji='❄️', style=discord.ButtonStyle.secondary, custom_id='malfred:flocons')
    async def flocons_bouton(self, interaction, button):
        with connexion() as db:
            creer_joueur(db, interaction.user.id)
            solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (interaction.user.id,)).fetchone()[0]
        await interaction.response.send_message(f'❄️ Tu possèdes **{solde} flocons** !', ephemeral=True)

    @discord.ui.button(label='Cadeaux du jour', emoji='🎁', style=discord.ButtonStyle.success, custom_id='malfred:cadeaux')
    async def cadeaux_bouton(self, interaction, button):
        embed = discord.Embed(title='🎁 Choisis ton poison !', description='1️⃣ Paquet du lâche : 70 % de gagner (+2 à +5), sinon −1 à −3\n2️⃣ Coffre du filou : 50 % de gagner (+5 à +12), sinon −4 à −8\n3️⃣ Cadeau du démon : 30 % de gagner (+15 à +30), sinon −8 à −15\n\nPour ouvrir : `!ouvrir 1`, `!ouvrir 2` ou `!ouvrir 3`.', color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.command()
async def boutique(ctx):
    await ctx.send(embed=afficher_boutique(), view=BoutiqueView())


@bot.command()
async def inventaire(ctx):
    await ctx.send(embed=afficher_inventaire(ctx.author))


@bot.command()
async def acheter(ctx, objet: str = ''):
    objet = objet.lower().strip()
    if objet not in OBJETS:
        await ctx.send('🛒 Tape **!boutique** puis sélectionne un objet dans le menu interactif.')
        return
    await ctx.send(effectuer_achat(ctx.author.id, objet))


@bot.command()
async def rencontre(ctx):
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, ctx.author.id)
        if not possede(db, ctx.author.id, 'boule'):
            reponse = '🔮 Pas de boule à neige ! Achètes-en une avec **!boutique**, pigeon !'
        else:
            retirer_objet(db, ctx.author.id, 'boule')
            montant = random.randint(-5, 10)
            solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (ctx.author.id,)).fetchone()[0]
            protege = montant < 0 and possede(db, ctx.author.id, 'bouclier')
            if protege:
                retirer_objet(db, ctx.author.id, 'bouclier')
            nouveau = solde if protege else max(0, solde + montant)
            db.execute('UPDATE joueurs SET flocons=? WHERE user_id=?', (nouveau, ctx.author.id))
            variation = nouveau - solde
            reponse = (f'🔮 Malfred secoue sa boule à neige... **{variation:+d} flocons** !\n'
                       + ('🛡️ Ton bouclier t’a protégé !\n' if protege else '')
                       + f'❄️ Nouveau solde : **{nouveau}**. 😈')
    await ctx.send(reponse)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
        await ctx.send('🎄 Argument invalide ! Vérifie **!cadeau** ou **!boutique**.')
        return
    raise error


if __name__ == '__main__':
    initialiser_base()
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('La variable DISCORD_TOKEN manque sur Railway.')
    bot.add_view(BoutiqueView())
    bot.run(token)
