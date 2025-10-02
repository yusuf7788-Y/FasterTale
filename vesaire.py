import sys
import os
import shutil
import psutil
import winreg
import ctypes
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
                             QLabel, QProgressBar, QTextEdit, QGroupBox, 
                             QCheckBox, QMessageBox, QSplitter, QTabWidget,
                             QSystemTrayIcon, QMenu, QAction, QStyle, QTreeWidget,
                             QTreeWidgetItem, QHeaderView, QToolBar, QStatusBar,
                             QFileDialog, QInputDialog, QLineEdit, QSpinBox,
                             QFormLayout, QDialog, QDialogButtonBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor, QPixmap
import json
from datetime import datetime, timedelta

def is_admin():
    """Yönetici yetkisi kontrolü"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class CleanerWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, cleaning_options):
        super().__init__()
        self.cleaning_options = cleaning_options
        self.total_freed = 0
        self.deleted_files = 0

    def run(self):
        try:
            results = self.perform_cleaning()
            self.finished_signal.emit(results)
        except Exception as e:
            self.error_signal.emit(str(e))

    def get_folder_size(self, folder_path):
        """Klasör boyutunu ve dosya sayısını hesapla"""
        total_size = 0
        file_count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        if os.path.isfile(filepath):
                            total_size += os.path.getsize(filepath)
                            file_count += 1
                    except OSError:
                        continue
        except OSError:
            pass
        return total_size, file_count

    def safe_delete(self, path):
        """Güvenli silme işlemi - boyutu silmeden önce al"""
        try:
            if os.path.isfile(path):
                # Boyutu silmeden önce al
                file_size = os.path.getsize(path)
                os.remove(path)
                return file_size, 1  # 1 dosya silindi
            elif os.path.isdir(path):
                # Klasör boyutunu ve dosya sayısını silmeden önce al
                folder_size, file_count = self.get_folder_size(path)
                shutil.rmtree(path, ignore_errors=True)
                return folder_size, file_count
        except OSError as e:
            print(f"Silme hatası {path}: {e}")
            return 0, 0
        return 0, 0

    def clean_temp_files(self):
        """Temp dosyalarını temizle"""
        temp_folders = [
            os.environ.get('TEMP', ''),
            os.environ.get('TMP', ''),
            r'C:\Windows\Temp',
            os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Temp')
        ]
        
        freed_space = 0
        deleted_count = 0
        
        for temp_folder in temp_folders:
            if not os.path.exists(temp_folder):
                continue
                
            self.progress_signal.emit(0, f"Taranıyor: {temp_folder}")
            
            try:
                for item in os.listdir(temp_folder):
                    item_path = os.path.join(temp_folder, item)
                    
                    # Kritik sistem dosyalarını atla
                    critical_folders = ['system32', 'drivers', 'winsxs', 'catroot', 'logs', 'system']
                    if any(critical in item_path.lower() for critical in critical_folders):
                        continue
                    
                    try:
                        # Boyutu ve sayıyı silmeden önce al
                        size, count = self.safe_delete(item_path)
                        freed_space += size
                        deleted_count += count
                    except OSError:
                        continue
                        
            except OSError:
                continue
        
        return freed_space, deleted_count

    def clean_prefetch(self):
        """Prefetch dosyalarını temizle"""
        prefetch_path = r'C:\Windows\Prefetch'
        freed_space = 0
        deleted_count = 0
        
        if not os.path.exists(prefetch_path):
            return freed_space, deleted_count
            
        try:
            for item in os.listdir(prefetch_path):
                if item.lower().endswith('.pf'):
                    item_path = os.path.join(prefetch_path, item)
                    try:
                        size, count = self.safe_delete(item_path)
                        freed_space += size
                        deleted_count += count
                    except OSError:
                        continue
        except OSError:
            pass
            
        return freed_space, deleted_count

    def clean_browser_cache(self):
        """Tarayıcı önbelleklerini temizle"""
        browsers = {
            'Chrome': [
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Cache'),
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Code Cache'),
            ],
            'Edge': [
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Cache'),
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Code Cache'),
            ],
            'Firefox': [
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Mozilla', 'Firefox', 'Profiles'),
            ]
        }
        
        freed_space = 0
        deleted_count = 0
        
        for browser, cache_paths in browsers.items():
            self.progress_signal.emit(0, f"{browser} önbelleği temizleniyor...")
            
            for cache_path in cache_paths:
                if not os.path.exists(cache_path):
                    continue
                    
                try:
                    if 'Firefox' in browser:
                        # Firefox için özel işlem
                        for profile in os.listdir(cache_path):
                            profile_path = os.path.join(cache_path, profile)
                            cache_folders = ['cache2', 'cache', 'thumbnails']
                            for cache_folder in cache_folders:
                                cache_folder_path = os.path.join(profile_path, cache_folder)
                                if os.path.exists(cache_folder_path):
                                    size, count = self.get_folder_size(cache_folder_path)
                                    shutil.rmtree(cache_folder_path, ignore_errors=True)
                                    freed_space += size
                                    deleted_count += count
                                    # Cache klasörünü yeniden oluştur
                                    os.makedirs(cache_folder_path, exist_ok=True)
                    else:
                        # Chrome/Edge için
                        size, count = self.get_folder_size(cache_path)
                        shutil.rmtree(cache_path, ignore_errors=True)
                        # Cache klasörünü yeniden oluştur
                        os.makedirs(cache_path, exist_ok=True)
                        freed_space += size
                        deleted_count += count
                        
                except OSError as e:
                    print(f"Tarayıcı cache temizleme hatası: {e}")
                    continue
        
        return freed_space, deleted_count

    def clean_recycle_bin(self):
        """Geri dönüşüm kutusunu temizle"""
        try:
            # Windows API kullanarak geri dönüşüm kutusunu boşalt
            SHEmptyRecycleBin = ctypes.windll.shell32.SHEmptyRecycleBinW
            result = SHEmptyRecycleBin(None, None, 0x0001)  # SHERB_NOCONFIRMATION
            
            if result == 0:
                # Başarılı, ama boyut bilgisi yok
                return 0, 0
            else:
                return 0, 0
                
        except Exception as e:
            print(f"Geri dönüşüm kutusu temizleme hatası: {e}")
            return 0, 0

    def clean_software_distribution(self):
        """Windows Update artıklarını temizle"""
        softwaredist_path = r'C:\Windows\SoftwareDistribution'
        freed_space = 0
        deleted_count = 0
        
        if not os.path.exists(softwaredist_path):
            return freed_space, deleted_count
            
        # Sadece bu alt klasörleri temizle (güvenli)
        safe_folders = ['Download', 'DataStore']
        
        for folder in safe_folders:
            folder_path = os.path.join(softwaredist_path, folder)
            if os.path.exists(folder_path):
                try:
                    size, count = self.get_folder_size(folder_path)
                    shutil.rmtree(folder_path, ignore_errors=True)
                    # Klasörü yeniden oluştur (Windows Update için gerekli)
                    os.makedirs(folder_path, exist_ok=True)
                    freed_space += size
                    deleted_count += count
                except OSError as e:
                    print(f"SoftwareDistribution temizleme hatası: {e}")
                    continue
        
        return freed_space, deleted_count

    def perform_cleaning(self):
        """Temizleme işlemini gerçekleştir"""
        total_freed = 0
        total_deleted = 0
        results = {}

        # Yönetici kontrolü
        if not is_admin():
            self.progress_signal.emit(0, "Yönetici yetkisi yok - bazı işlemler atlanacak...")

        progress_values = {
            'temp_files': 20,
            'prefetch': 40,
            'browser_cache': 60,
            'software_distribution': 80,
            'recycle_bin': 95
        }

        current_progress = 0

        if self.cleaning_options.get('temp_files', False):
            current_progress += 5
            self.progress_signal.emit(current_progress, "Temp dosyaları temizleniyor...")
            freed, count = self.clean_temp_files()
            total_freed += freed
            total_deleted += count
            results['temp_files'] = {'freed': freed, 'count': count}
            current_progress = progress_values['temp_files']
            self.progress_signal.emit(current_progress, f"Temp temizlendi: {self.format_size(freed)}")

        if self.cleaning_options.get('prefetch', False):
            current_progress += 5
            self.progress_signal.emit(current_progress, "Prefetch dosyaları temizleniyor...")
            freed, count = self.clean_prefetch()
            total_freed += freed
            total_deleted += count
            results['prefetch'] = {'freed': freed, 'count': count}
            current_progress = progress_values['prefetch']
            self.progress_signal.emit(current_progress, f"Prefetch temizlendi: {self.format_size(freed)}")

        if self.cleaning_options.get('browser_cache', False):
            current_progress += 5
            self.progress_signal.emit(current_progress, "Tarayıcı önbellekleri temizleniyor...")
            freed, count = self.clean_browser_cache()
            total_freed += freed
            total_deleted += count
            results['browser_cache'] = {'freed': freed, 'count': count}
            current_progress = progress_values['browser_cache']
            self.progress_signal.emit(current_progress, f"Tarayıcı cache temizlendi: {self.format_size(freed)}")

        if self.cleaning_options.get('software_distribution', False):
            current_progress += 5
            self.progress_signal.emit(current_progress, "Windows Update artıkları temizleniyor...")
            freed, count = self.clean_software_distribution()
            total_freed += freed
            total_deleted += count
            results['software_distribution'] = {'freed': freed, 'count': count}
            current_progress = progress_values['software_distribution']
            self.progress_signal.emit(current_progress, f"Windows Update temizlendi: {self.format_size(freed)}")

        if self.cleaning_options.get('recycle_bin', False):
            current_progress += 5
            self.progress_signal.emit(current_progress, "Geri dönüşüm kutusu temizleniyor...")
            freed, count = self.clean_recycle_bin()
            total_freed += freed
            total_deleted += count
            results['recycle_bin'] = {'freed': freed, 'count': count}
            current_progress = progress_values['recycle_bin']
            self.progress_signal.emit(current_progress, "Geri dönüşüm kutusu temizlendi")

        results['total'] = {'freed': total_freed, 'count': total_deleted}
        return results

    def format_size(self, size_bytes):
        """Byte'ları okunabilir formata çevir"""
        if size_bytes == 0:
            return "0 B"
            
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

class DiskAnalyzerWorker(QThread):
    analysis_complete = pyqtSignal(dict)
    progress_signal = pyqtSignal(int, str)

    def __init__(self):
        super().__init__()

    def run(self):
        analysis_results = self.analyze_disk_space()
        self.analysis_complete.emit(analysis_results)

    def analyze_disk_space(self):
        """Disk kullanımını analiz et"""
        analysis = {}
        
        # Temp klasörleri analizi
        temp_locations = [
            ('User Temp', os.environ.get('TEMP', '')),
            ('System Temp', r'C:\Windows\Temp'),
            ('Prefetch', r'C:\Windows\Prefetch'),
            ('Browser Cache', os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Cache'))
        ]
        
        for i, (name, path) in enumerate(temp_locations):
            if os.path.exists(path):
                size, count = self.get_folder_size(path)
                analysis[name] = {
                    'size': size,
                    'count': count,
                    'size_str': self.format_size(size),
                    'path': path
                }
                progress = 25 * (i + 1)
                self.progress_signal.emit(progress, f"{name} analiz ediliyor...")
        
        # Disk bilgileri
        disk_info = {}
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info[partition.device] = {
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': usage.percent
                }
            except PermissionError:
                continue
        
        analysis['disk_info'] = disk_info
        return analysis

    def get_folder_size(self, folder_path):
        """Klasör boyutunu ve dosya sayısını hesapla"""
        total_size = 0
        file_count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        if os.path.isfile(filepath):
                            total_size += os.path.getsize(filepath)
                            file_count += 1
                    except OSError:
                        continue
        except OSError:
            pass
        return total_size, file_count

    def format_size(self, size_bytes):
        """Byte'ları okunabilir formata çevir"""
        if size_bytes == 0:
            return "0 B"
            
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

class WindowsCleanerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db_manager = None
        self.cleaner_worker = None
        self.analyzer_worker = None
        self.init_ui()
        self.load_settings()
        
        # Yönetici kontrolü
        self.check_admin_status()
        
        # Sistem tepsisine icon ekle
        self.setup_tray_icon()

    def check_admin_status(self):
        """Yönetici durumunu kontrol et ve kullanıcıyı bilgilendir"""
        if not is_admin():
            self.status_bar.showMessage("UYARI: Yönetici olarak çalıştırılmadı - bazı işlemler kısıtlı")
            
            # Kullanıcıya bilgi ver (sadece ilk açılışta)
            if not hasattr(self, 'admin_warning_shown'):
                QMessageBox.warning(self, "Yönetici Yetkisi", 
                                  "Program yönetici yetkisi olmadan çalışıyor.\n\n"
                                  "Bazı sistem dosyalarına erişim kısıtlı olabilir.\n"
                                  "Tam erişim için programı 'Yönetici olarak çalıştırın'.")
                self.admin_warning_shown = True

    def init_ui(self):
        self.setWindowTitle("Windows Temizleyici Pro - Güvenli Sistem Optimizasyonu")
        self.setGeometry(100, 100, 900, 700)
        self.setMinimumSize(800, 600)

        # Merkezi widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Başlık
        title_label = QLabel("Windows Temizleyici Pro")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; margin: 10px;")
        layout.addWidget(title_label)

        # Admin durumu göstergesi
        self.admin_label = QLabel()
        self.admin_label.setAlignment(Qt.AlignCenter)
        self.update_admin_display()
        layout.addWidget(self.admin_label)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Temizleme sekmesi
        self.setup_cleaning_tab()
        
        # Analiz sekmesi
        self.setup_analysis_tab()
        
        # Ayarlar sekmesi
        self.setup_settings_tab()

        # Durum çubuğu
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Hazır")

        # İlerleme çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def update_admin_display(self):
        """Yönetici durumunu ekranda göster"""
        if is_admin():
            self.admin_label.setText("✅ Yönetici modunda çalışıyor")
            self.admin_label.setStyleSheet("color: #27ae60; font-weight: bold; background-color: #d5f4e6; padding: 5px; border-radius: 3px;")
        else:
            self.admin_label.setText("⚠️ Yönetici olarak çalıştırılmadı - bazı işlemler kısıtlı")
            self.admin_label.setStyleSheet("color: #e67e22; font-weight: bold; background-color: #fdebd0; padding: 5px; border-radius: 3px;")

    def setup_cleaning_tab(self):
        cleaning_tab = QWidget()
        layout = QVBoxLayout(cleaning_tab)

        # Temizleme seçenekleri grubu
        options_group = QGroupBox("Temizleme Seçenekleri")
        options_layout = QVBoxLayout(options_group)

        self.temp_check = QCheckBox("Geçici Dosyaları Temizle (Temp, %Temp%)")
        self.temp_check.setChecked(True)
        options_layout.addWidget(self.temp_check)

        self.prefetch_check = QCheckBox("Prefetch Önbelleğini Temizle")
        self.prefetch_check.setChecked(True)
        options_layout.addWidget(self.prefetch_check)

        self.browser_check = QCheckBox("Tarayıcı Önbelleklerini Temizle (Chrome, Edge, Firefox)")
        self.browser_check.setChecked(True)
        options_layout.addWidget(self.browser_check)

        self.recycle_check = QCheckBox("Geri Dönüşüm Kutusunu Boşalt")
        self.recycle_check.setChecked(True)
        options_layout.addWidget(self.recycle_check)

        self.update_check = QCheckBox("Windows Update Artıklarını Temizle (SoftwareDistribution)")
        self.update_check.setChecked(True)
        options_layout.addWidget(self.update_check)

        layout.addWidget(options_group)

        # Güvenlik uyarısı
        warning_label = QLabel("⚠️ UYARI: Bu araç SADECE güvenli dosyaları siler. System32, Drivers, WinSxS gibi kritik sistem dosyalarına DOKUNULMAZ.")
        warning_label.setStyleSheet("color: #e74c3c; background-color: #fdf2f2; padding: 10px; border: 1px solid #e74c3c; border-radius: 5px;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        # Butonlar
        button_layout = QHBoxLayout()

        self.analyze_btn = QPushButton("Disk Alanını Analiz Et")
        self.analyze_btn.clicked.connect(self.analyze_disk_space)
        button_layout.addWidget(self.analyze_btn)

        self.clean_btn = QPushButton("Seçilenleri Temizle")
        self.clean_btn.clicked.connect(self.start_cleaning)
        self.clean_btn.setStyleSheet("QPushButton { background-color: #27ae60; color: white; font-weight: bold; }")
        button_layout.addWidget(self.clean_btn)

        layout.addLayout(button_layout)

        # Sonuçlar alanı
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText("Temizleme sonuçları burada görünecek...")
        layout.addWidget(self.results_text)

        self.tabs.addTab(cleaning_tab, "Temizlik")

    def setup_analysis_tab(self):
        analysis_tab = QWidget()
        layout = QVBoxLayout(analysis_tab)

        # Disk analizi
        analysis_group = QGroupBox("Disk Kullanım Analizi")
        analysis_layout = QVBoxLayout(analysis_group)

        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setPlaceholderText("Disk analiz sonuçları burada görünecek...")
        analysis_layout.addWidget(self.analysis_text)

        layout.addWidget(analysis_group)

        self.tabs.addTab(analysis_tab, "Disk Analizi")

    def setup_settings_tab(self):
        settings_tab = QWidget()
        layout = QVBoxLayout(settings_tab)

        # Otomatik temizlik
        auto_group = QGroupBox("Otomatik Temizlik Ayarları")
        auto_layout = QFormLayout(auto_group)

        self.auto_clean = QCheckBox("Her başlangıçta otomatik temizlik yap")
        auto_layout.addRow(self.auto_clean)

        self.auto_clean_interval = QSpinBox()
        self.auto_clean_interval.setRange(1, 30)
        self.auto_clean_interval.setSuffix(" gün")
        auto_layout.addRow("Otomatik temizlik aralığı:", self.auto_clean_interval)

        layout.addWidget(auto_group)

        # Yedekleme
        backup_group = QGroupBox("Yedekleme Ayarları")
        backup_layout = QVBoxLayout(backup_group)

        self.backup_check = QCheckBox("Temizlemeden önce yedek oluştur")
        backup_layout.addWidget(self.backup_check)

        backup_btn = QPushButton("Yedekleme Klasörünü Seç")
        backup_btn.clicked.connect(self.select_backup_folder)
        backup_layout.addWidget(backup_btn)

        layout.addWidget(backup_group)

        # Sistem ayarları
        system_group = QGroupBox("Sistem Ayarları")
        system_layout = QVBoxLayout(system_group)

        restore_btn = QPushButton("Sistem Geri Yükleme Noktası Oluştur")
        restore_btn.clicked.connect(self.create_restore_point)
        system_layout.addWidget(restore_btn)

        admin_btn = QPushButton("Yönetici Olarak Yeniden Başlat")
        admin_btn.clicked.connect(self.restart_as_admin)
        admin_btn.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; }")
        system_layout.addWidget(admin_btn)

        layout.addWidget(system_group)

        layout.addStretch()

        self.tabs.addTab(settings_tab, "Ayarlar")

    def setup_tray_icon(self):
        """Sistem tepsi ikonunu ayarla"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        
        tray_menu = QMenu()
        
        show_action = QAction("Göster", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        quick_clean_action = QAction("Hızlı Temizlik", self)
        quick_clean_action.triggered.connect(self.quick_clean)
        tray_menu.addAction(quick_clean_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Çıkış", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()

    def quick_clean(self):
        """Hızlı temizlik işlemi"""
        options = {
            'temp_files': True,
            'prefetch': True,
            'browser_cache': False,
            'recycle_bin': True,
            'software_distribution': False
        }
        self.start_cleaning_with_options(options)

    def analyze_disk_space(self):
        """Disk alanını analiz et"""
        self.analyzer_worker = DiskAnalyzerWorker()
        self.analyzer_worker.progress_signal.connect(self.update_progress)
        self.analyzer_worker.analysis_complete.connect(self.display_analysis_results)
        self.analyzer_worker.start()
        
        self.progress_bar.setVisible(True)
        self.status_bar.showMessage("Disk analizi yapılıyor...")

    def display_analysis_results(self, results):
        """Analiz sonuçlarını göster"""
        self.progress_bar.setVisible(False)
        
        analysis_text = "=== DİSK KULLANIM ANALİZİ ===\n\n"
        
        # Klasör boyutları
        for name, data in results.items():
            if name != 'disk_info':
                analysis_text += f"{name}:\n"
                analysis_text += f"  Boyut: {data['size_str']}\n"
                analysis_text += f"  Dosya Sayısı: {data['count']}\n"
                analysis_text += f"  Yol: {data['path']}\n\n"
        
        # Disk bilgileri
        if 'disk_info' in results:
            analysis_text += "=== DİSK BİLGİLERİ ===\n\n"
            for disk, info in results['disk_info'].items():
                analysis_text += f"{disk}:\n"
                analysis_text += f"  Toplam: {self.format_size(info['total'])}\n"
                analysis_text += f"  Kullanılan: {self.format_size(info['used'])}\n"
                analysis_text += f"  Boş: {self.format_size(info['free'])}\n"
                analysis_text += f"  Doluluk: {info['percent']}%\n\n"
        
        self.analysis_text.setText(analysis_text)
        self.status_bar.showMessage("Disk analizi tamamlandı")

    def start_cleaning(self):
        """Temizleme işlemini başlat"""
        options = {
            'temp_files': self.temp_check.isChecked(),
            'prefetch': self.prefetch_check.isChecked(),
            'browser_cache': self.browser_check.isChecked(),
            'recycle_bin': self.recycle_check.isChecked(),
            'software_distribution': self.update_check.isChecked()
        }
        
        self.start_cleaning_with_options(options)

    def start_cleaning_with_options(self, options):
        """Seçeneklerle temizleme başlat"""
        if not any(options.values()):
            QMessageBox.warning(self, "Uyarı", "Lütfen en az bir temizleme seçeneği seçin!")
            return
        
        reply = QMessageBox.question(self, "Onay", 
                                   "Temizleme işlemini başlatmak istediğinizden emin misiniz?\n\n"
                                   "Bu işlem geri alınamaz!",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.cleaner_worker = CleanerWorker(options)
            self.cleaner_worker.progress_signal.connect(self.update_progress)
            self.cleaner_worker.finished_signal.connect(self.cleaning_finished)
            self.cleaner_worker.error_signal.connect(self.cleaning_error)
            self.cleaner_worker.start()
            
            self.progress_bar.setVisible(True)
            self.clean_btn.setEnabled(False)
            self.analyze_btn.setEnabled(False)
            self.status_bar.showMessage("Temizleme işlemi başlatıldı...")

    def update_progress(self, value, message):
        """İlerlemeyi güncelle"""
        self.progress_bar.setValue(value)
        self.status_bar.showMessage(message)

    def cleaning_finished(self, results):
        """Temizleme tamamlandığında"""
        self.progress_bar.setVisible(False)
        self.clean_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        
        total_freed = results['total']['freed']
        total_count = results['total']['count']
        
        result_text = "=== TEMİZLEME TAMAMLANDI ===\n\n"
        result_text += f"Toplam Kazanılan Alan: {self.format_size(total_freed)}\n"
        result_text += f"Silinen Öğe Sayısı: {total_count}\n\n"
        result_text += "Detaylar:\n"
        
        for category, data in results.items():
            if category != 'total':
                category_name = category.replace('_', ' ').title()
                result_text += f"  {category_name}: {self.format_size(data['freed'])} ({data['count']} öğe)\n"
        
        self.results_text.setText(result_text)
        self.status_bar.showMessage(f"Temizlik tamamlandı! {self.format_size(total_freed)} alan kazanıldı.")
        
        # Başarılı mesajı göster
        QMessageBox.information(self, "Başarılı", 
                              f"Temizleme işlemi başarıyla tamamlandı!\n\n"
                              f"Kazanılan alan: {self.format_size(total_freed)}\n"
                              f"Silinen öğe: {total_count}")

    def cleaning_error(self, error_message):
        """Temizleme hatası"""
        self.progress_bar.setVisible(False)
        self.clean_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        QMessageBox.critical(self, "Hata", f"Temizleme sırasında hata oluştu:\n{error_message}")

    def format_size(self, size_bytes):
        """Byte'ları okunabilir formata çevir"""
        if size_bytes == 0:
            return "0 B"
            
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

    def select_backup_folder(self):
        """Yedekleme klasörü seç"""
        folder = QFileDialog.getExistingDirectory(self, "Yedekleme Klasörünü Seç")
        if folder:
            self.settings['backup_folder'] = folder
            self.save_settings()

    def create_restore_point(self):
        """Sistem geri yükleme noktası oluştur"""
        try:
            QMessageBox.information(self, "Bilgi", 
                                  "Sistem geri yükleme noktası oluşturmak için yönetici olarak çalıştırmanız gerekebilir.")
        except Exception as e:
            QMessageBox.warning(self, "Uyarı", f"Geri yükleme noktası oluşturulamadı: {str(e)}")

    def restart_as_admin(self):
        """Yönetici olarak yeniden başlat"""
        reply = QMessageBox.question(self, "Yönetici Yeniden Başlat", 
                                   "Programı yönetici yetkileriyle yeniden başlatmak istiyor musunuz?",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                # Mevcut uygulamayı kapat ve yönetici olarak yeniden başlat
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
                QApplication.quit()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Yönetici olarak başlatılamadı: {str(e)}")

    def load_settings(self):
        """Ayarları yükle"""
        self.settings = {
            'auto_clean': False,
            'auto_clean_interval': 7,
            'backup_folder': '',
            'backup_enabled': False,
            'minimize_to_tray': True
        }
        
        # Ayarları dosyadan yükleme
        try:
            if os.path.exists('cleaner_settings.json'):
                with open('cleaner_settings.json', 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                    self.settings.update(saved_settings)
                    
                # UI'ı ayarlara göre güncelle
                self.auto_clean.setChecked(self.settings.get('auto_clean', False))
                self.auto_clean_interval.setValue(self.settings.get('auto_clean_interval', 7))
                self.backup_check.setChecked(self.settings.get('backup_enabled', False))
        except Exception as e:
            print(f"Ayarlar yüklenirken hata: {e}")

    def save_settings(self):
        """Ayarları kaydet"""
        try:
            # UI'dan ayarları al
            self.settings['auto_clean'] = self.auto_clean.isChecked()
            self.settings['auto_clean_interval'] = self.auto_clean_interval.value()
            self.settings['backup_enabled'] = self.backup_check.isChecked()
            
            # Ayarları dosyaya kaydet
            with open('cleaner_settings.json', 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"Ayarlar kaydedilirken hata: {e}")

    def quit_application(self):
        """Uygulamadan çık"""
        reply = QMessageBox.question(self, "Çıkış", 
                                   "Uygulamadan çıkmak istediğinizden emin misiniz?",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.save_settings()  # Çıkışta ayarları kaydet
            QApplication.quit()

    def closeEvent(self, event):
        """Pencere kapatma olayı"""
        self.save_settings()  # Kapatırken ayarları kaydet
        
        # Sistem tepsisine gizleme seçeneği
        if self.settings.get('minimize_to_tray', True):
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Windows Temizleyici",
                "Uygulama sistem tepsisinde çalışmaya devam ediyor",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            self.quit_application()

class ModernCleanerApp(QMainWindow):
    """Daha modern ve gelişmiş bir arayüz"""
    
    def __init__(self):
        super().__init__()
        self.cleaner_app = WindowsCleanerApp()
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Windows Temizleyici Pro - Modern Arayüz")
        self.setGeometry(100, 100, 1000, 750)
        
        # Modern stil
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2c3e50;
            }
            QTabWidget::pane {
                border: 1px solid #34495e;
                background-color: #ecf0f1;
            }
            QTabBar::tab {
                background-color: #34495e;
                color: white;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #3498db;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
            QCheckBox {
                color: #2c3e50;
                font-weight: bold;
            }
            QGroupBox {
                font-weight: bold;
                color: #2c3e50;
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

def check_dependencies():
    """Gerekli kütüphaneleri kontrol et"""
    required = ['psutil', 'PyQt5']
    missing = []
    
    for package in required:
        try:
            if package == 'PyQt5':
                import PyQt5
            elif package == 'psutil':
                import psutil
        except ImportError:
            missing.append(package)
    
    return missing

def install_dependencies(missing_packages):
    """Eksik kütüphaneleri yükle"""
    import subprocess
    import sys
    
    for package in missing_packages:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"[+] {package} başarıyla yüklendi")
        except subprocess.CalledProcessError:
            print(f"[-] {package} yüklenirken hata oluştu")
            return False
    return True

def main():
    # Eksik kütüphaneleri kontrol et
    missing = check_dependencies()
    if missing:
        print("Eksik kütüphaneler bulundu:")
        for package in missing:
            print(f"  - {package}")
        
        response = input("Otomatik olarak yüklemek ister misiniz? (e/h): ")
        if response.lower() in ['e', 'evet', 'y', 'yes']:
            if not install_dependencies(missing):
                print("Kütüphane yükleme başarısız. Lütfen manuel olarak yükleyin:")
                for package in missing:
                    print(f"pip install {package}")
                return
        else:
            print("Lütfen eksik kütüphaneleri manuel olarak yükleyin:")
            for package in missing:
                print(f"pip install {package}")
            return
    
    app = QApplication(sys.argv)
    
    # Uygulama stilini ayarla
    app.setStyle('Fusion')
    
    # Modern koyu tema
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(44, 62, 80))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 35, 45))
    palette.setColor(QPalette.AlternateBase, QColor(44, 62, 80))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(52, 73, 94))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(52, 152, 219))
    palette.setColor(QPalette.Highlight, QColor(52, 152, 219))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    palette.setColor(QPalette.Disabled, QPalette.Button, QColor(44, 62, 80))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 140, 141))
    app.setPalette(palette)
    
    # Uygulama fontu
    app.setFont(QFont("Segoe UI", 10))
    
    # Başlangıç mesajı
    print("Windows Temizleyici Pro başlatılıyor...")
    print("[+] Tüm bağımlılıklar yüklendi")
    print("[+] Yönetici kontrolü yapıldı")
    print("[+] GUI hazırlandı")
    
    window = WindowsCleanerApp()
    window.show()
    
    # İlk açılışta disk analizi öner
    if not hasattr(window, 'first_run_done'):
        reply = QMessageBox.question(window, "Hoş Geldiniz", 
                                   "Windows Temizleyici Pro'ya hoş geldiniz!\n\n"
                                   "İlk olarak disk alanınızı analiz etmek ister misiniz?",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            window.analyze_disk_space()
        window.first_run_done = True
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    # Yönetici yetkisi kontrolü
    if not is_admin():
        print("UYARI: Program yönetici yetkisi olmadan başlatıldı. Bazı işlemler kısıtlı olabilir.")
        print("Tam özellikler için programı 'Yönetici olarak çalıştırın'.")
    
    try:
        main()
    except Exception as e:
        print(f"Uygulama hatası: {e}")
        print("Lütfen aşağıdaki kütüphanelerin yüklü olduğundan emin olun:")
        print("pip install pyqt5 psutil")
        
        # Hata durumunda kullanıcıya bilgi ver
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "Başlatma Hatası", 
                           f"Uygulama başlatılırken hata oluştu:\n\n{str(e)}\n\n"
                           "Lütfen gerekli kütüphaneleri yükleyin:\n"
                           "pip install pyqt5 psutil")