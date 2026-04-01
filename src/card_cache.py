"""Cache local para información de cartas individuales."""

from datetime import datetime
from src.base_cache import BaseCache


class CardCache(BaseCache):
    """
    Cache de cartas TCG.

    Cada entrada tiene la forma:
        {
            "name": "Pikachu",
            "set_name": "Scarlet & Violet",
            "local_id": "025",
            "updated_at": "2025-12-11T19:17:37"
        }
    """

    def __init__(self):
        super().__init__(cache_file='card_cache.json')

    def set(self, tcg_card_id: str, card_info: dict) -> None:
        """
        Guarda la información de una carta, añadiendo timestamp automáticamente.

        Args:
            tcg_card_id: ID de la carta en TCGdex (ej: 'sv01-025')
            card_info: Dict con {name, set_name, local_id}
        """
        card_info['updated_at'] = datetime.now().isoformat()
        self.cache[tcg_card_id] = card_info
        self._save_cache()

    def bulk_set(self, cards_dict: dict) -> None:
        """
        Guarda múltiples cartas de una vez (un solo write al disco).

        Args:
            cards_dict: Dict de {tcg_card_id: {name, set_name, local_id}}
        """
        timestamp = datetime.now().isoformat()
        for tcg_id, info in cards_dict.items():
            info['updated_at'] = timestamp
            self.cache[tcg_id] = info
        self._save_cache()