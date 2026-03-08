import datetime
import os
import subprocess
import zipfile

INSTRUCTIONS_FILE = "devops_update.txt"

BACKUP_DIR = "backups"
LOG_DIR = "logs"

LOG_FILE = os.path.join(LOG_DIR, "operations.log")

AUTO_BACKUP_ALWAYS = True
KEEP_LAST_BACKUPS = 3


# ------------------------
# UTIL
# ------------------------


def timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def log(msg):
    ensure_dir(LOG_DIR)

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

    print(msg, flush=True)


# ------------------------
# BACKUP
# ------------------------


def list_backups():
    ensure_dir(BACKUP_DIR)

    files = [
        os.path.join(BACKUP_DIR, f)
        for f in os.listdir(BACKUP_DIR)
        if f.startswith("backup_") and f.endswith(".zip")
    ]

    files.sort()
    return files


def cleanup_old_backups():
    backups = list_backups()

    if len(backups) <= KEEP_LAST_BACKUPS:
        return

    old = backups[:-KEEP_LAST_BACKUPS]

    for f in old:
        try:
            os.remove(f)
            log(f"Deleted old backup {f}")
        except Exception as e:
            log(f"Cannot delete {f}: {e}")


def backup_repository():
    ensure_dir(BACKUP_DIR)

    ts = timestamp()
    zip_path = os.path.join(BACKUP_DIR, f"backup_{ts}.zip")

    log(f"Starting backup {zip_path}")

    excluded_dirs = {
        ".git",
        BACKUP_DIR,
        LOG_DIR,
        "__pycache__",
        "build",
        "dist",
        ".venv",
        "venv",
        "env",
        "ENV",
        ".pytest_cache",
        ".mypy_cache",
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in excluded_dirs]

            for file in files:
                if file.endswith((".pyc", ".pyo", ".pyd")):
                    continue

                src = os.path.join(root, file)
                rel = os.path.relpath(src, ".")

                z.write(src, rel)

    log(f"Backup created {zip_path}")

    cleanup_old_backups()

    return zip_path


def latest_backup():
    backups = list_backups()

    if not backups:
        return None

    return backups[-1]


def restore_backup(zip_path):
    if not zip_path or not os.path.exists(zip_path):
        log("Backup zip not found")
        return False

    log(f"RESTORE from {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(".")

    log("RESTORE completed")
    return True


def restore_last_backup():
    z = latest_backup()

    if not z:
        log("No backup available")
        return False

    return restore_backup(z)


# ------------------------
# FILE OPS
# ------------------------


def create_folder(path):
    if os.path.exists(path):
        log(f"[SKIP] folder exists {path}")
        return

    os.makedirs(path, exist_ok=True)
    log(f"[CREATE] folder {path}")


def create_file(path, content):
    ensure_dir(os.path.dirname(path))

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            existing = f.read()

        if existing == content:
            log(f"[SKIP] file identical {path}")
            return

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    log(f"[CREATE] file {path}")


def append_file(path, content):
    ensure_dir(os.path.dirname(path))

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            existing = f.read()

        normalized = content.strip()

        if normalized and normalized in existing:
            log(f"[SKIP] content already present in {path}")
            return

    with open(path, "a", encoding="utf-8") as f:
        if content and not content.startswith("\n"):
            f.write("\n")
        f.write(content)

    log(f"[MODIFY] append {path}")


# ------------------------
# CLEAN WHITESPACE
# ------------------------


def fix_whitespace():
    for root, dirs, files in os.walk("."):
        if ".git" in root:
            continue

        if root.startswith(f".{os.sep}{BACKUP_DIR}") or root == BACKUP_DIR:
            continue

        if root.startswith(f".{os.sep}{LOG_DIR}") or root == LOG_DIR:
            continue

        for file in files:
            if not file.endswith(
                (".py", ".txt", ".md", ".yml", ".yaml", ".json", ".ini")
            ):
                continue

            path = os.path.join(root, file)

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            new_lines = []

            for line in lines:
                line = line.rstrip()
                line = line.replace("\t", "    ")
                new_lines.append(line + "\n")

            while new_lines and new_lines[-1].strip() == "":
                new_lines.pop()

            new_lines.append("\n")

            with open(path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

    log("Whitespace fixed")


# ------------------------
# FORMAT + LINT + TEST
# ------------------------


def run_black():
    log("Running Black")
    subprocess.run(["black", "."], check=False)


def run_isort():
    log("Running isort")
    subprocess.run(["isort", "."], check=False)


def run_ruff():
    log("Running ruff")
    subprocess.run(["ruff", "check", ".", "--fix"], check=False)


def run_pytest():
    log("Running pytest")

    result = subprocess.run(
        ["pytest", "-v"],
        capture_output=True,
        text=True,
    )

    print(result.stdout, flush=True)
    print(result.stderr, flush=True)

    if result.returncode != 0:
        log("Tests FAILED")
        return False

    log("Tests PASSED")
    return True


# ------------------------
# PARSER HELPERS
# ------------------------


def read_block(lines, start_index):
    content = []
    i = start_index

    while i < len(lines) and lines[i].strip() != "EOF":
        content.append(lines[i])
        i += 1

    return "".join(content), i


# ------------------------
# PROCESS
# ------------------------


def process():
    if not os.path.exists(INSTRUCTIONS_FILE):
        log("No instruction file")
        return

    if AUTO_BACKUP_ALWAYS:
        backup_repository()

    with open(INSTRUCTIONS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line or line.startswith("#"):
            i += 1
            continue

        parts = line.split()
        cmd = parts[0]

        if cmd == "AUTO_BACKUP_BEFORE_RUN":
            backup_repository()
            i += 1
            continue

        if cmd in ["CREA_CARTELLA", "CREATE_FOLDER"]:
            create_folder(parts[1])
            i += 1
            continue

        if cmd in ["CREA_FILE", "CREATE_FILE"]:
            path = parts[1]

            i += 1
            content, i = read_block(lines, i)

            create_file(path, content)

            if i < len(lines) and lines[i].strip() == "EOF":
                i += 1

            continue

        if cmd in ["APPEND", "AGGIUNGI"]:
            path = parts[1]

            i += 1
            content, i = read_block(lines, i)

            append_file(path, content)

            if i < len(lines) and lines[i].strip() == "EOF":
                i += 1

            continue

        if cmd == "FIX_WHITESPACE":
            fix_whitespace()
            i += 1
            continue

        log(f"[WARN] Unknown command: {line}")
        i += 1

    try:
        fix_whitespace()
        run_black()
        run_isort()
        run_ruff()

        ok = run_pytest()
        if not ok:
            raise RuntimeError("Tests failed")

    except Exception as e:
        log(f"CI FAILED: {e}")
        restore_last_backup()
        raise


if __name__ == "__main__":
    process()
