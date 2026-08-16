# Kurulum

## Gereksinimler

- Python 3 (3.9+)
- Linux: X11 veya XWayland ile Wayland (`python3-venv` genellikle kurulu gelir)
- Windows: [python.org](https://www.python.org/downloads/) adresinden Python 3
  ("Add Python to PATH" seçeneği işaretli)

## Linux

### Yöntem A — `run.sh` ile çalıştır (önerilen)

1. Depoyu klonla ve içine gir:

   ```bash
   git clone https://github.com/kaganyuksek/keymap-overlay.git
   cd keymap-overlay
   ```

2. Başlatıcıyı çalıştır:

   ```bash
   ./run.sh
   ```

   İlk çalıştırmada script bir `.venv` sanal ortamı oluşturur ve PyQt6'yı kurar.
   Sonraki çalıştırmalarda yalnızca uygulamayı açar.

### Yöntem B — Manuel kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Windows

1. [python.org](https://www.python.org/downloads/) adresinden Python 3'ü kur ve
   **Add Python to PATH** seçeneğini işaretle.
2. Proje klasöründe bir terminal (PowerShell veya Komut İstemi) aç.
3. Sanal ortam oluştur ve etkinleştir:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   ```

4. Bağımlılıkları kur ve çalıştır:

   ```powershell
   pip install -r requirements.txt
   python main.py
   ```

## Tek dosyalık çalıştırılabilir oluşturma

Linux:

```bash
./build.sh
```

Windows:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name KeymapOverlay main.py
```

Çalıştırılabilir `dist/` içinde oluşur. `data/` ve `assets/` klasörlerini
çalıştırılabilirin yanında bulundurmayı unutma.

## Kullanım

- **Sürükle**: Pencereyi taşımak için sol üstteki tutamacı tut.
- **Kilitle / click-through**: Sağ üstteki kilit butonuna tıkla. Kilitliyken
  tıklamalar arkadaki pencereye geçer; kilidi açmak için tekrar tıkla (veya
  tepsi menüsünü kullan).
- **Tepsi ikonu**: Göster/gizle, kilitle/kilit aç, opaklığı değiştir veya çıkış
  için sağ tıkla.

Hotkey'leri değiştirmek için `data/keymap.json` dosyasını düzenle — kaydedince
overlay otomatik olarak yeniden yüklenir. İlk çalıştırmada bu dosya
`data/keymap.example.json` üzerinden oluşturulur.
