"""Almacenamiento en Google Drive con CSV."""

import io
import json
import os
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from src.config import FIELDNAMES
from src.storage_interface import StorageInterface


SCOPES = ['https://www.googleapis.com/auth/drive']


def _build_credentials():
    """
    Construye las credenciales de Google de dos formas posibles:
    - En producción (Render): lee el JSON desde la variable de entorno GOOGLE_CREDENTIALS_JSON
    - En local: lee el archivo cuya ruta está en GOOGLE_CREDENTIALS_PATH
    """
    json_str = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if json_str:
        info = json.loads(json_str)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    from src.config import GOOGLE_CREDENTIALS_PATH
    return service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
    )


class GoogleDriveStorage(StorageInterface):
    """Gestiona el inventario como un CSV almacenado en Google Drive."""

    def __init__(self, file_id: str):
        self.file_id = file_id
        creds = _build_credentials()
        self.service = build('drive', 'v3', credentials=creds)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _download_csv(self) -> pd.DataFrame:
        """Descarga el CSV desde Drive y lo devuelve como DataFrame."""
        request = self.service.files().get_media(fileId=self.file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buffer.seek(0)
        try:
            df = pd.read_csv(buffer, dtype={'count': int})
            if 'id' in df.columns:
                df = df.set_index('id')
            if 'available_count' not in df.columns:
                df['available_count'] = 0
            df['available_count'] = df['available_count'].fillna(0).astype(int)
            return df
        except pd.errors.EmptyDataError:
            return pd.DataFrame(columns=FIELDNAMES).set_index('id')

    def _upload_csv(self, df: pd.DataFrame) -> None:
        """Sube el DataFrame como CSV a Drive, sobreescribiendo el archivo."""
        buffer = io.BytesIO()
        df.to_csv(buffer, index=True)
        buffer.seek(0)
        media = MediaIoBaseUpload(buffer, mimetype='text/csv', resumable=False)
        self.service.files().update(
            fileId=self.file_id,
            media_body=media
        ).execute()

    # ------------------------------------------------------------------
    # StorageInterface
    # ------------------------------------------------------------------

    def load_inventory(self) -> pd.DataFrame:
        return self._download_csv()

    def save_inventory(self, df: pd.DataFrame) -> None:
        self._upload_csv(df)

    def add_card(self, card_data: dict) -> int:
        df = self.load_inventory()
        next_id = 1 if df.empty else int(df.index.max()) + 1
        df.loc[next_id] = card_data
        self.save_inventory(df)
        return next_id

    def update_card(self, card_id: int, card_data: dict) -> bool:
        df = self.load_inventory()
        if card_id not in df.index:
            return False
        df.loc[card_id] = card_data
        self.save_inventory(df)
        return True

    def delete_card(self, card_id: int) -> bool:
        df = self.load_inventory()
        if card_id not in df.index:
            return False
        df = df.drop(card_id)
        self.save_inventory(df)
        return True