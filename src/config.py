"""Configuración global del proyecto."""

import os
from dotenv import load_dotenv

load_dotenv()

# Modo de operación: 'local' o 'google_drive'
MODE = os.getenv('STORAGE_MODE', 'local')

# Rutas locales
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
INVENTORY_FILE = os.path.join(DATA_DIR, 'inventory.csv')

os.makedirs(DATA_DIR, exist_ok=True)

# Configuración Google Drive (solo relevante cuando MODE='google_drive')
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
GOOGLE_FILE_ID = os.getenv('GOOGLE_FILE_ID', '')

# Columnas del inventario ('id' es autogenerado, no se incluye en inputs)
FIELDNAMES = ['id', 'tcg_card_id', 'count', 'available_count', 'language', 'foil_type', 'stamp', 'condition']

# Contraseña de edición (se lee desde variable de entorno; fallback local para desarrollo)
EDIT_PASSWORD = os.getenv('EDIT_PASSWORD', 'pkm1234')

# Opciones de búsqueda (para compatibilidad con código existente)
SEARCH_OPTIONS = ["Buscar por Nombre de Carta", "Buscar por Edición"]

# Headers para mostrar en la UI
DISPLAY_HEADERS = {
    'card_name': "Nombre de Carta",
    'edition_name': "Edición",
    'card_local_number': "# Local",
    'tcg_card_id': "ID Global",
    'count': "Cantidad",
    'available_count': "Disponible",
    'language': "Idioma",
    'foil_type': "Brillo",
    'stamp': "Sello",
    'condition': "Condición",
}

# Valores válidos para cada campo
SUPPORTED_LANGUAGES = ['EN', 'ES', 'LA', 'PT', 'JP', 'KR', 'CN']

SUPPORTED_FOIL_TYPES = ['Normal', 'Holo', 'Reverse Holo', 'Full Art', 'Gold Rare']

SUPPORTED_CONDITIONS = ['NM', 'LP', 'MP', 'HP', 'DMG']

SUPPORTED_STAMPS = [
    'None', 'Pokemon Center', 'Prerelease', 'Staff',
    'World Championship', '1st Edition', 'Shadowless', 'League Promo', 'Halloween'
]