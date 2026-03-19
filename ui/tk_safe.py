try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
except Exception:
    class _DummyCallable:
        def __call__(self, *args, **kwargs):
            return None

        def __getattr__(self, name):
            return self

        def pack(self, *args, **kwargs):
            return None

        def grid(self, *args, **kwargs):
            return None

        def place(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        config = configure

        def bind(self, *args, **kwargs):
            return None

        def destroy(self, *args, **kwargs):
            return None

        def insert(self, *args, **kwargs):
            return None

        def delete(self, *args, **kwargs):
            return None

        def get(self, *args, **kwargs):
            return ""

        def set(self, *args, **kwargs):
            return None

        def focus(self, *args, **kwargs):
            return None

        def pack_forget(self, *args, **kwargs):
            return None

        def yview(self, *args, **kwargs):
            return None

        def xview(self, *args, **kwargs):
            return None

        def create_window(self, *args, **kwargs):
            return None

        def itemconfig(self, *args, **kwargs):
            return None

        def bbox(self, *args, **kwargs):
            return (0, 0, 0, 0)

        def after(self, *args, **kwargs):
            return None

        def after_cancel(self, *args, **kwargs):
            return None

        def protocol(self, *args, **kwargs):
            return None

        def transient(self, *args, **kwargs):
            return None

        def grab_set(self, *args, **kwargs):
            return None

        def update_idletasks(self, *args, **kwargs):
            return None

        def winfo_screenwidth(self, *args, **kwargs):
            return 1024

        def winfo_screenheight(self, *args, **kwargs):
            return 768

        def winfo_exists(self, *args, **kwargs):
            return False

        def selection(self, *args, **kwargs):
            return []

        def focus_get(self, *args, **kwargs):
            return None

        def get_children(self, *args, **kwargs):
            return []

        def selection_set(self, *args, **kwargs):
            return None

        def focus_set(self, *args, **kwargs):
            return None

        def tk_popup(self, *args, **kwargs):
            return None

        def grab_release(self, *args, **kwargs):
            return None

    class _DummyTkModule(_DummyCallable):
        BOTH = "both"
        LEFT = "left"
        RIGHT = "right"
        X = "x"
        Y = "y"
        W = "w"
        E = "e"
        N = "n"
        S = "s"
        END = "end"
        DISABLED = "disabled"
        NORMAL = "normal"
        VERTICAL = "vertical"

        StringVar = _DummyCallable
        BooleanVar = _DummyCallable
        Menu = _DummyCallable
        Toplevel = _DummyCallable
        Canvas = _DummyCallable

    tk = _DummyTkModule()
    messagebox = _DummyCallable()
    filedialog = _DummyCallable()
    scrolledtext = _DummyCallable()
    ttk = _DummyCallable()
