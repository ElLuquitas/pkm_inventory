"""Interfaz gráfica del inventario Pokémon TCG."""

import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
from async_tkinter_loop import async_handler
from io import BytesIO
from PIL import Image, ImageTk, ImageFile
import urllib.request
import ssl
import concurrent.futures

ImageFile.LOAD_TRUNCATED_IMAGES = True

from src.config import (
    DISPLAY_HEADERS, SUPPORTED_LANGUAGES, SUPPORTED_FOIL_TYPES,
    SUPPORTED_CONDITIONS, SUPPORTED_STAMPS
)
from src.inventory_controller import InventoryController
from src.api_service import TCGdexService
from tcgdexsdk import Query


class InventoryApp:
    """Aplicación principal de gestión de inventario."""

    def __init__(self, master):
        self.master = master
        master.title("Pokémon TCG Inventory Manager")
        master.geometry("1200x800")

        # Un solo punto de entrada para la lógica
        self.controller = InventoryController()

        # Estado de la UI
        self.selected_card_id = None
        self.input_vars = {}
        self.filter_vars = {}
        self.current_tree = None
        self.current_displayed_df = None

        self._create_widgets()
        self._load_and_enrich()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _create_widgets(self):
        self._create_search_and_filter_frame()
        ttk.Separator(self.master, orient='horizontal').pack(fill='x', pady=5)
        self._create_input_frame()
        self._create_results_frame()

    def _create_search_and_filter_frame(self):
        main_frame = ttk.LabelFrame(self.master, text="🔍 Búsqueda y Filtros", padding="10")
        main_frame.pack(fill='x', padx=10, pady=(10, 0))

        # Fila de búsqueda
        search_row = ttk.Frame(main_frame)
        search_row.pack(fill='x', pady=(0, 10))

        ttk.Label(search_row, text="Nombre de carta:", font=('', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        self.search_entry = ttk.Entry(search_row, width=30)
        self.search_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 10))
        self.search_entry.bind('<Return>', lambda e: self._on_search())

        ttk.Button(search_row, text="🔍 Buscar", command=self._on_search).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(search_row, text="🔄 Recargar", command=self._reload_inventory).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(search_row, text="🧹 Limpiar Todo", command=self._clear_all_filters).pack(side=tk.LEFT)

        ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=5)

        # Fila de filtros
        ttk.Label(main_frame, text="Filtros adicionales:", font=('', 9, 'bold')).pack(anchor='w', pady=(5, 5))
        filters_row = ttk.Frame(main_frame)
        filters_row.pack(fill='x', pady=(0, 5))

        self.set_combo = self._add_filter_combo(filters_row, 'set', "Edición:", [''], width=20)
        self._add_filter_combo(filters_row, 'language', "Idioma:", [''] + SUPPORTED_LANGUAGES, width=8)
        self._add_filter_combo(filters_row, 'foil', "Brillo:", [''] + SUPPORTED_FOIL_TYPES, width=15)
        self._add_filter_combo(filters_row, 'condition', "Condición:", [''] + SUPPORTED_CONDITIONS, width=8)
        self._add_filter_combo(filters_row, 'stamp', "Sello:", [''] + SUPPORTED_STAMPS, width=15)

        self.filter_label = ttk.Label(filters_row, text="", foreground="blue")
        self.filter_label.pack(side=tk.LEFT, padx=(15, 0))

    def _add_filter_combo(self, parent, key, label, values, width):
        """Helper para crear un combo de filtro y registrarlo en filter_vars."""
        ttk.Label(parent, text=label).pack(side=tk.LEFT, padx=(0, 5))
        var = tk.StringVar()
        var.trace('w', lambda *args: self._on_filter_changed())
        combo = ttk.Combobox(parent, textvariable=var, values=values, width=width, state='readonly')
        combo.pack(side=tk.LEFT, padx=(0, 15))
        self.filter_vars[key] = var
        return combo

    def _create_input_frame(self):
        frame = ttk.LabelFrame(self.master, text="📝 Añadir/Editar Carta", padding="10")
        frame.pack(fill='x', padx=10)

        fields = ttk.Frame(frame)
        fields.pack(fill='x')

        # ID Global
        ttk.Label(fields, text="ID Global (API):").grid(row=0, column=0, sticky='w', pady=2, padx=5)
        id_frame = ttk.Frame(fields)
        id_frame.grid(row=0, column=1, sticky='w', pady=2, padx=5)
        self.input_vars['tcg_card_id_var'] = tk.StringVar()
        ttk.Entry(id_frame, textvariable=self.input_vars['tcg_card_id_var'], width=22).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(id_frame, text="🔍 Buscar", command=self._open_card_browser, width=8).pack(side=tk.LEFT)

        # Cantidad
        ttk.Label(fields, text="Cantidad (#):").grid(row=0, column=2, sticky='w', pady=2, padx=5)
        self.input_vars['count_var'] = tk.StringVar(value='1')
        ttk.Entry(fields, textvariable=self.input_vars['count_var'], width=10).grid(row=0, column=3, sticky='w', pady=2, padx=5)

        # Idioma / Condición
        ttk.Label(fields, text="Idioma:").grid(row=1, column=0, sticky='w', pady=2, padx=5)
        self.input_vars['language_var'] = tk.StringVar(value='EN')
        ttk.Combobox(fields, textvariable=self.input_vars['language_var'], values=[''] + SUPPORTED_LANGUAGES, width=8, state='readonly').grid(row=1, column=1, sticky='w', pady=2, padx=5)

        ttk.Label(fields, text="Condición:").grid(row=1, column=2, sticky='w', pady=2, padx=5)
        self.input_vars['condition_var'] = tk.StringVar(value='NM')
        ttk.Combobox(fields, textvariable=self.input_vars['condition_var'], values=[''] + SUPPORTED_CONDITIONS, width=8, state='readonly').grid(row=1, column=3, sticky='w', pady=2, padx=5)

        # Brillo / Sello
        ttk.Label(fields, text="Tipo de Brillo:").grid(row=2, column=0, sticky='w', pady=2, padx=5)
        self.input_vars['foil_type_var'] = tk.StringVar(value='Normal')
        ttk.Combobox(fields, textvariable=self.input_vars['foil_type_var'], values=[''] + SUPPORTED_FOIL_TYPES, width=18, state='readonly').grid(row=2, column=1, sticky='w', pady=2, padx=5)

        ttk.Label(fields, text="Sello:").grid(row=2, column=2, sticky='w', pady=2, padx=5)
        self.input_vars['stamp_var'] = tk.StringVar(value='None')
        ttk.Combobox(fields, textvariable=self.input_vars['stamp_var'], values=[''] + SUPPORTED_STAMPS, width=18, state='readonly').grid(row=2, column=3, sticky='w', pady=2, padx=5)

        # Botones
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x', pady=(10, 0))

        self.add_button = ttk.Button(btn_frame, text="➕ Añadir al Inventario", command=self._on_add_card)
        self.add_button.pack(side=tk.LEFT, padx=(0, 5))

        self.update_button = ttk.Button(btn_frame, text="💾 Actualizar Carta", command=self._on_update_card, state=tk.DISABLED)
        self.update_button.pack(side=tk.LEFT, padx=(0, 5))

        self.delete_button = ttk.Button(btn_frame, text="🗑️ Eliminar Carta", command=self._on_delete_card, state=tk.DISABLED)
        self.delete_button.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(btn_frame, text="🧹 Limpiar Campos", command=self._clear_form).pack(side=tk.LEFT)

    def _create_results_frame(self):
        outer = ttk.LabelFrame(self.master, text="📋 Inventario", padding="5")
        outer.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        paned = tk.PanedWindow(outer, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5)
        paned.pack(fill='both', expand=True)

        # Panel izquierdo: tabla del inventario
        self.result_frame = ttk.Frame(paned)
        paned.add(self.result_frame, stretch='always')

        # Panel derecho: imagen de la carta seleccionada
        image_panel = ttk.Frame(paned, width=220)
        paned.add(image_panel, stretch='never')

        self._card_image_ref = None   # Referencia para evitar que el GC elimine la imagen
        self._card_image_data = None   # Bytes originales, para re-escalar sin perder calidad

        self.image_label = ttk.Label(
            image_panel,
            text="Selecciona una carta\npara ver su imagen",
            foreground='gray',
            anchor='center',
            justify='center',
        )
        self.image_label.pack(fill='both', expand=True, padx=10, pady=10)

        # Re-escalar cuando el panel contenedor cambia de tamaño.
        # Vinculamos al image_panel (el Frame), no al label, porque el Frame
        # siempre refleja el tamaño real del panel del PanedWindow.
        image_panel.bind('<Configure>', self._on_image_panel_resized)

    # ------------------------------------------------------------------
    # Carga de datos
    # ------------------------------------------------------------------

    def _load_and_enrich(self):
        """Carga el inventario y lanza el enriquecimiento en background."""
        df = self.controller.load_inventory()
        self._display(df)
        if not df.empty:
            self.master.after(100, lambda: asyncio.create_task(self._enrich_and_refresh()))

    async def _enrich_and_refresh(self):
        """Enriquece el inventario y actualiza la vista."""
        try:
            enriched = await self.controller.enrich_inventory()
            self._display(enriched)
            self._update_filter_options(enriched)
        except Exception as e:
            print(f"Error enriqueciendo inventario: {e}")

    def _reload_inventory(self):
        """Recarga el inventario desde el almacenamiento."""
        self.controller.load_inventory()
        self._load_and_enrich()

    # ------------------------------------------------------------------
    # Handlers de eventos (lo que hace la GUI ante cada acción)
    # ------------------------------------------------------------------

    def _on_search(self):
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("Advertencia", "Introduce un nombre de carta.")
            return
        filters = self._get_current_filters()
        filters['name'] = query
        result = self.controller.apply_filters(filters)
        self._display(result)

    def _on_filter_changed(self):
        filters = self._get_current_filters()
        result = self.controller.apply_filters(filters)
        self._display(result)
        # Actualizar contador
        base_total = len(self.controller.enriched_df or self.controller.inventory_df)
        if len(result) < base_total:
            self.filter_label.config(text=f"📊 Mostrando {len(result)} de {base_total} cartas")
        else:
            self.filter_label.config(text="")

    def _on_add_card(self):
        try:
            card_data = self._get_form_data()
            new_id = self.controller.add_card(card_data)
            messagebox.showinfo("Éxito", f"Carta añadida con ID: {new_id}")
            self._clear_form()
            self._reload_inventory()
        except ValueError as e:
            messagebox.showerror("Error de validación", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Error al guardar: {e}")

    def _on_update_card(self):
        if not self.selected_card_id:
            messagebox.showwarning("Advertencia", "No hay ninguna carta seleccionada.")
            return
        try:
            card_data = self._get_form_data()
            success = self.controller.update_card(self.selected_card_id, card_data)
            if success:
                messagebox.showinfo("Éxito", "Carta actualizada correctamente.")
                self._clear_form()
                self._reload_inventory()
            else:
                messagebox.showerror("Error", "No se pudo actualizar la carta.")
        except ValueError as e:
            messagebox.showerror("Error de validación", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Error al actualizar: {e}")

    def _on_delete_card(self):
        if not self.selected_card_id:
            messagebox.showwarning("Advertencia", "No hay ninguna carta seleccionada.")
            return
        if messagebox.askyesno("Confirmar", f"¿Eliminar la carta con ID {self.selected_card_id}?"):
            try:
                if self.controller.delete_card(self.selected_card_id):
                    messagebox.showinfo("Éxito", "Carta eliminada correctamente.")
                    self._clear_form()
                    self._reload_inventory()
                else:
                    messagebox.showerror("Error", "No se pudo eliminar la carta.")
            except Exception as e:
                messagebox.showerror("Error", f"Error al eliminar: {e}")

    def _on_card_selected(self, event):
        """Carga los datos de la carta seleccionada en el formulario."""
        tree = event.widget
        selected = tree.selection()
        if not selected:
            return

        card_id = int(tree.item(selected[0], 'tags')[0])
        self.selected_card_id = card_id
        tcg_card_id = tree.item(selected[0], 'text')

        self.input_vars['tcg_card_id_var'].set(tcg_card_id)

        if self.current_displayed_df is not None and card_id in self.current_displayed_df.index:
            row = self.current_displayed_df.loc[card_id]
            self.input_vars['count_var'].set(str(row['count']))
            self.input_vars['language_var'].set(row['language'])
            self.input_vars['foil_type_var'].set(row['foil_type'])
            self.input_vars['stamp_var'].set(row['stamp'] if row['stamp'] else 'None')
            self.input_vars['condition_var'].set(row['condition'])

        self.update_button.config(state=tk.NORMAL)
        self.delete_button.config(state=tk.NORMAL)
        self.add_button.config(text="➕ Añadir Nueva Carta")

        # Cargar imagen en el panel derecho
        asyncio.create_task(self._load_card_image(tcg_card_id))

    async def _load_card_image(self, tcg_card_id: str):
        """Descarga y muestra la imagen de una carta en el panel lateral."""
        import concurrent.futures

        self.image_label.config(image='', text="⏳ Cargando imagen...")
        self._card_image_ref = None

        try:
            card_data = await asyncio.wait_for(
                self.controller.api_service.tcgdex.card.get(tcg_card_id),
                timeout=10.0
            )

            if not (hasattr(card_data, 'image') and card_data.image):
                self.image_label.config(text="Sin imagen disponible")
                return

            image_url = f"{card_data.image}/high.png"

            def download():
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(image_url, context=ctx, timeout=10) as r:
                    return r.read()

            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                data = await asyncio.wait_for(
                    loop.run_in_executor(pool, download),
                    timeout=15.0
                )

            # Guardar los bytes originales y renderizar al tamaño actual del panel
            self._card_image_data = data
            self._render_image()

        except asyncio.TimeoutError:
            self.image_label.config(image='', text="⏱️ Timeout\ncargando imagen")
        except Exception as e:
            self.image_label.config(image='', text=f"❌ Error\n{str(e)[:40]}")

    def _render_image(self, panel_w: int = 0, panel_h: int = 0):
        """Escala la imagen original al tamaño indicado y la muestra."""
        if self._card_image_data is None:
            return

        # Si no se pasan dimensiones, leerlas del widget (usado al cargar por primera vez)
        if panel_w < 10 or panel_h < 10:
            panel_w = self.image_label.master.winfo_width()
            panel_h = self.image_label.master.winfo_height()

        if panel_w < 10 or panel_h < 10:
            return

        # Descontar padding interno del panel (10px a cada lado)
        panel_w = max(panel_w - 20, 1)
        panel_h = max(panel_h - 20, 1)

        image = Image.open(BytesIO(self._card_image_data))
        image.load()

        # Escalar con object-fit: contain — mantiene proporción sin recortar
        img_ratio = image.width / image.height
        panel_ratio = panel_w / panel_h

        if img_ratio > panel_ratio:
            new_w = panel_w
            new_h = int(panel_w / img_ratio)
        else:
            new_h = panel_h
            new_w = int(panel_h * img_ratio)

        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        self._card_image_ref = photo
        self.image_label.config(image=photo, text="")

    def _on_image_panel_resized(self, event):
        """Re-escala la imagen cuando el panel lateral cambia de tamaño."""
        # event.width y event.height son el nuevo tamaño del Frame contenedor
        self._render_image(panel_w=event.width, panel_h=event.height)

    @async_handler
    async def _on_card_double_clicked(self, event):
        """Abre la ventana de detalles al hacer doble clic."""
        tree = event.widget
        selected = tree.selection()
        if not selected:
            return
        try:
            card_id = int(tree.item(selected[0], 'tags')[0])
            if self.current_displayed_df is None or card_id not in self.current_displayed_df.index:
                return
            card_row = self.current_displayed_df.loc[card_id]
            tcg_card_id = card_row['tcg_card_id']
            CardDetailsWindow(self.master, self.controller.api_service, tcg_card_id, card_row, card_id)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir los detalles: {e}")

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _display(self, df):
        """Renderiza el DataFrame en la tabla de resultados."""
        for widget in self.result_frame.winfo_children():
            widget.destroy()

        if df is None or df.empty:
            ttk.Label(self.result_frame, text="Inventario vacío o sin coincidencias.").pack(pady=10)
            return

        tree_frame = ttk.Frame(self.result_frame)
        tree_frame.pack(fill='both', expand=True)

        if 'card_name' in df.columns:
            cols = ['card_local_number', 'card_name', 'edition_name', 'language', 'foil_type', 'stamp', 'condition', 'count']
        else:
            cols = ['language', 'foil_type', 'stamp', 'condition', 'count']
        cols = [c for c in cols if c in df.columns]

        tree = ttk.Treeview(tree_frame, columns=cols, show='tree headings', height=15)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        column_widths = {
            'card_local_number': 70, 'card_name': 180, 'edition_name': 150,
            'language': 70, 'foil_type': 120, 'stamp': 120, 'condition': 80, 'count': 70
        }

        # La columna #0 guarda el tcg_card_id internamente pero no se muestra.
        # El funcionamiento al hacer click depende del tag (card_id), no de esta columna.
        tree.column('#0', width=0, minwidth=0, stretch=False)

        for col in cols:
            header = DISPLAY_HEADERS.get(col, col.replace('_', ' ').title())
            tree.heading(col, text=f"{header} ▲▼", command=lambda c=col: self._sort_column(tree, c, False))
            tree.column(col, anchor=tk.W, width=column_widths.get(col, 100))

        for index, row in df.iterrows():
            tree.insert("", tk.END, text=row['tcg_card_id'], values=[row[c] for c in cols], tags=(str(index),))

        tree.bind('<<TreeviewSelect>>', self._on_card_selected)
        tree.bind('<Double-1>', self._on_card_double_clicked)

        self.current_tree = tree
        self.current_displayed_df = df

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _get_form_data(self) -> dict:
        """Extrae los datos del formulario como dict."""
        return {
            'tcg_card_id': self.input_vars['tcg_card_id_var'].get().strip(),
            'count': int(self.input_vars['count_var'].get()),
            'language': self.input_vars['language_var'].get().strip(),
            'foil_type': self.input_vars['foil_type_var'].get().strip(),
            'stamp': self.input_vars['stamp_var'].get().strip(),
            'condition': self.input_vars['condition_var'].get().strip(),
        }

    def _get_current_filters(self) -> dict:
        """Construye el dict de filtros desde los combos de la UI."""
        return {key: var.get() for key, var in self.filter_vars.items()}

    def _clear_form(self):
        for var in self.input_vars.values():
            var.set('')
        self.selected_card_id = None
        self.update_button.config(state=tk.DISABLED)
        self.delete_button.config(state=tk.DISABLED)
        self.add_button.config(text="➕ Añadir al Inventario")

    def _clear_all_filters(self):
        for var in self.filter_vars.values():
            var.set('')
        self.search_entry.delete(0, tk.END)
        df = self.controller.enriched_df or self.controller.inventory_df
        self._display(df)
        self.filter_label.config(text="")

    def _update_filter_options(self, df):
        """Actualiza los valores disponibles en el combo de edición."""
        if df.empty:
            return

        # Extraer los set_ids presentes en el DataFrame actual
        set_ids = df['tcg_card_id'].apply(
            lambda x: x.split('-')[0] if '-' in str(x) else ''
        ).unique()
        set_ids = [s for s in set_ids if s]

        # Convertir a nombres legibles usando el cache del controller
        display_names = sorted(
            self.controller.sets_cache.get_name(sid) for sid in set_ids
        )

        # Preservar la selección actual si sigue siendo válida
        current = self.filter_vars['set'].get()
        self.set_combo['values'] = [''] + display_names
        if current and current not in display_names:
            self.filter_vars['set'].set('')

    def _sort_column(self, tree, col, reverse):
        items = [(tree.set(item, col), item) for item in tree.get_children('')]
        try:
            items.sort(key=lambda x: float(x[0]) if x[0] not in ['N/A', ''] else float('inf'), reverse=reverse)
        except (ValueError, TypeError):
            items.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)
        for i, (_, item) in enumerate(items):
            tree.move(item, '', i)
        tree.heading(col, command=lambda: self._sort_column(tree, col, not reverse))

    def _sort_by_tcg_id(self, tree, reverse=False):
        def key(item):
            tcg_id = item[0]
            if '-' in tcg_id:
                set_id, num = tcg_id.rsplit('-', 1)
                try:
                    return (set_id, int(num))
                except ValueError:
                    return (set_id, num)
            return (tcg_id, 0)
        items = [(tree.item(item, 'text'), item) for item in tree.get_children('')]
        items.sort(key=key, reverse=reverse)
        for i, (_, item) in enumerate(items):
            tree.move(item, '', i)
        tree.heading('#0', command=lambda: self._sort_by_tcg_id(tree, not reverse))

    def _open_card_browser(self):
        CardBrowserWindow(self.master, self)


# ----------------------------------------------------------------------
# Ventanas auxiliares (sin cambios estructurales, solo limpieza menor)
# ----------------------------------------------------------------------

class CardDetailsWindow:
    """Ventana emergente con los detalles completos de una carta."""

    def __init__(self, parent, api_service, tcg_card_id, inventory_data, card_id):
        self.window = tk.Toplevel(parent)
        self.window.title("📇 Detalles de la Carta")
        self.window.geometry("900x650")
        self.window.transient(parent)

        self.api_service = api_service
        self.tcg_card_id = tcg_card_id
        self.inventory_data = inventory_data
        self.card_id = card_id
        self.card_image = None

        self.main_frame = ttk.Frame(self.window, padding="15")
        self.main_frame.pack(fill='both', expand=True)

        self.loading_label = ttk.Label(self.main_frame, text="⏳ Cargando información...", font=('', 11))
        self.loading_label.pack(pady=50)

        self._load_data()

    @async_handler
    async def _load_data(self):
        try:
            card_data = await asyncio.wait_for(
                self.api_service.tcgdex.card.get(self.tcg_card_id),
                timeout=10.0
            )
            self.loading_label.destroy()
            self._display_info(card_data)

            if hasattr(card_data, 'image') and card_data.image:
                image_url = f"{card_data.image}/high.png" if isinstance(card_data.image, str) else None
                if image_url and hasattr(self, 'image_label'):
                    await self._load_image(image_url)

        except asyncio.TimeoutError:
            self.loading_label.config(text="⏱️ Timeout al cargar. Intenta de nuevo.", foreground="orange")
        except Exception as e:
            self.loading_label.config(text=f"❌ Error: {e}", foreground="red")

    def _display_info(self, card_data):
        """Construye el layout de información de la carta."""
        content = ttk.Frame(self.main_frame)
        content.pack(fill='both', expand=True)

        # Panel izquierdo: imagen
        left = ttk.Frame(content, width=200)
        left.pack(side=tk.LEFT, fill='y', padx=(0, 15))
        self.image_label = ttk.Label(left, text="⏳ Cargando imagen...")
        self.image_label.pack()

        # Panel derecho: scrollable info
        right = ttk.Frame(content)
        right.pack(side=tk.LEFT, fill='both', expand=True)

        canvas = tk.Canvas(right)
        scrollbar = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill='both', expand=True)
        scrollbar.pack(side=tk.RIGHT, fill='y')

        # Datos básicos
        api_section = ttk.LabelFrame(scrollable_frame, text="📋 Información de la Carta", padding="10")
        api_section.pack(fill='x', pady=(0, 10))

        info_rows = [
            ("Nombre:", getattr(card_data, 'name', 'N/A')),
            ("Edición:", getattr(card_data.set, 'name', 'N/A') if hasattr(card_data, 'set') else 'N/A'),
            ("Número:", getattr(card_data, 'localId', 'N/A')),
            ("ID Global:", getattr(card_data, 'id', 'N/A')),
            ("Rareza:", getattr(card_data, 'rarity', 'N/A')),
            ("HP:", str(getattr(card_data, 'hp', 'N/A'))),
        ]

        # Datos del inventario
        inv_section = ttk.LabelFrame(scrollable_frame, text="📦 En tu Inventario", padding="10")
        inv_section.pack(fill='x', pady=(0, 10))
        for i, (label, value) in enumerate([
            ("ID Inventario:", str(self.card_id)),
            ("Cantidad:", str(self.inventory_data.get('count', 'N/A'))),
            ("Idioma:", str(self.inventory_data.get('language', 'N/A'))),
            ("Brillo:", str(self.inventory_data.get('foil_type', 'N/A'))),
            ("Condición:", str(self.inventory_data.get('condition', 'N/A'))),
        ]):
            ttk.Label(inv_section, text=label, font=('', 9, 'bold')).grid(row=i, column=0, sticky='w', pady=2, padx=(0, 10))
            ttk.Label(inv_section, text=value).grid(row=i, column=1, sticky='w', pady=2)

        for i, (label, value) in enumerate(info_rows):
            ttk.Label(api_section, text=label, font=('', 9, 'bold')).grid(row=i, column=0, sticky='w', pady=3, padx=(0, 10))
            ttk.Label(api_section, text=str(value)).grid(row=i, column=1, sticky='w', pady=3)

        # Ataques
        if hasattr(card_data, 'attacks') and card_data.attacks:
            attacks_section = ttk.LabelFrame(scrollable_frame, text="⚔️ Ataques", padding="10")
            attacks_section.pack(fill='x', pady=(0, 10))
            for i, attack in enumerate(card_data.attacks):
                name = getattr(attack, 'name', 'N/A')
                cost = ', '.join(getattr(attack, 'cost', [])) if hasattr(attack, 'cost') else 'N/A'
                damage = getattr(attack, 'damage', '-')
                effect = getattr(attack, 'effect', '')
                ttk.Label(attacks_section, text=f"{i+1}. {name}", font=('', 10, 'bold')).pack(anchor='w', pady=(5 if i > 0 else 0, 2))
                ttk.Label(attacks_section, text=f"   Costo: {cost} | Daño: {damage}").pack(anchor='w')
                if effect:
                    ttk.Label(attacks_section, text=f"   Efecto: {effect}", wraplength=400, foreground='gray').pack(anchor='w', pady=(0, 5))

    async def _load_image(self, image_url: str):
        try:
            def download():
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(image_url, context=ctx, timeout=10) as r:
                    return r.read()

            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                data = await asyncio.wait_for(loop.run_in_executor(pool, download), timeout=15.0)

            image = Image.open(BytesIO(data))
            image.load()
            ratio = 400 / image.height
            image = image.resize((int(image.width * ratio), 400), Image.Resampling.LANCZOS)
            self.card_image = ImageTk.PhotoImage(image)
            self.image_label.image = self.card_image
            self.image_label.config(image=self.card_image, text="")
        except asyncio.TimeoutError:
            self.image_label.config(text="⏱️ Imagen no disponible")
        except Exception as e:
            self.image_label.config(text=f"❌ Error al cargar imagen")


class CardBrowserWindow:
    """Ventana para buscar cartas en la API y seleccionarlas."""

    def __init__(self, parent, main_app):
        self.main_app = main_app
        self.window = tk.Toplevel(parent)
        self.window.title("🔍 Buscador de Cartas")
        self.window.geometry("900x600")
        self.window.transient(parent)

        self.api_service = TCGdexService()
        self.search_results = []
        self._create_widgets()

    def _create_widgets(self):
        search_frame = ttk.Frame(self.window, padding="10")
        search_frame.pack(fill='x')

        ttk.Label(search_frame, text="Buscar carta:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 10))
        entry.bind('<Return>', lambda e: self._search())
        entry.focus()

        self.search_button = ttk.Button(search_frame, text="🔍 Buscar en API", command=self._search)
        self.search_button.pack(side=tk.LEFT)

        ttk.Separator(self.window, orient='horizontal').pack(fill='x', pady=5)

        result_frame = ttk.LabelFrame(self.window, text="📋 Resultados (doble clic para seleccionar)", padding="10")
        result_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        container = ttk.Frame(result_frame)
        container.pack(fill='both', expand=True)

        cols = ('name', 'set_name', 'number', 'id', 'rarity')
        self.tree = ttk.Treeview(container, columns=cols, show='headings')
        vsb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        for col, text, width in [('name', 'Nombre', 200), ('set_name', 'Edición', 200),
                                   ('number', '# Carta', 80), ('id', 'ID Global', 150), ('rarity', 'Rareza', 120)]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=tk.CENTER if col == 'number' else tk.W)

        self.tree.pack(side=tk.LEFT, fill='both', expand=True)
        vsb.pack(side=tk.RIGHT, fill='y')
        self.tree.bind('<Double-1>', self._select_card)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.select_button.config(state=tk.NORMAL if self.tree.selection() else tk.DISABLED))

        btn_frame = ttk.Frame(self.window, padding="10")
        btn_frame.pack(fill='x')
        self.select_button = ttk.Button(btn_frame, text="✅ Seleccionar", command=self._select_card, state=tk.DISABLED)
        self.select_button.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="❌ Cancelar", command=self.window.destroy).pack(side=tk.LEFT)
        self.info_label = ttk.Label(btn_frame, text="💡 Escribe el nombre y presiona Enter", foreground="gray")
        self.info_label.pack(side=tk.RIGHT)

    @async_handler
    async def _search(self):
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Advertencia", "Introduce un nombre de carta.")
            return

        self.search_button.config(state=tk.DISABLED, text="Buscando...")
        self.info_label.config(text="⏳ Buscando en la API...")
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            resumes = await self.api_service.tcgdex.card.list(Query().contains("name", query))
            if not resumes:
                self.info_label.config(text="❌ No se encontraron cartas", foreground="red")
                return

            self.info_label.config(text=f"⏳ Obteniendo detalles de {len(resumes)} cartas...")
            cards = await asyncio.gather(*[self.api_service.tcgdex.card.get(r.id) for r in resumes], return_exceptions=True)

            self.search_results = []
            for card in cards:
                if not isinstance(card, Exception):
                    self.search_results.append(card)
                    self.tree.insert('', tk.END, values=(
                        getattr(card, 'name', 'N/A'),
                        getattr(card.set, 'name', 'N/A') if hasattr(card, 'set') else 'N/A',
                        getattr(card, 'localId', 'N/A'),
                        getattr(card, 'id', 'N/A'),
                        getattr(card, 'rarity', 'N/A'),
                    ))
            self.info_label.config(text=f"✅ {len(self.search_results)} cartas encontradas", foreground="green")

        except Exception as e:
            self.info_label.config(text=f"❌ Error: {e}", foreground="red")
        finally:
            self.search_button.config(state=tk.NORMAL, text="🔍 Buscar en API")

    def _select_card(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        card_id = self.tree.item(selected[0], 'values')[3]
        self.main_app.input_vars['tcg_card_id_var'].set(card_id)
        messagebox.showinfo("Carta Seleccionada", f"ID: {card_id}\n\nCompleta los demás campos y presiona Añadir.")
        self.window.destroy()