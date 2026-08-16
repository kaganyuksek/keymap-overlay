# Kurulum

## Gereksinimler

- Linux (X11 veya XWayland ile Wayland)
- Python 3 (3.9+)
- `python3-venv` (genellikle kurulu gelir; yoksa paket yöneticinle kur)

## Yöntem A — `run.sh` ile çalıştır (önerilen)

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

## Yöntem B — Manuel kurulum

1. Sanal ortam oluştur ve etkinleştir:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Bağımlılıkları kur:

   ```bash
   pip install -r requirements.txt
   ```

3. Çalıştır:

   ```bash
   python main.py
   ```

## Tek dosyalık çalıştırılabilir oluşturma

```bash
./build.sh
```

Bu, PyInstaller ile `dist/KeymapOverlay` üretir. `data/` ve `assets/`
klasörlerini çalıştırılabilirin yanında bulundurmayı unutma.

## Kullanım

- **Sürükle**: Pencereyi taşımak için sol üstteki tutamacı tut.
- **Kilitle / click-through**: Sağ üstteki kilit butonuna tıkla. Kilitliyken
  tıklamalar arkadaki pencereye geçer; kilidi açmak için tekrar tıkla (veya
  tepsi menüsünü kullan).
- **Tepsi ikonu**: Göster/gizle, kilitle/kilit aç, opaklığı değiştir veya çıkış
  için sağ tıkla.

Hotkey'leri değiştirmek için `data/keymap.json` dosyasını düzenle — kaydedince
overlay otomatik olarak yeniden yüklenir.
