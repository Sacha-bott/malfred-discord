
"""Gestion des 23 illustrations de Malfred.

Les images sont stockées dans le dossier assets/ sur GitHub.

Variable Railway :
MALFRED_IMAGES_BASE_URL=https://raw.githubusercontent.com/Sacha-bott/malfred-discord/main

Le dépôt doit être public pour que Discord puisse afficher les images.
"""

import os

SCENES = {
    'accueil': 1,
    'cadeaux': 2,
    'boutique': 3,
    'inventaire': 4,
    'classement': 5,
    'gain': 6,
    'perte': 7,
    'jackpot': 8,
    'zero': 9,
    'marche': 10,
    'marche_ouverture': 10,
    'achat_noir': 11,
    'marche_fermeture': 12,
    'activation': 13,
    'rencontre': 14,
    'grand_evenement': 15,
    'finale': 16,
    'activation_refusee': 17,
    'pas_assez': 18,
    'sacrifice': 19,
    'dette': 19,
    'objet_mysterieux': 20,
    'hotte': 21,
    'casino': 22,
    'tempete': 23,

    # Alias utilisés par le bot
    'achat': 3,
    'deja': 2,
}


def image(embed, scene):
    """Ajoute une illustration à un embed Discord."""

    base = os.getenv(
        'MALFRED_IMAGES_BASE_URL', ''
    ).strip().rstrip('/')

    if not base.startswith(('https://', 'http://')):
        return embed

    numero = SCENES.get(scene)

    if numero is None:
        return embed

    url = f'{base}/assets/Malfred_{numero:02d}.jpeg'

    embed.set_image(url=url)

    return embed
