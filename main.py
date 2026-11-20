import os
import random
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

DATABASE_PATH = os.getenv('DATABASE_PATH', '/data/malfred.db')
TZ = ZoneInfo('Europe/Zurich')
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

OBJETS = {
    'bouclier': ('🛡️ Bouclier givré', 25, 'Annule la prochaine perte de flocons.'),
    'trefle': ('🍀 Trèfle douteux', 15, '+15 points de chance sur le prochain cadeau ouvert.'),
    'boule': ('🔮 Boule à neige', 30, 'Donne droit à une rencontre supplémentaire.'),
    'paquet': ('🎁 Paquet suspect', 20, 'Rapporte immédiatement 0 à 30 flocons.'),
    'canard': ('🦆 Canard de contrebande', 15, 'Objet de collection totalement inutile.'),
}
CADEAUX = {
    1: (70, (2, 5), (1, 3), '🍬 Friandise suspecte'),
    2: (50, (5, 12), (4, 8), '🧰 Coffre du filou'),
    3: (30, (15, 30), (8, 15), '💀 Pacte maudit'),
}
PHRASES = {
    'accueil': [
        'Bienvenue au marché noir de Noël. Les réclamations vont directement à la cheminée.',
        'Approchez ! Tout est presque légal. Enfin, selon mes propres règles.',
        'Un lutin, des flocons et des décisions regrettables. Quel beau programme !',
        'Mes cadeaux sont garantis sans garantie. Joyeux Noël !',
    ],
    'cadeaux': [
        'Choisis soigneusement. Ou pas, j’adore les décisions impulsives.',
        'Trois cadeaux. Zéro assurance. Une merveilleuse tradition.',
        'La magie de Noël ? Non. Les probabilités, mon petit.',
        'J’ai personnellement saboté les emballages. Avec amour.',
        'Tu peux me faire confiance. Ce qui serait ta première erreur.',
    ],
    'gain': [
        'QUOI ?! Tu as gagné ? Je demande un audit de mes arnaques.',
        'Profite de tes flocons. Mon comptable pleure déjà.',
        'C’est Noël avant l’heure. Malheureusement pour ma trésorerie.',
        'Le hasard a décidé de me trahir. Encore.',
        'Tu repars plus riche. Ne prends pas cette habitude.',
        'Je vais devoir réduire le budget biscuits du personnel.',
        'Tu as gagné loyalement. Quelle insulte à mon commerce.',
        'Je soupçonne une intervention du Père Noël. Scandaleux.',
    ],
    'perte': [
        'Une magnifique transaction. Pour moi, évidemment.',
        'Ton sens des affaires me fascine. Dangereusement mauvais.',
        'Merci pour ce don à l’association des lutins malhonnêtes.',
        'La maison gagne ! La maison, c’est moi. Surprise !',
        'Une leçon coûteuse. J’accepte aussi les pourboires.',
        'Ton portefeuille vient de rencontrer mon esprit de Noël.',
        'J’appelle ça une taxe sur l’optimisme.',
        'La prochaine fois, essaie de négocier avec le hasard.',
    ],
    'protege': [
        'Ce bouclier a ruiné mon plan. Je déteste l’équipement de qualité.',
        'Tu n’as rien perdu ! Je vais porter plainte contre ce bouclier.',
        'Protection activée. Ma déception est immense.',
    ],
    'deja': [
        'Une seule tentative par jour. Même mes arnaques ont des horaires.',
        'Tu as déjà joué ! Reviens quand le calendrier aura bougé.',
        'La gourmandise est un vilain défaut. Et pourtant je m’y connais.',
        'Non non non. Je ne vais pas emballer deux cadeaux pour toi.',
        'Le guichet des cadeaux est fermé. Va admirer tes flocons.',
    ],
    'achat': [
        'Merci pour ta contribution à mon empire commercial.',
        'Un achat de plus, une conscience de moins.',
        'Aucun remboursement. Même si tu pleures très fort.',
        'Les lutins honnêtes me détestent pour cette astuce.',
    ],
    'achat_deja': [
        'La boutique a fermé ton dossier pour aujourd’hui.',
        'Un achat par jour. Je sais, c’est cruel. C’est voulu.',
        'Reviens demain avec une meilleure excuse.',
    ],
    'pauvre': [
        'Ton portefeuille fait un bruit de grelot vide.',
        'Même mes tarifs scandaleux ont des limites : il faut pouvoir payer.',
        'Essaie de gagner quelques flocons avant de revenir fanfaronner.',
    ],
}


def phrase(categorie):
    return random.choice(PHRASES[categorie])


def maintenant():
    return datetime.now(TZ)


def jour_suisse():
    return maintenant().date().isoformat()


def prochain_cadeau():
    local = maintenant()
    demain = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
    secondes = max(0, int((demain - local).total_seconds()))
    heures, reste = divmod(secondes, 3600)
    minutes, _ = divmod(reste, 60)
    return f'{heures} h {minutes:02d} min', int(demain.timestamp())


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


def solde_joueur(user_id):
    with connexion() as db:
        creer_joueur(db, user_id)
        return db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]


def a_joue_aujourdhui(user_id):
    with connexion() as db:
        creer_joueur(db, user_id)
        dernier = db.execute('SELECT dernier_cadeau FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]
        return dernier == jour_suisse()


def message_deja():
    attente, timestamp = prochain_cadeau()
    return f'🎄 {phrase("deja")}\n⏳ Prochain cadeau dans **{attente}**, <t:{timestamp}:R>.'


def ouvrir_cadeau(user_id, choix):
    chance, gains, pertes, nom = CADEAUX[choix]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        solde, dernier = db.execute(
            'SELECT flocons, dernier_cadeau FROM joueurs WHERE user_id=?', (user_id,)
        ).fetchone()
        if dernier == jour_suisse():
            return False, message_deja()
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
                   (nouveau, jour_suisse(), user_id))
    if victoire:
        commentaire = phrase('gain')
        resultat = f'🎉 **+{nouveau - solde} flocons !**'
    elif protege:
        commentaire = phrase('protege')
        resultat = '🛡️ **0 flocon perdu !** Le bouclier s’est brisé.'
    else:
        commentaire = phrase('perte')
        resultat = f'💀 **{nouveau - solde} flocons !**'
    texte = (f'Tu ouvres **{nom}** !\n\n{resultat}\n\n*{commentaire}*\n\n'
             f'❄️ Nouveau solde : **{nouveau} flocons**.')
    if bonus:
        texte += '\n🍀 Ton trèfle a ajouté 15 points de chance !'
    return True, texte


def afficher_cadeaux(user_id=None):
    deja = user_id is not None and a_joue_aujourdhui(user_id)
    if deja:
        description = message_deja() + '\n\n**Les cadeaux seront disponibles demain.**'
    else:
        description = f'{phrase("cadeaux")} 😈\n**Un seul cadeau par jour.**'
    embed = discord.Embed(title='🎁 LES CADEAUX PIÉGÉS', description=description, color=discord.Color.red())
    embed.add_field(name='🍬 Friandise suspecte · 70 %', value='Gain : **2 à 5** ❄️\nPerte : **1 à 3** ❄️', inline=False)
    embed.add_field(name='🧰 Coffre du filou · 50 %', value='Gain : **5 à 12** ❄️\nPerte : **4 à 8** ❄️', inline=False)
    embed.add_field(name='💀 Pacte maudit · 30 %', value='Gain : **15 à 30** ❄️\nPerte : **8 à 15** ❄️', inline=False)
    embed.set_footer(text='Choisis un cadeau avec les boutons ci-dessous' if not deja else 'Reviens demain pour retenter ta chance')
    return embed


def afficher_boutique():
    embed = discord.Embed(title='🛒 LA BOUTIQUE DE MALFRED',
        description='Le marché noir du pôle Nord. Les prix sont inventés, les regrets authentiques. 😈',
        color=discord.Color.green())
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
        if ancien and ancien[0] == jour_suisse():
            return f'🛒 {phrase("achat_deja")}'
        if possede(db, user_id, objet):
            return '🎒 Tu possèdes déjà cet objet ! Un exemplaire maximum, avare !'
        if solde < prix:
            return f'💸 **{prix} flocons** nécessaires, tu n’en as que **{solde}** ! {phrase("pauvre")}'
        db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?', (prix, user_id))
        db.execute('INSERT INTO boutique_joueurs (user_id, dernier_achat) VALUES (?, ?) '
                   'ON CONFLICT(user_id) DO UPDATE SET dernier_achat=excluded.dernier_achat', (user_id, jour_suisse()))
        if objet != 'paquet':
            db.execute('INSERT INTO inventaire (user_id, objet, quantite) VALUES (?, ?, 1)', (user_id, objet))
        gain = random.randint(0, 30) if objet == 'paquet' else 0
        if gain:
            db.execute('UPDATE joueurs SET flocons=flocons+? WHERE user_id=?', (gain, user_id))
        reponse = f'🛒 Tu achètes **{nom}** pour **{prix} flocons** !\n'
        if objet == 'paquet':
            reponse += f'🎁 Le paquet contenait **{gain} flocons** !\n'
        return reponse + f'❄️ Solde : **{solde - prix + gain} flocons**.\n*{phrase("achat")}*'


def afficher_accueil():
    return discord.Embed(title='🎄 MALFRED — LE LUTIN DU CHAOS',
        description=f'{phrase("accueil")} 😈\n\nChoisis une activité avec les boutons ci-dessous.\n\n'
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
    return discord.Embed(title='🏆 LES PLUS RICHES DU MARCHÉ NOIR',
                         description=description or 'Aucune fortune suspecte à déclarer.',
                         color=discord.Color.gold())


class CadeauxView(discord.ui.View):
    def __init__(self, deja=False):
        super().__init__(timeout=None if not deja else 180)
        if deja:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

    async def ouvrir(self, interaction, numero):
        succes, resultat = ouvrir_cadeau(interaction.user.id, numero)
        embed = discord.Embed(title='🎁 Verdict de Malfred', description=resultat,
                              color=discord.Color.green() if succes else discord.Color.gold())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='Friandise suspecte', emoji='🍬', style=discord.ButtonStyle.success, custom_id='malfred:ouvrir:1')
    async def paquet(self, interaction, button):
        await self.ouvrir(interaction, 1)

    @discord.ui.button(label='Coffre du filou', emoji='🧰', style=discord.ButtonStyle.primary, custom_id='malfred:ouvrir:2')
    async def coffre(self, interaction, button):
        await self.ouvrir(interaction, 2)

    @discord.ui.button(label='Pacte maudit', emoji='💀', style=discord.ButtonStyle.danger, custom_id='malfred:ouvrir:3')
    async def demon(self, interaction, button):
        await self.ouvrir(interaction, 3)


async def envoyer_cadeaux(interaction):
    deja = a_joue_aujourdhui(interaction.user.id)
    await interaction.response.send_message(embed=afficher_cadeaux(interaction.user.id),
                                            view=CadeauxView(deja=deja), ephemeral=True)


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
        await interaction.response.send_message(embed=afficher_inventaire(interaction.user), ephemeral=True)

    @discord.ui.button(label='Mes flocons', emoji='❄️', style=discord.ButtonStyle.secondary, custom_id='malfred:flocons')
    async def flocons_bouton(self, interaction, button):
        await interaction.response.send_message(f'❄️ Tu possèdes **{solde_joueur(interaction.user.id)} flocons** !', ephemeral=True)

    @discord.ui.button(label='Cadeaux du jour', emoji='🎁', style=discord.ButtonStyle.success, custom_id='malfred:cadeaux')
    async def cadeaux_bouton(self, interaction, button):
        await envoyer_cadeaux(interaction)


class InventaireView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Utiliser la boule à neige', emoji='🔮', style=discord.ButtonStyle.primary, custom_id='malfred:inventaire:boule')
    async def boule(self, interaction, button):
        await interaction.response.send_message(utiliser_boule(interaction.user.id), ephemeral=True)


class AccueilView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Cadeaux', emoji='🎁', style=discord.ButtonStyle.success, custom_id='malfred:menu:cadeaux')
    async def cadeaux(self, interaction, button):
        await envoyer_cadeaux(interaction)

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


@bot.event
async def on_ready():
    print(f'🎄 Malfred est réveillé : {bot.user}')


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
        _, resultat = ouvrir_cadeau(ctx.author.id, choix)
        await ctx.send(resultat)


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


@bot.command(name='resetcadeau')
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def resetcadeau(ctx, membre: discord.Member):
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, membre.id)
        db.execute('UPDATE joueurs SET dernier_cadeau=NULL WHERE user_id=?', (membre.id,))
    await ctx.send(f'🔧 Le cadeau quotidien de {membre.mention} est réinitialisé ! '
                   'Ses flocons et son inventaire n’ont pas changé. 😈')


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('⛔ Seuls les administrateurs peuvent utiliser cette commande.')
        return
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send('⛔ Cette commande fonctionne uniquement sur le serveur.')
        return
    if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
        await ctx.send('🎄 Argument invalide ! Exemple : **!resetcadeau @joueur**.')
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
