#!/bin/bash

# ============================================
# Script de lanzamiento para Pokémon TCG Inventory
# ============================================

# CONFIGURACIÓN - Modifica estas rutas según tu sistema
PROJECT_DIR="$HOME/Escritorio/pokemon_inventory"  # Cambia esto a tu ruta real
VENV_NAME=".venv"  # Nombre de tu entorno virtual

# Colores para mensajes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # Sin color

# Función para mostrar mensajes
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Verificar que el directorio existe
if [ ! -d "$PROJECT_DIR" ]; then
    log_error "Directorio del proyecto no encontrado: $PROJECT_DIR"
    log_error "Edita el script y actualiza PROJECT_DIR"
    exit 1
fi

# Cambiar al directorio del proyecto
cd "$PROJECT_DIR" || {
    log_error "No se pudo acceder al directorio del proyecto"
    exit 1
}

log_info "Directorio del proyecto: $PROJECT_DIR"

# Verificar que existe el entorno virtual
if [ ! -d "$VENV_NAME" ]; then
    log_error "Entorno virtual no encontrado: $VENV_NAME"
    log_warning "Crea el entorno virtual con: python3 -m venv venv"
    exit 1
fi

# Verificar que existe main.py
if [ ! -f "main.py" ]; then
    log_error "main.py no encontrado en el directorio del proyecto"
    exit 1
fi

# Verificar que existe .env
if [ ! -f ".env" ]; then
    log_warning "Archivo .env no encontrado"
    log_warning "La aplicación podría no funcionar sin configuración de Supabase"
fi

# Activar entorno virtual
log_info "Activando entorno virtual..."
source "$VENV_NAME/bin/activate"

if [ $? -ne 0 ]; then
    log_error "Error al activar el entorno virtual"
    exit 1
fi

# Verificar que las dependencias están instaladas
log_info "Verificando dependencias..."
python -c "import tkinter" 2>/dev/null || {
    log_error "tkinter no está instalado"
    log_warning "Instala con: sudo apt-get install python3-tk"
    deactivate
    exit 1
}

python -c "import pandas, tcgdexsdk, supabase" 2>/dev/null || {
    log_error "Algunas dependencias no están instaladas"
    log_warning "Instala con: pip install -r requirements.txt"
    deactivate
    exit 1
}

# Ejecutar la aplicación
log_info "Iniciando Pokémon TCG Inventory Manager..."
python main.py

# Capturar código de salida
EXIT_CODE=$?

# Desactivar entorno virtual
deactivate

# Mensajes de finalización
if [ $EXIT_CODE -eq 0 ]; then
    log_info "Aplicación cerrada correctamente"
else
    log_error "La aplicación terminó con errores (código: $EXIT_CODE)"
    exit $EXIT_CODE
fi
