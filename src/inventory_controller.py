"""
Controlador del inventario.
"""

import asyncio
import pandas as pd

from src.data_manager import DataManager
from src.api_service import TCGdexService
from src.card_cache import CardCache
from src.sets_cache import SetsCache


class InventoryController:
    """Orquesta todas las operaciones del inventario."""

    BATCH_SIZE = 10

    def __init__(self):
        self.data_manager = DataManager()
        self.api_service = TCGdexService()
        self.card_cache = CardCache()
        self.sets_cache = SetsCache()

        self.inventory_df: pd.DataFrame = pd.DataFrame()
        self.enriched_df: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Carga y enriquecimiento
    # ------------------------------------------------------------------

    def load_inventory(self) -> pd.DataFrame:
        """Carga el inventario crudo desde el almacenamiento."""
        self.inventory_df = self.data_manager.load_inventory()
        self.enriched_df = None
        return self.inventory_df

    async def enrich_inventory(self) -> pd.DataFrame:
        """
        Enriquece el inventario con nombres, ediciones, número local e image_url.
        Usa cache local; solo llama a la API para lo que falta.
        """
        if self.inventory_df.empty:
            return self.inventory_df

        await self._populate_card_cache()
        await self._populate_sets_cache()

        enriched = self.inventory_df.copy()
        enriched['card_name'] = enriched['tcg_card_id'].apply(
            lambda x: (self.card_cache.get(x) or {}).get('name', 'N/A')
        )
        enriched['card_local_number'] = enriched['tcg_card_id'].apply(
            lambda x: (self.card_cache.get(x) or {}).get('local_id', 'N/A')
        )
        enriched['edition_name'] = enriched['tcg_card_id'].apply(
            self._get_set_name_for_card
        )
        # image_url incluida en el enriquecimiento para evitar llamadas extra
        enriched['image_url'] = enriched['tcg_card_id'].apply(
            lambda x: (self.card_cache.get(x) or {}).get('image_url')
        )
        enriched['regulation_mark'] = enriched['tcg_card_id'].apply(
            lambda x: (self.card_cache.get(x) or {}).get('regulation_mark')
        )
        # Asegurar que available_count existe y es entero
        if 'available_count' not in enriched.columns:
            enriched['available_count'] = 0
        enriched['available_count'] = enriched['available_count'].fillna(0).astype(int)

        self.enriched_df = enriched
        return enriched

    # ------------------------------------------------------------------
    # Operaciones CRUD
    # ------------------------------------------------------------------

    def add_card(self, card_data: dict) -> int:
        self._validate_card_data(card_data)
        return self.data_manager.add_card(card_data)

    def update_card(self, card_id: int, card_data: dict) -> bool:
        self._validate_card_data(card_data)
        return self.data_manager.update_card(card_id, card_data)

    def delete_card(self, card_id: int) -> bool:
        return self.data_manager.delete_card(card_id)

    def increment_count(self, card_id: int) -> bool:
        if card_id not in self.inventory_df.index:
            return False
        row = self.inventory_df.loc[card_id]
        new_count = row['count'] + 1
        # available_count sube en 1 junto con count (mantener proporción)
        new_avail = int(row.get('available_count', 0) or 0) + 1
        return self.data_manager.update_card(card_id, {
            **row.to_dict(), 'count': new_count, 'available_count': new_avail
        })

    def decrement_count(self, card_id: int) -> tuple[bool, bool]:
        if card_id not in self.inventory_df.index:
            return False, False
        row = self.inventory_df.loc[card_id]
        new_count = row['count'] - 1
        if new_count < 0:
            return False, False  # No bajar de 0
        # available_count baja en 1 pero nunca por debajo de 0
        cur_avail = int(row.get('available_count', 0) or 0)
        new_avail = max(0, cur_avail - 1)
        return self.data_manager.update_card(card_id, {
            **row.to_dict(), 'count': new_count, 'available_count': new_avail
        }), False

    # ------------------------------------------------------------------
    # Filtrado
    # ------------------------------------------------------------------

    def apply_filters(self, filters: dict) -> pd.DataFrame:
        base = self.enriched_df if self.enriched_df is not None else self.inventory_df
        df = base.copy()

        name = filters.get('name', '').strip().lower()
        if name:
            if 'card_name' in df.columns:
                df = df[df['card_name'].str.lower().str.contains(name, na=False)]
            else:
                df = df[df['tcg_card_id'].str.lower().str.contains(name, na=False)]

        set_filter = filters.get('set', '').strip()
        if set_filter:
            set_id = self.sets_cache.get_id_by_name(set_filter)
            df = df[df['tcg_card_id'].str.startswith(set_id + '-', na=False)]

        language = filters.get('language', '').strip()
        if language:
            df = df[df['language'].str.upper() == language.upper()]

        foil = filters.get('foil', '').strip()
        if foil:
            df = df[df['foil_type'].str.contains(foil, case=False, na=False)]

        condition = filters.get('condition', '').strip()
        if condition:
            df = df[df['condition'].str.upper() == condition.upper()]

        stamp = filters.get('stamp', '').strip()
        if stamp:
            if stamp.lower() == 'none':
                df = df[df['stamp'].isna() | (df['stamp'].str.strip() == '') | (df['stamp'].str.lower() == 'none')]
            else:
                df = df[df['stamp'].str.contains(stamp, case=False, na=False)]

        if filters.get('available_only'):
            if 'available_count' in df.columns:
                df = df[df['available_count'].fillna(0).astype(int) > 0]

        return df

    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    async def _populate_card_cache(self) -> None:
        """Descarga desde la API las cartas que faltan en el cache."""
        unique_ids = self.inventory_df['tcg_card_id'].unique().tolist()
        missing = self.card_cache.get_missing_keys(unique_ids)

        if not missing:
            return

        new_data = {}
        for i in range(0, len(missing), self.BATCH_SIZE):
            batch = missing[i:i + self.BATCH_SIZE]
            tasks = [self.api_service.tcgdex.card.get(tcg_id) for tcg_id in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for tcg_id, card in zip(batch, results):
                if not isinstance(card, Exception):
                    image_base = getattr(card, 'image', None)
                    new_data[tcg_id] = {
                        'name':      getattr(card, 'name', 'N/A'),
                        'set_name':  getattr(card.set, 'name', 'N/A') if hasattr(card, 'set') else 'N/A',
                        'local_id':  getattr(card, 'localId', 'N/A'),
                        'image_url': f"{image_base}/high.png" if image_base else None,
                    }

        if new_data:
            self.card_cache.bulk_set(new_data)

    async def _populate_sets_cache(self) -> None:
        """Descarga desde la API los sets que faltan en el cache."""
        set_ids = self.inventory_df['tcg_card_id'].apply(
            lambda x: x.split('-')[0] if '-' in str(x) else ''
        ).unique()
        set_ids = [s for s in set_ids if s]
        missing = self.sets_cache.get_missing_keys(set_ids)

        if not missing:
            return

        new_sets = {}
        for set_id in missing:
            try:
                set_data = await self.api_service.tcgdex.set.get(set_id)
                new_sets[set_id] = getattr(set_data, 'name', set_id.upper())
            except Exception:
                new_sets[set_id] = set_id.upper()

        if new_sets:
            self.sets_cache.bulk_set(new_sets)

    def _get_set_name_for_card(self, tcg_card_id: str) -> str:
        if '-' not in tcg_card_id:
            return 'N/A'
        set_id = tcg_card_id.split('-')[0]
        return self.sets_cache.get(set_id) or 'N/A'

    def _validate_card_data(self, card_data: dict) -> None:
        tcg_id = card_data.get('tcg_card_id', '').strip()
        if not tcg_id:
            raise ValueError("El ID Global no puede estar vacío.")
        count = card_data.get('count', 0)
        if not isinstance(count, int) or count < 0:
            raise ValueError("La cantidad debe ser un número entero mayor o igual a 0.")
        available = card_data.get('available_count', 0)
        try:
            available = int(available)
        except (TypeError, ValueError):
            available = 0
        if available < 0:
            raise ValueError("La cantidad disponible no puede ser negativa.")
        if available > count:
            raise ValueError("La cantidad disponible no puede superar la cantidad total.")
        card_data['available_count'] = available