"""Small runtime translation layer for the desktop UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QListWidget,
    QTabBar,
    QWidget,
)


LANGUAGE_NAMES = {
    "eng": "English",
    "fa": "فارسی",
    "es": "Español",
}

_TRANSLATIONS = {
    "fa": {
        "Remote Controllers": "کنترلرهای راه دور",
        "Input Test": "تست ورودی",
        "Gyro Steering": "فرمان ژیروسکوپی",
        "Calibrate Center": "کالیبره‌کردن مرکز",
        "Sensitivity": "حساسیت",
        "Deadzone": "ناحیهٔ مرده",
        "Gyro shortcut target": "دستهٔ میانبر ژیروسکوپ",
        "Controller Emulation": "شبیه‌سازی دسته",
        "Remote Gamepad": "📱 دستهٔ راه دور",
        "Hotkeys": "میانبرها",
        "Profiles": "🗂️ پروفایل‌ها",
        "Test XInput": "🧪 تست XInput",
        "Settings": "تنظیمات",
        "Virtual gamepad unavailable": "گیم‌پد مجازی در دسترس نیست",
        "ViGEmBus is required to create a virtual Xbox/XInput controller. Install the driver on this Windows PC, then recheck or restart VPadConnect. Other application features remain available.": "برای ساخت دستهٔ مجازی Xbox/XInput باید ViGEmBus روی همین رایانهٔ ویندوزی نصب باشد. درایور را نصب کنید و وضعیت را دوباره بررسی کنید یا VPadConnect را از نو اجرا کنید. سایر قابلیت‌های برنامه همچنان در دسترس هستند.",
        "Mouse control, hotkeys, physical HID detection, and Web Companion PC Remote are not blocked by this requirement.": "این پیش‌نیاز، کنترل ماوس، میانبرها، شناسایی HID و کنترل رایانه از طریق Web Companion را محدود نمی‌کند.",
        "Install ViGEmBus ↗": "نصب ViGEmBus ↗",
        "Recheck status": "بررسی دوبارهٔ وضعیت",
        "ViGEmBus is not installed": "ViGEmBus نصب نیست",
        "OPTIONAL WINDOWS DRIVER": "درایور اختیاری ویندوز",
        "Install ViGEmBus on this Windows PC to enable virtual Xbox/XInput output. Touch mouse and PC Remote stay available without it.": "برای فعال‌شدن خروجی مجازی Xbox/XInput، ViGEmBus را روی این رایانهٔ ویندوزی نصب کنید. ماوس لمسی و کنترل رایانه همچنان بدون آن کار می‌کنند.",
        "Recheck": "بررسی دوباره",
        "Remote action permissions": "مجوزهای کنترل از راه دور",
        "Keyboard and text": "صفحه‌کلید و متن",
        "Media and volume": "رسانه و صدا",
        "Clipboard access": "دسترسی به کلیپ‌بورد",
        "Approved app shortcuts": "میانبرهای برنامهٔ مجاز",
        "Presentation controls": "کنترل ارائه",
        "Power actions (off by default)": "عملیات برق (به‌طور پیش‌فرض خاموش)",
        "TLS fingerprint: start the server to create this PC's identity.": "اثر انگشت TLS: برای ساخت هویت این رایانه، سرور را شروع کنید.",
        "TLS SHA-256 fingerprint — enter this exact value in the remote client before pairing:": "اثر انگشت SHA-256 گواهی — پیش از جفت‌سازی، همین مقدار را در برنامهٔ کنترل از راه دور وارد کنید:",
        "About": "ℹ️ دربارهٔ برنامه",
        "Web Companion": "کنترل از طریق مرورگر",
        "Quit": "🚪 خروج",
        "No profile active": "پروفایل فعالی وجود ندارد",
        "Active profile": "پروفایل فعال",
        "active": "فعال",
        "Open ArvinNotDev on GitHub": "باز کردن صفحهٔ ArvinNotDev در گیت‌هاب",
        "Device": "دستگاه",
        "UI": "رابط کاربری",
        "Developer": "توسعه‌دهنده",
        "Device Settings": "تنظیمات دستگاه",
        "UI Settings": "تنظیمات رابط کاربری",
        "Developer Settings": "تنظیمات توسعه‌دهنده",
        "Customize controller input, mouse behavior, and output preferences.": "ورودی دسته، رفتار ماوس و تنظیمات خروجی را شخصی‌سازی کنید.",
        "Personalize appearance and accessibility.": "ظاهر برنامه و دسترس‌پذیری را شخصی‌سازی کنید.",
        "Diagnostics, raw controller reports, and rotating logs for troubleshooting.": "گزارش‌های عیب‌یابی، گزارش خام دسته و فایل‌های گزارش چرخشی.",
        "Reduce interface animations": "کاهش پویانمایی‌های رابط کاربری",
        "Browse…": "انتخاب مسیر…",
        "Open log file": "باز کردن فایل گزارش",
        "Open log folder": "باز کردن پوشهٔ گزارش",
        "Clear logs": "پاک‌کردن گزارش‌ها",
        "Diagnostic logs cleared.": "گزارش‌های عیب‌یابی پاک شدند.",
        "File logging enabled · rotating at 2 MiB, keeping 3 backups": "ثبت گزارش در فایل فعال است · چرخش در ۲ مگابایت، نگهداری ۳ نسخه",
        "Could not activate file logging. Check that the selected folder exists and is writable.": "فعال‌سازی ثبت گزارش ممکن نشد. مطمئن شوید پوشهٔ انتخاب‌شده وجود دارد و قابل نوشتن است.",
        "Detailed diagnostics are enabled. Turn on Log to file to retain them after closing the app.": "گزارش‌گیری دقیق فعال است. برای نگهداری گزارش‌ها پس از بستن برنامه، «ثبت گزارش در فایل» را فعال کنید.",
        "File logging is off. Enable it to save diagnostic logs to disk.": "ثبت گزارش در فایل خاموش است. برای ذخیرهٔ گزارش‌های عیب‌یابی آن را فعال کنید.",
        "Input poll interval (ms)": "فاصله خواندن ورودی (میلی‌ثانیه)",
        "Auto reconnect": "اتصال مجدد خودکار",
        "D-Pad as mouse": "تبدیل D-Pad به ماوس",
        "Mouse mode": "حالت ماوس",
        "Mouse sensitivity": "حساسیت ماوس",
        "Mouse deadzone": "ناحیهٔ مردهٔ ماوس",
        "Left joystick deadzone": "ناحیهٔ مردهٔ جوی‌استیک چپ",
        "Right joystick deadzone": "ناحیهٔ مردهٔ جوی‌استیک راست",
        "Axis inversion": "معکوس‌سازی محورها",
        "Left": "چپ",
        "Right": "راست",
        "Invert X joystick": "معکوس‌سازی محور X",
        "Invert Y joystick": "معکوس‌سازی محور Y",
        "Invert buttons": "معکوس‌سازی دکمه‌ها",
        "Language": "زبان",
        "Theme": "پوسته",
        "Debug": "اشکال‌زدایی",
        "Raw HID debug": "اشکال‌زدایی HID خام",
        "Open live terminal": "باز کردن ترمینال زنده",
        "Raw HID Live Terminal": "ترمینال زندهٔ HID خام",
        "RAW INPUT STREAM": "جریان زندهٔ ورودی خام",
        "LIVE": "زنده",
        "PAUSED": "متوقف",
        "DISABLED": "غیرفعال",
        "Waiting for HID reports…": "در انتظار گزارش‌های HID…",
        "Live capture is off. Enable Raw HID debug to receive reports.": "ثبت زنده خاموش است. برای دریافت گزارش‌ها، اشکال‌زدایی HID خام را فعال کنید.",
        "Capture is paused. Incoming reports are ignored until resumed.": "ثبت موقتاً متوقف شده است؛ گزارش‌های ورودی تا زمان ادامه نادیده گرفته می‌شوند.",
        "Live capture is receiving reports.": "ثبت زنده در حال دریافت گزارش‌ها است.",
        "Packets": "بسته‌ها",
        "Rate": "نرخ",
        "Last report": "آخرین گزارش",
        "Device": "دستگاه",
        "Auto-scroll": "اسکرول خودکار",
        "Pause stream": "توقف جریان",
        "Resume stream": "ادامهٔ جریان",
        "Clear": "پاک‌کردن",
        "Copy latest": "کپی آخرین گزارش",
        "Save capture…": "ذخیرهٔ خروجی…",
        "Close": "بستن",
        "Could not save capture:": "ذخیرهٔ خروجی ممکن نشد:",
        "Log to file": "ثبت گزارش در فایل",
        "Log file path": "مسیر فایل گزارش",
        "Reset": "بازنشانی",
        "Apply Now": "اعمال فوری",
        "Auto-save is on": "ذخیرهٔ خودکار فعال است",
        "✓ Auto-saved": "✓ ذخیرهٔ خودکار انجام شد",
        "Save Settings to Profile": "ذخیرهٔ تنظیمات در پروفایل",
        "Profiles Not Available": "پروفایل‌ها در دسترس نیستند",
        "Profile manager is not initialized.": "مدیر پروفایل آماده نشده است.",
        "New Profile": "پروفایل جدید",
        "Profile name:": "نام پروفایل:",
        "Overwrite Profile?": "بازنویسی پروفایل؟",
        "Profile Saved": "پروفایل ذخیره شد",
        "Profile Updated": "پروفایل به‌روزرسانی شد",
        "Profiles": "پروفایل‌ها",
        "Manage your application settings profiles": "پروفایل‌های تنظیمات برنامه را مدیریت کنید",
        "Select a profile": "یک پروفایل انتخاب کنید",
        "Description": "توضیحات",
        "Add a description for this profile…": "برای این پروفایل توضیحی بنویسید…",
        "Save Description": "ذخیرهٔ توضیحات",
        "Metadata": "اطلاعات",
        "Created: —": "ساخته‌شده: —",
        "Modified: —": "آخرین تغییر: —",
        "Created": "ساخته‌شده",
        "Modified": "آخرین تغییر",
        "Settings Summary": "خلاصهٔ تنظیمات",
        "Built with care for gamers 🎮": "با عشق برای گیمرها ساخته شده 🎮",
        "Activate Profile": "فعال‌سازی پروفایل",
        "✓ Active": "✓ فعال",
        "＋ New": "＋ جدید",
        "⧉ Copy": "⧉ کپی",
        "✎ Rename": "✎ تغییر نام",
        "🗑 Delete": "🗑 حذف",
        "Delete": "حذف",
        "Add Controller": "➕ افزودن دسته",
        "📷 Set Image": "📷 انتخاب تصویر",
        "⬇ Import": "⬇ درون‌ریزی",
        "⬆ Export": "⬆ برون‌بری",
        "Remove profile image": "حذف تصویر پروفایل",
        "Save as new profile…": "ذخیره به‌عنوان پروفایل جدید…",
        "Overwrite": "بازنویسی",
        "Emulated Devices": "دستگاه‌های شبیه‌سازی‌شده",
        "Battery": "باتری",
        "Connected Clients": "کلاینت‌های متصل",
        "Trusted Platforms": "دستگاه‌های مورد اعتماد",
        "Start Server": "شروع سرور",
        "Stop Server": "توقف سرور",
        "Remove": "حذف",
        "Disconnect": "قطع اتصال",
        "Emulate": "شبیه‌سازی",
        "Stop": "توقف",
        "Choose a controller to define hotkeys on.\n(Hotkeys will be applied to all controllers.)":
            "دسته‌ای را برای تعریف میانبر انتخاب کنید.\n(میانبرها روی همهٔ دسته‌ها اعمال می‌شوند.)",
        "Add Hotkey": "افزودن میانبر",
        "Delete Hotkey": "حذف میانبر",
        "Redo": "دوباره",
        "Apply": "اعمال",
        "Current Hotkeys": "میانبرهای فعلی",
        "Hotkey Settings": "تنظیمات میانبر",
        "Xbox 360 Controller Monitor": "مانیتور دستهٔ Xbox 360",
        "Buttons": "دکمه‌ها",
        "No buttons pressed": "هیچ دکمه‌ای فشرده نشده است",
        "Controller": "دسته",
        "Lightbar": "نوار نور",
        "Lightbar settings": "تنظیمات نوار نور",
        "Lightbar On": "روشن بودن نوار نور",
        "Choose color…": "انتخاب رنگ…",
        "HEX": "HEX",
        "Battery Lightbar": "نمایش باتری با نوار نور",
        "Charging indication": "نمایش وضعیت شارژ",
        "Save": "ذخیره",
        "Cancel": "لغو",
        "HidHide": "HidHide",
        "Unhide All": "نمایش همه",
        "Open Link": "باز کردن لینک",
        "Hide": "مخفی کردن",
        "Unhide": "نمایش",
        "Hidden": "مخفی",
        "Visible": "قابل مشاهده",
        "Unknown": "ناشناخته",
        "✨  VPADCONNECT": "✨  VPADCONNECT",
        "Built with care for gamers 🎮": "با عشق برای گیمرها ساخته شده 🎮",
        "Developer: آروین جعفری": "توسعه‌دهنده: آروین جعفری",
        "🐙 GitHub Profile": "🐙 پروفایل گیت‌هاب",
        "📦 Project Repository": "📦 مخزن پروژه",
        "💡 Tip: Create a profile for each game and switch between them in seconds.":
            "💡 نکته: برای هر بازی یک پروفایل بسازید و در چند ثانیه جابه‌جا شوید.",
        "A modern bridge between your controllers, XInput, keyboard, and mouse.":
            "پل مدرن بین دسته‌ها، XInput، صفحه‌کلید و ماوس شما.",
        "VPadConnect helps you connect physical HID controllers to virtual Xbox 360 devices with flexible profiles, hotkeys, mouse mode, remote gamepad support, and HidHide integration.":
            "VPadConnect دسته‌های HID فیزیکی را با پروفایل‌های "
            "انعطاف‌پذیر، میانبرها، حالت ماوس، دستهٔ راه دور و HidHide به دستگاه‌های "
            "مجازی Xbox 360 متصل می‌کند.",
        "English": "انگلیسی",
        "فارسی": "فارسی",
        "Español": "اسپانیایی",
    },
    "es": {
        "Remote Controllers": "Mandos remotos",
        "Input Test": "Prueba de entrada",
        "Gyro Steering": "Dirección por giroscopio",
        "Calibrate Center": "Calibrar centro",
        "Sensitivity": "Sensibilidad",
        "Deadzone": "Zona muerta",
        "Gyro shortcut target": "Mando objetivo del atajo de giroscopio",
        "Controller Emulation": "Emulación de mandos",
        "Remote Gamepad": "📱 Gamepad remoto",
        "Hotkeys": "Atajos",
        "Profiles": "🗂️ Perfiles",
        "Test XInput": "🧪 Probar XInput",
        "Settings": "Ajustes",
        "Virtual gamepad unavailable": "Mando virtual no disponible",
        "ViGEmBus is required to create a virtual Xbox/XInput controller. Install the driver on this Windows PC, then recheck or restart VPadConnect. Other application features remain available.": "ViGEmBus es necesario para crear un mando virtual Xbox/XInput. Instala el controlador en este PC con Windows y vuelve a comprobarlo o reinicia VPadConnect. Las demás funciones siguen disponibles.",
        "Mouse control, hotkeys, physical HID detection, and Web Companion PC Remote are not blocked by this requirement.": "Este requisito no bloquea el ratón, los atajos, la detección HID física ni el control remoto del PC mediante Web Companion.",
        "Install ViGEmBus ↗": "Instalar ViGEmBus ↗",
        "Recheck status": "Volver a comprobar",
        "ViGEmBus is not installed": "ViGEmBus no está instalado",
        "OPTIONAL WINDOWS DRIVER": "CONTROLADOR OPCIONAL DE WINDOWS",
        "Install ViGEmBus on this Windows PC to enable virtual Xbox/XInput output. Touch mouse and PC Remote stay available without it.": "Instala ViGEmBus en este PC con Windows para habilitar la salida virtual Xbox/XInput. El ratón táctil y el control remoto del PC siguen disponibles sin él.",
        "Recheck": "Volver a comprobar",
        "Remote action permissions": "Permisos de control remoto",
        "Keyboard and text": "Teclado y texto",
        "Media and volume": "Multimedia y volumen",
        "Clipboard access": "Acceso al portapapeles",
        "Approved app shortcuts": "Accesos a aplicaciones aprobadas",
        "Presentation controls": "Controles de presentación",
        "Power actions (off by default)": "Acciones de energía (desactivadas por defecto)",
        "TLS fingerprint: start the server to create this PC's identity.": "Huella TLS: inicia el servidor para crear la identidad de este PC.",
        "TLS SHA-256 fingerprint — enter this exact value in the remote client before pairing:": "Huella SHA-256 TLS: introduce este valor exacto en el cliente remoto antes de emparejar.",
        "About": "ℹ️ Acerca de",
        "Web Companion": "Control desde el navegador",
        "Quit": "🚪 Salir",
        "No profile active": "No hay perfil activo",
        "Active profile": "Perfil activo",
        "active": "activo",
        "Device": "Dispositivo",
        "UI": "Interfaz",
        "Developer": "Desarrollador",
        "Device Settings": "Ajustes del dispositivo",
        "UI Settings": "Ajustes de la interfaz",
        "Developer Settings": "Ajustes del desarrollador",
        "Raw HID debug": "Depuración HID sin procesar",
        "Open live terminal": "Abrir terminal en vivo",
        "Raw HID Live Terminal": "Terminal HID en vivo",
        "RAW INPUT STREAM": "FLUJO DE ENTRADA SIN PROCESAR",
        "LIVE": "EN VIVO",
        "PAUSED": "EN PAUSA",
        "DISABLED": "DESACTIVADO",
        "Waiting for HID reports…": "Esperando informes HID…",
        "Live capture is off. Enable Raw HID debug to receive reports.": "La captura en vivo está desactivada. Activa la depuración HID sin procesar para recibir informes.",
        "Capture is paused. Incoming reports are ignored until resumed.": "La captura está en pausa; se ignoran los informes entrantes hasta reanudarla.",
        "Live capture is receiving reports.": "La captura en vivo está recibiendo informes.",
        "Packets": "Paquetes",
        "Rate": "Frecuencia",
        "Last report": "Último informe",
        "Device": "Dispositivo",
        "Auto-scroll": "Desplazamiento automático",
        "Pause stream": "Pausar flujo",
        "Resume stream": "Reanudar flujo",
        "Clear": "Limpiar",
        "Copy latest": "Copiar último",
        "Save capture…": "Guardar captura…",
        "Close": "Cerrar",
        "Could not save capture:": "No se pudo guardar la captura:",
        "Customize controller input, mouse behavior, and output preferences.": "Personaliza la entrada del mando, el comportamiento del ratón y las preferencias de salida.",
        "Personalize appearance and accessibility.": "Personaliza la apariencia y la accesibilidad.",
        "Diagnostics, raw controller reports, and rotating logs for troubleshooting.": "Diagnósticos, informes HID sin procesar y registros rotativos para solucionar problemas.",
        "Reduce interface animations": "Reducir las animaciones de la interfaz",
        "Browse…": "Examinar…",
        "Open log file": "Abrir archivo de registro",
        "Open log folder": "Abrir carpeta de registros",
        "Clear logs": "Borrar registros",
        "Diagnostic logs cleared.": "Registros de diagnóstico borrados.",
        "File logging enabled · rotating at 2 MiB, keeping 3 backups": "Registro en archivo activado · rotación a 2 MiB, se conservan 3 copias",
        "Could not activate file logging. Check that the selected folder exists and is writable.": "No se pudo activar el registro en archivo. Comprueba que la carpeta exista y permita escritura.",
        "Detailed diagnostics are enabled. Turn on Log to file to retain them after closing the app.": "Los diagnósticos detallados están activados. Habilita el registro en archivo para conservarlos al cerrar la aplicación.",
        "File logging is off. Enable it to save diagnostic logs to disk.": "El registro en archivo está desactivado. Actívalo para guardar los diagnósticos en disco.",
        "Auto reconnect": "Reconexión automática",
        "D-Pad as mouse": "D-Pad como ratón",
        "Mouse mode": "Modo ratón",
        "Mouse sensitivity": "Sensibilidad del ratón",
        "Mouse deadzone": "Zona muerta del ratón",
        "Axis inversion": "Inversión de ejes",
        "Language": "Idioma",
        "Theme": "Tema",
        "Reset": "Restablecer",
        "Apply Now": "Aplicar ahora",
        "Auto-save is on": "Guardado automático activo",
        "Save Settings to Profile": "Guardar ajustes en el perfil",
        "Profiles": "Perfiles",
        "Manage your application settings profiles": "Gestiona tus perfiles de configuración",
        "Select a profile": "Selecciona un perfil",
        "Description": "Descripción",
        "Save Description": "Guardar descripción",
        "Metadata": "Metadatos",
        "Settings Summary": "Resumen de ajustes",
        "Created": "Creado",
        "Modified": "Modificado",
        "Activate Profile": "Activar perfil",
        "＋ New": "＋ Nuevo",
        "⧉ Copy": "⧉ Copiar",
        "✎ Rename": "✎ Renombrar",
        "🗑 Delete": "🗑 Eliminar",
        "Delete": "Eliminar",
        "Add Controller": "➕ Añadir mando",
        "📷 Set Image": "📷 Elegir imagen",
        "⬇ Import": "⬇ Importar",
        "⬆ Export": "⬆ Exportar",
        "Emulated Devices": "Dispositivos emulados",
        "Connected Clients": "Clientes conectados",
        "Trusted Platforms": "Plataformas de confianza",
        "Start Server": "Iniciar servidor",
        "Stop Server": "Detener servidor",
        "Remove": "Eliminar",
        "Disconnect": "Desconectar",
        "Emulate": "Emular",
        "Stop": "Detener",
        "Redo": "Rehacer",
        "Apply": "Aplicar",
        "Current Hotkeys": "Atajos actuales",
        "HidHide": "HidHide",
        "Unhide All": "Mostrar todos",
        "Open Link": "Abrir enlace",
        "Hide": "Ocultar",
        "Unhide": "Mostrar",
        "Hidden": "Oculto",
        "Visible": "Visible",
        "Unknown": "Desconocido",
        "Lightbar": "Barra de luz",
        "Lightbar settings": "Ajustes de la barra de luz",
        "Lightbar On": "Barra de luz encendida",
        "Choose color…": "Elegir color…",
        "HEX": "HEX",
        "Battery Lightbar": "Barra de luz de batería",
        "Charging indication": "Indicador de carga",
        "Save": "Guardar",
        "Cancel": "Cancelar",
        "✨  VPADCONNECT": "✨  VPADCONNECT",
        "Built with care for gamers 🎮": "Creado con cariño para gamers 🎮",
        "Developer: آروین جعفری": "Desarrollador: آروین جعفری",
        "🐙 GitHub Profile": "🐙 Perfil de GitHub",
        "📦 Project Repository": "📦 Repositorio del proyecto",
        "💡 Tip: Create a profile for each game and switch between them in seconds.":
            "💡 Consejo: crea un perfil para cada juego y cambia entre ellos en segundos.",
        "A modern bridge between your controllers, XInput, keyboard, and mouse.":
            "Un puente moderno entre tus mandos, XInput, teclado y ratón.",
        "VPadConnect helps you connect physical HID controllers to virtual Xbox 360 devices with flexible profiles, hotkeys, mouse mode, remote gamepad support, and HidHide integration.":
            "VPadConnect conecta mandos HID físicos con dispositivos "
            "Xbox 360 virtuales mediante perfiles flexibles, atajos, modo ratón, "
            "gamepad remoto e integración con HidHide.",
        "English": "Inglés",
        "فارسی": "Persa",
        "Español": "Español",
    },
}


def tr(text: str, language: str = "eng") -> str:
    """Translate a source string, leaving unknown/dynamic text untouched."""
    if not text or language == "eng":
        return text
    return _TRANSLATIONS.get(language, {}).get(text, text)


def _translate_widget(widget: QWidget, language: str) -> None:
    if widget.property("_i18n_dynamic"):
        return
    source = widget.property("_i18n_source")
    if source is None:
        if isinstance(widget, QGroupBox):
            source = widget.title()
        elif isinstance(widget, QAbstractButton):
            source = widget.text()
        elif isinstance(widget, QLabel):
            source = widget.text()
        else:
            source = widget.windowTitle()
        widget.setProperty("_i18n_source", source)

    if isinstance(widget, QGroupBox):
        widget.setTitle(tr(source, language))
    elif isinstance(widget, QAbstractButton):
        widget.setText(tr(source, language))
    elif isinstance(widget, QLabel):
        widget.setText(tr(source, language))
    elif source:
        widget.setWindowTitle(tr(source, language))

    if isinstance(widget, QComboBox):
        for index in range(widget.count()):
            item_source = widget.itemData(index, Qt.UserRole + 1000)
            if item_source is None:
                item_source = widget.itemText(index)
                widget.setItemData(index, item_source, Qt.UserRole + 1000)
            widget.setItemText(index, tr(item_source, language))

    if isinstance(widget, QListWidget):
        for index in range(widget.count()):
            item = widget.item(index)
            item_source = item.data(Qt.UserRole + 1000)
            if item_source is None:
                item_source = item.text()
                item.setData(Qt.UserRole + 1000, item_source)
            item.setText(tr(item_source, language))

    if isinstance(widget, QTabBar):
        for index in range(widget.count()):
            tab_source = widget.tabData(index)
            if tab_source is None:
                tab_source = widget.tabText(index)
                widget.setTabData(index, tab_source)
            widget.setTabText(index, tr(tab_source, language))


def apply_translations(root: QWidget, language: str) -> None:
    """Translate all static widgets below ``root`` without changing layout."""
    for widget in [root, *root.findChildren(QWidget)]:
        _translate_widget(widget, language)
    for action in root.findChildren(QAction):
        source = action.property("_i18n_source")
        if source is None:
            source = action.text()
            action.setProperty("_i18n_source", source)
        action.setText(tr(source, language))
