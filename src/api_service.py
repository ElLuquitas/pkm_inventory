"""Servicio para interactuar con la API de TCGdex."""

import asyncio
import pandas as pd
from tcgdexsdk import TCGdex, Query


class TCGdexService:
    """Maneja todas las interacciones con la API de TCGdex."""
    
    def __init__(self):
        self.tcgdex = TCGdex()
    
    async def search_by_card_name(self, inventory_df: pd.DataFrame, search_term: str):
        """
        Busca cartas en el inventario por nombre.
        
        Args:
            inventory_df: DataFrame del inventario
            search_term: Término de búsqueda
            
        Returns:
            Tupla (DataFrame de resultados, mensaje de estado)
        """
        try:
            # Buscar en la API
            card_resumes = await self.tcgdex.card.list(
                Query().contains("name", search_term)
            )
            
            if not card_resumes:
                return pd.DataFrame(), "No se encontraron cartas en la API."
            
            # Filtrar cartas que tenemos en inventario
            api_card_ids = {resume.id for resume in card_resumes}
            local_matches = inventory_df[
                inventory_df['tcg_card_id'].isin(api_card_ids)
            ].copy()
            
            if local_matches.empty:
                return pd.DataFrame(), "No tienes ninguna de las cartas encontradas."
            
            # Enriquecer con datos de la API
            enriched_df = await self._enrich_card_data(local_matches)
            
            return enriched_df, f"Éxito: {len(enriched_df)} entradas encontradas."
            
        except Exception as e:
            return pd.DataFrame(), f"Error en búsqueda por nombre: {str(e)}"
    
    async def search_by_set_name(self, inventory_df: pd.DataFrame, set_name_search: str):
        """
        Busca cartas en el inventario por nombre de edición.
        
        Args:
            inventory_df: DataFrame del inventario
            set_name_search: Nombre de la edición a buscar
            
        Returns:
            Tupla (DataFrame de resultados, mensaje de estado)
        """
        try:
            # Buscar edición en la API
            set_resumes = await self.tcgdex.set.list(
                Query().contains("name", set_name_search)
            )
            
            if not set_resumes:
                return pd.DataFrame(), "No se encontró ninguna edición en la API."
            
            # Usar la primera edición encontrada
            set_id = set_resumes[0].id
            set_name_full = set_resumes[0].name
            set_prefix = f"{set_id}-"
            
            # Filtrar cartas de esta edición
            local_matches = inventory_df[
                inventory_df['tcg_card_id'].str.startswith(set_prefix, na=False)
            ].copy()
            
            if local_matches.empty:
                return pd.DataFrame(), f"No tienes cartas de '{set_name_full}' en tu inventario."
            
            # Enriquecer con datos de la API
            enriched_df = await self._enrich_card_data(local_matches, set_name_full)
            
            return enriched_df, f"Éxito: {len(enriched_df)} entradas de la edición '{set_name_full}'."
            
        except Exception as e:
            return pd.DataFrame(), f"Error en búsqueda por edición: {str(e)}"
    
    async def _enrich_card_data(self, df: pd.DataFrame, set_name: str = None) -> pd.DataFrame:
        """
        Enriquece el DataFrame con información detallada de la API.
        
        Args:
            df: DataFrame a enriquecer
            set_name: Nombre de la edición (opcional)
            
        Returns:
            DataFrame enriquecido
        """
        unique_tcg_ids = df['tcg_card_id'].unique()
        
        # Obtener detalles de todas las cartas en paralelo
        tasks = [self.tcgdex.card.get(tcg_id) for tcg_id in unique_tcg_ids]
        full_cards = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Crear cache de detalles
        card_details_cache = {}
        for tcg_id, card_data in zip(unique_tcg_ids, full_cards):
            if not isinstance(card_data, Exception):
                card_details_cache[tcg_id] = {
                    'name': getattr(card_data, 'name', 'N/A'),
                    'set_name': getattr(card_data.set, 'name', 'N/A') if hasattr(card_data, 'set') else 'N/A',
                    'local_id': getattr(card_data, 'localId', 'N/A')
                }
        
        # Agregar columnas enriquecidas
        df['card_name'] = df['tcg_card_id'].apply(
            lambda x: card_details_cache.get(x, {}).get('name', 'N/A')
        )
        df['card_local_number'] = df['tcg_card_id'].apply(
            lambda x: card_details_cache.get(x, {}).get('local_id', 'N/A')
        )
        
        if set_name:
            df['edition_name'] = set_name
        else:
            df['edition_name'] = df['tcg_card_id'].apply(
                lambda x: card_details_cache.get(x, {}).get('set_name', 'N/A')
            )
        
        return df