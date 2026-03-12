from types import SimpleNamespace

from controllers.telegram_controller import TelegramController


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DummyLabel:
    def __init__(self):
        self.last = None

    def configure(self, **kwargs):
        self.last = kwargs


class DummyDB:
    def __init__(self):
        self.saved = None

    def get_telegram_settings(self):
        return {"session_string": "abc"}

    def save_telegram_settings(self, data):
        self.saved = data


class DummyExecutor:
    def submit(self, _name, fn):
        return fn()


class DummyUIQ:
    def post(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyApp:
    def __init__(self):
        self.db = DummyDB()
        self.executor = DummyExecutor()
        self.uiq = DummyUIQ()
        self.telegram_listener = None
        self.tg_api_id_var = DummyVar("123")
        self.tg_api_hash_var = DummyVar("hash")
        self.tg_phone_var = DummyVar("+39000")
        self.tg_auto_bet_var = DummyVar(True)
        self.tg_confirm_var = DummyVar(False)
        self.tg_auto_stake_var = DummyVar("2.5")
        self.tg_code_var = DummyVar("")
        self.tg_2fa_var = DummyVar("")
        self.tg_status_label = DummyLabel()
        self.tg_available_status = DummyLabel()
        self.tg_available_tree = SimpleNamespace(delete=lambda *a, **k: None, get_children=lambda: [])


def test_telegram_controller_save_settings(monkeypatch):
    app = DummyApp()
    ctrl = TelegramController(app)
    calls = []
    monkeypatch.setattr("controllers.telegram_controller.messagebox.showinfo", lambda *a, **k: calls.append((a, k)))
    ctrl.save_settings()
    assert app.db.saved["api_id"] == "123"
    assert app.db.saved["api_hash"] == "hash"
    assert app.db.saved["auto_stake"] == 2.5
    assert len(calls) == 1


def test_telegram_controller_session_path_contains_pickfair(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = DummyApp()
    ctrl = TelegramController(app)
    path = ctrl._get_session_path()
    assert "Pickfair" in path
    assert path.endswith("telegram_session")
