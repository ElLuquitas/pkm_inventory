"""Punto de entrada de la aplicación."""

import tkinter as tk
from async_tkinter_loop import async_mainloop
from src.gui import InventoryApp


def main():
    """Función principal."""
    root = tk.Tk()
    app = InventoryApp(root)
    async_mainloop(root)


if __name__ == "__main__":
    main()