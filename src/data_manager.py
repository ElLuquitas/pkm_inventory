"""Manejo de datos con storage configurable."""

import pandas as pd
from src.config import FIELDNAMES, MODE, GOOGLE_FILE_ID
from src.storage_interface import StorageInterface
from src.local_storage import LocalStorage


# Campos válidos de una carta en el inventario (excluye 'id' que es autogenerado)
CARD_FIELDS = [f for f in FIELDNAMES if f != 'id']


def _build_storage() -> StorageInterface:
    """Instancia el backend de almacenamiento según STORAGE_MODE."""
    if MODE == 'google_drive':
        from src.google_drive_storage import GoogleDriveStorage
        return GoogleDriveStorage(file_id=GOOGLE_FILE_ID)
    return LocalStorage()


class DataManager:
    """
    Gestiona el inventario usando el backend de almacenamiento configurado.

    Responsabilidades de esta clase:
    - Seleccionar el backend correcto (local o google_drive)
    - Validar y limpiar los datos antes de persistirlos
    - Exponer una API simple al resto de la aplicación

    Lo que NO hace esta clase:
    - Saber cómo se guarda físicamente (eso es el Storage)
    - Saber cómo se muestran los datos (eso es la GUI o la API)
    """

    def __init__(self, storage: StorageInterface = None):
        self.storage = storage if storage else _build_storage()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load_inventory(self) -> pd.DataFrame:
        """Carga el inventario completo."""
        return self.storage.load_inventory()

    def add_card(self, card_data: dict) -> int:
        """Valida y añade una carta. Retorna el ID asignado."""
        return self.storage.add_card(self._clean(card_data))

    def update_card(self, card_id: int, card_data: dict) -> bool:
        """Valida y actualiza una carta. Retorna False si no existe."""
        return self.storage.update_card(card_id, self._clean(card_data))

    def delete_card(self, card_id: int) -> bool:
        """Elimina una carta. Retorna False si no existe."""
        return self.storage.delete_card(card_id)

    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    def _clean(self, card_data: dict) -> dict:
        """
        Extrae solo los campos válidos de un diccionario de carta.

        Evita que columnas enriquecidas (card_name, edition_name, etc.)
        lleguen accidentalmente al almacenamiento.
        """
        return {field: card_data[field] for field in CARD_FIELDS}