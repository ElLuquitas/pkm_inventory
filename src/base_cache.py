"""Clase base para sistemas de cache en JSON."""

import json
import os
from src.config import DATA_DIR, MODE


class BaseCache:
    """
    Gestiona un cache persistente en JSON.

    Cuando MODE='google_drive' y se proporciona un drive_file_id,
    el cache se carga desde Drive al iniciar y se persiste a Drive
    en cada escritura. El archivo local actúa como copia temporal.
    """

    def __init__(self, cache_file: str, drive_file_id: str = ''):
        self.cache_file = os.path.join(DATA_DIR, cache_file)
        self.drive_file_id = drive_file_id if MODE == 'google_drive' else ''
        self._drive_storage = None
        self.cache = self._load_cache()

    # ------------------------------------------------------------------
    # Drive helpers
    # ------------------------------------------------------------------

    def _get_drive_storage(self):
        """Instancia el storage de Drive de forma lazy."""
        if self._drive_storage is None:
            from src.google_drive_storage import GoogleDriveStorage
            from src.config import GOOGLE_FILE_ID
            self._drive_storage = GoogleDriveStorage(file_id=GOOGLE_FILE_ID)
        return self._drive_storage

    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    def _load_cache(self) -> dict:
        """
        Carga el cache. Si MODE='google_drive' y hay file_id, lo descarga
        desde Drive. Si falla o no hay file_id, usa el archivo local.
        """
        if self.drive_file_id:
            try:
                storage = self._get_drive_storage()
                data = storage.download_json(self.drive_file_id)
                # Guardar copia local como backup
                self._write_local(data)
                return data
            except Exception as e:
                print(f"[{self.__class__.__name__}] No se pudo cargar desde Drive: {e}. Usando local.")

        return self._read_local()

    def _read_local(self) -> dict:
        """Lee el cache desde el archivo local JSON."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"[{self.__class__.__name__}] Error leyendo cache local: {e}")
            return {}

    def _write_local(self, data: dict) -> None:
        """Escribe el cache al archivo local."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[{self.__class__.__name__}] Error escribiendo cache local: {e}")

    def _save_cache(self) -> None:
        """Persiste el cache: a Drive si corresponde, siempre también local."""
        self._write_local(self.cache)
        if self.drive_file_id:
            try:
                storage = self._get_drive_storage()
                storage.upload_json(self.drive_file_id, self.cache)
            except Exception as e:
                print(f"[{self.__class__.__name__}] Error subiendo cache a Drive: {e}")

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
            'cache_file':    self.cache_file,
            'file_exists':   os.path.exists(self.cache_file),
            'drive_enabled': bool(self.drive_file_id),
        }