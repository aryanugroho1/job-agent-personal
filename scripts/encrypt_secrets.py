"""
Utility script to generate AGENT_MASTER_KEY and encrypt .env to .env.enc
"""
import sys
import os
from pathlib import Path

# Fix Windows encoding issues (e.g. CP932 / CP1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cryptography.fernet import Fernet
from dotenv import dotenv_values

def main():
    print("=== Environment Encryptor Utility ===")
    
    # Check if .env exists
    env_file = Path(".env")
    if not env_file.exists():
        print("[ERROR] File .env tidak ditemukan. Buat .env berdasarkan .env.example terlebih dahulu.")
        sys.exit(1)
        
    master_key = os.getenv("AGENT_MASTER_KEY")
    if not master_key and Path("AGENT_MASTER_KEY.txt").exists():
        master_key = Path("AGENT_MASTER_KEY.txt").read_text(encoding="utf-8").strip()
        print(f"[INFO] Menggunakan master key yang tersimpan di AGENT_MASTER_KEY.txt")

    if not master_key:
        generate = input("Generate master key baru? (y/n): ").strip().lower()
        if generate == 'y':
            master_key = Fernet.generate_key().decode()
            print("\n" + "=" * 60)
            print("[KEY] AGENT_MASTER_KEY BARU:")
            print(f"      {master_key}")
            print("=" * 60)
            print("SIMPAN KUNCI INI DI TEMPAT AMAN! Jangan simpan di repo Git.")
            print("Di Coolify, masukkan kunci ini ke Environment Variables sebagai AGENT_MASTER_KEY\n")
            
            # Save a backup locally (in .gitignore)
            with open("AGENT_MASTER_KEY.txt", "w", encoding="utf-8") as kf:
                kf.write(master_key)
            print("[INFO] Kunci juga telah disimpan sementara di AGENT_MASTER_KEY.txt (diabaikan oleh Git).")
        else:
            master_key = input("Masukkan AGENT_MASTER_KEY yang sudah ada: ").strip()

    vals = dotenv_values(env_file)
    from agents.crypto_env import encrypt_dict_to_file
    encrypt_dict_to_file(dict(vals), master_key, Path(".env.enc"), bundle_configs=True)
    print("\n[OK] Berhasil mengenkripsi .env dan file konfigurasi rahasia ke .env.enc!")
    print("[PACKED] File yang terbungkus aman dalam enkripsi:")
    print("   - .env")
    print("   - config/service_account.json (jika ada)")
    print("   - config/linkedin_cookies.json & linkedin_state.json (jika ada)")
    print("   - config/indeed_cookies.json & indeed_state.json (jika ada)")
    print("\n[SUCCESS] File .env.enc siap di-commit ke Git. Data rahasia Anda aman.")

if __name__ == "__main__":
    main()
