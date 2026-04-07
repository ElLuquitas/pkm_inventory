"""Almacenamiento local con CSV."""

import pandas as pd
from src.config import INVENTORY_FILE, FIELDNAMES
from src.storage_interface import StorageInterface


class LocalStorage(StorageInterface):
    """Gestiona el almacenamiento local con CSV."""
    
    def load_inventory(self) -> pd.DataFrame:
        """Carga el DataFrame desde el CSV."""
        try:
            df = pd.read_csv(INVENTORY_FILE, dtype={'count': int})
            if 'id' in df.columns:
                df = df.set_index('id')
            # Compatibilidad hacia atrás: añadir columna si no existe
            if 'available_count' not in df.columns:
                df['available_count'] = 0
            df['available_count'] = df['available_count'].fillna(0).astype(int)
            return df
        except (FileNotFoundError, pd.errors.EmptyDataError):
            return pd.DataFrame(columns=FIELDNAMES).set_index('id')
    
    def save_inventory(self, df: pd.DataFrame) -> None:
        """Guarda el DataFrame al CSV."""
        df.to_csv(INVENTORY_FILE, index=True)
    
    def add_card(self, card_data: dict) -> int:
        """Añade una carta al inventario."""
        df = self.load_inventory()
        
        if df.empty:
            next_id = 1
        else:
            next_id = df.index.max() + 1
        
        df.loc[next_id] = card_data
        self.save_inventory(df)
        return next_id
    
    def update_card(self, card_id: int, card_data: dict) -> bool:
        """Actualiza una carta existente."""
        df = self.load_inventory()
        
        if card_id not in df.index:
            return False
        
        df.loc[card_id] = card_data
        self.save_inventory(df)
        return True
    
    def delete_card(self, card_id: int) -> bool:
        """Elimina una carta del inventario."""
        df = self.load_inventory()
        
        if card_id not in df.index:
            return False
        
        df = df.drop(card_id)
        self.save_inventory(df)
        return True