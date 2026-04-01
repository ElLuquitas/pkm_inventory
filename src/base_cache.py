"""Clase base para sistemas de cache en JSON."""

import json
import os
from src.config import DATA_DIR


class BaseCache:
    """
    Gestiona un cache persistente en un archivo JSON.

    Las subclases solo necesitan definir el nombre del archivo
    y los métodos específicos de su dominio (get, set, etc.).
    """

    def __init__(self, cache_file: str):
        self.cache_file = os.path.join(DATA_DIR, cache_file)
        self.cache = self._load_cache()

    # ------------------------------------------------------------------
    # Métodos internos (no llamar desde fuera)
    # ------------------------------------------------------------------

    def _load_cache(self) -> dict:
        """Carga el cache desde el archivo JSON. Si no existe, retorna {}."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"[{self.__class__.__name__}] Error cargando cache: {e}")
            return {}

    def _save_cache(self) -> None:
        """Persiste el cache actual al archivo JSON."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[{self.__class__.__name__}] Error guardando cache: {e}")

    # ------------------------------------------------------------------
    # API pública compartida por todas las subclases
    # ------------------------------------------------------------------

    def get(self, key: str):
        """Retorna el valor para una clave, o None si no existe."""
        return self.cache.get(key)

    def delete(self, key: str) -> None:
        """Elimina una entrada del cache."""
        if key in self.cache:
            del self.cache[key]
            self._save_cache()

    def get_missing_keys(self, keys: list) -> list:
        """Retorna las claves de la lista que NO están en el cache."""
        return [k for k in keys if k not in self.cache]

    def clear(self) -> None:
        """Vacía el cache completamente."""
        self.cache = {}
        self._save_cache()

    def get_stats(self) -> dict:
        """Retorna estadísticas básicas del cache."""
        return {
            'total_entries': len(self.cache),
            'cache_file': self.cache_file,
            'file_exists': os.path.exists(self.cache_file),
        }