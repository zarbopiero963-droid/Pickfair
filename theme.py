"""
Pickfair Dark Theme for CustomTkinter
Professional trading interface colors
"""

COLORS = {
    'bg_dark': '#0b111a',
    'bg_surface': '#121a26',
    'bg_panel': '#1a2633',
    'bg_card': '#1f2d3d',
    'bg_hover': '#243447',
    
    'text_primary': '#e8eaed',
    'text_secondary': '#8fa0b5',
    'text_tertiary': '#5f7185',
    
    'back': '#1e88e5',
    'back_hover': '#1976d2',
    'back_light': '#bbdefb',
    
    'lay': '#e5399b',
    'lay_hover': '#d81b7a',
    'lay_light': '#f8bbd9',
    
    'profit': '#66bb6a',
    'profit_bg': '#1b3d1e',
    'loss': '#ef5350',
    'loss_bg': '#3d1b1b',
    
    'warning': '#ffc107',
    'info': '#26c6da',
    'info_hover': '#00acc1',
    'success': '#66bb6a',
    'error': '#ef5350',
    
    'border': '#2d3e50',
    'border_light': '#3d4f62',
    
    'button_primary': '#1e88e5',
    'button_secondary': '#455a64',
    'button_danger': '#ef5350',
    'button_success': '#66bb6a',
    
    # Treeview tag colors
    'clickable_back': '#0066cc',
    'clickable_lay': '#cc0066',
    'matched': '#28a745',
    'pending': '#ffc107',
    'partially_matched': '#17a2b8',
    'settled': '#6c757d',
}

FONTS = {
    'default': ('Segoe UI', 11),
    'small': ('Segoe UI', 10),
    'heading': ('Segoe UI', 13, 'bold'),
    'title': ('Segoe UI', 16, 'bold'),
    'mono': ('Consolas', 11),
    'mono_small': ('Consolas', 10),
}

def configure_customtkinter():
    """Configure CustomTkinter appearance settings."""
    import customtkinter as ctk
    
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

def get_treeview_style():
    """Return ttk Treeview style configuration for dark theme."""
    return {
        'Treeview': {
            'background': COLORS['bg_panel'],
            'foreground': COLORS['text_primary'],
            'fieldbackground': COLORS['bg_panel'],
            'font': FONTS['small'],
            'rowheight': 26,
        },
        'Treeview.Heading': {
            'background': COLORS['bg_surface'],
            'foreground': COLORS['text_primary'],
            'font': ('Segoe UI', 10, 'bold'),
        }
    }

def configure_ttk_dark_theme(style):
    """Configure ttk widgets for dark theme (Treeview, etc.)"""
    style.theme_use('clam')
    
    style.configure('Treeview',
                    background=COLORS['bg_panel'],
                    foreground=COLORS['text_primary'],
                    fieldbackground=COLORS['bg_panel'],
                    font=FONTS['small'],
                    rowheight=26)
    
    style.configure('Treeview.Heading',
                    background=COLORS['bg_surface'],
                    foreground=COLORS['text_primary'],
                    font=('Segoe UI', 10, 'bold'))
    
    style.map('Treeview',
              background=[('selected', COLORS['back'])],
              foreground=[('selected', '#ffffff')])
    
    style.map('Treeview.Heading',
              background=[('active', COLORS['bg_hover'])])
