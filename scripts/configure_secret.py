"""Write an ignored local secret using hidden stdin, never command-line args."""
import os
import sys
from pathlib import Path

original_attributes = None
if sys.stdin.isatty():
    import termios
    original_attributes = termios.tcgetattr(sys.stdin)
    attributes = termios.tcgetattr(sys.stdin)
    attributes[3] &= ~termios.ECHO
    termios.tcsetattr(sys.stdin, termios.TCSANOW, attributes)
print('Ready for API key on hidden stdin.', flush=True)
try:
    value = sys.stdin.readline().strip()
finally:
    if original_attributes is not None:
        termios.tcsetattr(sys.stdin, termios.TCSANOW, original_attributes)
if not value or not value.isalnum() or len(value) < 20:
    raise SystemExit('Clave inválida')
path = Path(__file__).resolve().parents[1] / '.env'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('ODDS_API_KEY=' + value + '\nODDS_API_MONTHLY_BUDGET=450\nKRAKEN_PORT=8765\n')
os.chmod(path, 0o600)
print('Clave guardada localmente con permisos 600; excluida de Git.', flush=True)
