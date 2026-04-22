import os
import sys
import threading
from pathlib import Path
from PIL import Image, ImageOps
import customtkinter as ctk

# --- НАСТРОЙКИ ПУТЕЙ И ФОРМАТОВ ---
if getattr(sys, 'frozen', False):
    WORK_DIR = Path(sys.executable).parent
else:
    WORK_DIR = Path(__file__).resolve().parent

OUT_DIR = WORK_DIR / "output"
SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.webp')

# --- НАСТРОЙКИ ИНТЕРФЕЙСА ---
ctk.set_appearance_mode("Dark")  # Темная тема ("Light", "Dark", "System")
ctk.set_default_color_theme("blue")  # Цветовой акцент

class PhotoConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SHARP CLI -> WebP Converter")
        self.geometry("550x450")
        self.resizable(False, False)

        # Словарь режимов работы
        self.modes = {
            "1. Без изменения разрешения (85%)": {'q': 85, 'mode': None, 'size': None},
            "2. Без изменения разрешения (75%)": {'q': 75, 'mode': None, 'size': None},
            "3. Fit outside 1920x1080 (75%)": {'q': 75, 'mode': 'outside', 'size': (1920, 1080)},
            "4. Fit outside 1080x1920 (75%)": {'q': 75, 'mode': 'outside', 'size': (1080, 1920)},
            "5. Fit inside 1920x1080 (75%)": {'q': 75, 'mode': 'inside', 'size': (1920, 1080)},
            "6. Квадрат 400x400 (75%)": {'q': 75, 'mode': 'exact', 'size': (400, 400)},
            "7. Размер 600x800 3:4 (75%)": {'q': 75, 'mode': 'exact', 'size': (600, 800)},
            "8. Размер 1200x900 4:3 (75%)": {'q': 75, 'mode': 'exact', 'size': (1200, 900)}
        }

        self.create_widgets()

    def create_widgets(self):
        # Заголовок
        self.lbl_title = ctk.CTkLabel(self, text="Конвертер изображений в WebP", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_title.pack(pady=(20, 10))

        # Выпадающий список
        self.combo_mode = ctk.CTkComboBox(self, values=list(self.modes.keys()), width=350, state="readonly")
        self.combo_mode.set(list(self.modes.keys())[0])
        self.combo_mode.pack(pady=10)

        # Кнопка старта
        self.btn_start = ctk.CTkButton(self, text="Начать обработку", width=200, height=40, command=self.start_processing_thread)
        self.btn_start.pack(pady=10)

        # Текстовое поле для логов
        self.log_box = ctk.CTkTextbox(self, width=500, height=200, state="disabled")
        self.log_box.pack(pady=(10, 20))
        
        self.log(f"Рабочая папка: {WORK_DIR}\nГотово к работе...\n")

    def log(self, message):
        """Функция для добавления текста в окно логов"""
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.yview("end") # Автопрокрутка вниз

    def start_processing_thread(self):
        """Запускаем обработку в отдельном потоке, чтобы не заморозить UI"""
        self.btn_start.configure(state="disabled")
        selected = self.combo_mode.get()
        settings = self.modes[selected]
        
        # Запуск потока
        thread = threading.Thread(target=self.process_images, args=(settings['q'], settings['mode'], settings['size']))
        thread.start()

    def process_images(self, quality, resize_mode, size):
        OUT_DIR.mkdir(exist_ok=True)
        files = [f for f in WORK_DIR.iterdir() if f.suffix.lower() in SUPPORTED_FORMATS]
        
        if not files:
            self.log("[!] В текущей папке нет подходящих изображений.")
            self.btn_start.configure(state="normal")
            return

        self.log(f"\nНайдено файлов: {len(files)}. Начинаю обработку...")
        
        for file in files:
            try:
                with Image.open(file) as img:
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    
                    if resize_mode and size:
                        img_w, img_h = img.size
                        target_w, target_h = size
                        
                        if img_w > target_w or img_h > target_h:
                            if resize_mode == 'outside':
                                img = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, bleed=0.0, centering=(0.5, 0.5))
                            elif resize_mode == 'inside':
                                img.thumbnail(size, Image.Resampling.LANCZOS)
                            elif resize_mode == 'exact':
                                img = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS)

                    out_name = file.stem + ".webp"
                    out_path = OUT_DIR / out_name
                    img.save(out_path, "webp", quality=quality)
                    self.log(f" [+] {file.name} -> {out_name}")
                    
            except Exception as e:
                self.log(f" [-] Ошибка при обработке {file.name}: {e}")
                
        self.log("\nГОТОВО!")
        self.btn_start.configure(state="normal")

if __name__ == "__main__":
    app = PhotoConverterApp()
    app.mainloop()