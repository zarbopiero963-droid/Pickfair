import threading

class TreeManager:
    """
    Gestisce l'aggiornamento dei Treeview in modo intelligente.
    Evita il flickering, mantiene le selezioni e i nodi aperti.
    """
    def __init__(self, tree):
        self.tree = tree
        self._lock = threading.Lock()

    def _save_state(self):
        """Salva quali nodi sono aperti e cosa è selezionato."""
        open_nodes = set()
        for item in self.tree.get_children():
            if self.tree.item(item, "open"):
                open_nodes.add(item)
                
            # Cerca anche nei sotto-nodi (livello 2)
            for child in self.tree.get_children(item):
                if self.tree.item(child, "open"):
                    open_nodes.add(child)

        selected = self.tree.selection()
        return open_nodes, selected

    def _restore_state(self, open_nodes, selected):
        """Ripristina lo stato precedente."""
        for item in open_nodes:
            if self.tree.exists(item):
                self.tree.item(item, open=True)

        for sel in selected:
            if self.tree.exists(sel):
                self.tree.selection_add(sel)

    def update_hierarchical(self, data, parent_getter, id_getter, text_getter, values_getter):
        """
        Aggiornamento incrementale per alberi gerarchici (es. Nazione -> Partita).
        - data: lista di dizionari con i dati
        - parent_getter: funzione per ottenere l'id del nodo padre (es. nazione)
        - id_getter: funzione per ottenere l'id univoco della riga
        """
        with self._lock:
            open_nodes, selected = self._save_state()

            # Mappa degli elementi esistenti
            existing_parents = set(self.tree.get_children(''))
            existing_children = set()
            for parent in existing_parents:
                existing_children.update(self.tree.get_children(parent))

            new_parents = set()
            new_children = set()

            for item_data in data:
                parent_id = str(parent_getter(item_data))
                item_id = str(id_getter(item_data))
                item_text = text_getter(item_data)
                item_values = values_getter(item_data)

                # Gestione del nodo padre (es. Nazione)
                if parent_id not in new_parents:
                    new_parents.add(parent_id)
                    if parent_id not in existing_parents:
                        self.tree.insert('', 'end', iid=parent_id, text=parent_id, open=False)

                # Gestione del nodo figlio (es. Partita)
                new_children.add(item_id)
                if item_id in existing_children:
                    # Aggiorna solo se i valori sono cambiati
                    current_values = self.tree.item(item_id, "values")
                    if str(current_values) != str(tuple(str(v) for v in item_values)):
                        self.tree.item(item_id, values=item_values)
                else:
                    self.tree.insert(parent_id, 'end', iid=item_id, text='', values=item_values)

            # Rimozione elementi non più presenti
            for child_id in existing_children:
                if child_id not in new_children:
                    if self.tree.exists(child_id):
                        self.tree.delete(child_id)

            for parent_id in existing_parents:
                if parent_id not in new_parents:
                    if self.tree.exists(parent_id):
                        self.tree.delete(parent_id)

            self._restore_state(open_nodes, selected)

    def update_flat(self, data, id_getter, values_getter, tags_getter=None):
        """
        Aggiornamento incrementale per alberi piatti (es. Lista Runner).
        """
        with self._lock:
            open_nodes, selected = self._save_state()
            existing_items = set(self.tree.get_children(''))
            new_items = set()

            for item_data in data:
                item_id = str(id_getter(item_data))
                item_values = values_getter(item_data)
                item_tags = tags_getter(item_data) if tags_getter else ()
                
                new_items.add(item_id)

                if item_id in existing_items:
                    # Ottimizzazione: aggiorna solo se necessario
                    current = self.tree.item(item_id)
                    current_values = current.get("values", [])
                    current_tags = current.get("tags", [])
                    
                    if str(current_values) != str(tuple(str(v) for v in item_values)) or list(current_tags) != list(item_tags):
                        self.tree.item(item_id, values=item_values, tags=item_tags)
                else:
                    self.tree.insert('', 'end', iid=item_id, values=item_values, tags=item_tags)

            # Rimuovi elementi spariti
            for item_id in existing_items:
                if item_id not in new_items:
                    if self.tree.exists(item_id):
                        self.tree.delete(item_id)

            self._restore_state(open_nodes, selected)