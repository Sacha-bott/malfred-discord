import os
import random
import sqlite3
from datetime import datetime, timezone

import discord
from discord.ext import commands

DATABASE_PATH = os.getenv('DATABASE_PATH', '/data/malfred.db')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

OBJETS = {
    'bouclier': ('🛡️ Bouclier givré', 25, 'Annule la prochaine perte de flocons.'),
    'trefle': ('🍀 Trèfle douteux', 15, '+15 points de chance sur le prochain cadeau ouvert.'),
    'boule': ('🔮 Boule à neige', 30, 'Donne droit à une rencontre supplémentaire.'),
    'paquet': ('🎁 Paquet suspect', 20, 'Rapporte immédiatement 0 à 30 flocons.'),
    'canard': ('🦆 Canard de contrebande', 15, 'Objet de collection totalement inutile.'),
}

CADEAUX = {
    1: (70, (2, 5), (1, 3), '🍬 Friandise suspecte', 'Même les bonbons ont des secrets.', discord.Color.green()),
    2: (50, (5, 12), (4, 8), '🗝️ Coffre du filou', 'La clé est gratuite. Les regrets aussi.', discord.Color.gold()),
    3: (30, (15, 30), (8, 15), '🩸 Pacte maudit', 'Signe ici. Non, ne lis pas.', discord.Color.red()),
}

PHRASES_DEJA = [
    '🎄 Un seul cadeau par jour, petit escroc. Tu pensais vraiment me duper ?',
    '🧦 Reviens demain ! Mon stock de catastrophes est limité.',
    '😈 J’admire ton audace, mais le calendrier sait compter.',
    '🪤 Deux cadeaux en un jour ? C’est moi l’arnaqueur ici !',
    '🎁 Pas si vite ! Le prochain piège t’attend demain.',
]


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


def solde_joueur(user_id):
    with connexion() as db:
        creer_joueur(db, user_id)
        return db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]


def ouvrir_cadeau(user_id, choix):
    chance, gains, pertes, nom, _, _ = CADEAUX[choix]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        solde, dernier = db.execute('SELECT flocons, dernier_cadeau FROM joueurs WHERE user_id=?', (user_id,)).fetchone()
        if dernier == jour_utc():
            return random.choice(PHRASES_DEJA)
        bonus = 15 if possede(db, user_id, 'trefle') else 0
        if bonus:
            retirer_objet(db, user_id, 'trefle')
        victoire = random.randint(1, 100) <= chance + bonus
        montant = random.randint(*(gains if victoire else pertes))
        protege = not victoire and possede(db, user_id, 'bouclier')
        if protege:
            retirer_objet(db, user_id, 'bouclier')
        nouveau = solde + montant if victoire else (solde if protege else max(0, solde - montant))
        db.execute('UPDATE joueurs SET flocons=?, dernier_cadeau=? WHERE user_id=?', (nouveau, jour_utc(), user_id))
    if victoire:
        phrase = random.choice(['Mon comptable va me tuer !', 'C’est scandaleux, tu as gagné !', 'Un miracle. Je demande un remboursement.', 'Tu as soudoyé les rennes ou quoi ?'])
        resultat = f'🎉 **+{nouveau - solde} flocons !**'
    elif protege:
        phrase = '🛡️ Ton bouclier s’est brisé en absorbant la perte !'
        resultat = '❄️ **0 flocon perdu !**'
    else:
        phrase = random.choice(['HAHA ! Les affaires reprennent.', 'C’est Noël pour MOI ! 😈', 'Fallait lire les petites lignes.', 'Je viens de financer mon prochain traîneau.', 'Tu viens de faire un don à mon ego.'])
        resultat = f'💀 **{nouveau - solde} flocons !**'
    return (f'**{nom}**\n{resultat}\n{phrase}\n❄️ Nouveau solde : **{nouveau} flocons**.'
            + (' 🍀 Trèfle utilisé !' if bonus else ''))


def embed_cadeau(numero):
    chance, gains, pertes, nom, phrase, couleur = CADEAUX[numero]
    embed = discord.Embed(title=nom, description=f'*« {phrase} »*\n\n🎲 **{chance} % de chance de gagner**', color=couleur)
    embed.add_field(name='✨ Si tu gagnes', value=f'**+{gains[0]} à +{gains[1]} ❄️**', inline=True)
    embed.add_field(name='💀 Si tu perds', value=f'**−{pertes[0]} à −{pertes[1]} ❄️**', inline=True)
    embed.set_footer(text='Un seul cadeau par jour, tous types confondus')
    return embed


class BoutonCadeau(discord.ui.View):
    def __init__(self, numero):
        super().__init__(timeout=None)
        self.numero = numero
        labels = {1: ('Tenter ma chance', '🍬', discord.ButtonStyle.success),
                  2: ('Ouvrir le coffre', '🗝️', discord.ButtonStyle.primary),
                  3: ('Signer le pacte', '🩸', discord.ButtonStyle.danger)}
        label, emoji, style = labels[numero]
        bouton = discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f'malfred:cadeau:separe:{numero}')
        bouton.callback = self.cliquer
        self.add_item(bouton)

    async def cliquer(self, interaction):
        resultat = ouvrir_cadeau(interaction.user.id, self.numero)
        embed = discord.Embed(title='🎁 Verdict de Malfred', description=resultat, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def envoyer_cadeaux(destination, ephemeral=False):
    for numero in CADEAUX:
        await destination.send(embed=embed_cadeau(numero), view=BoutonCadeau(numero), ephemeral=ephemeral)


def afficher_boutique():
    embed = discord.Embed(title='🛒 LE MARCHÉ NOIR DE MALFRED',
                          description=random.choice(['Mes prix sont aussi honnêtes que moi. 😈', 'Soldes ? Ce mot est interdit ici.', 'Entre, mais surveille ton portefeuille.']),
                          color=discord.Color.purple())
    for _, (nom, prix, description) in OBJETS.items():
        embed.add_field(name=f'{nom} — {prix} ❄️', value=description, inline=False)
    embed.set_footer(text='1 achat par jour • 1 exemplaire par objet • Aucun échange')
    return embed


def afficher_inventaire(user):
    with connexion() as db:
        creer_joueur(db, user.id)
        objets = db.execute('SELECT objet FROM inventaire WHERE user_id=? ORDER BY objet', (user.id,)).fetchall()
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user.id,)).fetchone()[0]
    contenu = '\n'.join(OBJETS[code][0] for (code,) in objets if code in OBJETS)
    return discord.Embed(title=f'🎒 Inventaire de {user.display_name}',
                         description=(contenu or 'Vide ! Même les mites ont déménagé. 😈') + f'\n\n❄️ **{solde} flocons**',
                         color=discord.Color.gold())


def effectuer_achat(user_id, objet):
    nom, prix, _ = OBJETS[objet]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]
        ancien = db.execute('SELECT dernier_achat FROM boutique_joueurs WHERE user_id=?', (user_id,)).fetchone()
        if ancien and ancien[0] == jour_utc():
            return random.choice(['🛒 Un achat par jour. Mes règles, mon empire.', '😈 Tu as déjà dépensé aujourd’hui. Reviens demain !'])
        if possede(db, user_id, objet):
            return '🎒 Tu possèdes déjà cet objet ! Un exemplaire maximum.'
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
        options = [discord.SelectOption(label=nom.split(' ', 1)[1], value=code,
                   description=f'{prix} flocons — {description[:65]}', emoji=nom.split(' ', 1)[0])
                   for code, (nom, prix, description) in OBJETS.items()]
        super().__init__(placeholder='Choisis un objet à acheter…', options=options, custom_id='malfred:choix_objet')

    async def callback(self, interaction):
        objet = self.values[0]
        nom, prix, description = OBJETS[objet]
        await interaction.response.send_message(f'🛒 **{nom}** — **{prix} ❄️**\n{description}\nTu confirmes cet achat ?',
                                                view=ConfirmerAchat(objet), ephemeral=True)


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
        await interaction.response.send_message(embed=afficher_inventaire(interaction.user), view=InventaireView(), ephemeral=True)

    @discord.ui.button(label='Mes flocons', emoji='❄️', style=discord.ButtonStyle.secondary, custom_id='malfred:flocons')
    async def flocons_bouton(self, interaction, button):
        await interaction.response.send_message(f'❄️ Tu possèdes **{solde_joueur(interaction.user.id)} flocons** !', ephemeral=True)

    @discord.ui.button(label='Cadeaux du jour', emoji='🎁', style=discord.ButtonStyle.success, custom_id='malfred:cadeaux')
    async def cadeaux_bouton(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        await envoyer_cadeaux(interaction.followup, ephemeral=True)


def afficher_accueil():
    return discord.Embed(title='🎄 MALFRED — LE LUTIN DU CHAOS',
                         description=random.choice(['Bienvenue dans mon marché noir de Noël. 😈', 'Je vends du rêve, pas des garanties.', 'Entrez donc, mes futurs clients ruinés !'])
                         + '\n\n🎁 **Cadeaux** · Trois risques, un choix quotidien\n🛒 **Boutique** · Dépense tes flocons\n🎒 **Inventaire** · Regarde tes objets\n🏆 **Classement** · Espionne les riches',
                         color=discord.Color.green())


def afficher_classement(guild):
    with connexion() as db:
        scores = db.execute('SELECT user_id, flocons FROM joueurs ORDER BY flocons DESC, user_id ASC').fetchall()
    if guild:
        scores = [(uid, score) for uid, score in scores if guild.get_member(uid) is not None]
    top = scores[:10]
    description = '\n'.join(f'**{i}.** <@{uid}> — **{score}** ❄️' for i, (uid, score) in enumerate(top, 1))
    return discord.Embed(title='🏆 LES PLUS RICHES DU PÔLE NORD',
                         description=description or 'Personne à plumer pour le moment.', color=discord.Color.gold())


class AccueilView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Cadeaux', emoji='🎁', style=discord.ButtonStyle.success, custom_id='malfred:menu:cadeaux')
    async def cadeaux(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        await envoyer_cadeaux(interaction.followup, ephemeral=True)

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
            return '🔮 Tu ne possèdes pas de boule à neige !'
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
async def malfred(ctx):
    await ctx.send(embed=afficher_accueil(), view=AccueilView())


@bot.command(aliases=['flocon'])
async def flocons(ctx):
    await ctx.send(f'❄️ {ctx.author.mention}, tu possèdes **{solde_joueur(ctx.author.id)} flocons** !')


@bot.command()
async def cadeau(ctx):
    await envoyer_cadeaux(ctx)


@bot.command()
async def ouvrir(ctx, choix: int = 0):
    if choix not in CADEAUX:
        await envoyer_cadeaux(ctx)
    else:
        await ctx.send(ouvrir_cadeau(ctx.author.id, choix))


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
async def on_ready():
    print(f'🎄 Malfred est réveillé : {bot.user}')


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
    bot.add_view(InventaireView())
    for numero in CADEAUX:
        bot.add_view(BoutonCadeau(numero))
    bot.run(token)
