"""API REST para el inventario Pokémon TCG."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.inventory_controller import InventoryController


# ------------------------------------------------------------------
# Modelos de entrada/salida
# ------------------------------------------------------------------

class CardInput(BaseModel):
    tcg_card_id: str = Field(..., example="sv01-001")
    count: int = Field(..., gt=0, example=1)
    available_count: int = Field(default=0, ge=0, example=0)
    language: str = Field(..., example="EN")
    foil_type: str = Field(..., example="Normal")
    stamp: str = Field(default="None", example="None")
    condition: str = Field(..., example="NM")


class CardFilters(BaseModel):
    name: str = ""
    set: str = ""
    language: str = ""
    foil: str = ""
    condition: str = ""
    stamp: str = ""
    available_only: bool = False


# ------------------------------------------------------------------
# Startup: carga el inventario una vez al iniciar el servidor
# ------------------------------------------------------------------

controller = InventoryController()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Solo carga el CSV — el enriquecimiento ocurre en el primer GET /inventory
    controller.load_inventory()
    yield


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(
    title="Pokémon TCG Inventory API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restringir en producción si se desea
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def df_to_records(df) -> list:
    """Convierte un DataFrame a lista de dicts, reemplazando NaN por None."""
    return df.reset_index().where(df.reset_index().notna(), other=None).to_dict(orient="records")


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@app.get("/config", summary="Configuración pública del frontend", include_in_schema=False)
def get_config():
    """Expone la contraseña de edición desde variable de entorno al frontend."""
    from src.config import EDIT_PASSWORD
    return {"edit_password": EDIT_PASSWORD}


@app.get("/", summary="Frontend web", include_in_schema=False)
def serve_frontend():
    """Sirve el index.html para el frontend web."""
    return FileResponse("index.html")


@app.get("/inventory", summary="Obtener inventario completo enriquecido")
async def get_inventory():
    """Retorna todas las cartas con nombre, edición y atributos."""
    if controller.enriched_df is None:
        await controller.enrich_inventory()
    df = controller.enriched_df if controller.enriched_df is not None else controller.inventory_df
    if df is None or df.empty:
        return []
    return df_to_records(df)


@app.post("/inventory/filter", summary="Filtrar inventario")
def filter_inventory(filters: CardFilters):
    """Aplica filtros y retorna las cartas que coinciden."""
    result = controller.apply_filters(filters.model_dump())
    return df_to_records(result)


@app.post("/cards", summary="Agregar carta", status_code=201)
async def add_card(card: CardInput):
    """Agrega una carta nueva al inventario y re-enriquece."""
    try:
        new_id = controller.add_card(card.model_dump())
        controller.load_inventory()
        await controller.enrich_inventory()
        return {"id": new_id, "message": "Carta agregada correctamente."}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.put("/cards/{card_id}", summary="Actualizar carta")
async def update_card(card_id: int, card: CardInput):
    """Actualiza los datos de una carta existente y re-enriquece."""
    try:
        success = controller.update_card(card_id, card.model_dump())
        if not success:
            raise HTTPException(status_code=404, detail=f"Carta con ID {card_id} no encontrada.")
        controller.load_inventory()
        await controller.enrich_inventory()
        return {"message": "Carta actualizada correctamente."}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.delete("/cards/{card_id}", summary="Eliminar carta")
async def delete_card(card_id: int):
    """Elimina una carta del inventario y re-enriquece."""
    success = controller.delete_card(card_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Carta con ID {card_id} no encontrada.")
    controller.load_inventory()
    await controller.enrich_inventory()
    return {"message": "Carta eliminada correctamente."}


@app.post("/cards/{card_id}/increment", summary="Incrementar cantidad")
def increment(card_id: int):
    """Incrementa en 1 la cantidad de una carta."""
    controller.load_inventory()
    success = controller.increment_count(card_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Carta con ID {card_id} no encontrada.")
    return {"message": "Cantidad incrementada."}


@app.post("/cards/{card_id}/decrement", summary="Decrementar cantidad")
def decrement(card_id: int):
    """Decrementa en 1 la cantidad de una carta. No elimina si llega a 0."""
    controller.load_inventory()
    success, reached_zero = controller.decrement_count(card_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Carta con ID {card_id} no encontrada.")
    return {"message": "Cantidad decrementada.", "reached_zero": reached_zero}


@app.get("/sets", summary="Listar ediciones disponibles")
def get_sets():
    """Retorna todas las ediciones presentes en el inventario."""
    if controller.sets_cache:
        return controller.sets_cache.get_all()
    return []


@app.post("/admin/rebuild-cache", summary="Reconstruir cache de cartas", include_in_schema=False)
async def rebuild_cache():
    """
    Reconstruye el card_cache para todas las cartas del inventario,
    incluyendo regulation_mark e image_url. Llamar manualmente una vez tras deploy.
    """
    if controller.inventory_df is None or controller.inventory_df.empty:
        controller.load_inventory()

    unique_ids = controller.inventory_df['tcg_card_id'].unique().tolist()
    # Forzar re-descarga de TODAS las cartas (no solo las faltantes)
    controller.card_cache.clear()

    import asyncio
    from datetime import datetime

    new_data = {}
    errors = []
    BATCH = 10

    for i in range(0, len(unique_ids), BATCH):
        batch = unique_ids[i:i + BATCH]
        tasks = [controller.api_service.tcgdex.card.get(cid) for cid in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for cid, card in zip(batch, results):
            if not isinstance(card, Exception):
                image_base = getattr(card, 'image', None)
                new_data[cid] = {
                    'name':            getattr(card, 'name', 'N/A'),
                    'set_name':        getattr(card.set, 'name', 'N/A') if hasattr(card, 'set') else 'N/A',
                    'local_id':        getattr(card, 'localId', 'N/A'),
                    'image_url':       f"{image_base}/high.png" if image_base else None,
                    'regulation_mark': getattr(card, 'regulationMark', None),
                    'updated_at':      datetime.now().isoformat(),
                }
            else:
                errors.append(cid)

    if new_data:
        controller.card_cache.bulk_set(new_data)

    # Re-enriquecer con los nuevos datos
    await controller.enrich_inventory()

    return {
        "total": len(unique_ids),
        "updated": len(new_data),
        "errors": len(errors),
        "error_ids": errors[:20],
    }


@app.post("/reload", summary="Recargar inventario y caches desde Drive")
async def reload():
    """Fuerza una recarga del inventario y los caches desde Google Drive."""
    # Recargar caches desde Drive (si MODE=google_drive)
    controller.card_cache.cache = controller.card_cache._load_cache()
    controller.sets_cache.cache = controller.sets_cache._load_cache()
    controller.load_inventory()
    await controller.enrich_inventory()
    return {"message": "Inventario y caches recargados."}


@app.get("/tcgdex/search", summary="Buscar cartas en TCGdex por nombre")
async def tcgdex_search(q: str):
    """
    Busca cartas en la API de TCGdex por nombre.
    La image_url se obtiene de card_data.image, igual que la GUI original.
    """
    if not q or len(q) < 2:
        return []
    try:
        from tcgdexsdk import Query
        import asyncio
        resumes = await controller.api_service.tcgdex.card.list(
            Query().contains("name", q)
        )
        if not resumes:
            return []

        tcg_ids = [
            getattr(r, 'id', None) for r in resumes[:40]
            if getattr(r, 'id', None) and '-' in getattr(r, 'id', '')
        ]
        tasks = [controller.api_service.tcgdex.card.get(tcg_id) for tcg_id in tcg_ids]
        cards_data = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for tcg_id, card_data in zip(tcg_ids, cards_data):
            if isinstance(card_data, Exception):
                continue
            image_base = getattr(card_data, 'image', None)
            image_url = f"{image_base}/high.png" if image_base else None
            set_obj = getattr(card_data, 'set', None)
            set_name = getattr(set_obj, 'name', tcg_id.split('-')[0].upper()) if set_obj else tcg_id.split('-')[0].upper()
            results.append({
                "id": tcg_id,
                "name": getattr(card_data, 'name', 'N/A'),
                "set_name": set_name,
                "image_url": image_url,
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/card-image/{tcg_card_id}", summary="URL de imagen de una carta")
async def card_image_url(tcg_card_id: str):
    """
    Devuelve la URL de imagen consultando card_data.image de la SDK,
    igual que hace la GUI original con card_data.image/high.png.
    Cachea el resultado para evitar llamadas repetidas.
    """
    # Revisar si ya tenemos la image_url en cache
    cached = controller.card_cache.get(tcg_card_id)
    if cached and cached.get('image_url'):
        return {"image_url": cached['image_url']}

    try:
        card_data = await controller.api_service.tcgdex.card.get(tcg_card_id)
        image_base = getattr(card_data, 'image', None)
        if not image_base:
            raise HTTPException(status_code=404, detail="Imagen no disponible para esta carta.")
        image_url = f"{image_base}/high.png"

        # Persistir en cache
        entry = controller.card_cache.get(tcg_card_id) or {}
        entry['image_url'] = image_url
        controller.card_cache.set(tcg_card_id, entry)

        return {"image_url": image_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Decklist checker
# ------------------------------------------------------------------

class DecklistInput(BaseModel):
    text: str
    available_only: bool = False


# Cache en memoria: abbreviation (mayúsculas) → set_id TCGdex
_abbrev_cache: dict[str, str] = {}


async def _resolve_abbrev(abbrev: str) -> str | None:
    """
    Convierte un código abreviado de carta (ej. 'MEG') al set_id de TCGdex (ej. 'me01').
    Primero busca en el sets_cache del controller (por si el id coincide en minúsculas),
    luego consulta TCGdex filtrando por abbreviation.
    """
    key = abbrev.upper()
    if key in _abbrev_cache:
        return _abbrev_cache[key]

    # Intentar match directo: algunos sets tienen id == abbrev.lower()
    lower = abbrev.lower()
    if controller.sets_cache.get(lower):
        _abbrev_cache[key] = lower
        return lower

    # Buscar en el sets_cache por nombre parcial (fallback débil)
    all_sets = controller.sets_cache.get_all()
    for set_id in all_sets:
        if set_id.lower() == lower:
            _abbrev_cache[key] = set_id
            return set_id

    # Consultar TCGdex: buscar por abbreviation con timeout
    try:
        from tcgdexsdk import Query
        import asyncio
        sets = await asyncio.wait_for(
            controller.api_service.tcgdex.set.list(
                Query().equal("abbreviation", abbrev.upper())
            ),
            timeout=8.0
        )
        if sets:
            found_id = getattr(sets[0], 'id', None)
            if found_id:
                _abbrev_cache[key] = found_id
                return found_id
    except Exception:
        pass

    # Segundo intento: listar todos los sets y buscar manualmente con timeout
    try:
        import asyncio
        sets = await asyncio.wait_for(
            controller.api_service.tcgdex.set.list(),
            timeout=10.0
        )
        if sets:
            for s in sets:
                abbr = getattr(s, 'abbreviation', None)
                if abbr and abbr.upper() == key:
                    found_id = getattr(s, 'id', None)
                    if found_id:
                        _abbrev_cache[key] = found_id
                        return found_id
    except Exception:
        pass

    return None


def _parse_decklist(text: str) -> list[dict]:
    """
    Parsea el texto de una decklist en categorías con cartas.
    Retorna lista de: {type: 'category'|'card', ...}
    """
    result = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Línea de categoría: "Pokémon: 13" o "Trainer: 39"
        if ':' in line and line.split(':')[0].strip().replace(' ', '').isalpha():
            parts = line.split(':', 1)
            result.append({'type': 'category', 'label': parts[0].strip(), 'total': parts[1].strip()})
            continue
        # Línea de carta: "4 Charizard MEG 131"
        tokens = line.split()
        if len(tokens) >= 3:
            try:
                qty = int(tokens[0])
                number = tokens[-1]
                abbrev = tokens[-2]
                name = ' '.join(tokens[1:-2])
                result.append({
                    'type': 'card',
                    'qty': qty,
                    'name': name,
                    'abbrev': abbrev,
                    'number': number,
                })
            except (ValueError, IndexError):
                continue
    return result


@app.post("/decklist/check", summary="Cruzar decklist con inventario")
async def check_decklist(body: DecklistInput):
    """
    Parsea una decklist en formato Limitless/PTCGL y la cruza con el inventario.
    Retorna categorías con sus cartas y estado (tengo / faltan).
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="La lista está vacía.")

    df = controller.enriched_df if controller.enriched_df is not None else controller.inventory_df
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Inventario no cargado.")

    parsed = _parse_decklist(body.text)
    results = []

    for item in parsed:
        if item['type'] == 'category':
            results.append(item)
            continue

        abbrev = item['abbrev']
        number_raw = item['number']

        # Resolver abbreviation → set_id
        set_id = await _resolve_abbrev(abbrev)

        if not set_id:
            results.append({**item, 'tcg_id': None, 'have': 0, 'missing': item['qty'],
                             'error': f"Edición '{abbrev}' no encontrada"})
            continue

        # Construir tcg_card_id: número con ceros hasta 3 dígitos si es numérico
        try:
            num_int = int(number_raw)
            number_fmt = str(num_int).zfill(3)
        except ValueError:
            number_fmt = number_raw  # Números como "SV001", "TG01", etc.

        tcg_id = f"{set_id}-{number_fmt}"

        # Buscar en inventario
        mask = df['tcg_card_id'] == tcg_id
        if mask.any():
            if body.available_only and 'available_count' in df.columns:
                have = int(df.loc[mask, 'available_count'].fillna(0).astype(int).sum())
            else:
                have = int(df.loc[mask, 'count'].sum())
        else:
            have = 0

        missing = max(0, item['qty'] - have)
        results.append({**item, 'tcg_id': tcg_id, 'have': have, 'missing': missing})

    return results