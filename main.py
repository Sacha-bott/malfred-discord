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


CADEAUX = {
    1: (70, (2, 5), (1, 3), 'Paquet du lâche'),
    2: (50, (5, 12), (4, 8), 'Coffre du filou'),
    3: (30, (15, 30), (8, 15), 'Cadeau du démon'),
}


def solde_joueur(user_id):
    with connexion() as db:
        creer_joueur(db, user_id)
        return db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]


def ouvrir_cadeau(user_id, choix):
    chance, gains, pertes, nom = CADEAUX[choix]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        solde, dernier = db.execute(
            'SELECT flocons, dernier_cadeau FROM joueurs WHERE user_id=?', (user_id,)
        ).fetchone()
        if dernier == jour_utc():
            return '🎄 Doucement, petit pigeon ! Tu as déjà ouvert ton cadeau aujourd’hui. Reviens demain ! 😈'
        bonus = 15 if possede(db, user_id, 'trefle') else 0
        if bonus:
            retirer_objet(db, user_id, 'trefle')
        victoire = random.randint(1, 100) <= chance + bonus
        montant = random.randint(*(gains if victoire else pertes))
        protege = not victoire and possede(db, user_id, 'bouclier')
        if protege:
            retirer_objet(db, user_id, 'bouclier')
        nouveau = solde + montant if victoire else (solde if protege else max(0, solde - montant))
        db.execute('UPDATE joueurs SET flocons=?, dernier_cadeau=? WHERE user_id=?',
                   (nouveau, jour_utc(), user_id))
    if victoire:
        phrase = random.choice(['Mon comptable va me tuer !', 'La chance tourne, pigeon.', 'J’ai emballé le mauvais cadeau ! 😤'])
        resultat = f'🎉 **+{nouveau - solde} flocons !**'
    elif protege:
        phrase = '🛡️ Ton bouclier s’est brisé en absorbant la perte !'
        resultat = '❄️ **0 flocon perdu !**'
    else:
        phrase = random.choice(['HAHA ! Merci, pigeon !', 'C’est Noël pour MOI ! 😈', 'Fallait lire les petites lignes.'])
        resultat = f'💀 **{nouveau - solde} flocons !**'
    return (f'🎁 Tu ouvres **{nom}** !\n{resultat}\n{phrase}\n'
            f'❄️ Nouveau solde : **{nouveau} flocons**.'
            + (' 🍀 Trèfle utilisé !' if bonus else ''))


def afficher_cadeaux():
    embed = discord.Embed(title='🎁 LES CADEAUX PIÉGÉS',
        description='Choisis ton poison, petit pigeon ! 😈\n**Un seul cadeau par jour.**',
        color=discord.Color.red())
    embed.add_field(name='🟢 Paquet du lâche · 70 %', value='Gain : **2 à 5** ❄️\nPerte : **1 à 3** ❄️', inline=False)
    embed.add_field(name='🟡 Coffre du filou · 50 %', value='Gain : **5 à 12** ❄️\nPerte : **4 à 8** ❄️', inline=False)
    embed.add_field(name='🔴 Cadeau du démon · 30 %', value='Gain : **15 à 30** ❄️\nPerte : **8 à 15** ❄️', inline=False)
    embed.set_footer(text='Appuie directement sur un bouton pour ouvrir ton cadeau')
    return embed


@bot.command()
async def malfred(ctx):
    await ctx.send(embed=afficher_accueil(), view=AccueilView())


@bot.command(aliases=['flocon'])
async def flocons(ctx):
    await ctx.send(f'❄️ {ctx.author.mention}, tu possèdes **{solde_joueur(ctx.author.id)} flocons** !')


@bot.command()
async def cadeau(ctx):
    await ctx.send(embed=afficher_cadeaux(), view=CadeauxView())


@bot.command()
async def ouvrir(ctx, choix: int = 0):
    if choix not in CADEAUX:
        await ctx.send(embed=afficher_cadeaux(), view=CadeauxView())
    else:
        await ctx.send(ouvrir_cadeau(ctx.author.id, choix))


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
        await interaction.response.send_message(embed=afficher_cadeaux(), view=CadeauxView(), ephemeral=True)


def afficher_accueil():
    return discord.Embed(title='🎄 MALFRED — LE LUTIN DU CHAOS',
        description='Bienvenue au marché noir de Noël, bande de pigeons ! 😈\n'
                    'Choisis une activité avec les boutons ci-dessous.\n\n'
                    '🎁 **Cadeaux** · Tente ta chance chaque jour\n'
                    '🛒 **Boutique** · Dépense tes flocons\n'
                    '🎒 **Inventaire** · Regarde tes objets\n'
                    '🏆 **Classement** · Espionne les riches',
        color=discord.Color.green())


def afficher_classement(guild):
    with connexion() as db:
        scores = db.execute('SELECT user_id, flocons FROM joueurs ORDER BY flocons DESC, user_id ASC').fetchall()
    if guild:
        scores = [(uid, score) for uid, score in scores if guild.get_member(uid) is not None]
    top = scores[:10]
    description = '\n'.join(f'**{i}.** <@{uid}> — **{score}** ❄️' for i, (uid, score) in enumerate(top, 1))
    return discord.Embed(title='🏆 LES PIGEONS LES PLUS RICHES',
                         description=description or 'Aucun pigeon à plumer pour le moment.',
                         color=discord.Color.gold())


class CadeauxView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def ouvrir(self, interaction, numero):
        resultat = ouvrir_cadeau(interaction.user.id, numero)
        await interaction.response.send_message(embed=discord.Embed(
            title='🎁 Verdict de Malfred', description=resultat, color=discord.Color.gold()), ephemeral=True)

    @discord.ui.button(label='Paquet du lâche', emoji='🟢', style=discord.ButtonStyle.success, custom_id='malfred:ouvrir:1')
    async def paquet(self, interaction, button):
        await self.ouvrir(interaction, 1)

    @discord.ui.button(label='Coffre du filou', emoji='🟡', style=discord.ButtonStyle.primary, custom_id='malfred:ouvrir:2')
    async def coffre(self, interaction, button):
        await self.ouvrir(interaction, 2)

    @discord.ui.button(label='Cadeau du démon', emoji='🔴', style=discord.ButtonStyle.danger, custom_id='malfred:ouvrir:3')
    async def demon(self, interaction, button):
        await self.ouvrir(interaction, 3)


class AccueilView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Cadeaux', emoji='🎁', style=discord.ButtonStyle.success, custom_id='malfred:menu:cadeaux')
    async def cadeaux(self, interaction, button):
        await interaction.response.send_message(embed=afficher_cadeaux(), view=CadeauxView(), ephemeral=True)

    @discord.ui.button(label='Boutique', emoji='🛒', style=discord.ButtonStyle.primary, custom_id='malfred:menu:boutique')
    async def boutique(self, interaction, button):
        await interaction.response.send_message(embed=afficher_boutique(), view=BoutiqueView(), ephemeral=True)

    @discord.ui.button(label='Inventaire', emoji='🎒', style=discord.ButtonStyle.secondary, custom_id='malfred:menu:inventaire')
    async def inventaire(self, interaction, button):
        await interaction.response.send_message(embed=afficher_inventaire(interaction.user), view=InventaireView(), ephemeral=True)

    @discord.ui.button(label='Classement', emoji='🏆', style=discord.ButtonStyle.secondary, custom_id='malfred:menu:classement')
    async def classement(self, interaction, button):
        await interaction.response.send_message(embed=afficher_classement(interaction.guild), ephemeral=True)

    @discord.ui.button(label='Mes flocons', emoji='❄️', style=discord.ButtonStyle.secondary, custom_id='malfred:menu:flocons', row=1)
    async def flocons(self, interaction, button):
        await interaction.response.send_message(f'❄️ Tu possèdes **{solde_joueur(interaction.user.id)} flocons** !', ephemeral=True)


def utiliser_boule(user_id):
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        if not possede(db, user_id, 'boule'):
            return '🔮 Tu ne possèdes pas de boule à neige, pigeon !'
        retirer_objet(db, user_id, 'boule')
        montant = random.randint(-5, 10)
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]
        protege = montant < 0 and possede(db, user_id, 'bouclier')
        if protege:
            retirer_objet(db, user_id, 'bouclier')
        nouveau = solde if protege else max(0, solde + montant)
        db.execute('UPDATE joueurs SET flocons=? WHERE user_id=?', (nouveau, user_id))
    return (f'🔮 Malfred secoue sa boule à neige... **{nouveau - solde:+d} flocons** !\n'
            + ('🛡️ Ton bouclier t’a protégé !\n' if protege else '')
            + f'❄️ Nouveau solde : **{nouveau}**. 😈')


class InventaireView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Utiliser la boule à neige', emoji='🔮', style=discord.ButtonStyle.primary, custom_id='malfred:inventaire:boule')
    async def boule(self, interaction, button):
        await interaction.response.send_message(utiliser_boule(interaction.user.id), ephemeral=True)


@bot.command()
async def boutique(ctx):
    await ctx.send(embed=afficher_boutique(), view=BoutiqueView())


@bot.command()
async def inventaire(ctx):
    await ctx.send(embed=afficher_inventaire(ctx.author), view=InventaireView())


@bot.command()
async def acheter(ctx, objet: str = ''):
    objet = objet.lower().strip()
    if objet not in OBJETS:
        await ctx.send('🛒 Tape **!boutique** puis sélectionne un objet dans le menu interactif.')
        return
    await ctx.send(effectuer_achat(ctx.author.id, objet))


@bot.command()
async def rencontre(ctx):
    await ctx.send(utiliser_boule(ctx.author.id))


@bot.command()
async def classement(ctx):
    await ctx.send(embed=afficher_classement(ctx.guild))


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
    bot.add_view(AccueilView())
    bot.add_view(CadeauxView())
    bot.add_view(InventaireView())
    bot.run(token)
