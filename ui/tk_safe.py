try:
    import tkinter as tk
    from tkinter import messagebox, filedialog, scrolledtext, ttk
except Exception:
    # fallback CI / headless
    class Dummy:
        def __getattr__(self, name):
            return lambda *a, **k: None

    tk = Dummy()
    messagebox = Dummy()
    filedialog = Dummy()
    scrolledtext = Dummy()
    ttk = Dummy()
