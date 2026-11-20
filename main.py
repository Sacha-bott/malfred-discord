import os
import random
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

logging.basicConfig(level=logging.INFO)
TZ = ZoneInfo('Europe/Zurich')
DATABASE_PATH = os.getenv('DATABASE_PATH', '/data/malfred.db')
GUILD_ID = int(os.getenv('GUILD_ID', '0') or 0)
MARKET_CHANNEL_ID = int(os.getenv('MALFRED_CHANNEL_ID', '0') or 0)
STAFF_IDS = {int(s.strip()) for s in os.getenv('MALFRED_ADMIN_IDS', '').split(',') if s.strip().isdigit()}

# IDs recopiés des emotes Discord fournies par Saphi.
EMOJI_IDS = {
    'amoureux': 1573298335266115614,
    'flocon': 1573298111219109948,  # corrigé !
    'fume': 1573298043090899164,
    'machiavelique': 1573297932361408594,
    'moquerie': 1573298266936709150,
    'mort': 1573298187677208596,
    'riche': 1573297742925799504,
    'triste': 1573297857728090203,
}
E = {k: f'<:malfred_{k}:{v}>' for k, v in EMOJI_IDS.items()}

def button_emoji(key):
    # Si le bot ne peut pas utiliser une emote externe, le bouton reste fonctionnel.
    return discord.PartialEmoji(name=f'malfred_{key}', id=EMOJI_IDS[key])

def image(embed, key):
    # Une image 16:9 hébergée publiquement, pas une petite vignette.
    url = os.getenv(f'MALFRED_IMAGE_{key.upper()}', '').strip()
    if url.startswith(('https://', 'http://')):
        embed.set_image(url=url)
    return embed

intents = discord.Intents.default()
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

OBJETS = {
    'bouclier': ('🛡️ Bouclier givré', 25, 'Protège contre la prochaine perte du cadeau quotidien.'),
    'trefle': ('🍀 Trèfle douteux', 15, '+15 points de chance sur le prochain cadeau.'),
    'boule': ('🔮 Boule à neige', 30, 'Rencontre supplémentaire : -5 à +10 flocons.'),
    'paquet': ('🎁 Paquet suspect', 20, 'À ouvrir manuellement : 0 à 30 flocons.'),
    'canard': ('🦆 Canard de contrebande', 15, 'Objet de collection.'),
}
NOIR = {
    'noir_trefle': ('🍀 Trèfle corrompu', '8 ❄️', 'Réduit de 10 la prochaine perte de cadeau après activation.'),
    'noir_miroir': ('🪞 Miroir du tricheur', 'Sacrifier 1 objet', 'Prévoit le gain ou la perte d’un cadeau. Renoncer consomme le cadeau du jour.'),
    'noir_chaussette': ('🧦 Chaussette maudite', '5 ❄️', 'Rapporte 0 à 10 flocons lors de son utilisation.'),
    'noir_potion': ('🧪 Potion du dernier espoir', 'Gratuite, moitié basse', 'Rattrapage de 5 à 10 flocons, une fois pendant le jeu.'),
    'noir_de': ('🎲 Dé du désespoir', 'Cadeau du lendemain', 'Une chance sur deux de gagner 12 flocons; bloque le cadeau de demain.'),
    'noir_contrat': ('📜 Contrat douteux', '10 ❄️', 'Reçoit 15 flocons à activation; dette de 8 dans trois jours.'),
    'noir_canard': ('🦆 Canard de contrebande doré', '20 ❄️', 'Collection; +5 flocons une fois à la finale du 24 décembre.'),
    'noir_sablier': ('⌛ Sablier volé', '12 ❄️', 'Rejoue le cadeau du jour une fois; le second résultat remplace le premier.'),
}
CADEAUX = {
    1: (70, (2, 5), (1, 3), '🍬 Friandise suspecte'),
    2: (50, (5, 12), (4, 8), '🧰 Coffre du filou'),
    3: (30, (15, 30), (8, 15), '💀 Pacte maudit'),
}
REPLIQUES = {
    'accueil': ['Bienvenue dans mon atelier. Les réclamations vont directement à la cheminée.', 'Entrez, entrez ! Les flocons ne vont pas se voler tout seuls.', 'Joyeux Noël ! Enfin, surtout pour mon compte en banque.'],
    'cadeaux': ['Trois présents, trois façons de regretter tes choix.', 'La magie de Noël ? Non. Les probabilités.', 'La chance sourit aux audacieux. Moi, je souris aux perdants.'],
    'boutique': ['Mes prix sont fixes, ma morale beaucoup moins.', 'Chaque objet est garanti presque authentique.', 'Je n’accepte ni retours, ni pleurnicheries.'],
    'deja': ['Un cadeau par jour ! Tu pensais vraiment m’avoir deux fois ?', 'Reviens demain. Mon stock de catastrophes doit se recharger.'],
    'gain': ['Scandale ! J’avais pourtant truqué l’emballage.', 'Tu as gagné. Je vais bouder dans une congère.'],
    'perte': ['Quel magnifique don à ma caisse personnelle !', 'Les petites lignes étaient pourtant écrites en tout petit.'],
    'achat': ['Merci pour cette transaction parfaitement douteuse.', 'Je garde évidemment le reçu.'],
}

def phrase(k): return random.choice(REPLIQUES[k])
def now(): return datetime.now(TZ)
def jour(): return now().date().isoformat()
def db_open():
    directory = os.path.dirname(DATABASE_PATH)
    if directory: os.makedirs(directory, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=20)
    db.execute('PRAGMA busy_timeout=20000')
    return db

def init_db():
    with db_open() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS joueurs(user_id INTEGER PRIMARY KEY, flocons INTEGER NOT NULL DEFAULT 20, dernier_cadeau TEXT);
        CREATE TABLE IF NOT EXISTS boutique_joueurs(user_id INTEGER PRIMARY KEY, dernier_achat TEXT);
        CREATE TABLE IF NOT EXISTS inventaire(user_id INTEGER NOT NULL, objet TEXT NOT NULL, quantite INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(user_id,objet));
        CREATE TABLE IF NOT EXISTS activations(user_id INTEGER PRIMARY KEY, trefle INTEGER DEFAULT 0, bouclier INTEGER DEFAULT 0, miroir INTEGER DEFAULT 0, corrompu INTEGER DEFAULT 0, dernier_resultat TEXT, sablier_utilise TEXT, blocage_cadeau TEXT, dette INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS marches(id INTEGER PRIMARY KEY AUTOINCREMENT, debut TEXT NOT NULL, fin TEXT NOT NULL, offres TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS achats_noirs(marche_id INTEGER, user_id INTEGER, nombre INTEGER DEFAULT 0, PRIMARY KEY(marche_id,user_id));
        CREATE TABLE IF NOT EXISTS etat_marche(cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tirages(user_id INTEGER PRIMARY KEY, jour TEXT, choix INTEGER, solde_avant INTEGER, resultat INTEGER, montant INTEGER, rejoue INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS dettes(user_id INTEGER, echeance TEXT, montant INTEGER, PRIMARY KEY(user_id,echeance));
        CREATE TABLE IF NOT EXISTS participations_evenements(user_id INTEGER, evenement TEXT, PRIMARY KEY(user_id,evenement));
        ''')

def joueur(db, uid): db.execute('INSERT OR IGNORE INTO joueurs(user_id) VALUES (?)', (uid,))
def balance(db, uid):
    joueur(db, uid)
    return db.execute('SELECT flocons FROM joueurs WHERE user_id=?', (uid,)).fetchone()[0]
def solde(uid):
    with db_open() as db: return balance(db, uid)
def quantite(db, uid, code):
    row = db.execute('SELECT quantite FROM inventaire WHERE user_id=? AND objet=?', (uid, code)).fetchone()
    return row[0] if row else 0

def ajouter(db, uid, code):
    db.execute('INSERT INTO inventaire(user_id,objet,quantite) VALUES (?,?,1) ON CONFLICT(user_id,objet) DO UPDATE SET quantite=quantite+1', (uid, code))
def consommer(db, uid, code):
    if quantite(db, uid, code) < 1: return False
    db.execute('UPDATE inventaire SET quantite=quantite-1 WHERE user_id=? AND objet=?', (uid, code))
    db.execute('DELETE FROM inventaire WHERE user_id=? AND objet=? AND quantite<=0', (uid, code))
    return True

def activer_row(db, uid): db.execute('INSERT OR IGNORE INTO activations(user_id) VALUES (?)', (uid,))
def marche_actuel(db):
    t = now().isoformat()
    return db.execute('SELECT id,fin,offres FROM marches WHERE debut<=? AND fin>? ORDER BY id DESC LIMIT 1', (t,t)).fetchone()

def ouvrir_cadeau(uid, choix):
    chance, gains, pertes, nom = CADEAUX[choix]
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE')
        avant = balance(db, uid)
        dernier = db.execute('SELECT dernier_cadeau FROM joueurs WHERE user_id=?', (uid,)).fetchone()[0]
        if dernier == jour(): return '🎄 ' + phrase('deja'), discord.Color.orange(), False, 'deja'
        activer_row(db, uid)
        trefle, bouclier, corrompu, blocage = db.execute('SELECT trefle,bouclier,corrompu,blocage_cadeau FROM activations WHERE user_id=?',(uid,)).fetchone()
        if blocage == jour(): return '🎲 Ton dé du désespoir a sacrifié le cadeau du jour.', discord.Color.orange(), False, 'deja'
        bonus = 15 if trefle else 0
        if trefle:
            db.execute('UPDATE activations SET trefle=0 WHERE user_id=?', (uid,))
            consommer(db, uid, 'trefle')
        prediction = db.execute('SELECT valeur FROM etat_marche WHERE cle=?', (f'miroir:{uid}',)).fetchone()
        if prediction and prediction[0].startswith(f'{choix}:'):
            victoire = prediction[0].endswith(':gain')
            db.execute('DELETE FROM etat_marche WHERE cle=?',(f'miroir:{uid}',))
        else:
            victoire = random.randint(1,100) <= min(100, chance+bonus)
        montant = random.randint(*(gains if victoire else pertes))
        protege = bool(bouclier) and not victoire
        if protege:
            db.execute('UPDATE activations SET bouclier=0 WHERE user_id=?',(uid,))
            consommer(db, uid, 'bouclier')
        if corrompu and not victoire:
            montant = max(0, montant-10)
            db.execute('UPDATE activations SET corrompu=0 WHERE user_id=?',(uid,))
            consommer(db, uid, 'noir_trefle')
        apres = avant+montant if victoire else (avant if protege else max(0, avant-montant))
        db.execute('UPDATE joueurs SET flocons=?,dernier_cadeau=? WHERE user_id=?',(apres,jour(),uid))
        db.execute('INSERT INTO tirages(user_id,jour,choix,solde_avant,resultat,montant,rejoue) VALUES (?,?,?,?,?,?,0) ON CONFLICT(user_id) DO UPDATE SET jour=excluded.jour,choix=excluded.choix,solde_avant=excluded.solde_avant,resultat=excluded.resultat,montant=excluded.montant,rejoue=0',(uid,jour(),choix,avant,apres,apres-avant))
    if victoire:
        msg=f'🎉 **+{apres-avant} flocons !**\n{phrase("gain")}'
        humeur='gain'; color=discord.Color.green()
    elif protege:
        msg='🛡️ Ton bouclier a absorbé la perte !'; humeur='gain'; color=discord.Color.blue()
    else:
        msg=f'💀 **-{avant-apres} flocons !**\n{phrase("perte")}'
        humeur='zero' if apres==0 else 'perte'; color=discord.Color.red()
    if bonus: msg+='\n🍀 Ton trèfle a été utilisé.'
    return f'**{nom}**\n\n{msg}\n\n❄️ Nouveau solde : **{apres} flocons**.', color, True, humeur

def achat_normal(uid, code):
    nom, prix, _ = OBJETS[code]
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE')
        avant=balance(db,uid)
        last=db.execute('SELECT dernier_achat FROM boutique_joueurs WHERE user_id=?',(uid,)).fetchone()
        if last and last[0]==jour(): return '🛒 Un achat normal par jour !',False
        if quantite(db,uid,code): return '🎒 Tu possèdes déjà cet objet.',False
        if avant<prix: return f'💸 Il faut {prix} flocons, tu en as {avant}.',False
        db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?',(prix,uid))
        db.execute('INSERT INTO boutique_joueurs(user_id,dernier_achat) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET dernier_achat=excluded.dernier_achat',(uid,jour()))
        ajouter(db,uid,code) # même le paquet est stocké jusqu'à activation manuelle
    return f'🛒 **{nom}** acheté pour **{prix} ❄️** !\n{phrase("achat")}\n❄️ Solde : **{avant-prix}**.',True

def achat_noir(uid,code,sacrifice=None):
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE')
        marche=marche_actuel(db)
        if not marche: return '🕯️ Marché fermé. Tu arrives après la fête.',False
        mid,_,offres=marche
        if code not in offres.split(','): return 'Cet objet n’est pas proposé pendant cette ouverture.',False
        avant=balance(db,uid)
        row=db.execute('SELECT nombre FROM achats_noirs WHERE marche_id=? AND user_id=?',(mid,uid)).fetchone()
        if row and row[0]>=2: return 'Deux achats maximum par ouverture du Marché Noir.',False
        if quantite(db,uid,code): return 'Tu possèdes déjà cet objet.',False
        if code=='noir_potion':
            if db.execute('SELECT 1 FROM etat_marche WHERE cle=?',(f'potion:{uid}',)).fetchone(): return 'Tu as déjà obtenu une potion.',False
            rang=db.execute('SELECT COUNT(*) FROM joueurs WHERE flocons>(SELECT flocons FROM joueurs WHERE user_id=?)',(uid,)).fetchone()[0]
            total=db.execute('SELECT COUNT(*) FROM joueurs').fetchone()[0]
            if rang<total//2: return 'Réservé à la moitié basse du classement.',False
        elif code=='noir_miroir':
            if not sacrifice or sacrifice==code or not quantite(db,uid,sacrifice): return 'Choisis un objet à sacrifier.',False
            consommer(db,uid,sacrifice)
        elif code=='noir_de':
            if now().month==12 and now().day>=24: return 'Trop tard pour sacrifier le cadeau de demain.',False
            # Le blocage se produit à l'activation, pas à l'achat.
        else:
            prix={'noir_trefle':8,'noir_chaussette':5,'noir_contrat':10,'noir_canard':20,'noir_sablier':12}.get(code,0)
            if avant<prix: return f'Il te manque {prix-avant} flocons.',False
            db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?',(prix,uid))
        ajouter(db,uid,code)
        db.execute('INSERT INTO achats_noirs(marche_id,user_id,nombre) VALUES (?,?,1) ON CONFLICT(marche_id,user_id) DO UPDATE SET nombre=nombre+1',(mid,uid))
        if code=='noir_potion': db.execute('INSERT INTO etat_marche(cle,valeur) VALUES (?,?)',(f'potion:{uid}','1'))
    return f'🕯️ **{NOIR[code][0]}** acheté et rangé dans ton inventaire ! {phrase("achat")}',True

def activer(uid,code):
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE')
        avant=balance(db,uid)
        activer_row(db,uid)
        if not quantite(db,uid,code): return 'Tu ne possèdes pas cet objet.',False
        if code in ('trefle','bouclier','noir_trefle'):
            col={'trefle':'trefle','bouclier':'bouclier','noir_trefle':'corrompu'}[code]
            if db.execute(f'SELECT {col} FROM activations WHERE user_id=?',(uid,)).fetchone()[0]: return 'Cet effet est déjà activé.',False
            db.execute(f'UPDATE activations SET {col}=1 WHERE user_id=?',(uid,))
            return '✨ Objet activé ! Son effet attend le prochain cadeau concerné.',True
        if code=='noir_miroir': return '🪞 Utilise `/miroir_voir` pour choisir un cadeau à observer.',False
        if code=='noir_sablier': return '⌛ Utilise `/rejouer` après ton cadeau du jour.',False
        if code in ('canard','noir_canard'): return '🦆 Cet objet de collection se conserve. Le canard doré donnera son bonus à la finale.',False
        if code=='noir_de':
            demain=(now().date()+timedelta(days=1)).isoformat()
            if now().month==12 and now().day>=24: return 'Le jeu se termine aujourd’hui, ce dé ne peut plus être utilisé.',False
            if db.execute('SELECT blocage_cadeau FROM activations WHERE user_id=?',(uid,)).fetchone()[0]==demain: return 'Le cadeau de demain est déjà bloqué.',False
            db.execute('UPDATE activations SET blocage_cadeau=? WHERE user_id=?',(demain,uid))
        consommer(db,uid,code)
        gain=0
        if code=='boule': gain=random.randint(-5,10)
        elif code=='paquet': gain=random.randint(0,30)
        elif code=='noir_chaussette': gain=random.randint(0,10)
        elif code=='noir_potion': gain=random.randint(5,10)
        elif code=='noir_de': gain=12 if random.random()<.5 else 0
        elif code=='noir_contrat':
            gain=15
            echeance=(now().date()+timedelta(days=3)).isoformat()
            db.execute('INSERT INTO dettes(user_id,echeance,montant) VALUES (?,?,8) ON CONFLICT(user_id,echeance) DO UPDATE SET montant=montant+8',(uid,echeance))
        apres=max(0,avant+gain)
        db.execute('UPDATE joueurs SET flocons=? WHERE user_id=?',(apres,uid))
    nom=OBJETS[code][0] if code in OBJETS else NOIR[code][0]
    return f'{nom} activé : **{apres-avant:+d} ❄️**. Nouveau solde : **{apres}**.',True

async def publier(interaction,titre,texte,couleur,scene='achat'):
    salon=interaction.channel
    if not salon or not hasattr(salon,'send'): return False
    embed=discord.Embed(title=titre,description=texte,color=couleur)
    embed.set_author(name=interaction.user.display_name,icon_url=interaction.user.display_avatar.url)
    image(embed,scene)
    try:
        await salon.send(content=interaction.user.mention,embed=embed,allowed_mentions=discord.AllowedMentions.none())
        return True
    except discord.HTTPException:
        logging.exception('Publication impossible')
        return False

def accueil_embed():
    e=discord.Embed(title=f"{E['machiavelique']} MALFRED — LE LUTIN DU CHAOS",description=phrase('accueil')+' 😈\n\nChoisis une activité ci-dessous :',color=discord.Color.dark_green())
    for label,desc,emoji in [('Cadeaux','Un pari chaque jour','amoureux'),('Boutique','Dépense tes flocons','riche'),('Inventaire','Tes trouvailles douteuses','machiavelique'),('Classement','Les plus riches','riche')]:
        e.add_field(name=f'{E[emoji]} {label}',value=desc,inline=True)
    e.set_footer(text='Malfred décline toute responsabilité pour tes décisions.')
    return image(e,'accueil')

def cadeaux_embed():
    e=discord.Embed(title=f"{E['amoureux']} LES CADEAUX PIÉGÉS",description=phrase('cadeaux')+' 😈\n**Un cadeau par jour.**',color=discord.Color.red())
    for n,emoji in [(1,'amoureux'),(2,'riche'),(3,'mort')]:
        chance,gains,pertes,nom=CADEAUX[n]
        e.add_field(name=f'{E[emoji]} {nom} · {chance} %',value=f'🟢 Gain : **{gains[0]} à {gains[1]}** ❄️\n🔻 Perte : **{pertes[0]} à {pertes[1]}** ❄️',inline=False)
    return image(e,'cadeaux')

def boutique_embed():
    e=discord.Embed(title=f"{E['riche']} LA BOUTIQUE DE MALFRED",description=phrase('boutique')+' 😈',color=discord.Color.green())
    for nom,prix,desc in OBJETS.values(): e.add_field(name=f'{nom} — {prix} ❄️',value=desc,inline=False)
    e.set_footer(text='1 achat normal par jour • Objets activables depuis l’inventaire')
    return image(e,'boutique')

def inventaire_embed(user):
    with db_open() as db:
        avant=balance(db,user.id)
        rows=db.execute('SELECT objet,quantite FROM inventaire WHERE user_id=? AND quantite>0 ORDER BY objet',(user.id,)).fetchall()
        activer_row(db,user.id)
        effects=db.execute('SELECT trefle,bouclier,corrompu FROM activations WHERE user_id=?',(user.id,)).fetchone()
    noms={**{k:v[0] for k,v in OBJETS.items()},**{k:v[0] for k,v in NOIR.items()}}
    desc='\n'.join(f'{noms.get(k,k)} ×{q} (`{k}`)' for k,q in rows) or 'C’est vide. Même les mites ont déménagé.'
    actifs=[label for label,flag in zip(['🍀 Trèfle','🛡️ Bouclier','🍀 Trèfle corrompu'],effects) if flag]
    if actifs: desc+='\n\n**Effets activés :** '+', '.join(actifs)
    e=discord.Embed(title=f'🎒 Inventaire de {user.display_name}',description=desc+f"\n\n{E['flocon']} **{avant} flocons**",color=discord.Color.gold())
    return image(e,'inventaire')

def classement_embed():
    with db_open() as db: scores=db.execute('SELECT user_id,flocons FROM joueurs ORDER BY flocons DESC,user_id ASC LIMIT 10').fetchall()
    desc='\n'.join(f'**{i}.** <@{uid}> — **{n} ❄️**' for i,(uid,n) in enumerate(scores,1)) or 'Personne à plumer pour le moment.'
    return image(discord.Embed(title=f"{E['riche']} LES FORTUNES DU PÔLE NORD",description=desc,color=discord.Color.gold()),'classement')

class CadeauxView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def jouer(self,interaction,choix):
        texte,couleur,ok,scene=ouvrir_cadeau(interaction.user.id,choix)
        if not ok: return await interaction.response.send_message(texte,ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        publie=await publier(interaction,f"{E['flocon']} LE VERDICT DE MALFRED",texte,couleur,scene)
        await interaction.followup.send('🎄 Résultat visible dans le salon !' if publie else '⚠️ Cadeau enregistré, annonce impossible : vérifie les permissions.',ephemeral=True)
    @discord.ui.button(label='Friandise suspecte',emoji=button_emoji('amoureux'),style=discord.ButtonStyle.success,custom_id='malfred:ouvrir:1')
    async def choix1(self,i,b): await self.jouer(i,1)
    @discord.ui.button(label='Coffre du filou',emoji=button_emoji('riche'),style=discord.ButtonStyle.primary,custom_id='malfred:ouvrir:2')
    async def choix2(self,i,b): await self.jouer(i,2)
    @discord.ui.button(label='Pacte maudit',emoji=button_emoji('mort'),style=discord.ButtonStyle.danger,custom_id='malfred:ouvrir:3')
    async def choix3(self,i,b): await self.jouer(i,3)

class ConfirmerAchat(discord.ui.View):
    def __init__(self,code): super().__init__(timeout=120);self.code=code
    @discord.ui.button(label='Confirmer',emoji=button_emoji('riche'),style=discord.ButtonStyle.success)
    async def confirmer(self,i,b):
        msg,ok=achat_normal(i.user.id,self.code)
        await i.response.edit_message(content='✅ Achat enregistré dans ton inventaire !' if ok else msg,embed=None,view=None)
        if ok: await publier(i,'🛒 UNE NOUVELLE ARNAQUE !',msg,discord.Color.green(),'achat')
    @discord.ui.button(label='Annuler',style=discord.ButtonStyle.secondary)
    async def annuler(self,i,b): await i.response.edit_message(content='Achat annulé.',embed=None,view=None)

class ChoixObjet(discord.ui.Select):
    def __init__(self):
        opts=[discord.SelectOption(label=nom.split(' ',1)[1],value=code,description=f'{prix} flocons — {desc}'[:100],emoji=nom.split(' ',1)[0]) for code,(nom,prix,desc) in OBJETS.items()]
        super().__init__(placeholder='Choisis un objet…',options=opts,custom_id='malfred:choix_objet')
    async def callback(self,i):
        code=self.values[0];nom,prix,desc=OBJETS[code]
        await i.response.send_message(embed=discord.Embed(title=nom,description=f'{desc}\n\n**Prix : {prix} ❄️**\nConfirmer ?',color=discord.Color.gold()),view=ConfirmerAchat(code),ephemeral=True)

class BoutiqueView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None);self.add_item(ChoixObjet())
    @discord.ui.button(label='Inventaire',emoji=button_emoji('machiavelique'),style=discord.ButtonStyle.secondary,custom_id='malfred:boutique:inventaire',row=1)
    async def inventaire(self,i,b): await i.response.send_message(embed=inventaire_embed(i.user),view=InventaireView(),ephemeral=True)
    @discord.ui.button(label='Mes flocons',emoji=button_emoji('flocon'),style=discord.ButtonStyle.secondary,custom_id='malfred:boutique:flocons',row=1)
    async def flocons(self,i,b): await i.response.send_message(f'❄️ Tu as **{solde(i.user.id)} flocons**.',ephemeral=True)

class InventaireView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label='Utiliser la boule à neige',emoji=button_emoji('flocon'),style=discord.ButtonStyle.primary,custom_id='malfred:inventaire:boule')
    async def boule(self,i,b):
        msg,ok=activer(i.user.id,'boule')
        if not ok: return await i.response.send_message(msg,ephemeral=True)
        await i.response.defer(ephemeral=True)
        await publier(i,'🔮 RENCONTRE IMPROBABLE',msg,discord.Color.purple(),'rencontre')
        await i.followup.send('🔮 Rencontre enregistrée !',ephemeral=True)

class AccueilView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label='Cadeaux',emoji=button_emoji('amoureux'),style=discord.ButtonStyle.success,custom_id='malfred:menu:cadeaux')
    async def cadeaux(self,i,b): await i.response.send_message(embed=cadeaux_embed(),view=CadeauxView(),ephemeral=True)
    @discord.ui.button(label='Boutique',emoji=button_emoji('riche'),style=discord.ButtonStyle.primary,custom_id='malfred:menu:boutique')
    async def boutique(self,i,b): await i.response.send_message(embed=boutique_embed(),view=BoutiqueView(),ephemeral=True)
    @discord.ui.button(label='Inventaire',emoji=button_emoji('machiavelique'),style=discord.ButtonStyle.secondary,custom_id='malfred:menu:inventaire')
    async def inventaire(self,i,b): await i.response.send_message(embed=inventaire_embed(i.user),view=InventaireView(),ephemeral=True)
    @discord.ui.button(label='Classement',emoji=button_emoji('riche'),style=discord.ButtonStyle.secondary,custom_id='malfred:menu:classement')
    async def classement(self,i,b): await i.response.send_message(embed=classement_embed())
    @discord.ui.button(label='Mes flocons',emoji=button_emoji('flocon'),style=discord.ButtonStyle.secondary,custom_id='malfred:menu:flocons',row=1)
    async def flocons(self,i,b): await i.response.send_message(f'❄️ Tu as **{solde(i.user.id)} flocons**.',ephemeral=True)

@bot.tree.command(name='malfred',description='Ouvre le menu interactif de Malfred 🎄')
async def cmd_malfred(i:discord.Interaction): await i.response.send_message(embed=accueil_embed(),view=AccueilView())
@bot.tree.command(name='cadeau',description='Choisis ton cadeau piégé du jour 🎁')
async def cmd_cadeau(i:discord.Interaction): await i.response.send_message(embed=cadeaux_embed(),view=CadeauxView(),ephemeral=True)
@bot.tree.command(name='boutique',description='Visite la boutique douteuse de Malfred 🛒')
async def cmd_boutique(i:discord.Interaction): await i.response.send_message(embed=boutique_embed(),view=BoutiqueView(),ephemeral=True)
@bot.tree.command(name='inventaire',description='Consulte tes objets 🎒')
async def cmd_inventaire(i:discord.Interaction): await i.response.send_message(embed=inventaire_embed(i.user),view=InventaireView(),ephemeral=True)
@bot.tree.command(name='flocons',description='Consulte ton solde de flocons ❄️')
async def cmd_flocons(i:discord.Interaction): await i.response.send_message(f'❄️ Tu as **{solde(i.user.id)} flocons**.',ephemeral=True)
@bot.tree.command(name='classement',description='Découvre les plus riches du pôle Nord 🏆')
async def cmd_classement(i:discord.Interaction): await i.response.send_message(embed=classement_embed())
@bot.tree.command(name='rencontre',description='Utilise ta boule à neige 🔮')
async def cmd_rencontre(i:discord.Interaction):
    msg,ok=activer(i.user.id,'boule')
    await i.response.send_message(msg,ephemeral=True)
    if ok: await publier(i,'🔮 RENCONTRE IMPROBABLE',msg,discord.Color.purple(),'rencontre')

def staff(i): return i.user.id in STAFF_IDS or (isinstance(i.user,discord.Member) and i.user.guild_permissions.manage_guild)
@bot.tree.command(name='admin_reset_cadeau',description='Staff : réinitialise le cadeau du jour')
@app_commands.describe(joueur='Joueur à réinitialiser')
@app_commands.guild_only()
async def reset_cadeau(i:discord.Interaction,joueur:discord.User):
    if not staff(i): return await i.response.send_message('🔒 Réservé au staff.',ephemeral=True)
    with db_open() as db:
        joueur_id=joueur.id;db.execute('BEGIN IMMEDIATE');balance(db,joueur_id)
        db.execute('UPDATE joueurs SET dernier_cadeau=NULL WHERE user_id=?',(joueur_id,))
    await i.response.send_message(f'✅ Cadeau réinitialisé pour {joueur.mention}, flocons inchangés.',ephemeral=True)

class MarcheSelect(discord.ui.Select):
    def __init__(self,offres):
        opts=[discord.SelectOption(label=NOIR[k][0][:90],value=k,description=(NOIR[k][1]+' • '+NOIR[k][2])[:100]) for k in offres]
        super().__init__(placeholder='Choisir une marchandise…',options=opts,custom_id='malfred:marche:selection')
    async def callback(self,i):
        code=self.values[0]
        await i.response.send_message(f'**{NOIR[code][0]}**\n{NOIR[code][2]}\nCoût : {NOIR[code][1]}\nConfirmer ?',view=MarcheConfirm(code),ephemeral=True)
class MarcheConfirm(discord.ui.View):
    def __init__(self,code): super().__init__(timeout=120);self.code=code
    @discord.ui.button(label='Confirmer',style=discord.ButtonStyle.success)
    async def oui(self,i,b):
        if self.code=='noir_miroir':
            with db_open() as db:
                options=[discord.SelectOption(label=(OBJETS[k][0] if k in OBJETS else NOIR[k][0])[:90],value=k) for k,q in db.execute('SELECT objet,quantite FROM inventaire WHERE user_id=?',(i.user.id,)) if q>0 and k!='noir_miroir' and (k in OBJETS or k in NOIR)]
            if not options: return await i.response.edit_message(content='Tu n’as aucun objet à sacrifier.',embed=None,view=None)
            return await i.response.edit_message(content='Quel objet sacrifier ?',embed=None,view=SacrificeView(options))
        msg,ok=achat_noir(i.user.id,self.code)
        await i.response.edit_message(content=msg,embed=None,view=None)
        if ok: await publier(i,'🕯️ ACHAT CLANDESTIN',msg,discord.Color.dark_purple(),'achat')
class SacrificeSelect(discord.ui.Select):
    def __init__(self,options): super().__init__(placeholder='Objet à sacrifier',options=options)
    async def callback(self,i):
        msg,ok=achat_noir(i.user.id,'noir_miroir',self.values[0])
        await i.response.edit_message(content=msg,embed=None,view=None)
        if ok: await publier(i,'🕯️ ÉCHANGE CLANDESTIN',msg,discord.Color.dark_purple(),'sacrifice')
class SacrificeView(discord.ui.View):
    def __init__(self,options): super().__init__(timeout=120);self.add_item(SacrificeSelect(options))
class MarcheView(discord.ui.View):
    def __init__(self,offres): super().__init__(timeout=300);self.add_item(MarcheSelect(offres))

@bot.tree.command(name='marche',description='Voir le Marché Noir surprise de Malfred')
async def cmd_marche(i:discord.Interaction):
    with db_open() as db: marche=marche_actuel(db)
    if not marche: return await i.response.send_message('🕯️ Le Marché Noir est fermé.',ephemeral=True)
    mid,fin,offres=marche;codes=offres.split(',')
    e=discord.Embed(title=f"{E['machiavelique']} MALFRED ET SON MARCHÉ NOIR",description='Stock illimité • 2 achats par joueur par ouverture\nFerme à '+fin+' (heure suisse)\n\n'+'\n'.join(f'**{NOIR[k][0]}** — {NOIR[k][1]}\n{NOIR[k][2]}' for k in codes),color=discord.Color.dark_purple())
    await i.response.send_message(embed=image(e,'marche'),view=MarcheView(codes),ephemeral=True)

@bot.tree.command(name='activer',description='Activer manuellement un objet de ton inventaire')
@app_commands.describe(objet='Code affiché dans /inventaire')
async def cmd_activer(i:discord.Interaction,objet:str):
    code=objet.strip().lower()
    msg,ok=activer(i.user.id,code) if code in OBJETS or code in NOIR else ('Objet inconnu.',False)
    await i.response.send_message(msg,ephemeral=True)
    if ok: await publier(i,'🎒 OBJET ACTIVÉ',msg,discord.Color.purple(),'activation')

@bot.tree.command(name='miroir_voir',description='Prévoir un cadeau avec ton miroir')
@app_commands.describe(choix='1 Friandise, 2 Coffre, 3 Pacte')
async def cmd_miroir(i:discord.Interaction,choix:int):
    if choix not in CADEAUX: return await i.response.send_message('Choisis 1, 2 ou 3.',ephemeral=True)
    uid=i.user.id
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE');balance(db,uid);activer_row(db,uid)
        if not quantite(db,uid,'noir_miroir'): msg='Tu ne possèdes pas de miroir.'
        elif db.execute('SELECT dernier_cadeau FROM joueurs WHERE user_id=?',(uid,)).fetchone()[0]==jour(): msg='Tu as déjà ouvert ton cadeau.'
        elif db.execute('SELECT 1 FROM etat_marche WHERE cle=?',(f'miroir:{uid}',)).fetchone(): msg='Tu as déjà une prévision active.'
        else:
            chance=CADEAUX[choix][0]
            trefle=db.execute('SELECT trefle FROM activations WHERE user_id=?',(uid,)).fetchone()[0]
            victoire=random.randint(1,100)<=min(100,chance+(15 if trefle else 0))
            consommer(db,uid,'noir_miroir')
            db.execute('INSERT INTO etat_marche(cle,valeur) VALUES (?,?)',(f'miroir:{uid}',f'{choix}:'+('gain' if victoire else 'perte')))
            msg=f'🪞 Pour **{CADEAUX[choix][3]}**, le miroir annonce **'+('un gain' if victoire else 'une perte')+'**. Ouvre ce cadeau ou renonce.'
    await i.response.send_message(msg,ephemeral=True)

@bot.tree.command(name='renoncer_cadeau',description='Renoncer après consultation du miroir')
async def cmd_renoncer(i:discord.Interaction):
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE');key=f'miroir:{i.user.id}'
        if not db.execute('SELECT 1 FROM etat_marche WHERE cle=?',(key,)).fetchone(): msg='Tu n’as pas de prévision active.'
        else:
            balance(db,i.user.id)
            db.execute('UPDATE joueurs SET dernier_cadeau=? WHERE user_id=?',(jour(),i.user.id))
            db.execute('DELETE FROM etat_marche WHERE cle=?',(key,))
            msg='🪞 Tu renonces au cadeau du jour.'
    await i.response.send_message(msg,ephemeral=True)

@bot.tree.command(name='rejouer',description='Utiliser le sablier pour rejouer le cadeau du jour')
async def cmd_rejouer(i:discord.Interaction):
    uid=i.user.id
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE');actuel=balance(db,uid)
        tirage=db.execute('SELECT jour,choix,solde_avant,resultat,rejoue FROM tirages WHERE user_id=?',(uid,)).fetchone()
        if not tirage or tirage[0]!=jour() or tirage[4]: msg='⌛ Aucun cadeau du jour à rejouer, ou sablier déjà utilisé.';ok=False
        elif not quantite(db,uid,'noir_sablier'): msg='Tu n’as pas de sablier.';ok=False
        else:
            _,choix,avant,apres,_=tirage
            chance,gains,pertes,nom=CADEAUX[choix]
            victoire=random.randint(1,100)<=chance
            montant=random.randint(*(gains if victoire else pertes))
            diff=montant if victoire else -montant
            nouveau=max(0,actuel-(apres-avant)+diff)
            db.execute('UPDATE joueurs SET flocons=? WHERE user_id=?',(nouveau,uid))
            db.execute('UPDATE tirages SET rejoue=1,resultat=?,montant=? WHERE user_id=?',(nouveau,diff,uid))
            consommer(db,uid,'noir_sablier')
            msg=f'{nom} : **{diff:+d} ❄️** sur le second tirage. Solde : **{nouveau} ❄️**.';ok=True
    await i.response.send_message('⌛ Résultat publié !' if ok else msg,ephemeral=True)
    if ok: await publier(i,'⌛ LE SABLIER A PARLÉ',msg,discord.Color.gold(),'activation')

@bot.tree.command(name='admin_ouvrir_marche',description='Staff : ouvrir le Marché Noir pour six heures')
@app_commands.guild_only()
async def admin_ouvrir_marche(i:discord.Interaction):
    if not staff(i): return await i.response.send_message('Réservé au staff.',ephemeral=True)
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE')
        if marche_actuel(db): msg='Le marché est déjà ouvert.';ok=False
        else:
            debut=now();fin=debut+timedelta(hours=6)
            offres=','.join(random.sample(list(NOIR),4))
            db.execute('INSERT INTO marches(debut,fin,offres) VALUES (?,?,?)',(debut.isoformat(),fin.isoformat(),offres))
            msg='🕯️ Marché ouvert pendant six heures ! `/marche`';ok=True
    await i.response.send_message(msg,ephemeral=True)
    if ok: await publier(i,'🕯️ MARCHÉ NOIR OUVERT',msg,discord.Color.dark_purple(),'marche')

# Quatre événements gratuits et indépendants des boutiques / cadeaux.
EVENEMENTS={5:('hotte','🎁 La Hotte des Regrets'),12:('casino','🎰 Le Casino du Lutin'),19:('tempete','❄️ La Tempête des Flocons'),24:('finale','👑 Le Dernier Coup de Malfred')}

def evenement_actuel():
    t=now()
    if t.month!=12 or t.day not in EVENEMENTS or t.year!=2026: return None
    if t.day==24 and t.hour>=21: return None
    return EVENEMENTS[t.day]

def jouer_evenement(uid,choix):
    ev=evenement_actuel()
    if not ev: return '🎪 Aucun grand événement ouvert actuellement.',False,None
    code,nom=ev
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE');avant=balance(db,uid)
        if db.execute('SELECT 1 FROM participations_evenements WHERE user_id=? AND evenement=?',(uid,code)).fetchone(): return 'Tu as déjà participé à cet événement.',False,None
        if code=='hotte':
            if choix not in (1,2,3): return 'Choisis un des trois sacs.',False,None
            # Chaque sac donne un tirage indépendant, non annoncé à l'avance.
            delta=random.choice([-5,-3,0,3,6,9,12])
            detail=f'Sac n°{choix} ouvert !'
        elif code=='casino':
            if choix!=1: return 'Actionne la machine à sous.',False,None
            symbols=[random.choice(['🍒','🔔','❄️','🦆']) for _ in range(3)]
            delta=18 if len(set(symbols))==1 else 6 if len(set(symbols))==2 else random.choice([-3,0,2])
            detail=' '.join(symbols)
        elif code=='tempete':
            if choix not in (1,2): return 'Choisis abri ou tempête.',False,None
            delta=3 if choix==1 else random.choice([-8,-5,8,12,16])
            detail='Tu t’es abrité.' if choix==1 else 'Tu as couru dans la tempête !'
        else:
            if choix not in (1,2): return 'Choisis sécurité ou dernier pari.',False,None
            delta=4 if choix==1 else random.choice([-12,-8,12,18,24])
            detail='Tu as sécurisé ton bonus.' if choix==1 else 'Tu as tenté le tout pour le tout !'
        apres=max(0,avant+delta)
        db.execute('UPDATE joueurs SET flocons=? WHERE user_id=?',(apres,uid))
        db.execute('INSERT INTO participations_evenements(user_id,evenement) VALUES (?,?)',(uid,code))
    return f'**{nom}**\n{detail}\nRésultat : **{apres-avant:+d} ❄️**\nNouveau solde : **{apres} ❄️**.',True,code

class EvenementView(discord.ui.View):
    def __init__(self,code):
        super().__init__(timeout=300)
        if code=='hotte': labels=['Sac 1','Sac 2','Sac 3']
        elif code=='casino': labels=['Actionner la machine']
        elif code=='tempete': labels=['Se mettre à l’abri','Courir dans la neige']
        else: labels=['Sécuriser le bonus','Tenter le grand pari']
        for idx,label in enumerate(labels,1):
            btn=discord.ui.Button(label=label,style=discord.ButtonStyle.primary if idx>1 else discord.ButtonStyle.success)
            async def callback(i,n=idx):
                msg,ok,scene=jouer_evenement(i.user.id,n)
                await i.response.send_message('🎪 Ton résultat est publié !' if ok else msg,ephemeral=True)
                if ok: await publier(i,'🎪 GRAND ÉVÉNEMENT',msg,discord.Color.gold(),scene)
            btn.callback=callback
            self.add_item(btn)

@bot.tree.command(name='evenement',description='Participer au grand événement du jour')
async def cmd_evenement(i:discord.Interaction):
    ev=evenement_actuel()
    if not ev: return await i.response.send_message('🎪 Aucun grand événement ouvert aujourd’hui.',ephemeral=True)
    code,nom=ev
    e=discord.Embed(title=nom,description='Une participation gratuite par joueur, indépendante du cadeau quotidien et des boutiques. Choisis ci-dessous !',color=discord.Color.gold())
    await i.response.send_message(embed=image(e,code),view=EvenementView(code),ephemeral=True)

async def entretien_marche():
    await bot.wait_until_ready()
    while not bot.is_closed():
        annonce=False;fermeture=False
        try:
            with db_open() as db:
                db.execute('BEGIN IMMEDIATE')
                t=now();d=t.date().isoformat()
                if MARKET_CHANNEL_ID and t.year==2026 and t.month==12 and 1<=t.day<=24 and t.hour>=10:
                    fait=db.execute('SELECT 1 FROM etat_marche WHERE cle=?',(f'tirage:{d}',)).fetchone()
                    if not fait:
                        db.execute('INSERT INTO etat_marche(cle,valeur) VALUES (?,?)',(f'tirage:{d}','1'))
                        n=db.execute('SELECT COUNT(*) FROM marches').fetchone()[0]
                        last=db.execute('SELECT fin FROM marches ORDER BY id DESC LIMIT 1').fetchone()
                        eligible=n<4 and (not last or (t-datetime.fromisoformat(last[0])).total_seconds()>=48*3600)
                        reste=24-t.day
                        chance=.19 if n<2 else .07
                        if n<2 and reste<=max(0,(2-n)*3): chance=1
                        if eligible and random.random()<chance:
                            fin=t+timedelta(hours=6)
                            db.execute('INSERT INTO marches(debut,fin,offres) VALUES (?,?,?)',(t.isoformat(),fin.isoformat(),','.join(random.sample(list(NOIR),4))))
                            annonce=True
                # Signaler la fermeture une seule fois, après expiration.
                last=db.execute('SELECT id,fin FROM marches ORDER BY id DESC LIMIT 1').fetchone()
                if last and datetime.fromisoformat(last[1])<=t:
                    cle=f'fermeture:{last[0]}'
                    if not db.execute('SELECT 1 FROM etat_marche WHERE cle=?',(cle,)).fetchone():
                        db.execute('INSERT INTO etat_marche(cle,valeur) VALUES (?,?)',(cle,'1'))
                        fermeture=True
                for uid,echeance,montant in db.execute('SELECT user_id,echeance,montant FROM dettes WHERE echeance<=?',(d,)).fetchall():
                    avant=balance(db,uid);paye=min(avant,montant)
                    db.execute('UPDATE joueurs SET flocons=flocons-? WHERE user_id=?',(paye,uid))
                    db.execute('DELETE FROM dettes WHERE user_id=? AND echeance=?',(uid,echeance))
                    if montant>paye:
                        demain=(t.date()+timedelta(days=1)).isoformat()
                        db.execute('INSERT INTO dettes(user_id,echeance,montant) VALUES (?,?,?) ON CONFLICT(user_id,echeance) DO UPDATE SET montant=montant+excluded.montant',(uid,demain,montant-paye))
                # Bonus du canard doré le 24, attribué une seule fois.
                if t.year==2026 and t.month==12 and t.day==24:
                    for (uid,) in db.execute("SELECT user_id FROM inventaire WHERE objet='noir_canard' AND quantite>0").fetchall():
                        cle=f'canard_bonus:{uid}'
                        if not db.execute('SELECT 1 FROM etat_marche WHERE cle=?',(cle,)).fetchone():
                            balance(db,uid)
                            db.execute('UPDATE joueurs SET flocons=flocons+5 WHERE user_id=?',(uid,))
                            db.execute('INSERT INTO etat_marche(cle,valeur) VALUES (?,?)',(cle,'1'))
            if MARKET_CHANNEL_ID:
                salon=bot.get_channel(MARKET_CHANNEL_ID)
                if salon:
                    if annonce: await salon.send(f"{E['machiavelique']} **LE MARCHÉ NOIR EST OUVERT !** Six heures pour négocier. `/marche`")
                    if fermeture: await salon.send(f"{E['moquerie']} **MARCHÉ NOIR FERMÉ !** Malfred s'est enfui avec sa caisse.")
        except Exception: logging.exception('Entretien du Marché Noir')
        await asyncio.sleep(900)

async def setup_hook():
    bot.add_view(AccueilView());bot.add_view(CadeauxView());bot.add_view(BoutiqueView());bot.add_view(InventaireView())
    asyncio.create_task(entretien_marche())
    if GUILD_ID:
        guild=discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        result=await bot.tree.sync(guild=guild)
    else: result=await bot.tree.sync()
    logging.info('%s commandes synchronisées',len(result))
bot.setup_hook=setup_hook

@bot.event
async def on_ready(): logging.info('🎄 Malfred connecté : %s',bot.user)

@bot.tree.error
async def on_slash_error(i:discord.Interaction,error:app_commands.AppCommandError):
    logging.exception('Erreur commande : %r',error)
    try:
        if i.response.is_done(): await i.followup.send('⚠️ Malfred a trébuché dans une congère.',ephemeral=True)
        else: await i.response.send_message('⚠️ Malfred a trébuché dans une congère.',ephemeral=True)
    except discord.HTTPException: pass

if __name__=='__main__':
    init_db()
    token=os.getenv('DISCORD_TOKEN')
    if not token: raise RuntimeError('Variable DISCORD_TOKEN manquante.')
    bot.run(token)
