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


# ------------------------------------------------------------------
# Startup: carga el inventario una vez al iniciar el servidor
# ------------------------------------------------------------------

controller = InventoryController()


@asynccontextmanager
async def lifespan(app: FastAPI):
    controller.load_inventory()
    await controller.enrich_inventory()
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


@app.get("/", summary="Frontend web", include_in_schema=False)
def serve_frontend():
    """Sirve el index.html para el frontend web."""
    return FileResponse("index.html")


@app.get("/inventory", summary="Obtener inventario completo enriquecido")
def get_inventory():
    """Retorna todas las cartas con nombre, edición y atributos."""
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


@app.post("/reload", summary="Recargar inventario desde Drive")
async def reload():
    """Fuerza una recarga del inventario desde Google Drive."""
    controller.load_inventory()
    await controller.enrich_inventory()
    return {"message": "Inventario recargado."}


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