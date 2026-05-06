"""API REST para el inventario Pokémon TCG."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.inventory_controller import InventoryController, build_functional_hash


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
# Decklist checker — resolución de abreviaciones via pokemontcg.io + TCGdex
# ------------------------------------------------------------------

class DecklistInput(BaseModel):
    text: str
    available_only: bool = False


def _normalize(name: str) -> str:
    """Normaliza un nombre para comparación fuzzy: minúsculas, sin signos."""
    import re
    return re.sub(r'[^a-z0-9 ]', '', name.lower()).strip()


async def _build_ptcgl_map() -> dict:
    """
    Construye el mapa {ABBREV_UPPER: tcgdex_set_id} cruzando pokemontcg.io con TCGdex.

    1. Descarga todos los sets de pokemontcg.io (campo ptcgoCode + name).
    2. Para cada set, busca en el sets_cache de TCGdex el set_id cuyo nombre
       coincida (match exacto primero, luego fuzzy).
    3. Retorna el mapa completo.
    """
    import httpx
    import asyncio

    # --- Paso 1: obtener sets de pokemontcg.io ---
    ptcgio_sets = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            page = 1
            while True:
                r = await client.get(
                    "https://api.pokemontcg.io/v2/sets",
                    params={"pageSize": 250, "page": page, "select": "ptcgoCode,name"}
                )
                data = r.json()
                batch = data.get("data", [])
                if not batch:
                    break
                ptcgio_sets.extend(batch)
                if len(batch) < 250:
                    break
                page += 1
    except Exception as e:
        print(f"[ptcgl_map] Error consultando pokemontcg.io: {e}")
        return {}

    if not ptcgio_sets:
        return {}

    # --- Paso 2: cruzar con sets_cache de TCGdex ---
    # sets_cache: {set_id: set_name} — ya tenemos nombres de TCGdex
    tcgdex_sets = {
        set_id: name
        for set_id, name in controller.sets_cache.get_all().items()
        if isinstance(name, str) and not set_id.startswith('_')
    }
    # Índice normalizado para búsqueda rápida
    tcgdex_normalized = {_normalize(name): set_id for set_id, name in tcgdex_sets.items()}

    mapping = {}
    unresolved = []

    for s in ptcgio_sets:
        code = (s.get("ptcgoCode") or "").strip().upper()
        name = (s.get("name") or "").strip()
        if not code or not name:
            continue

        norm = _normalize(name)

        # Match exacto normalizado
        if norm in tcgdex_normalized:
            mapping[code] = tcgdex_normalized[norm]
            continue

        # Match parcial: tcgdex name contiene el nombre de pokemontcg o viceversa
        found = None
        for tcgdex_norm, set_id in tcgdex_normalized.items():
            if norm in tcgdex_norm or tcgdex_norm in norm:
                found = set_id
                break
        if found:
            mapping[code] = found
        else:
            unresolved.append((code, name))

    if unresolved:
        print(f"[ptcgl_map] {len(unresolved)} sets sin resolver: {unresolved[:10]}")

    print(f"[ptcgl_map] Mapa construido: {len(mapping)} abreviaciones resueltas.")
    return mapping


async def _ensure_ptcgl_map() -> dict:
    """
    Retorna el mapa de abreviaciones, construyéndolo si no existe en el cache.
    Persiste el resultado en sets_cache (y por ende en Drive si está configurado).
    """
    if controller.sets_cache.has_ptcgl_map():
        return controller.sets_cache.get_ptcgl_map()

    print("[ptcgl_map] Construyendo mapa PTCGL→TCGdex por primera vez…")
    mapping = await _build_ptcgl_map()
    if mapping:
        controller.sets_cache.set_ptcgl_map(mapping)
    return mapping


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
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="La lista está vacía.")

    df = controller.enriched_df if controller.enriched_df is not None else controller.inventory_df
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Inventario no cargado.")

    # Asegurar que el mapa de abreviaciones esté disponible
    ptcgl_map = await _ensure_ptcgl_map()

    parsed = _parse_decklist(body.text)
    results = []
    current_category = ''  # rastrea la sección actual: 'pokémon', 'trainer', 'energy'

    for item in parsed:
        if item['type'] == 'category':
            current_category = item['label'].lower()
            results.append(item)
            continue

        abbrev = item['abbrev'].upper()
        number_raw = item['number']

        # Resolver abbreviation → set_id desde el mapa
        set_id = ptcgl_map.get(abbrev)

        if not set_id:
            results.append({
                **item,
                'tcg_id': None,
                'have': 0,
                'missing': item['qty'],
                'error': f"Edición '{abbrev}' no encontrada en el mapa"
            })
            continue

        # Construir tcg_card_id con número formateado
        try:
            number_fmt = str(int(number_raw)).zfill(3)
        except ValueError:
            number_fmt = number_raw  # ej. "SV001", "TG01"

        tcg_id = f"{set_id}-{number_fmt}"

        # Buscar en inventario considerando todas las ediciones equivalentes
        mask = df['tcg_card_id'] == tcg_id
        reprint_ids: list[str] = []

        is_trainer_or_energy = any(
            kw in current_category for kw in ('trainer', 'energy', 'energía', 'entrenador')
        )
        is_pokemon = 'pok' in current_category  # cubre 'pokémon', 'pokemon'

        inventory_ids = df['tcg_card_id'].unique().tolist()

        if is_trainer_or_energy:
            # Para Trainer y Energy: sumar todas las ediciones con el mismo nombre,
            # independientemente de si la edición exacta está en el inventario.
            card_name_target = (controller.card_cache.get(tcg_id) or {}).get('name') or item['name']
            norm_target = _normalize(card_name_target)

            all_matches = [
                cid for cid in inventory_ids
                if _normalize((controller.card_cache.get(cid) or {}).get('name', '')) == norm_target
            ]
            reprint_ids = [cid for cid in all_matches if cid != tcg_id]
            if all_matches:
                match_mask = df['tcg_card_id'].isin(all_matches)
                if body.available_only and 'available_count' in df.columns:
                    have = int(df.loc[match_mask, 'available_count'].fillna(0).astype(int).sum())
                else:
                    have = int(df.loc[match_mask, 'count'].sum())
            else:
                have = 0

        elif is_pokemon:
            # Para Pokémon: sumar todas las ediciones con el mismo functional_hash.
            # Obtener el hash de la carta pedida: primero desde cache, si no desde la API.
            target_hash = (controller.card_cache.get(tcg_id) or {}).get('functional_hash')

            if not target_hash:
                try:
                    card_data = await controller.api_service.tcgdex.card.get(tcg_id)
                    target_hash = build_functional_hash(card_data)
                    if target_hash:
                        image_base = getattr(card_data, 'image', None)
                        controller.card_cache.set(tcg_id, {
                            'name':            getattr(card_data, 'name', 'N/A'),
                            'set_name':        getattr(card_data.set, 'name', 'N/A') if hasattr(card_data, 'set') else 'N/A',
                            'local_id':        getattr(card_data, 'localId', 'N/A'),
                            'image_url':       f"{image_base}/high.png" if image_base else None,
                            'category':        getattr(card_data, 'category', None),
                            'functional_hash': target_hash,
                        })
                except Exception:
                    target_hash = None

            if target_hash:
                all_matches = [
                    cid for cid in inventory_ids
                    if (controller.card_cache.get(cid) or {}).get('functional_hash') == target_hash
                ]
                reprint_ids = [cid for cid in all_matches if cid != tcg_id]
                if all_matches:
                    match_mask = df['tcg_card_id'].isin(all_matches)
                    if body.available_only and 'available_count' in df.columns:
                        have = int(df.loc[match_mask, 'available_count'].fillna(0).astype(int).sum())
                    else:
                        have = int(df.loc[match_mask, 'count'].sum())
                else:
                    have = 0
            else:
                # Sin hash: caer de vuelta al conteo exacto si existe
                if mask.any():
                    if body.available_only and 'available_count' in df.columns:
                        have = int(df.loc[mask, 'available_count'].fillna(0).astype(int).sum())
                    else:
                        have = int(df.loc[mask, 'count'].sum())
                else:
                    have = 0

        else:
            # Categoría desconocida: conteo exacto
            if mask.any():
                if body.available_only and 'available_count' in df.columns:
                    have = int(df.loc[mask, 'available_count'].fillna(0).astype(int).sum())
                else:
                    have = int(df.loc[mask, 'count'].sum())
            else:
                have = 0

        missing = max(0, item['qty'] - have)
        results.append({
            **item,
            'tcg_id': tcg_id,
            'have': have,
            'missing': missing,
            **({"reprint_ids": reprint_ids} if reprint_ids else {}),
        })

    return results


@app.post("/admin/rebuild-ptcgl-map", summary="Reconstruir mapa PTCGL→TCGdex", include_in_schema=False)
async def rebuild_ptcgl_map():
    """
    Fuerza la reconstrucción del mapa de abreviaciones Limitless/PTCGL → TCGdex.
    Llamar manualmente si aparecen sets nuevos sin resolver.
    """
    # Limpiar el mapa existente para forzar reconstrucción
    existing = controller.sets_cache.get_ptcgl_map()
    controller.sets_cache.cache.pop(controller.sets_cache._PTCGL_MAP_KEY, None)

    mapping = await _build_ptcgl_map()
    if mapping:
        controller.sets_cache.set_ptcgl_map(mapping)
        return {"status": "ok", "resolved": len(mapping)}
    return {"status": "error", "resolved": 0}