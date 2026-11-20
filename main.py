import os
import random
import sqlite3
import logging
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
            return '🎄 ' + phrase('deja'), discord.Color.orange()
        bonus = 15 if possede(db, user_id, 'trefle') else 0
        if bonus:
            retirer_objet(db, user_id, 'trefle')
        victoire = random.randint(1, 100) <= chance + bonus
        montant = random.randint(*(gains if victoire else pertes))
        protege = not victoire and possede(db, user_id, 'bouclier')
        if protege:
            retirer_objet(db, user_id, 'bouclier')
        nouveau = solde + montant if victoire else (solde if protege else max(0, solde - montant))
        db.execute('UPDATE joueurs SET flocons=?, dernier_cadeau=? WHERE user_id=?', (nouveau, aujourd_hui(), user_id))
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
    return f'**{nom}**\n\n{bilan}\n\n❄️ Nouveau solde : **{nouveau} flocons**.', couleur


def effectuer_achat(user_id, objet):
    nom, prix, _ = OBJETS[objet]
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]
        ancien = db.execute('SELECT dernier_achat FROM boutique_joueurs WHERE user_id=?', (user_id,)).fetchone()
        if ancien and ancien[0] == aujourd_hui():
            return '🛒 Un achat par jour. Ma boutique n’est pas un buffet à volonté.'
        if possede(db, user_id, objet):
            return '🎒 Tu possèdes déjà cet objet. Un exemplaire maximum !'
        if solde < prix:
            return f'💸 Il faut **{prix} flocons** et tu n’en as que **{solde}**.'
        db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?', (prix, user_id))
        db.execute('''INSERT INTO boutique_joueurs (user_id, dernier_achat) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET dernier_achat=excluded.dernier_achat''', (user_id, aujourd_hui()))
        if objet != 'paquet':
            db.execute('INSERT INTO inventaire (user_id, objet, quantite) VALUES (?, ?, 1)', (user_id, objet))
        gain = random.randint(0, 30) if objet == 'paquet' else 0
        if gain:
            db.execute('UPDATE joueurs SET flocons=flocons+? WHERE user_id=?', (gain, user_id))
    supplement = f'\n🎁 Le paquet contenait **{gain} flocons** !' if objet == 'paquet' else ''
    return f'🛒 Achat : **{nom}** pour **{prix} flocons** !{supplement}\n{phrase("achat")}\n❄️ Solde : **{solde - prix + gain}**.'


def utiliser_boule(user_id):
    with connexion() as db:
        db.execute('BEGIN IMMEDIATE')
        creer_joueur(db, user_id)
        if not possede(db, user_id, 'boule'):
            return '🔮 Tu n’as pas de boule à neige. Même ma magie a des limites.'
        retirer_objet(db, user_id, 'boule')
        montant = random.randint(-5, 10)
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user_id,)).fetchone()[0]
        protege = montant < 0 and possede(db, user_id, 'bouclier')
        if protege:
            retirer_objet(db, user_id, 'bouclier')
        nouveau = solde if protege else max(0, solde + montant)
        db.execute('UPDATE joueurs SET flocons=? WHERE user_id=?', (nouveau, user_id))
    return (f'🔮 La boule tourbillonne… **{nouveau - solde:+d} flocons** !\n'
            + ('🛡️ Ton bouclier a absorbé la perte.\n' if protege else '')
            + f'❄️ Nouveau solde : **{nouveau}**.')


def embed_accueil():
    e = discord.Embed(title='🎄 MALFRED — LE LUTIN DU CHAOS',
        description=f'{phrase("accueil")} 😈\n\nChoisis une activité ci-dessous :', color=discord.Color.dark_green())
    e.add_field(name='🎁 Cadeaux', value='Un pari chaque jour', inline=True)
    e.add_field(name='🛒 Boutique', value='Dépense tes flocons', inline=True)
    e.add_field(name='🎒 Inventaire', value='Tes trouvailles douteuses', inline=True)
    e.add_field(name='🏆 Classement', value='Les plus riches', inline=True)
    e.set_footer(text='Malfred décline toute responsabilité pour tes décisions.')
    return e


def embed_cadeaux():
    e = discord.Embed(title='🎁 LES CADEAUX PIÉGÉS',
        description=f'{phrase("cadeaux")} 😈\n**Un cadeau par jour.**', color=discord.Color.red())
    e.add_field(name='🍬 Friandise suspecte · 70 %', value='🟢 Gain : **2 à 5** ❄️\n🔻 Perte : **1 à 3** ❄️', inline=False)
    e.add_field(name='🧰 Coffre du filou · 50 %', value='🟡 Gain : **5 à 12** ❄️\n🔻 Perte : **4 à 8** ❄️', inline=False)
    e.add_field(name='💀 Pacte maudit · 30 %', value='🔴 Gain : **15 à 30** ❄️\n🔻 Perte : **8 à 15** ❄️', inline=False)
    e.set_footer(text='Choisis directement avec les boutons sous cet encadré.')
    return e


def embed_boutique():
    e = discord.Embed(title='🛒 LE MARCHÉ NOIR DE MALFRED',
        description=phrase('boutique') + ' 😈', color=discord.Color.green())
    for _, (nom, prix, description) in OBJETS.items():
        e.add_field(name=f'{nom} — {prix} ❄️', value=description, inline=False)
    e.set_footer(text='1 achat par jour • 1 exemplaire de chaque objet • Pas d’échanges')
    return e


def embed_inventaire(user):
    with connexion() as db:
        creer_joueur(db, user.id)
        objets = db.execute('SELECT objet FROM inventaire WHERE user_id=? ORDER BY objet', (user.id,)).fetchall()
        solde = db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (user.id,)).fetchone()[0]
    contenu = '\n'.join(OBJETS[code][0] for (code,) in objets if code in OBJETS)
    return discord.Embed(title=f'🎒 Inventaire de {user.display_name}',
        description=(contenu or 'C’est vide. Même les mites ont déménagé.') + f'\n\n❄️ **{solde} flocons**',
        color=discord.Color.gold())


def embed_classement(guild):
    with connexion() as db:
        scores = db.execute('SELECT user_id, flocons FROM joueurs ORDER BY flocons DESC, user_id ASC').fetchall()
    # Classement de tous les joueurs enregistrés dans cette base.
    top = scores[:10]
    description = '\n'.join(f'**{i}.** <@{uid}> — **{score} ❄️**' for i, (uid, score) in enumerate(top, 1))
    return discord.Embed(title='🏆 LES FORTUNES DU PÔLE NORD',
        description=description or 'Personne à plumer pour le moment.', color=discord.Color.gold())


class CadeauxView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def jouer(self, interaction, numero):
        texte, couleur = ouvrir_cadeau(interaction.user.id, numero)
        await interaction.response.send_message(embed=discord.Embed(
            title='🎁 Le verdict de Malfred', description=texte, color=couleur), ephemeral=True)

    @discord.ui.button(label='Friandise suspecte', emoji='🍬', style=discord.ButtonStyle.success, custom_id='malfred:ouvrir:1')
    async def choix1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.jouer(interaction, 1)

    @discord.ui.button(label='Coffre du filou', emoji='🧰', style=discord.ButtonStyle.primary, custom_id='malfred:ouvrir:2')
    async def choix2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.jouer(interaction, 2)

    @discord.ui.button(label='Pacte maudit', emoji='💀', style=discord.ButtonStyle.danger, custom_id='malfred:ouvrir:3')
    async def choix3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.jouer(interaction, 3)


class ConfirmerAchat(discord.ui.View):
    def __init__(self, objet):
        super().__init__(timeout=120)
        self.objet = objet

    @discord.ui.button(label='Confirmer', emoji='💰', style=discord.ButtonStyle.success)
    async def confirmer(self, interaction: discord.Interaction, button: discord.ui.Button):
        resultat = effectuer_achat(interaction.user.id, self.objet)
        await interaction.response.edit_message(content=resultat, embed=None, view=None)

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

    @discord.ui.button(label='Inventaire', emoji='🎒', style=discord.ButtonStyle.secondary, custom_id='malfred:boutique:inventaire', row=1)
    async def inventaire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_inventaire(interaction.user), view=InventaireView(), ephemeral=True)

    @discord.ui.button(label='Mes flocons', emoji='❄️', style=discord.ButtonStyle.secondary, custom_id='malfred:boutique:flocons', row=1)
    async def flocons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f'❄️ Tu as **{solde_joueur(interaction.user.id)} flocons**.', ephemeral=True)


class InventaireView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Utiliser la boule à neige', emoji='🔮', style=discord.ButtonStyle.primary, custom_id='malfred:inventaire:boule')
    async def boule(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(utiliser_boule(interaction.user.id), ephemeral=True)


class AccueilView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Cadeaux', emoji='🎁', style=discord.ButtonStyle.success, custom_id='malfred:menu:cadeaux')
    async def cadeaux(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_cadeaux(), view=CadeauxView(), ephemeral=True)

    @discord.ui.button(label='Boutique', emoji='🛒', style=discord.ButtonStyle.primary, custom_id='malfred:menu:boutique')
    async def boutique(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_boutique(), view=BoutiqueView(), ephemeral=True)

    @discord.ui.button(label='Inventaire', emoji='🎒', style=discord.ButtonStyle.secondary, custom_id='malfred:menu:inventaire')
    async def inventaire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_inventaire(interaction.user), view=InventaireView(), ephemeral=True)

    @discord.ui.button(label='Classement', emoji='🏆', style=discord.ButtonStyle.secondary, custom_id='malfred:menu:classement')
    async def classement(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_classement(interaction.guild), ephemeral=True)

    @discord.ui.button(label='Mes flocons', emoji='❄️', style=discord.ButtonStyle.secondary, custom_id='malfred:menu:flocons', row=1)
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
    await interaction.response.send_message(embed=embed_classement(interaction.guild), ephemeral=True)


@bot.tree.command(name='rencontre', description='Utilise ta boule à neige pour une rencontre 🔮')
async def cmd_rencontre(interaction: discord.Interaction):
    await interaction.response.send_message(utiliser_boule(interaction.user.id), ephemeral=True)


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


# Les commandes ont été déclarées sur bot : on utilise setup_hook sur cette même instance.
async def setup_hook():
    bot.add_view(AccueilView())
    bot.add_view(CadeauxView())
    bot.add_view(BoutiqueView())
    bot.add_view(InventaireView())
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
