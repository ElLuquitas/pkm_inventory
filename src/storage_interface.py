"""Interfaz abstracta para diferentes backends de almacenamiento."""

from abc import ABC, abstractmethod
import pandas as pd


class StorageInterface(ABC):
    """Interfaz base para sistemas de almacenamiento."""
    
    @abstractmethod
    def load_inventory(self) -> pd.DataFrame:
        """Carga el inventario completo."""
        pass
    
    @abstractmethod
    def save_inventory(self, df: pd.DataFrame) -> None:
        """Guarda el inventario completo."""
        pass
    
    @abstractmethod
    def add_card(self, card_data: dict) -> int:
        """Añade una carta y retorna su ID."""
        pass
    
    @abstractmethod
    def update_card(self, card_id: int, card_data: dict) -> bool:
        """Actualiza una carta existente."""
        pass
    
    @abstractmethod
    def delete_card(self, card_id: int) -> bool:
        """Elimina una carta."""
        pass