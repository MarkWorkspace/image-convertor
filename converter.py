import os
import sys
import threading
import subprocess
import concurrent.futures
from pathlib import Path
from tkinter import filedialog, colorchooser
from PIL import Image, ImageOps
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass
import customtkinter as ctk

# --- НАСТРОЙКИ ---
SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.bmp', '.tiff', '.tif', '.gif')

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Глобально переопределяем синий цвет акцентов на кастомный
ACCENT_COLOR = "#9c1e23"
HOVER_COLOR = "#7a171b"  # Немного затемненный оттенок для эффекта наведения

theme = ctk.ThemeManager.theme
theme["CTkButton"]["fg_color"] = [ACCENT_COLOR, ACCENT_COLOR]
theme["CTkButton"]["hover_color"] = [HOVER_COLOR, HOVER_COLOR]
theme["CTkCheckBox"]["fg_color"] = [ACCENT_COLOR, ACCENT_COLOR]
theme["CTkCheckBox"]["hover_color"] = [HOVER_COLOR, HOVER_COLOR]
theme["CTkSlider"]["button_color"] = [ACCENT_COLOR, ACCENT_COLOR]
theme["CTkSlider"]["button_hover_color"] = [HOVER_COLOR, HOVER_COLOR]
theme["CTkSlider"]["progress_color"] = [ACCENT_COLOR, ACCENT_COLOR]
theme["CTkProgressBar"]["progress_color"] = [ACCENT_COLOR, ACCENT_COLOR]

def resource_path(relative_path):
    """ Получает абсолютный путь к ресурсам, работает и в dev, и в скомпилированном PyInstaller файле """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ToolTip:
    """
    Создает всплывающую подсказку для виджета customtkinter.
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.schedule_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def schedule_tooltip(self, event=None):
        self.unschedule_tooltip()
        self.id = self.widget.after(250, self.show_tooltip)

    def unschedule_tooltip(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def show_tooltip(self):
        if self.tooltip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + 20
        
        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True) # Убирает рамки окна
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        label = ctk.CTkLabel(self.tooltip_window, text=self.text, wraplength=250, justify="left",
                             fg_color=("gray85", "gray17"), text_color=("gray10", "gray90"),
                             corner_radius=6, padx=8, pady=4)
        label.pack()

    def hide_tooltip(self, event=None):
        self.unschedule_tooltip()
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None

class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        
        self.result = False
        
        label = ctk.CTkLabel(self, text=text, wraplength=280)
        label.pack(pady=(25, 20), padx=20)
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        btn_yes = ctk.CTkButton(btn_frame, text="Да", width=120, command=self.on_yes)
        btn_yes.pack(side="left", expand=True, padx=(0, 5))
        
        btn_no = ctk.CTkButton(btn_frame, text="Отмена", width=120, fg_color="gray40", hover_color="gray30", command=self.on_no)
        btn_no.pack(side="right", expand=True, padx=(5, 0))
        
        self.update_idletasks()
        width = 340
        height = 140
        # Вычисляем координаты центра поверх родительского окна
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        self.transient(parent) # Окно всегда поверх родительского
        self.grab_set()        # Блокируем родительское окно (модальность)
        
        self.protocol("WM_DELETE_WINDOW", self.on_no)
        self.wait_window()
        
    def on_yes(self):
        self.result = True
        self.destroy()
        
    def on_no(self):
        self.result = False
        self.destroy()

class PhotoConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("WebP Converter Pro")
        self.geometry("600x690")
        self.resizable(False, False)

        # Установка иконки окна приложения
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        # Начальная папка по умолчанию — там, где запущен скрипт
        if getattr(sys, 'frozen', False):
            self.source_dir = str(Path(sys.executable).parent)
        else:
            self.source_dir = str(Path(__file__).resolve().parent)

        self.selected_files = []
        self.export_dir = ""

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

        self.is_processing = False
        self.stop_event = threading.Event()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.create_widgets()

    def create_widgets(self):
        # Заголовок
        self.lbl_title = ctk.CTkLabel(self, text="Конвертер изображений в WebP", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_title.pack(pady=(20, 10))

        # Секция выбора папки
        self.frame_dir = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_dir.pack(pady=10, padx=20, fill="x")

        self.frame_buttons = ctk.CTkFrame(self.frame_dir, fg_color="transparent")
        self.frame_buttons.pack(side="left", padx=(0, 10))

        self.btn_browse_dir = ctk.CTkButton(self.frame_buttons, text="Выбрать папку", width=120, command=self.select_directory)
        self.btn_browse_dir.pack(pady=(0, 2))

        self.lbl_or = ctk.CTkLabel(self.frame_buttons, text="или")
        self.lbl_or.pack(pady=(0, 2))

        self.btn_browse_files = ctk.CTkButton(self.frame_buttons, text="Выбрать файлы", width=120, command=self.select_files)
        self.btn_browse_files.pack()

        # Создаем правый фрейм для строки пути и списка файлов
        self.frame_right = ctk.CTkFrame(self.frame_dir, fg_color="transparent")
        self.frame_right.pack(side="left", fill="both", expand=True)

        self.entry_path = ctk.CTkEntry(self.frame_right, placeholder_text="Путь не выбран")
        self.entry_path.insert(0, self.source_dir)
        self.entry_path.configure(state="readonly")
        self.entry_path.pack(fill="x")

        # Поле для вывода списка файлов (изначально скрыто, так как не делаем pack)
        self.file_list_box = ctk.CTkTextbox(self.frame_right, height=60, state="disabled")

        # --- Секция выбора папки сохранения ---
        self.frame_out = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_out.pack(pady=(0, 10), padx=20, fill="x")

        self.btn_browse_out = ctk.CTkButton(self.frame_out, text="Папка экспорта", width=120, command=self.select_export_directory)
        self.btn_browse_out.pack(side="left", padx=(0, 10))

        self.btn_clear_out = ctk.CTkButton(self.frame_out, text="✕", width=28, fg_color="gray40", hover_color="gray30", command=self.clear_export_directory)
        self.btn_clear_out.pack(side="right")

        self.entry_out_path = ctk.CTkEntry(self.frame_out, placeholder_text="По умолчанию (в папке с оригиналами)")
        self.entry_out_path.configure(state="readonly")
        self.entry_out_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Вкладки настроек
        self.tabview = ctk.CTkTabview(self, width=560, height=130, 
                                      segmented_button_selected_color=ACCENT_COLOR,
                                      segmented_button_selected_hover_color=HOVER_COLOR)
        self.tabview.pack(pady=(5, 10), padx=20, fill="x")

        self.tabview.add("Пресеты")
        self.tabview.add("Пользовательские")

        # --- Вкладка 1: Пресеты ---
        self.combo_mode = ctk.CTkComboBox(self.tabview.tab("Пресеты"), values=list(self.modes.keys()), width=400, state="readonly")
        self.combo_mode.set(list(self.modes.keys())[0])
        self.combo_mode.pack(pady=20)

        # --- Вкладка 2: Пользовательские ---
        self.frame_custom = ctk.CTkFrame(self.tabview.tab("Пользовательские"), fg_color="transparent")
        self.frame_custom.pack(fill="both", expand=True, padx=10, pady=5)

        self.row1 = ctk.CTkFrame(self.frame_custom, fg_color="transparent")
        self.row1.pack(fill="x", pady=2)
        
        ctk.CTkLabel(self.row1, text="Разрешение:").pack(side="left", padx=(0,5))
        self.combo_custom_mode = ctk.CTkComboBox(self.row1, values=["Оригинал", "Обрезать под размер", "Вписать в размер", "Растянуть", "С рамками"], width=170, state="readonly", command=self.on_mode_change)
        self.combo_custom_mode.set("Оригинал")
        self.combo_custom_mode.pack(side="left", padx=(0,15))

        # Контейнер для полей и замочка (выравниваем по правому краю)
        self.frame_resolution_container = ctk.CTkFrame(self.row1, fg_color="transparent")
        self.frame_resolution_container.pack(side="right")

        self.frame_dims_and_lock = ctk.CTkFrame(self.frame_resolution_container, fg_color="transparent")
        self.frame_dims_and_lock.pack(anchor="e")

        self.frame_dims = ctk.CTkFrame(self.frame_dims_and_lock, fg_color="transparent")
        self.frame_dims.pack(side="left")

        # Переменные для отслеживания ввода с привязкой событий
        self.var_w = ctk.StringVar(value="1920")
        self.var_w.trace_add("write", self.on_w_change)

        self.frame_w = ctk.CTkFrame(self.frame_dims, fg_color="transparent")
        self.frame_w.pack(fill="x", pady=(0, 2))
        self.lbl_w = ctk.CTkLabel(self.frame_w, text="Ширина:")
        self.lbl_w.pack(side="left", padx=(0,5))
        self.entry_w = ctk.CTkEntry(self.frame_w, width=60, textvariable=self.var_w)
        self.entry_w.pack(side="right")
        
        self.var_h = ctk.StringVar(value="1080")
        self.var_h.trace_add("write", self.on_h_change)

        self.frame_h = ctk.CTkFrame(self.frame_dims, fg_color="transparent")
        self.frame_h.pack(fill="x")
        self.lbl_h = ctk.CTkLabel(self.frame_h, text="Высота:")
        self.lbl_h.pack(side="left", padx=(0,5))
        self.entry_h = ctk.CTkEntry(self.frame_h, width=60, textvariable=self.var_h)
        self.entry_h.pack(side="right")

        self.is_locked = False
        self.aspect_ratio = 1920 / 1080
        self.updating_ratio = False

        self.btn_lock = ctk.CTkButton(self.frame_dims_and_lock, text="🔓", width=40, height=58, 
                                      font=ctk.CTkFont(size=24), command=self.toggle_lock)
        self.default_lock_fg = self.btn_lock.cget("fg_color")
        self.btn_lock.configure(fg_color="transparent", border_width=1, border_color="gray50", text_color="gray50")
        self.btn_lock.pack(side="left", fill="y", padx=(5, 0))

        self.checkbox_only_shrink = ctk.CTkCheckBox(self.frame_resolution_container, text="Только уменьшать", checkbox_width=16, checkbox_height=16, border_width=1.5)
        self.checkbox_only_shrink.pack(pady=(5,0), anchor="e")
        self.checkbox_only_shrink.select() # Включено по умолчанию для защиты качества
        tooltip_text = "Если опция активна, то настройка изменения разрешения не применяется к изображениям, которые меньше указанного разрешения."
        ToolTip(self.checkbox_only_shrink, tooltip_text)

        # Отключаем поля, так как по умолчанию выбран режим "Оригинал"
        self.entry_w.configure(state="disabled", text_color="gray50")
        self.entry_h.configure(state="disabled", text_color="gray50")
        self.lbl_w.configure(text_color="gray50")
        self.lbl_h.configure(text_color="gray50")
        self.btn_lock.configure(state="disabled", text_color="gray50", fg_color="transparent", border_width=1, border_color="gray50")
        self.checkbox_only_shrink.configure(state="disabled")

        # Настройки для режима "С рамками" (скрыты по умолчанию)
        self.row1_pad = ctk.CTkFrame(self.frame_custom, fg_color="transparent")
        
        ctk.CTkLabel(self.row1_pad, text="Цвет рамок:").pack(side="left", padx=(0,5))
        self.btn_pad_color = ctk.CTkButton(self.row1_pad, text="Выбрать цвет", width=120, command=self.choose_color)
        self.btn_pad_color.pack(side="left", padx=(0,5))
        
        self.color_preview = ctk.CTkLabel(self.row1_pad, text="", width=24, height=24, fg_color="#FFFFFF", corner_radius=4)
        self.color_preview.pack(side="left", padx=(0,15))

        self.checkbox_transparent = ctk.CTkCheckBox(self.row1_pad, text="Прозрачный фон", command=self.toggle_transparent, checkbox_width=16, checkbox_height=16, border_width=1.5)
        self.checkbox_transparent.pack(side="left")
        
        self.pad_color = (255, 255, 255, 255) # по умолчанию белый

        self.row2 = ctk.CTkFrame(self.frame_custom, fg_color="transparent")
        self.row2.pack(fill="x", pady=(10,2))

        self.lbl_q_title = ctk.CTkLabel(self.row2, text="Качество:")
        self.lbl_q_title.pack(side="left", padx=(0,5))
        self.slider_q = ctk.CTkSlider(self.row2, from_=1, to=100, number_of_steps=99, command=self.update_q_label)
        self.slider_q.set(85)
        self.slider_q.pack(side="left", padx=(0,10))
        self.lbl_q_val = ctk.CTkLabel(self.row2, text="85%")
        self.lbl_q_val.pack(side="left")

        # Сохраняем оригинальные цвета ползунка для восстановления
        self.default_progress_color = self.slider_q.cget("progress_color")
        self.default_button_color = self.slider_q.cget("button_color")

        self.checkbox_lossless = ctk.CTkCheckBox(self.row2, text="Lossless", command=self.toggle_lossless, checkbox_width=16, checkbox_height=16, border_width=1.5)
        self.checkbox_lossless.pack(side="left", padx=(30,0))

        # Контейнер для кнопки старта и прогресс-бара
        self.frame_action = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_action.pack(pady=15, padx=20, fill="x")

        # Кнопка старта
        self.btn_start = ctk.CTkButton(self.frame_action, text="Начать обработку", width=250, height=45, 
                                       font=ctk.CTkFont(size=15, weight="bold"), command=self.start_processing_thread)
        self.btn_start.pack()

        # Прогресс-бар и проценты
        self.frame_progress = ctk.CTkFrame(self.frame_action, fg_color="transparent")

        self.progress_bar = ctk.CTkProgressBar(self.frame_progress)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)
        
        self.btn_cancel = ctk.CTkButton(self.frame_progress, text="Отмена", width=80, command=self.cancel_processing)
        self.btn_cancel.pack(side="right")

        self.lbl_progress_pct = ctk.CTkLabel(self.frame_progress, text="0%", width=40, anchor="e")
        self.lbl_progress_pct.pack(side="right", padx=(0, 5))

        self.checkbox_open_folder = ctk.CTkCheckBox(self, text="Открыть папку по завершении", checkbox_width=16, checkbox_height=16, border_width=1.5)
        self.checkbox_open_folder.pack(pady=(0, 5))
        self.checkbox_open_folder.select()

        # Окно логов
        self.log_box = ctk.CTkTextbox(self, width=560, height=200, state="disabled")
        self.log_box.pack(pady=(10, 20), padx=20)
        
        self.log("Приложение готово.")
        self.log(f"Текущая директория: {self.source_dir}")

    def update_q_label(self, value):
        self.lbl_q_val.configure(text=f"{int(value)}%")

    def toggle_lossless(self):
        if self.checkbox_lossless.get():
            self.slider_q.configure(state="disabled", 
                                    progress_color="gray50", 
                                    button_color="gray50")
            self.lbl_q_title.configure(text_color="gray50")
            self.lbl_q_val.configure(text_color="gray50")
        else:
            self.slider_q.configure(state="normal", 
                                    progress_color=self.default_progress_color, 
                                    button_color=self.default_button_color)
            self.lbl_q_title.configure(text_color=("gray10", "gray90"))
            self.lbl_q_val.configure(text_color=("gray10", "gray90"))

    def toggle_lock(self):
        self.is_locked = not self.is_locked
        if self.is_locked:
            self.btn_lock.configure(text="🔒", text_color=("gray10", "gray90"), fg_color=self.default_lock_fg, border_width=0)
            try:
                w = float(self.var_w.get())
                h = float(self.var_h.get())
                if h > 0:
                    self.aspect_ratio = w / h
            except ValueError:
                pass
        else:
            self.btn_lock.configure(text="🔓", text_color="gray50", fg_color="transparent", border_width=1, border_color="gray50")

    def on_w_change(self, *args):
        if self.is_locked and not self.updating_ratio:
            try:
                w_str = self.var_w.get().strip()
                if not w_str: return
                w = float(w_str)
                self.updating_ratio = True
                self.var_h.set(str(int(max(1, w / self.aspect_ratio))))
                self.updating_ratio = False
            except ValueError:
                pass

    def on_h_change(self, *args):
        if self.is_locked and not self.updating_ratio:
            try:
                h_str = self.var_h.get().strip()
                if not h_str: return
                h = float(h_str)
                self.updating_ratio = True
                self.var_w.set(str(int(max(1, h * self.aspect_ratio))))
                self.updating_ratio = False
            except ValueError:
                pass

    def on_mode_change(self, choice):
        # Логика включения/отключения полей ширины и высоты
        if choice == "Оригинал":
            self.entry_w.configure(state="disabled", text_color="gray50")
            self.entry_h.configure(state="disabled", text_color="gray50")
            self.lbl_w.configure(text_color="gray50")
            self.lbl_h.configure(text_color="gray50")
            self.btn_lock.configure(state="disabled", text_color="gray50", fg_color="transparent", border_width=1, border_color="gray50")
            self.checkbox_only_shrink.configure(state="disabled")
        else:
            self.entry_w.configure(state="normal", text_color=("gray10", "gray90"))
            self.entry_h.configure(state="normal", text_color=("gray10", "gray90"))
            self.lbl_w.configure(text_color=("gray10", "gray90"))
            self.lbl_h.configure(text_color=("gray10", "gray90"))
            if self.is_locked:
                self.btn_lock.configure(state="normal", text_color=("gray10", "gray90"), fg_color=self.default_lock_fg, border_width=0)
            else:
                self.btn_lock.configure(state="normal", text_color="gray50", fg_color="transparent", border_width=1, border_color="gray50")
            self.checkbox_only_shrink.configure(state="normal")

        if choice == "С рамками":
            self.row1_pad.pack(fill="x", pady=2, after=self.row1)
        else:
            self.row1_pad.pack_forget()

    def choose_color(self):
        color = colorchooser.askcolor(title="Выберите цвет рамок")[0]
        if color:
            self.pad_color = (int(color[0]), int(color[1]), int(color[2]), 255)
            hex_color = '#%02x%02x%02x' % (self.pad_color[0], self.pad_color[1], self.pad_color[2])
            self.color_preview.configure(fg_color=hex_color)

    def toggle_transparent(self):
        if self.checkbox_transparent.get():
            self.btn_pad_color.configure(state="disabled")
        else:
            self.btn_pad_color.configure(state="normal")

    def select_directory(self):
        directory = filedialog.askdirectory(initialdir=self.source_dir)
        if directory:
            self.source_dir = directory
            self.selected_files = []
            self.update_entry_path(directory)
            self.log(f"Выбрана новая папка: {directory}")
            
            # Скрываем список файлов при выборе папки
            self.file_list_box.pack_forget()
            
    def select_files(self):
        filetypes = [("Изображения", "*.jpg *.jpeg *.png *.webp *.heic *.bmp *.tiff *.tif *.gif"), ("Все файлы", "*.*")]
        files = filedialog.askopenfilenames(initialdir=self.source_dir, filetypes=filetypes)
        if files:
            self.selected_files = list(files)
            self.source_dir = ""
            self.update_entry_path(f"Выбрано файлов: {len(self.selected_files)}")
            self.log(f"Выбрано файлов: {len(self.selected_files)}")
            
            # Показываем и заполняем список
            self.file_list_box.pack(fill="both", expand=True, pady=(5, 0))
            self.file_list_box.configure(state="normal")
            self.file_list_box.delete("1.0", "end")
            for f in self.selected_files:
                self.file_list_box.insert("end", Path(f).name + "\n")
            self.file_list_box.configure(state="disabled")
            
    def update_entry_path(self, text):
        self.entry_path.configure(state="normal")
        self.entry_path.delete(0, "end")
        self.entry_path.insert(0, text)
        self.entry_path.configure(state="readonly")

    def select_export_directory(self):
        directory = filedialog.askdirectory(initialdir=self.export_dir or self.source_dir)
        if directory:
            self.export_dir = directory
            self.entry_out_path.configure(state="normal")
            self.entry_out_path.delete(0, "end")
            self.entry_out_path.insert(0, directory)
            self.entry_out_path.configure(state="readonly")
            self.log(f"Папка для сохранения выбрана: {directory}")

    def clear_export_directory(self):
        self.export_dir = ""
        self.entry_out_path.configure(state="normal")
        self.entry_out_path.delete(0, "end")
        self.entry_out_path.configure(state="readonly")
        self.log("Папка для сохранения сброшена (будет использована папка по умолчанию).")

    def log(self, message):
        if not self.winfo_exists():
            return
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"> {message}\n")
        self.log_box.configure(state="disabled")
        self.log_box.yview("end")

    def on_closing(self):
        if self.is_processing:
            dialog = ConfirmDialog(self, "Подтверждение", "Остановить текущую операцию и закрыть приложение?")
            if dialog.result:
                self.stop_event.set()
                self.destroy()
        else:
            self.destroy()

    def cancel_processing(self):
        self.log("Отмена операции...")
        self.stop_event.set()

    def start_processing_thread(self):
        self.btn_start.configure(state="disabled")
        self.btn_start.pack_forget()
        self.frame_progress.pack(fill="x", pady=10)
        self.btn_browse_dir.configure(state="disabled")
        self.btn_browse_files.configure(state="disabled")
        self.btn_browse_out.configure(state="disabled")
        self.btn_clear_out.configure(state="disabled")
        
        active_tab = self.tabview.get()
        lossless = False
        pad_color = None
        if active_tab == "Пресеты":
            selected = self.combo_mode.get()
            settings = self.modes[selected]
            q = settings['q']
            mode = settings['mode']
            size = settings['size']
        else:
            try:
                lossless = bool(self.checkbox_lossless.get())
                q = int(self.slider_q.get())
                
                mode_map = {
                    "Оригинал": None,
                    "Обрезать под размер": "outside",
                    "Вписать в размер": "inside",
                    "Растянуть": "exact",
                    "С рамками": "pad"
                }
                mode = mode_map.get(self.combo_custom_mode.get())
                
                if mode == 'pad':
                    if self.checkbox_transparent.get():
                        pad_color = (0, 0, 0, 0)
                    else:
                        pad_color = self.pad_color
                
                if mode is not None:
                    w_str = self.entry_w.get().strip()
                    h_str = self.entry_h.get().strip()
                    if not w_str or not h_str:
                        self.log("[!] Ошибка: Для изменения размера укажите ширину и высоту.")
                        self.finalize()
                        return
                    size = (int(w_str), int(h_str))
                else:
                    size = None
            except ValueError:
                self.log("[!] Ошибка: Некорректные числовые значения в настройках.")
                self.finalize()
                return
        
        only_shrink = bool(self.checkbox_only_shrink.get())
        open_folder = bool(self.checkbox_open_folder.get())
        self.progress_bar.set(0)
        self.lbl_progress_pct.configure(text="0%")
        self.is_processing = True
        self.stop_event.clear()
        thread = threading.Thread(target=self.process_images, args=(q, mode, size, lossless, pad_color, only_shrink, open_folder), daemon=True)
        thread.start()

    def process_single_image(self, file, output_path, quality, resize_mode, size, lossless, pad_color, only_shrink):
        if self.stop_event.is_set():
            return False, ""
            
        try:
            with Image.open(file) as img:
                # Сохраняем прозрачность
                if img.mode == "P":
                    img = img.convert("RGBA")
                
                if resize_mode and size:
                    img_w, img_h = img.size
                    target_w, target_h = size
                    
                    is_smaller = (img_w <= target_w and img_h <= target_h)
                    
                    if is_smaller and only_shrink:
                        # Если фото маленькое и мы НЕ хотим его растягивать
                        if resize_mode == 'pad':
                            # Создаем большой холст и кладем фото по центру
                            if pad_color and len(pad_color) == 4 and pad_color[3] == 0:
                                img = img.convert("RGBA")
                                current_pad_color = pad_color
                            else:
                                current_pad_color = pad_color if img.mode == "RGBA" else pad_color[:3]
                            
                            new_img = Image.new(img.mode, size, current_pad_color)
                            offset_x = (target_w - img_w) // 2
                            offset_y = (target_h - img_h) // 2
                            new_img.paste(img, (offset_x, offset_y))
                            img = new_img
                    else:
                        # Обычная обработка (для больших фото или если разрешено растягивание)
                        if resize_mode == 'outside':
                            img = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                        elif resize_mode == 'inside':
                            img = ImageOps.contain(img, size, method=Image.Resampling.LANCZOS)
                        elif resize_mode == 'exact':
                            img = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS)
                        elif resize_mode == 'pad':
                            # Если требуется прозрачность, переводим изображение в RGBA перед заливкой
                            if pad_color and len(pad_color) == 4 and pad_color[3] == 0:
                                img = img.convert("RGBA")
                                current_pad_color = pad_color
                            else:
                                current_pad_color = pad_color if img.mode == "RGBA" else pad_color[:3]
                            img = ImageOps.pad(img, size, method=Image.Resampling.LANCZOS, color=current_pad_color)

                out_name = file.stem + ".webp"
                final_dest = output_path / out_name
                img.save(final_dest, "webp", quality=quality, lossless=lossless)
                return True, f"OK: {file.name} -> {out_name}"
                
        except Exception as e:
            return False, f"Ошибка в файле {file.name}: {e}"

    def process_images(self, quality, resize_mode, size, lossless=False, pad_color=None, only_shrink=True, open_folder=True):
        try:
            if self.selected_files:
                files = [Path(f) for f in self.selected_files if Path(f).suffix.lower() in SUPPORTED_FORMATS]
                if files:
                    default_output_path = files[0].parent / "output"
            elif self.source_dir:
                source_path = Path(self.source_dir)
                default_output_path = source_path / "output"
                files = [f for f in source_path.iterdir() if f.suffix.lower() in SUPPORTED_FORMATS]
            else:
                files = []
            
            if not files:
                self.log("[!] Не найдено подходящих изображений для обработки.")
                self.finalize()
                return

            output_path = Path(self.export_dir) if self.export_dir else default_output_path

            total_files = len(files)

            # Создаем папку output непосредственно перед обработкой
            output_path.mkdir(exist_ok=True)
            self.log(f"Папка экспорта: {output_path.name}")
            self.log(f"Найдено файлов: {total_files}. Обработка...")

            processed_count = 0
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(
                        self.process_single_image, file, output_path, quality, resize_mode, size, lossless, pad_color, only_shrink
                    ): file for file in files
                }

                for future in concurrent.futures.as_completed(futures):
                    if self.stop_event.is_set():
                        # Отменяем еще не начатые задачи
                        for f in futures:
                            f.cancel()
                        break
                    
                    if not self.winfo_exists():
                        for f in futures:
                            f.cancel()
                        return
                        
                    success, msg = future.result()
                    if msg:
                        self.log(msg)
                        
                    processed_count += 1
                    progress_val = processed_count / total_files
                    
                    self.progress_bar.set(progress_val)
                    self.lbl_progress_pct.configure(text=f"{int(progress_val * 100)}%")
            
            if self.stop_event.is_set():
                self.log("--- ОПЕРАЦИЯ ПРЕРВАНА ---")
            else:
                self.log("--- ВСЕ ОПЕРАЦИИ ЗАВЕРШЕНЫ ---")
                
                # Открываем папку с результатами
                if open_folder:
                    if sys.platform == "win32":
                        os.startfile(output_path)
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", str(output_path)])
                    else:
                        subprocess.Popen(["xdg-open", str(output_path)])

        except Exception as e:
            self.log(f"Критическая ошибка: {e}")
        
        self.finalize()

    def finalize(self):
        if not self.winfo_exists():
            return
        self.is_processing = False
        self.frame_progress.pack_forget()
        self.btn_start.pack()
        self.btn_start.configure(state="normal")
        self.btn_browse_dir.configure(state="normal")
        self.btn_browse_files.configure(state="normal")
        self.btn_browse_out.configure(state="normal")
        self.btn_clear_out.configure(state="normal")

if __name__ == "__main__":
    app = PhotoConverterApp()
    app.mainloop()