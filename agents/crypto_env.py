import os
import json
from pathlib import Path
from cryptography.fernet import Fernet

ENC_FILE_PATH = Path(".env.enc")

def load_encrypted_env(key: str | None = None) -> dict:
    """
    Decrypts .env.enc directly into RAM and injects into os.environ.
    Zero-disk-leakage for sensitive production runs.
    """
    master_key = key or os.getenv("AGENT_MASTER_KEY")
    if not master_key:
        master_key = input("🔑 Enter AGENT_MASTER_KEY: ").strip()

    cipher_suite = Fernet(master_key.encode())
    if not ENC_FILE_PATH.exists():
        # Fallback to standard .env if present (e.g. initial dev setup)
        env_fallback = Path(".env")
        if env_fallback.exists():
            from dotenv import dotenv_values
            vals = dotenv_values(env_fallback)
            for k, v in vals.items():
                if v is not None:
                    os.environ[k] = str(v)
            return dict(vals)
        raise FileNotFoundError(f"Neither {ENC_FILE_PATH} nor .env found.")

    with open(ENC_FILE_PATH, "rb") as f:
        encrypted_data = f.read()

    decrypted_bytes = cipher_suite.decrypt(encrypted_data)
    config = json.loads(decrypted_bytes.decode("utf-8"))

    # Restore bundled config files if present in encrypted payload
    bundled_files = config.pop("_bundled_files", {})
    for rel_path, content_str in bundled_files.items():
        file_path = Path(rel_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content_str)
            print(f"[CryptoEnv] Restored secure config file: {rel_path}")

    # Injeksi ke os.environ dalam runtime RAM
    for k, v in config.items():
        os.environ[k] = str(v)

    return config

def encrypt_dict_to_file(data: dict, master_key: str, out_path: Path = ENC_FILE_PATH, bundle_configs: bool = True):
    """
    Encrypts a dictionary of credentials into .env.enc using Fernet.
    Optionally bundles sensitive config files (cookies & service account).
    """
    payload = dict(data)
    if bundle_configs:
        bundled = {}
        for target_file in [
            Path("config/service_account.json"),
            Path("config/linkedin_cookies.json"),
            Path("config/linkedin_state.json"),
            Path("config/indeed_cookies.json"),
            Path("config/indeed_state.json")
        ]:
            if target_file.exists():
                with open(target_file, "r", encoding="utf-8") as f:
                    bundled[str(target_file).replace("\\", "/")] = f.read()
        payload["_bundled_files"] = bundled

    cipher_suite = Fernet(master_key.encode())
    raw_json = json.dumps(payload, indent=2).encode("utf-8")
    encrypted_bytes = cipher_suite.encrypt(raw_json)
    with open(out_path, "wb") as f:
        f.write(encrypted_bytes)
