# How to run
Either download and run the PygameGame.exe file, or run the game from source using the commands below.

## Windows 11 CMD
```batch
git clone https://gitlab.com/vojtechlechovsky/pygame-game.git
cd pygame-game
py install 3.12
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python src\main.py
```

## Windows 11 PowerShell
```powershell
git clone https://gitlab.com/vojtechlechovsky/pygame-game.git
cd pygame-game
py install 3.12
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src\main.py
```

## Ubuntu 24.04
```bash
git clone https://gitlab.com/vojtechlechovsky/pygame-game.git
cd pygame-game
sudo apt install python3.12-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 src/main.py
```
