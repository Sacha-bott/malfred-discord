import os
import random
import sqlite3
import logging
import asyncio
from datetime import timedelta
from discord.ext import tasks
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

logging.basicConfig(level=logging.INFO)
DATABASE_PATH = os.getenv('DATABASE_PATH', '/data/malfred.db')
GUILD_ID = int(os.getenv('GUILD_ID', '0') or '0')
STAFF_IDS = {int(x.strip()) for x in os.getenv('MALFRED_ADMIN_IDS', '').split(',') if x.strip().isdigit()}
TZ = ZoneInfo('Europe/Zurich')
MARKET_CHANNEL_ID = int(os.getenv('MALFRED_CHANNEL_ID', '0') or '0')

# Emotes personnalisées officielles du serveur La Salle de Bain.
MALFRED_EMOTES = {
    'amoureux': '<:malfred_amoureux:1573298335266115614>',
    'flocon': '<:malfred_flocon:157329811219109948>',
    'fume': '<:malfred_fume:1573298043090899164>',
    'machiavelique': '<:malfred_machiavelique:1573297932361408594>',
    'moquerie': '<:malfred_moquerie:1573298266936709150>',
    'mort': '<:malfred_mort:1573298187677208596>',
    'riche': '<:malfred_riche:1573297742925799504>',
    'triste': '<:malfred_triste:1573297857728090203>',
}

# Les URL CDN des emotes permettent aussi d'afficher un portrait de Malfred
# dans les embeds, sans héberger de fichier image supplémentaire.
MALFRED_IDS = {k: int(v.rsplit(':', 1)[1][:-1]) for k, v in MALFRED_EMOTES.items()}
def portrait_malfred(humeur):
    return f"https://cdn.discordapp.com/emojis/{MALFRED_IDS[humeur]}.png?size=256&quality=lossless"
def illustrer(embed, humeur):
    # Les grandes illustrations 16:9 nécessitent une URL publique de l'image originale.
    # Exemple Railway : MALFRED_IMAGE_ACCUEIL=https://.../accueil.png
    image_url = os.getenv('MALFRED_IMAGE_' + humeur.upper(), '').strip()
    if image_url.startswith(('https://', 'http://')):
        embed.set_image(url=image_url)
    return embed

intents = discord.Intents.default()
# Pas de message_content, ni de members intent : commandes / et boutons uniquement.
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

OBJETS = {
    'bouclier': ('🛡️ Bouclier givré', 25, 'Annule ta prochaine perte de flocons.'),
    'trefle': ('🍀 Trèfle douteux', 15, '+15 points de chance au prochain cadeau.'),
    'boule': ('🔮 Boule à neige', 30, 'Débloque une rencontre supplémentaire.'),
    'paquet': ('🎁 Paquet suspect', 20, 'Rapporte immédiatement 0 à 30 flocons.'),
    'canard': ('🦆 Canard de contrebande', 15, 'Une pièce de collection absolument inutile.'),
}
CADEAUX = {
    1: (70, (2, 5), (1, 3), '🍬 Friandise suspecte'),
    2: (50, (5, 12), (4, 8), '🧰 Coffre du filou'),
    3: (30, (15, 30), (8, 15), '💀 Pacte maudit'),
}
REPLIQUES = {
    'accueil': [
        'Bienvenue dans mon atelier. Les réclamations vont directement à la cheminée.',
        'Entrez, entrez ! Les flocons ne vont pas se voler tout seuls.',
        'Joyeux Noël ! Enfin, surtout pour mon compte en banque.',
        'Le marché noir du pôle Nord ouvre ses portes. Ne touchez à rien.',
    ],
    'cadeaux': [
        'Trois présents, trois façons de regretter tes choix.',
        'La magie de Noël ? Non. Les probabilités.',
        'Un cadeau gratuit ? Tu me prends pour un philanthrope ?',
        'La chance sourit aux audacieux. Moi, je souris aux perdants.',
    ],
    'boutique': [
        'Mes prix sont fixes, ma morale beaucoup moins.',
        'Chaque objet est garanti presque authentique.',
        'Je n’accepte ni retours, ni pleurnicheries.',
        'Tu sens cette odeur ? C’est celle des mauvaises affaires.',
    ],
    'deja': [
        'Un cadeau par jour ! Tu pensais vraiment m’avoir deux fois ?',
        'Le calendrier dit non. Moi aussi, mais avec davantage de mépris.',
        'Tu as déjà tenté ta chance aujourd’hui. Va embêter un renne.',
        'Les cadeaux ne repoussent pas en dix minutes, génie.',
        'Reviens demain. Mon stock de catastrophes doit se recharger.',
    ],
    'gain': [
        'Scandale ! J’avais pourtant truqué l’emballage.',
        'Bon. Profite avant que mon comptable ne découvre ça.',
        'Une victoire ? C’est manifestement une erreur administrative.',
        'Je déteste quand les probabilités font leur travail.',
        'Tu as gagné. Je vais aller bouder dans une congère.',
    ],
    'perte': [
        'Quel magnifique don à ma caisse personnelle !',
        'Le Père Noël t’envoie ses condoléances.',
        'Tu viens de financer mon prochain traîneau.',
        'Les petites lignes étaient pourtant écrites en tout petit.',
        'C’est douloureux ? Pour toi, peut-être. Pour moi, délicieux.',
    ],
    'achat': [
        'Merci pour cette transaction parfaitement douteuse.',
        'Une vente ! Mon cœur de glace frémit.',
        'Je te souhaite de ne jamais lire les conditions générales.',
        'C’est emballé. Je garde évidemment le reçu.',
    ],
}


def phrase(categorie):
    return random.choice(REPLIQUES[categorie])


def aujourd_hui():
    return datetime.now(TZ).date().isoformat()


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
        db.execute('''CREATE TABLE IF NOT EXISTS activations (user_id INTEGER PRIMARY KEY, trefle INTEGER DEFAULT 0, bouclier INTEGER DEFAULT 0, miroir INTEGER DEFAULT 0, corrompu INTEGER DEFAULT 0, dernier_resultat TEXT, sablier_utilise TEXT, blocage_cadeau TEXT, dette INTEGER DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS marches (id INTEGER PRIMARY KEY AUTOINCREMENT, debut TEXT NOT NULL, fin TEXT NOT NULL, offres TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS achats_noirs (marche_id INTEGER, user_id INTEGER, nombre INTEGER DEFAULT 0, PRIMARY KEY(marche_id,user_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS etat_marche (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS tirages (user_id INTEGER PRIMARY KEY, jour TEXT, choix INTEGER, solde_avant INTEGER, resultat INTEGER, montant INTEGER, rejoue INTEGER DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS dettes (user_id INTEGER, echeance TEXT, montant INTEGER, PRIMARY KEY(user_id,echeance))''')



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


def ouvrir_cadeau(user_id, choix):
    chance, gains, pertes, nom = CADEAUX[choix]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        solde, dernier = db.execute('SELECT flocons, dernier_cadeau FROM joueurs WHERE user_id=?', (user_id,)).fetchone()
        if dernier == aujourd_hui():
            return '🎄 ' + phrase('deja'), discord.Color.orange(), False
        db.execute('INSERT OR IGNORE INTO activations(user_id) VALUES (?)', (user_id,))
        trefle, bouclier_actif, corrompu, blocage = db.execute('SELECT trefle,bouclier,corrompu,blocage_cadeau FROM activations WHERE user_id=?', (user_id,)).fetchone()
        if blocage == aujourd_hui():
            return '🎲 Ton dé du désespoir a sacrifié le cadeau du jour.', discord.Color.orange(), False
        bonus = 15 if trefle else 0
        if bonus:
            retirer_objet(db, user_id, 'trefle')
            db.execute('UPDATE activations SET trefle=0 WHERE user_id=?', (user_id,))
        prevision=db.execute('SELECT valeur FROM etat_marche WHERE cle=?',(f'miroir:{user_id}',)).fetchone()
        if prevision and prevision[0].startswith(str(choix)+':'):
            victoire=prevision[0].endswith(':gain')
            db.execute('DELETE FROM etat_marche WHERE cle=?',(f'miroir:{user_id}',))
        else:
            victoire = random.randint(1, 100) <= chance + bonus
        montant = random.randint(*(gains if victoire else pertes))
        protege = not victoire and bool(bouclier_actif)
        if protege:
            retirer_objet(db, user_id, 'bouclier')
            db.execute('UPDATE activations SET bouclier=0 WHERE user_id=?', (user_id,))
        if not victoire and corrompu:
            montant = max(0, montant - 10)
            db.execute('UPDATE activations SET corrompu=0 WHERE user_id=?', (user_id,))
            retirer_objet(db, user_id, 'noir_trefle')
        nouveau = solde + montant if victoire else (solde if protege else max(0, solde - montant))
        db.execute('UPDATE joueurs SET flocons=?, dernier_cadeau=? WHERE user_id=?', (nouveau, aujourd_hui(), user_id))
        db.execute('UPDATE activations SET dernier_resultat=? WHERE user_id=?', (str(choix), user_id))
        db.execute('INSERT INTO tirages(user_id,jour,choix,solde_avant,resultat,montant,rejoue) VALUES (?,?,?,?,?,?,0) ON CONFLICT(user_id) DO UPDATE SET jour=excluded.jour,choix=excluded.choix,solde_avant=excluded.solde_avant,resultat=excluded.resultat,montant=excluded.montant,rejoue=0', (user_id,aujourd_hui(),choix,solde,nouveau, nouveau-solde))
    if victoire:
        bilan = f'🎉 **+{nouveau - solde} flocons !**\n{phrase("gain")}'
        couleur = discord.Color.green()
    elif protege:
        bilan = '🛡️ Ton bouclier givré s’est brisé. **Aucun flocon perdu !**'
        couleur = discord.Color.blue()
    else:
        bilan = f'💀 **-{solde - nouveau} flocons !**\n{phrase("perte")}'
        couleur = discord.Color.red()
    if bonus:
        bilan += '\n🍀 Ton trèfle a été utilisé.'
    return f'**{nom}**\n\n{bilan}\n\n❄️ Nouveau solde : **{nouveau} flocons**.', couleur, True


def effectuer_achat(user_id, objet):
    nom, prix, _ = OBJETS[objet]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]
        ancien = db.execute('SELECT dernier_achat FROM boutique_joueurs WHERE user_id=?', (user_id,)).fetchone()
        if ancien and ancien[0] == aujourd_hui():
            return '🛒 Un achat par jour. Ma boutique n’est pas un buffet à volonté.', False
        if possede(db, user_id, objet):
            return '🎒 Tu possèdes déjà cet objet. Un exemplaire maximum !', False
        if solde < prix:
            return f'💸 Il faut **{prix} flocons** et tu n’en as que **{solde}**.', False
        db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?', (prix, user_id))
        db.execute('''INSERT INTO boutique_joueurs (user_id, dernier_achat) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET dernier_achat=excluded.dernier_achat''', (user_id, aujourd_hui()))
        if objet != 'paquet':
            db.execute('INSERT INTO inventaire (user_id, objet, quantite) VALUES (?, ?, 1)', (user_id, objet))
        gain = random.randint(0, 30) if objet == 'paquet' else 0
        if gain:
            db.execute('UPDATE joueurs SET flocons=flocons+? WHERE user_id=?', (gain, user_id))
    supplement = f'\n🎁 Le paquet contenait **{gain} flocons** !' if objet == 'paquet' else ''
    return f'🛒 Achat : **{nom}** pour **{prix} flocons** !{supplement}\n{phrase("achat")}\n❄️ Solde : **{solde - prix + gain}**.', True


def utiliser_boule(user_id):
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        if not possede(db, user_id, 'boule'):
            return '🔮 Tu n’as pas de boule à neige. Même ma magie a des limites.', False
        retirer_objet(db, user_id, 'boule')
        montant = random.randint(-5, 10)
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]
        protege = False  # Le bouclier activé protège uniquement un cadeau quotidien.
        if protege:
            retirer_objet(db, user_id, 'bouclier')
        nouveau = solde if protege else max(0, solde + montant)
        db.execute('UPDATE joueurs SET flocons=? WHERE user_id=?', (nouveau, user_id))
    return (f'🔮 La boule tourbillonne… **{nouveau - solde:+d} flocons** !\n'
            + ('🛡️ Ton bouclier a absorbé la perte.\n' if protege else '')
            + f'❄️ Nouveau solde : **{nouveau}**.'), True



async def annoncer_publiquement(interaction, titre, texte, couleur):
    """Publie un événement réussi dans le salon, sans révéler les menus privés."""
    salon = interaction.channel
    if salon is None or not hasattr(salon, 'send'):
        return False
    embed = discord.Embed(title=titre, description=texte, color=couleur)
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    humeur = 'triste' if ('+' in texte and 'flocons' in texte and '-' not in texte) else 'moquerie' if ('-' in texte and 'flocons' in texte) else 'machiavelique'
    illustrer(embed, humeur)
    try:
        await salon.send(content=interaction.user.mention, embed=embed,
                         allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False))
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        logging.warning('Annonce publique impossible : %r', exc)
        return False

def embed_accueil():
    e = discord.Embed(title=f"{MALFRED_EMOTES['machiavelique']} MALFRED — LE LUTIN DU CHAOS",
        description=f'{phrase("accueil")} 😈\n\nChoisis une activité ci-dessous :', color=discord.Color.dark_green())
    e.add_field(name=f'{MALFRED_EMOTES['amoureux']} Cadeaux', value='Un pari chaque jour', inline=True)
    e.add_field(name=f'{MALFRED_EMOTES['riche']} Boutique', value='Dépense tes flocons', inline=True)
    e.add_field(name=f'{MALFRED_EMOTES['machiavelique']} Inventaire', value='Tes trouvailles douteuses', inline=True)
    e.add_field(name=f'{MALFRED_EMOTES['riche']} Classement', value='Les plus riches', inline=True)
    e.set_footer(text='Malfred décline toute responsabilité pour tes décisions.')
    return illustrer(e, 'machiavelique')


def embed_cadeaux():
    e = discord.Embed(title=f"{MALFRED_EMOTES['amoureux']} LES CADEAUX PIÉGÉS",
        description=f'{phrase("cadeaux")} 😈\n**Un cadeau par jour.**', color=discord.Color.red())
    e.add_field(name=f"{MALFRED_EMOTES['amoureux']} Friandise suspecte · 70 %", value='🟢 Gain : **2 à 5** ❄️\n🔻 Perte : **1 à 3** ❄️', inline=False)
    e.add_field(name=f"{MALFRED_EMOTES['riche']} Coffre du filou · 50 %", value='🟡 Gain : **5 à 12** ❄️\n🔻 Perte : **4 à 8** ❄️', inline=False)
    e.add_field(name=f"{MALFRED_EMOTES['mort']} Pacte maudit · 30 %", value='🔴 Gain : **15 à 30** ❄️\n🔻 Perte : **8 à 15** ❄️', inline=False)
    e.set_footer(text='Choisis directement avec les boutons sous cet encadré.')
    return illustrer(e, 'amoureux')


def embed_boutique():
    e = discord.Embed(title=f"{MALFRED_EMOTES['riche']} LA BOUTIQUE DE MALFRED",
        description=phrase('boutique') + ' 😈', color=discord.Color.green())
    for _, (nom, prix, description) in OBJETS.items():
        e.add_field(name=f'{nom} — {prix} ❄️', value=description, inline=False)
    e.set_footer(text='1 achat par jour • 1 exemplaire de chaque objet • Pas d’échanges')
    return illustrer(e, 'riche')


def embed_inventaire(user):
    with connexion() as db:
        creer_joueur(db, user.id)
        objets = db.execute('SELECT objet FROM inventaire WHERE user_id=? ORDER BY objet', (user.id,)).fetchall()
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user.id,)).fetchone()[0]
    contenu = '\n'.join((OBJETS[code][0] if code in OBJETS else NOIR[code][0] if code in NOIR else code)+f' (`{code}`)' for (code,) in objets)
    e = discord.Embed(title=f'🎒 Inventaire de {user.display_name}',
        description=(contenu or 'C’est vide. Même les mites ont déménagé.') + f"\n\n{MALFRED_EMOTES['flocon']} **{solde} flocons**",
        color=discord.Color.gold())
    return illustrer(e, 'amoureux')


def embed_classement(guild):
    with connexion() as db:
        scores = db.execute('SELECT user_id, flocons FROM joueurs ORDER BY flocons DESC, user_id ASC').fetchall()
    # Classement de tous les joueurs enregistrés dans cette base.
    top = scores[:10]
    description = '\n'.join(f'**{i}.** <@{uid}> — **{score} ❄️**' for i, (uid, score) in enumerate(top, 1))
    e = discord.Embed(title=f"{MALFRED_EMOTES['riche']} LES FORTUNES DU PÔLE NORD",
        description=description or 'Personne à plumer pour le moment.', color=discord.Color.gold())
    return illustrer(e, 'riche')


class CadeauxView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def jouer(self, interaction, numero):
        texte, couleur, reussi = ouvrir_cadeau(interaction.user.id, numero)
        if not reussi:
            await interaction.response.send_message(texte, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        publie = await annoncer_publiquement(interaction, f"{MALFRED_EMOTES['flocon']} LE VERDICT DE MALFRED", texte, couleur)
        await interaction.followup.send('🎄 Ton résultat est visible par tout le salon !' if publie else
                                        '⚠️ Cadeau enregistré, mais Malfred ne peut pas publier ici. Vérifie ses permissions.', ephemeral=True)

    @discord.ui.button(label='Friandise suspecte', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['amoureux']), style=discord.ButtonStyle.success, custom_id='malfred:ouvrir:1')
    async def choix1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.jouer(interaction, 1)

    @discord.ui.button(label='Coffre du filou', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['riche']), style=discord.ButtonStyle.primary, custom_id='malfred:ouvrir:2')
    async def choix2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.jouer(interaction, 2)

    @discord.ui.button(label='Pacte maudit', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['mort']), style=discord.ButtonStyle.danger, custom_id='malfred:ouvrir:3')
    async def choix3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.jouer(interaction, 3)


class ConfirmerAchat(discord.ui.View):
    def __init__(self, objet):
        super().__init__(timeout=120)
        self.objet = objet

    @discord.ui.button(label='Confirmer', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['riche']), style=discord.ButtonStyle.success)
    async def confirmer(self, interaction: discord.Interaction, button: discord.ui.Button):
        resultat, reussi = effectuer_achat(interaction.user.id, self.objet)
        await interaction.response.edit_message(content=('✅ Achat effectué ! Regarde dans le salon.' if reussi else resultat), embed=None, view=None)
        if reussi:
            publie = await annoncer_publiquement(interaction, '🛒 UNE NOUVELLE ARNAQUE !', resultat, discord.Color.green())
            if not publie:
                await interaction.followup.send('⚠️ Achat enregistré, mais annonce impossible : vérifie les permissions du bot.', ephemeral=True)

    @discord.ui.button(label='Annuler', style=discord.ButtonStyle.secondary)
    async def annuler(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content='Achat annulé. Je vais m’en remettre. Peut-être.', embed=None, view=None)


class ChoixObjet(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=nom.split(' ', 1)[1], value=code,
            description=f'{prix} flocons — {description[:65]}', emoji=nom.split(' ', 1)[0])
            for code, (nom, prix, description) in OBJETS.items()]
        super().__init__(placeholder='🛒 Choisis un objet…', options=options, custom_id='malfred:choix_objet')

    async def callback(self, interaction: discord.Interaction):
        objet = self.values[0]
        nom, prix, description = OBJETS[objet]
        e = discord.Embed(title=f'🛒 {nom}', description=f'{description}\n\n**Prix : {prix} ❄️**\nTu confirmes ?',
                          color=discord.Color.gold())
        await interaction.response.send_message(embed=e, view=ConfirmerAchat(objet), ephemeral=True)


class BoutiqueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ChoixObjet())

    @discord.ui.button(label='Inventaire', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['machiavelique']), style=discord.ButtonStyle.secondary, custom_id='malfred:boutique:inventaire', row=1)
    async def inventaire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_inventaire(interaction.user), view=InventaireView(), ephemeral=True)

    @discord.ui.button(label='Mes flocons', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['flocon']), style=discord.ButtonStyle.secondary, custom_id='malfred:boutique:flocons', row=1)
    async def flocons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f'❄️ Tu as **{solde_joueur(interaction.user.id)} flocons**.', ephemeral=True)


class InventaireView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Utiliser la boule à neige', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['flocon']), style=discord.ButtonStyle.primary, custom_id='malfred:inventaire:boule')
    async def boule(self, interaction: discord.Interaction, button: discord.ui.Button):
        resultat, reussi = utiliser_boule(interaction.user.id)
        if not reussi:
            await interaction.response.send_message(resultat, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        publie = await annoncer_publiquement(interaction, '🔮 RENCONTRE IMPROBABLE', resultat, discord.Color.purple())
        await interaction.followup.send('🔮 Rencontre annoncée dans le salon !' if publie else
                                        '⚠️ Rencontre enregistrée, mais annonce impossible : vérifie les permissions du bot.', ephemeral=True)


class AccueilView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Cadeaux', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['amoureux']), style=discord.ButtonStyle.success, custom_id='malfred:menu:cadeaux')
    async def cadeaux(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_cadeaux(), view=CadeauxView(), ephemeral=True)

    @discord.ui.button(label='Boutique', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['riche']), style=discord.ButtonStyle.primary, custom_id='malfred:menu:boutique')
    async def boutique(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_boutique(), view=BoutiqueView(), ephemeral=True)

    @discord.ui.button(label='Inventaire', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['machiavelique']), style=discord.ButtonStyle.secondary, custom_id='malfred:menu:inventaire')
    async def inventaire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_inventaire(interaction.user), view=InventaireView(), ephemeral=True)

    @discord.ui.button(label='Classement', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['riche']), style=discord.ButtonStyle.secondary, custom_id='malfred:menu:classement')
    async def classement(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_classement(interaction.guild))

    @discord.ui.button(label='Mes flocons', emoji=discord.PartialEmoji.from_str(MALFRED_EMOTES['flocon']), style=discord.ButtonStyle.secondary, custom_id='malfred:menu:flocons', row=1)
    async def flocons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f'❄️ Tu as **{solde_joueur(interaction.user.id)} flocons**.', ephemeral=True)


@bot.tree.command(name='malfred', description='Ouvre le menu interactif de Malfred 🎄')
async def cmd_malfred(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_accueil(), view=AccueilView())


@bot.tree.command(name='cadeau', description='Choisis ton cadeau piégé du jour 🎁')
async def cmd_cadeau(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_cadeaux(), view=CadeauxView(), ephemeral=True)


@bot.tree.command(name='boutique', description='Visite la boutique douteuse de Malfred 🛒')
async def cmd_boutique(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_boutique(), view=BoutiqueView(), ephemeral=True)


@bot.tree.command(name='inventaire', description='Consulte tes objets 🎒')
async def cmd_inventaire(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_inventaire(interaction.user), view=InventaireView(), ephemeral=True)


@bot.tree.command(name='flocons', description='Consulte ton solde de flocons ❄️')
async def cmd_flocons(interaction: discord.Interaction):
    await interaction.response.send_message(f'❄️ Tu as **{solde_joueur(interaction.user.id)} flocons**.', ephemeral=True)


@bot.tree.command(name='classement', description='Découvre les plus riches du pôle Nord 🏆')
async def cmd_classement(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_classement(interaction.guild))


@bot.tree.command(name='rencontre', description='Utilise ta boule à neige pour une rencontre 🔮')
async def cmd_rencontre(interaction: discord.Interaction):
    resultat, reussi = utiliser_boule(interaction.user.id)
    if not reussi:
        await interaction.response.send_message(resultat, ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    publie = await annoncer_publiquement(interaction, '🔮 RENCONTRE IMPROBABLE', resultat, discord.Color.purple())
    await interaction.followup.send('🔮 Rencontre annoncée dans le salon !' if publie else
                                    '⚠️ Rencontre enregistrée, mais annonce impossible : vérifie les permissions du bot.', ephemeral=True)


def est_staff(interaction):
    if interaction.user.id in STAFF_IDS:
        return True
    # Les personnes ayant la permission « Gérer le serveur » peuvent administrer Malfred.
    return isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_guild


@bot.tree.command(name='admin_reset_cadeau', description='Staff : réinitialise le cadeau quotidien d’un joueur')
@app_commands.describe(joueur='Joueur dont le cadeau doit être réinitialisé')
@app_commands.guild_only()
async def cmd_admin_reset(interaction: discord.Interaction, joueur: discord.User):
    if not est_staff(interaction):
        await interaction.response.send_message('🔒 Cette commande est réservée au staff autorisé.', ephemeral=True)
        return
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, joueur.id)
        db.execute('UPDATE joueurs SET dernier_cadeau=NULL WHERE user_id=?', (joueur.id,))
    await interaction.response.send_message(
        f'✅ Cadeau quotidien réinitialisé pour {joueur.mention}. **Ses flocons sont inchangés.**', ephemeral=True)



# --- MARCHÉ NOIR : catalogue indépendant de la boutique normale ---
# Les prix et effets sont affichés avant achat. Aucune monnaie réelle.
NOIR = {
    'noir_trefle': ('🍀 Trèfle corrompu', '8 ❄️', 'Réduit de 10 la prochaine perte sur cadeau, après activation.'),
    'noir_miroir': ('🪞 Miroir du tricheur', '1 objet à sacrifier', 'Révèle victoire ou défaite du prochain cadeau; renoncer consomme le cadeau.'),
    'noir_chaussette': ('🧦 Chaussette maudite', '5 ❄️', '0 à 10 flocons lors de son utilisation.'),
    'noir_potion': ('🧪 Potion du dernier espoir', 'Gratuite si moitié basse', '5 à 10 flocons de rattrapage, une fois sur tout l’événement.'),
    'noir_de': ('🎲 Dé du désespoir', 'Cadeau de demain', '50 % de chances de gagner 12 flocons, sinon 0; bloque demain.'),
    'noir_contrat': ('📜 Contrat douteux', '10 ❄️', 'Reçoit 15 flocons; dette de 8 flocons dans trois jours.'),
    'noir_canard': ('🦆 Canard doré', '20 ❄️', 'Collection; bonus de 5 flocons appliqué une seule fois le 24 décembre.'),
    'noir_sablier': ('⌛ Sablier volé', '12 ❄️', 'Rejoue une fois le cadeau du jour; le second résultat remplace le premier.'),
}

def now_ch():
    return datetime.now(TZ)

def marche_actuel(db):
    return db.execute('SELECT id,fin,offres FROM marches WHERE debut<=? AND fin>? ORDER BY id DESC LIMIT 1', (now_ch().isoformat(), now_ch().isoformat())).fetchone()

def ajouter_objet(db, uid, code):
    db.execute('INSERT INTO inventaire(user_id,objet,quantite) VALUES (?,?,1) ON CONFLICT(user_id,objet) DO UPDATE SET quantite=quantite+1', (uid,code))

def quantite(db, uid, code):
    row=db.execute('SELECT quantite FROM inventaire WHERE user_id=? AND objet=?',(uid,code)).fetchone()
    return row[0] if row else 0

def consommer(db, uid, code):
    if quantite(db,uid,code)<1: return False
    db.execute('UPDATE inventaire SET quantite=quantite-1 WHERE user_id=? AND objet=?',(uid,code))
    db.execute('DELETE FROM inventaire WHERE user_id=? AND objet=? AND quantite<=0',(uid,code))
    return True

def achat_noir(uid, code, sacrifice=None):
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        marche=marche_actuel(db)
        if not marche: return '🕯️ Marché fermé. Tu arrives après la fête.',False
        mid,_,offres=marche
        if code not in offres.split(','): return 'Cet objet n’est pas proposé aujourd’hui.',False
        creer_joueur(db,uid)
        count=db.execute('SELECT nombre FROM achats_noirs WHERE marche_id=? AND user_id=?',(mid,uid)).fetchone()
        if count and count[0]>=2: return 'Deux achats maximum pendant cette ouverture.',False
        if quantite(db,uid,code): return 'Tu possèdes déjà cet objet.',False
        if code=='noir_potion':
            if db.execute('SELECT 1 FROM etat_marche WHERE cle=?',(f'potion:{uid}',)).fetchone(): return 'Tu as déjà reçu une potion pendant cet événement.',False
            rang=db.execute('SELECT COUNT(*) FROM joueurs WHERE flocons>(SELECT flocons FROM joueurs WHERE user_id=?)',(uid,)).fetchone()[0]
            total=db.execute('SELECT COUNT(*) FROM joueurs').fetchone()[0]
            if rang < total//2: return 'Réservé à la moitié basse du classement.',False
        elif code=='noir_miroir':
            if not sacrifice or sacrifice==code or quantite(db,uid,sacrifice)<1: return 'Choisis un objet possédé à sacrifier.',False
            consommer(db,uid,sacrifice)
        elif code=='noir_de':
            if now_ch().date().day>=24 and now_ch().month==12: return 'Trop tard pour sacrifier demain.',False
            db.execute('INSERT OR IGNORE INTO activations(user_id) VALUES (?)',(uid,))
            demain=(now_ch().date()+timedelta(days=1)).isoformat()
            db.execute('UPDATE activations SET blocage_cadeau=? WHERE user_id=?',(demain,uid))
        else:
            prix={'noir_trefle':8,'noir_chaussette':5,'noir_contrat':10,'noir_canard':20,'noir_sablier':12}.get(code,0)
            solde=db.execute('SELECT flocons FROM joueurs WHERE user_id=?',(uid,)).fetchone()[0]
            if solde<prix: return f'Il te manque {prix-solde} flocons.',False
            db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?',(prix,uid))
        ajouter_objet(db,uid,code)
        db.execute('INSERT INTO achats_noirs(marche_id,user_id,nombre) VALUES (?,?,1) ON CONFLICT(marche_id,user_id) DO UPDATE SET nombre=nombre+1',(mid,uid))
        if code=='noir_potion': db.execute('INSERT INTO etat_marche(cle,valeur) VALUES (?,?)',(f'potion:{uid}','1'))
        return f'🕯️ **{NOIR[code][0]}** acheté ! {phrase("achat")}',True

def activer(uid,code):
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db,uid)
        db.execute('INSERT OR IGNORE INTO activations(user_id) VALUES (?)',(uid,))
        if quantite(db,uid,code)<1: return 'Tu ne possèdes pas cet objet.',False
        if code in ('trefle','bouclier','noir_trefle'):
            col={'trefle':'trefle','bouclier':'bouclier','noir_trefle':'corrompu'}[code]
            db.execute(f'UPDATE activations SET {col}=1 WHERE user_id=?',(uid,))
            return '✨ Objet activé : il sera consommé au prochain cadeau concerné.',True
        if code=='noir_miroir':
            # Prévisualisation simple : un tirage fixé au moment de l'activation.
            return '🪞 Utilise `/miroir_voir` pour choisir le cadeau à observer.',False
        if code=='noir_sablier': return '⌛ Utilise `/rejouer` après avoir ouvert un cadeau aujourd’hui.',False
        if code=='noir_canard': return '🦆 Ce canard reste dans ton inventaire jusqu’à la finale.',False
        consommer(db,uid,code)
        solde=db.execute('SELECT flocons FROM joueurs WHERE user_id=?',(uid,)).fetchone()[0]
        gain=0
        if code=='noir_chaussette': gain=random.randint(0,10)
        if code=='noir_potion': gain=random.randint(5,10)
        if code=='noir_de': gain=12 if random.random()<0.5 else 0
        if code=='noir_contrat':
            gain=15
            echeance=(now_ch().date()+timedelta(days=3)).isoformat()
            db.execute('INSERT INTO dettes(user_id,echeance,montant) VALUES (?,?,8) ON CONFLICT(user_id,echeance) DO UPDATE SET montant=montant+8',(uid,echeance))
        db.execute('UPDATE joueurs SET flocons=flocons+? WHERE user_id=?',(gain,uid))
        return f'{NOIR[code][0]} : **+{gain} ❄️**. Nouveau solde : **{solde+gain}**.',True

class MarcheSelect(discord.ui.Select):
    def __init__(self,offres):
        super().__init__(placeholder='Choisir une marchandise...', options=[discord.SelectOption(label=NOIR[k][0][:90],value=k,description=(NOIR[k][1]+' • '+NOIR[k][2])[:100]) for k in offres],custom_id='malfred:marche:selection')
    async def callback(self,interaction):
        code=self.values[0]
        await interaction.response.send_message(f'**{NOIR[code][0]}**\n{NOIR[code][2]}\nCoût : {NOIR[code][1]}\nConfirmer ?',view=MarcheConfirm(code),ephemeral=True)

class MarcheConfirm(discord.ui.View):
    def __init__(self,code):
        super().__init__(timeout=120);self.code=code
    @discord.ui.button(label='Confirmer',style=discord.ButtonStyle.success)
    async def oui(self,interaction,button):
        if self.code=='noir_miroir':
            with connexion() as db:
                options=[discord.SelectOption(label=(OBJETS[k][0] if k in OBJETS else NOIR[k][0])[:90],value=k) for k,q in db.execute('SELECT objet,quantite FROM inventaire WHERE user_id=?',(interaction.user.id,)) if q>0 and k!='noir_miroir']
            if not options:
                await interaction.response.edit_message(content='Tu n’as aucun objet à sacrifier.',view=None);return
            await interaction.response.edit_message(content='Quel objet sacrifier ?',view=SacrificeView(options),embed=None);return
        msg,ok=achat_noir(interaction.user.id,self.code)
        await interaction.response.edit_message(content=msg,view=None,embed=None)
        if ok: await annoncer_publiquement(interaction,'🕯️ ACHAT CLANDESTIN',msg,discord.Color.dark_purple())

class SacrificeSelect(discord.ui.Select):
    def __init__(self,options): super().__init__(placeholder='Objet à sacrifier',options=options)
    async def callback(self,interaction):
        msg,ok=achat_noir(interaction.user.id,'noir_miroir',self.values[0]);await interaction.response.edit_message(content=msg,view=None)
        if ok: await annoncer_publiquement(interaction,'🕯️ ÉCHANGE CLANDESTIN',msg,discord.Color.dark_purple())
class SacrificeView(discord.ui.View):
    def __init__(self,options): super().__init__(timeout=120);self.add_item(SacrificeSelect(options))
class MarcheView(discord.ui.View):
    def __init__(self,offres): super().__init__(timeout=300);self.add_item(MarcheSelect(offres))

@bot.tree.command(name='marche',description='Voir le Marché Noir surprise de Malfred')
async def cmd_marche(interaction:discord.Interaction):
    with connexion() as db: marche=marche_actuel(db)
    if not marche:
        await interaction.response.send_message('🕯️ Le Marché Noir est fermé. Malfred a disparu dans une ruelle.',ephemeral=True);return
    mid,fin,offres=marche;codes=offres.split(',')
    e=discord.Embed(title=f"{MALFRED_EMOTES['machiavelique']} MALFRED ET SON MARCHÉ NOIR",description='Stock illimité • 2 achats par joueur et par ouverture\nFerme à '+fin+' (heure suisse)\n\n'+'\n'.join(f'**{NOIR[k][0]}** — {NOIR[k][1]}\n{NOIR[k][2]}' for k in codes),color=discord.Color.dark_purple())
    await interaction.response.send_message(embed=illustrer(e, 'machiavelique'),view=MarcheView(codes),ephemeral=True)

@bot.tree.command(name='activer',description='Activer manuellement un objet de ton inventaire')
@app_commands.describe(objet='Code de l’objet, visible avec /inventaire')
async def cmd_activer(interaction:discord.Interaction,objet:str):
    msg,ok=activer(interaction.user.id,objet.strip().lower()) if objet in OBJETS or objet in NOIR else ('Objet inconnu.',False)
    await interaction.response.send_message(msg,ephemeral=not ok)
    if ok: await annoncer_publiquement(interaction,'🎒 OBJET ACTIVÉ',msg,discord.Color.purple())

@bot.tree.command(name='miroir_voir',description='Prévoir le résultat d’un cadeau avec ton miroir')
@app_commands.describe(choix='1 Friandise, 2 Coffre, 3 Pacte')
async def cmd_miroir(interaction:discord.Interaction,choix:int):
    if choix not in CADEAUX:
        await interaction.response.send_message('Choisis 1, 2 ou 3.',ephemeral=True);return
    uid=interaction.user.id
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE');creer_joueur(db,uid)
        if not quantite(db,uid,'noir_miroir'):
            await interaction.response.send_message('Tu ne possèdes pas de miroir.',ephemeral=True);return
        if db.execute('SELECT dernier_cadeau FROM joueurs WHERE user_id=?',(uid,)).fetchone()[0]==aujourd_hui():
            await interaction.response.send_message('Tu as déjà ouvert ton cadeau.',ephemeral=True);return
        chance=CADEAUX[choix][0]
        active=db.execute('SELECT trefle FROM activations WHERE user_id=?',(uid,)).fetchone()
        victoire=random.randint(1,100)<=chance+(15 if active and active[0] else 0)
        consommer(db,uid,'noir_miroir')
        db.execute('INSERT OR REPLACE INTO etat_marche(cle,valeur) VALUES (?,?)',(f'miroir:{uid}',f'{choix}:'+('gain' if victoire else 'perte')))
    await interaction.response.send_message(f'🪞 Pour **{CADEAUX[choix][3]}**, le miroir annonce **'+('un gain' if victoire else 'une perte')+'**. Ouvre ce cadeau ou renonce. Un autre choix ne bénéficie pas de la prévision.',ephemeral=True)

@bot.tree.command(name='renoncer_cadeau',description='Renoncer au cadeau du jour après consultation du miroir')
async def cmd_renoncer(interaction:discord.Interaction):
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE');key=f'miroir:{interaction.user.id}'
        if not db.execute('SELECT 1 FROM etat_marche WHERE cle=?',(key,)).fetchone():
            await interaction.response.send_message('Tu n’as pas utilisé de miroir.',ephemeral=True);return
        creer_joueur(db,interaction.user.id)
        db.execute('UPDATE joueurs SET dernier_cadeau=? WHERE user_id=?',(aujourd_hui(),interaction.user.id))
        db.execute('DELETE FROM etat_marche WHERE cle=?',(key,))
    await interaction.response.send_message('🪞 Tu renonces à ton cadeau du jour.',ephemeral=True)

@bot.tree.command(name='rejouer',description='Utiliser le sablier pour retenter le cadeau du jour')
async def cmd_rejouer(interaction:discord.Interaction):
    uid=interaction.user.id
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE');creer_joueur(db,uid)
        tirage=db.execute('SELECT jour,choix,solde_avant,resultat,rejoue FROM tirages WHERE user_id=?',(uid,)).fetchone()
        if not tirage or tirage[0]!=aujourd_hui() or tirage[4]:
            await interaction.response.send_message('⌛ Aucun cadeau du jour à rejouer, ou sablier déjà utilisé.',ephemeral=True);return
        if not quantite(db,uid,'noir_sablier'):
            await interaction.response.send_message('Tu n’as pas de sablier.',ephemeral=True);return
        _,choix,avant,apres,_=tirage
        actuel=db.execute('SELECT flocons FROM joueurs WHERE user_id=?',(uid,)).fetchone()[0]
        chance,gains,pertes,nom=CADEAUX[choix]
        victoire=random.randint(1,100)<=chance
        montant=random.randint(*(gains if victoire else pertes))
        difference=montant if victoire else -montant
        # Les autres opérations intervenues depuis le cadeau sont conservées.
        nouveau=max(0,actuel-(apres-avant)+difference)
        db.execute('UPDATE joueurs SET flocons=? WHERE user_id=?',(nouveau,uid))
        db.execute('UPDATE tirages SET rejoue=1,resultat=?,montant=? WHERE user_id=?',(nouveau,difference,uid))
        consommer(db,uid,'noir_sablier')
    await interaction.response.send_message('⌛ Le sablier a été utilisé ! Résultat publié dans le salon.',ephemeral=True)
    await annoncer_publiquement(interaction,'⌛ LE SABLIER A PARLÉ',f'{nom} : **{difference:+d} ❄️** sur le second tirage. Solde : **{nouveau} ❄️**.',discord.Color.gold())

@bot.tree.command(name='admin_ouvrir_marche',description='Staff : ouvrir le Marché Noir pour six heures (test)')
@app_commands.guild_only()
async def admin_ouvrir_marche(interaction:discord.Interaction):
    if not est_staff(interaction):
        await interaction.response.send_message('Réservé au staff.',ephemeral=True);return
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        if marche_actuel(db):
            await interaction.response.send_message('Le marché est déjà ouvert.',ephemeral=True);return
        debut=now_ch();fin=debut+timedelta(hours=6)
        offres=','.join(random.sample(list(NOIR),4))
        db.execute('INSERT INTO marches(debut,fin,offres) VALUES (?,?,?)',(debut.isoformat(),fin.isoformat(),offres))
    await interaction.response.send_message('🕯️ Marché de test ouvert pendant six heures ! Utilisez `/marche`.',ephemeral=True)
    await annoncer_publiquement(interaction,'🕯️ MARCHÉ NOIR OUVERT','Six heures pour découvrir les marchandises ! `/marche`',discord.Color.dark_purple())

async def entretien_marche():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            if MARKET_CHANNEL_ID:
                with connexion() as db:
                    db.execute('BEGIN IMMEDIATE')
                    maintenant=now_ch();jour=maintenant.date().isoformat()
                    fait=db.execute('SELECT valeur FROM etat_marche WHERE cle=?',('tirage:'+jour,)).fetchone()
                    if not fait and maintenant.month==12 and 1<=maintenant.day<=24 and maintenant.hour>=10:
                        db.execute('INSERT INTO etat_marche(cle,valeur) VALUES (?,?)',('tirage:'+jour,'1'))
                        n=db.execute('SELECT COUNT(*) FROM marches').fetchone()[0]
                        dernier=db.execute('SELECT fin FROM marches ORDER BY id DESC LIMIT 1').fetchone()
                        eligible=n<4 and (not dernier or (maintenant-datetime.fromisoformat(dernier[0])).total_seconds()>=48*3600)
                        jours_restants=24-maintenant.day
                        chance=0.19 if n<2 else 0.07
                        if n<2 and jours_restants<=max(0,(2-n)*3): chance=1.0
                        if eligible and random.random()<chance:
                            offres=','.join(random.sample(list(NOIR),4))
                            fin=(maintenant+timedelta(hours=6)).isoformat()
                            db.execute('INSERT INTO marches(debut,fin,offres) VALUES (?,?,?)',(maintenant.isoformat(),fin,offres))
                            salon=bot.get_channel(MARKET_CHANNEL_ID)
                            if salon:
                                try: await salon.send(f"{MALFRED_EMOTES['machiavelique']} **LE MARCHÉ NOIR DE MALFRED EST OUVERT !**\nSix heures pour négocier avec le pire commerçant du pôle Nord. Utilisez `/marche` .")
                                except discord.HTTPException: logging.exception('Annonce marché impossible')
                    # Dettes dues, solde jamais négatif; report du reste.
                    dettes=db.execute('SELECT user_id,echeance,montant FROM dettes WHERE echeance<=?',(jour,)).fetchall()
                    for uid,date,montant in dettes:
                        creer_joueur(db,uid)
                        solde=db.execute('SELECT flocons FROM joueurs WHERE user_id=?',(uid,)).fetchone()[0]
                        paye=min(solde,montant)
                        db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?',(paye,uid))
                        db.execute('DELETE FROM dettes WHERE user_id=? AND echeance=?',(uid,date))
                        if montant>paye:
                            nouveau=(maintenant.date()+timedelta(days=1)).isoformat()
                            db.execute('INSERT INTO dettes VALUES (?,?,?) ON CONFLICT(user_id,echeance) DO UPDATE SET montant=montant+excluded.montant',(uid,nouveau,montant-paye))
        except Exception: logging.exception('Entretien Marché Noir')
        await asyncio.sleep(900)


# Les commandes ont été déclarées sur bot : on utilise setup_hook sur cette même instance.
async def setup_hook():
    bot.add_view(AccueilView())
    bot.add_view(CadeauxView())
    bot.add_view(BoutiqueView())
    bot.add_view(InventaireView())
    bot.loop.create_task(entretien_marche())
    if GUILD_ID:
        serveur = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=serveur)
        commandes = await bot.tree.sync(guild=serveur)
        logging.info('Synchronisation de %s commandes sur le serveur %s', len(commandes), GUILD_ID)
    else:
        commandes = await bot.tree.sync()
        logging.info('Synchronisation globale de %s commandes (apparition parfois différée)', len(commandes))


bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    logging.info('🎄 Malfred est connecté : %s (ID %s)', bot.user, bot.user.id)


@bot.tree.error
async def on_slash_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logging.error('Erreur commande / : %r', error)
    message = '⚠️ Malfred a trébuché dans une congère. Réessaie dans un instant.'
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


if __name__ == '__main__':
    initialiser_base()
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('La variable DISCORD_TOKEN manque sur Railway.')
    bot.run(token)
