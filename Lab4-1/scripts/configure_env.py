"""Create a local secret without printing it or overwriting existing configuration."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / '.env'
if target.exists():
    print('Existing .env retained.')
else:
    text = (root / '.env.example').read_text(encoding='utf-8')
    target.write_text(text.replace('replace-with-a-random-secret-of-at-least-32-characters', secrets.token_hex(32)), encoding='utf-8')
    print('Created local .env; secret not displayed.')
