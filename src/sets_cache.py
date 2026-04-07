"""Cache local para información de ediciones (sets)."""

from src.base_cache import BaseCache


# Datos iniciales para pre-poblar el cache en la primera ejecución.
# Evita que el cache empiece vacío y reduce las llamadas a la API.
# La API sigue siendo la fuente de verdad — estos datos son solo semilla.
_SEED_SETS = {
    'base1': 'Base Set', 'base2': 'Jungle', 'basep': 'Wizards Black Star Promos',
    'base3': 'Fossil', 'base4': 'Base Set 2', 'base5': 'Team Rocket',
    'gym1': 'Gym Heroes', 'gym2': 'Gym Challenge',
    'neo1': 'Neo Genesis', 'neo2': 'Neo Discovery', 'neo3': 'Neo Revelation', 'neo4': 'Neo Destiny',
    'lc': 'Legendary Collection', 'ecard1': 'Expedition Base Set', 'ecard2': 'Aquapolis', 'ecard3': 'Skyridge',
    'ex1': 'Ruby & Sapphire', 'ex2': 'Sandstorm', 'ex3': 'Dragon', 'ex4': 'Team Magma vs Team Aqua',
    'ex5': 'Hidden Legends', 'ex6': 'FireRed & LeafGreen', 'ex7': 'Team Rocket Returns',
    'ex8': 'Deoxys', 'ex9': 'Emerald', 'ex10': 'Unseen Forces', 'ex11': 'Delta Species',
    'ex12': 'Legend Maker', 'ex13': 'Holon Phantoms', 'ex14': 'Crystal Guardians',
    'ex15': 'Dragon Frontiers', 'ex16': 'Power Keepers',
    'dp1': 'Diamond & Pearl', 'dpp': 'DP Black Star Promos', 'dp2': 'Mysterious Treasures',
    'dp3': 'Secret Wonders', 'dp4': 'Great Encounters', 'dp5': 'Majestic Dawn',
    'dp6': 'Legends Awakened', 'dp7': 'Stormfront',
    'pl1': 'Platinum', 'pl2': 'Rising Rivals', 'pl3': 'Supreme Victors', 'pl4': 'Arceus',
    'hgss1': 'HeartGold SoulSilver', 'hgssp': 'HGSS Black Star Promos',
    'hgss2': 'Unleashed', 'hgss3': 'Undaunted', 'hgss4': 'Triumphant', 'col1': 'Call of Legends',
    'bw1': 'Black & White', 'bwp': 'BW Black Star Promos', 'bw2': 'Emerging Powers',
    'bw3': 'Noble Victories', 'bw4': 'Next Destinies', 'bw5': 'Dark Explorers',
    'bw6': 'Dragons Exalted', 'dv1': 'Dragon Vault', 'bw7': 'Boundaries Crossed',
    'bw8': 'Plasma Storm', 'bw9': 'Plasma Freeze', 'bw10': 'Plasma Blast', 'bw11': 'Legendary Treasures',
    'xyp': 'XY Black Star Promos', 'xy1': 'XY', 'xy2': 'Flashfire', 'xy3': 'Furious Fists',
    'xy4': 'Phantom Forces', 'xy5': 'Primal Clash', 'xy6': 'Roaring Skies', 'xy7': 'Ancient Origins',
    'xy8': 'BREAKthrough', 'xy9': 'BREAKpoint', 'g1': 'Generations',
    'xy10': 'Fates Collide', 'xy11': 'Steam Siege', 'xy12': 'Evolutions',
    'sm1': 'Sun & Moon', 'smp': 'SM Black Star Promos', 'sm2': 'Guardians Rising',
    'sm3': 'Burning Shadows', 'sm3.5': 'Shining Legends', 'sm4': 'Crimson Invasion',
    'sm5': 'Ultra Prism', 'sm6': 'Forbidden Light', 'sm7': 'Celestial Storm',
    'sm7.5': 'Dragon Majesty', 'sm8': 'Lost Thunder', 'sm9': 'Team Up',
    'sm10': 'Unbroken Bonds', 'sm11': 'Unified Minds', 'sm115': 'Hidden Fates', 'sm12': 'Cosmic Eclipse',
    'swshp': 'SWSH Black Star Promos', 'swsh1': 'Sword & Shield', 'swsh2': 'Rebel Clash',
    'swsh3': 'Darkness Ablaze', "swsh3.5": "Champion's Path", 'swsh4': 'Vivid Voltage',
    'swsh4.5': 'Shining Fates', 'swsh5': 'Battle Styles', 'swsh6': 'Chilling Reign',
    'swsh7': 'Evolving Skies', 'cel25': 'Celebrations', 'swsh8': 'Fusion Strike',
    'swsh9': 'Brilliant Stars', 'swsh10': 'Astral Radiance', 'swsh10.5': 'Pokémon GO',
    'swsh11': 'Lost Origin', 'swsh12': 'Silver Tempest', 'swsh12.5': 'Crown Zenith',
    'svp': 'SVP Black Star Promos', 'sv01': 'Scarlet & Violet', 'sv02': 'Paldea Evolved',
    'sv03': 'Obsidian Flames', 'sv03.5': '151', 'sv04': 'Paradox Rift', 'sv04.5': 'Paldean Fates',
    'sv05': 'Temporal Forces', 'sv06': 'Twilight Masquerade', 'sv06.5': 'Shrouded Fable',
    'sv07': 'Stellar Crown', 'sv08': 'Surging Sparks', 'sv08.5': 'Prismatic Evolutions',
    'sv09': 'Journey Together', 'sv10': 'Destined Rivals',
    'sv10.5b': 'Black Bolt', 'sv10.5w': 'White Flare',
    'A1': 'Genetic Apex', 'P-A': 'Promos-A', 'A1a': 'Mythical Island',
    'A2': 'Space-Time Smackdown', 'A2a': 'Triumphant Light', 'A2b': 'Shining Revelry',
    'A3': 'Celestial Guardians', 'A3a': 'Extradimensional Crisis', 'A3b': 'Eevee Grove',
    'A4': 'Wisdom of Sea and Sky', 'A4a': 'Secluded Springs',
    'me01': 'Mega Evolution', 'mep': 'MEP Black Star Promos', 'B1': 'Mega Rising', 'me02': 'Phantasmal Flames',
}


class SetsCache(BaseCache):
    """
    Cache de sets TCG.

    Cada entrada tiene la forma: { "sv01": "Scarlet & Violet" }

    Al inicializarse, pre-popula el cache con datos semilla si está vacío,
    para que la primera ejecución no dependa completamente de la API.
    La API sigue siendo la fuente de verdad: sus datos sobreescriben la semilla.
    """

    def __init__(self):
        super().__init__(cache_file='sets_cache.json')
        self._seed_if_empty()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def set(self, set_id: str, set_name: str) -> None:
        """Guarda el nombre de un set."""
        self.cache[set_id] = set_name
        self._save_cache()

    def bulk_set(self, sets_dict: dict) -> None:
        """Guarda múltiples sets de una vez (un solo write al disco)."""
        self.cache.update(sets_dict)
        self._save_cache()

    def get_all(self) -> dict:
        """Retorna todos los sets en el cache."""
        return dict(self.cache)

    def get_name(self, set_id: str) -> str:
        """
        Retorna el nombre de un set, o el ID en mayúsculas como fallback.

        Preferir este método sobre get() cuando se necesita siempre
        un string legible para mostrar en la UI.
        """
        return self.cache.get(set_id) or set_id.upper()

    def get_id_by_name(self, display_name: str) -> str:
        """
        Busca el set_id a partir de su nombre para mostrar.
        """
        for set_id, name in self.cache.items():
            if isinstance(name, str) and name == display_name:
                return set_id
        return display_name

    def search(self, query: str) -> dict:
        """Busca sets cuyo ID o nombre contengan el query."""
        q = query.lower()
        return {
            set_id: name
            for set_id, name in self.cache.items()
            if isinstance(name, str) and (q in set_id.lower() or q in name.lower())
        }

    # ------------------------------------------------------------------
    # Mapa PTCGL/Limitless abbreviation → TCGdex set_id
    # Se guarda dentro del cache bajo la clave especial "_ptcgl_map"
    # ------------------------------------------------------------------

    _PTCGL_MAP_KEY = '_ptcgl_map'

    def get_ptcgl_map(self) -> dict:
        """Retorna el mapa {ABBREV: set_id} o {} si no está construido."""
        return self.cache.get(self._PTCGL_MAP_KEY) or {}

    def has_ptcgl_map(self) -> bool:
        """Indica si el mapa ya fue construido."""
        return bool(self.cache.get(self._PTCGL_MAP_KEY))

    def set_ptcgl_map(self, mapping: dict) -> None:
        """Guarda el mapa de abreviaciones y persiste."""
        self.cache[self._PTCGL_MAP_KEY] = mapping
        self._save_cache()

    def resolve_abbrev(self, abbrev: str) -> str | None:
        """
        Dado un código abreviado de Limitless/PTCGL (ej. 'MEG'),
        retorna el TCGdex set_id (ej. 'me01'), o None si no está en el mapa.
        """
        return self.get_ptcgl_map().get(abbrev.upper())

    # ------------------------------------------------------------------
    # Método interno
    # ------------------------------------------------------------------

    def _seed_if_empty(self) -> None:
        """
        Pre-popula el cache con datos semilla si está vacío.
        No sobreescribe entradas existentes para no pisar datos de la API.
        """
        if not self.cache:
            self.cache.update(_SEED_SETS)
            self._save_cache()