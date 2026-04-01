"""Almacenamiento en Google Drive con CSV."""

import io
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from src.config import FIELDNAMES
from src.storage_interface import StorageInterface


SCOPES = ['https://www.googleapis.com/auth/drive']


class GoogleDriveStorage(StorageInterface):
    """Gestiona el inventario como un CSV almacenado en Google Drive."""

    def __init__(self, credentials_path: str, file_id: str):
        """
        Args:
            credentials_path: Ruta al archivo JSON de la cuenta de servicio.
            file_id: ID del archivo CSV en Google Drive.
        """
        self.file_id = file_id
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES
        )
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
        """Descarga y devuelve el inventario desde Drive."""
        return self._download_csv()

    def save_inventory(self, df: pd.DataFrame) -> None:
        """Sube el DataFrame completo a Drive."""
        self._upload_csv(df)

    def add_card(self, card_data: dict) -> int:
        """Añade una carta al inventario y retorna su nuevo ID."""
        df = self.load_inventory()
        next_id = 1 if df.empty else int(df.index.max()) + 1
        df.loc[next_id] = card_data
        self.save_inventory(df)
        return next_id

    def update_card(self, card_id: int, card_data: dict) -> bool:
        """Actualiza una carta existente. Retorna False si no existe."""
        df = self.load_inventory()
        if card_id not in df.index:
            return False
        df.loc[card_id] = card_data
        self.save_inventory(df)
        return True

    def delete_card(self, card_id: int) -> bool:
        """Elimina una carta. Retorna False si no existe."""
        df = self.load_inventory()
        if card_id not in df.index:
            return False
        df = df.drop(card_id)
        self.save_inventory(df)
        return True