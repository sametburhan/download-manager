# Download Manager - Tarayıcı Eklentisi Manuel Kurulum Kılavuzu (Sideloading)

Bu eklenti, tarayıcınızdaki dosya indirmelerini ve video akışlarını otomatik olarak yakalayarak masaüstü **Download Manager** uygulamasına aktarır.

Pazar yeri (Chrome Web Store / Firefox Add-ons) dışından manuel olarak yüklemek için aşağıdaki adımları izleyin:

---

## 1. Google Chrome & Chromium Tabanlı Tarayıcılar (Brave, Edge vb.)

1. Tarayıcınızı açın ve adres çubuğuna şunu yazıp Enter'a basın:
   ```text
   chrome://extensions
   ```
2. Sağ üst köşedeki **"Geliştirici Modu" (Developer mode)** anahtarını açın.
3. Sol üstte beliren **"Paketlenmemiş öğe yükle" (Load unpacked)** butonuna tıklayın.
4. Açılan dosya seçim penceresinden projenizdeki `extension` klasörünü seçin:
   ```text
   c:\Users\samet\Desktop\download manager\extension
   ```
5. Eklenti hemen yüklenecek ve araç çubuğunuzda `⚡` simgesi belirecektir.
6. Masaüstü uygulamasını (`python app/main.py`) başlattığınızda simge üzerinde yeşil **ON** rozeti görünecektir.

---

## 2. Opera Tarayıcısı

1. Opera adres çubuğuna şunu yazın:
   ```text
   opera://extensions
   ```
2. Sağ üstteki **"Geliştirici Modu"** butonunu aktif hale getirin.
3. **"Paketlenmemiş uzantıyı yükle" (Load unpacked)** butonuna tıklayın.
4. `c:\Users\samet\Desktop\download manager\extension` klasörünü seçin.

---

## 3. Mozilla Firefox

1. Firefox adres çubuğuna şunu yazın:
   ```text
   about:debugging#/runtime/this-firefox
   ```
2. **"Geçici Eklenti Yükle..." (Load Temporary Add-on...)** butonuna tıklayın.
3. `extension` klasörünün içindeki `manifest.json` dosyasını seçin.
4. Eklenti Firefox'a geçici olarak eklenecek ve yerel WebSocket ile haberleşecektir.

---

## 4. Kullanım İpuçları

- **Otomatik Yakalama:** Bir ZIP, EXE, ISO, MP4 vb. indirme bağlantısına tıkladığınızda tarayıcının kendi indirmesi iptal edilir ve masaüstü Download Manager penceresi otomatik olarak açılır.
- **Sağ Tık Menüsü:** Herhangi bir indirme bağlantısına veya videoya sağ tıklayıp **"Download Manager ile İndir"** seçeneğini kullanabilirsiniz.
- **Eklenti Popup Penceresi:** Araç çubuğundaki eklenti simgesine tıklayarak anlık bağlantı durumunu görebilir, otomatik yakalamayı açıp kapatabilir veya doğrudan bir URL yapıştırıp indirebilirsiniz.
