"""
Controlador del inventario.

Esta capa intermedia entre la GUI y los servicios de datos se encarga de:
- Orquestar las operaciones del inventario (cargar, enriquecer, filtrar)
- Coordinar DataManager, TCGdexService y los caches
- Mantener el estado del inventario enriquecido

La GUI solo llama métodos de este controlador y no sabe nada de
cómo funciona la API, el cache o el almacenamiento.
"""

import asyncio
import pandas as pd

from src.data_manager import DataManager
from src.api_service import TCGdexService
from src.card_cache import CardCache
from src.sets_cache import SetsCache


class InventoryController:
    """Orquesta todas las operaciones del inventario."""

    BATCH_SIZE = 10  # Cartas por lote al consultar la API

    def __init__(self):
        self.data_manager = DataManager()
        self.api_service = TCGdexService()
        self.card_cache = CardCache()
        self.sets_cache = SetsCache()

        # Estado interno del inventario
        self.inventory_df: pd.DataFrame = pd.DataFrame()
        self.enriched_df: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Carga y enriquecimiento
    # ------------------------------------------------------------------

    def load_inventory(self) -> pd.DataFrame:
        """Carga el inventario crudo desde el almacenamiento."""
        self.inventory_df = self.data_manager.load_inventory()
        self.enriched_df = None  # Invalidar enriquecimiento anterior
        return self.inventory_df

    async def enrich_inventory(self) -> pd.DataFrame:
        """
        Enriquece el inventario con nombres de cartas y ediciones.

        Primero consulta el cache local. Solo llama a la API para las
        cartas y sets que no están en cache todavía.

        Returns:
            DataFrame enriquecido con columnas: card_name, edition_name,
            card_local_number.
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

        self.enriched_df = enriched
        return enriched

    # ------------------------------------------------------------------
    # Operaciones CRUD
    # ------------------------------------------------------------------

    def add_card(self, card_data: dict) -> int:
        """
        Añade una carta al inventario.

        Returns:
            ID asignado a la nueva carta.

        Raises:
            ValueError: Si los datos son inválidos.
        """
        self._validate_card_data(card_data)
        return self.data_manager.add_card(card_data)

    def update_card(self, card_id: int, card_data: dict) -> bool:
        """Actualiza una carta existente. Retorna True si tuvo éxito."""
        self._validate_card_data(card_data)
        return self.data_manager.update_card(card_id, card_data)

    def delete_card(self, card_id: int) -> bool:
        """Elimina una carta. Retorna True si tuvo éxito."""
        return self.data_manager.delete_card(card_id)

    def increment_count(self, card_id: int) -> bool:
        """Incrementa en 1 la cantidad de una carta."""
        if card_id not in self.inventory_df.index:
            return False
        row = self.inventory_df.loc[card_id]
        return self.data_manager.update_card(card_id, {
            **row.to_dict(),
            'count': row['count'] + 1
        })

    def decrement_count(self, card_id: int) -> tuple[bool, bool]:
        """
        Decrementa en 1 la cantidad de una carta.

        Returns:
            Tupla (éxito, llegó_a_cero). Si llegó a cero, la carta
            NO se elimina automáticamente — eso lo decide la GUI.
        """
        if card_id not in self.inventory_df.index:
            return False, False
        row = self.inventory_df.loc[card_id]
        new_count = row['count'] - 1
        if new_count <= 0:
            return True, True  # Llegó a cero, GUI decide si eliminar
        return self.data_manager.update_card(card_id, {
            **row.to_dict(),
            'count': new_count
        }), False

    # ------------------------------------------------------------------
    # Filtrado
    # ------------------------------------------------------------------

    def apply_filters(self, filters: dict) -> pd.DataFrame:
        """
        Aplica filtros al inventario enriquecido (o crudo si no hay).

        Args:
            filters: Dict con claves opcionales:
                - 'name': str — busca en card_name o tcg_card_id
                - 'set': str — nombre display de la edición (ej: 'sv01')
                - 'language': str
                - 'foil': str
                - 'condition': str
                - 'stamp': str

        Returns:
            DataFrame filtrado.
        """
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
            # La GUI pasa el nombre display (ej: "Scarlet & Violet").
            # Hay que convertirlo al set_id (ej: "sv01") para filtrar el DataFrame.
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
                    new_data[tcg_id] = {
                        'name': getattr(card, 'name', 'N/A'),
                        'set_name': getattr(card.set, 'name', 'N/A') if hasattr(card, 'set') else 'N/A',
                        'local_id': getattr(card, 'localId', 'N/A'),
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
        """Extrae el set_id de un card_id y busca su nombre en el cache."""
        if '-' not in tcg_card_id:
            return 'N/A'
        set_id = tcg_card_id.split('-')[0]
        return self.sets_cache.get(set_id) or 'N/A'

    def _validate_card_data(self, card_data: dict) -> None:
        """
        Valida que los datos de una carta sean correctos.

        Raises:
            ValueError: Con un mensaje descriptivo si algo falla.
        """
        tcg_id = card_data.get('tcg_card_id', '').strip()
        if not tcg_id:
            raise ValueError("El ID Global no puede estar vacío.")

        count = card_data.get('count', 0)
        if not isinstance(count, int) or count <= 0:
            raise ValueError("La cantidad debe ser un número entero mayor a 0.")