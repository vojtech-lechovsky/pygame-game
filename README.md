# 2D Platform Game

A 2D platform game written in Python using Pygame, featuring movement, collisions, jumping, animations, multiple levels, moving platforms, and snake enemies. The project uses custom game logic without a dedicated physics engine.

# Short Video Demonstration

https://github.com/user-attachments/assets/e58d3d13-b8c3-47c2-9ffc-0cf7af6f36f4

# Game Controls
| Input | Description |
| - | - |
| `WASD` | Player movement |
| `Mouse Left` | Attack animation |
| `E` | Enter door |
| `Q` | Restart level |

# How To Run
Either download and run the PygameGame.exe file, or run the game from source using the commands below.

## Windows 11 CMD
```batch
git clone https://github.com/vojtech-lechovsky/pygame-game.git
cd pygame-game
py install 3.12
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python src\main.py
```

## Windows 11 PowerShell
```powershell
git clone https://github.com/vojtech-lechovsky/pygame-game.git
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
git clone https://github.com/vojtech-lechovsky/pygame-game.git
cd pygame-game
sudo apt install python3.12-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 src/main.py
```
