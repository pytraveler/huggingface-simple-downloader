"""Every worded string in the program, in both languages, in one place.

A `Text` carries the two wordings together rather than a key that looks them up.
There is then no key to go stale: a string that is added has both languages by
construction, and a string that is deleted takes both with it. The cost is that
the file is long, which is the right cost - it is read once and never debugged.

Errors raised deep in `hub` and `transfer` also carry a `Text`, because the
window is what will show them and it is the window that knows the language. See
`Failure`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

LANGS = ("en", "ru")


@dataclass(frozen=True)
class Text:
    en: str
    ru: str

    def __call__(self, lang: str) -> str:
        return self.ru if lang == "ru" else self.en

    def fmt(self, **kw: object) -> "Text":
        """Fill both wordings from the same values."""
        return Text(self.en.format(**kw), self.ru.format(**kw))

    def __str__(self) -> str:
        return self.en


class Failure(Exception):
    """An error with something to say to the user in either language."""

    def __init__(self, text: Text) -> None:
        super().__init__(text.en)
        self.text = text


def system_lang() -> str:
    """Russian if Windows is set to it, English otherwise.

    `GetUserDefaultUILanguage` is asked first because it answers what the user
    reads, while `locale` answers what the console is formatted for - on a
    Russian Windows with an English application locale those disagree.
    """
    try:
        import ctypes

        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
        return "ru" if (lcid & 0x3FF) == 0x19 else "en"
    except Exception:
        pass
    try:
        import locale

        name = (locale.getlocale()[0] or "") + (locale.getdefaultlocale()[0] or "")  # type: ignore[attr-defined]
    except Exception:
        name = ""
    return "ru" if "ru" in name.lower()[:8] else "en"


def pick_lang(saved: str = "") -> str:
    """Which language to open in, from the most deliberate answer available.

    The same three sources in the same order as `lang.bat` and `lang.sh`, so the
    launcher's messages and the window's captions cannot end up in different
    languages: `HFDL_LANG` beats the remembered setting, which beats the
    system's own idea of what the user reads.
    """
    env = (os.environ.get("HFDL_LANG") or "").strip().lower()[:2]
    if env in LANGS:
        return env
    if saved in LANGS:
        return saved
    return system_lang()


APP_TITLE = Text("HuggingFace Simple Downloader", "HuggingFace Simple Downloader")
SEC_SOURCE = Text(" Repository ", " Репозиторий ")
SEC_FILES = Text(" Files ", " Файлы ")
SEC_TARGET = Text(" Save to ", " Куда сохранять ")
SEC_QUEUE = Text(" Downloads ", " Загрузки ")
SEC_LOG = Text(" Log ", " Журнал ")

LBL_REPO = Text("Repository or link:", "Репозиторий или ссылка:")
HINT_REPO = Text(
    "Qwen/Qwen3-8B, or any huggingface.co link",
    "Qwen/Qwen3-8B или любая ссылка huggingface.co",
)
LBL_REVISION = Text("Branch:", "Ветка:")
LBL_ENDPOINT = Text("Mirror:", "Зеркало:")
BTN_FETCH = Text("Load the file list", "Загрузить список файлов")
TYPE_MODEL = Text("Model", "Модель")
TYPE_DATASET = Text("Dataset", "Датасет")
TYPE_SPACE = Text("Space", "Space")
BTN_OPEN_PAGE = Text("Open on the site", "Открыть на сайте")
MENU_FORGET_ONE = Text("Forget this entry", "Забыть эту строку")
MENU_FORGET_ALL = Text("Clear the history", "Очистить историю")

COL_NAME = Text("File", "Файл")
COL_SIZE = Text("Size", "Размер")
COL_LOCAL = Text("On disk", "На диске")
BTN_ALL = Text("Select all", "Выбрать всё")
BTN_NONE = Text("Clear", "Снять всё")
BTN_INVERT = Text("Invert", "Инвертировать")
LBL_FILTER = Text("Filter:", "Фильтр:")
HINT_FILTER = Text(".safetensors", ".safetensors")
BTN_EXPAND = Text("Expand", "Развернуть")
BTN_COLLAPSE = Text("Collapse", "Свернуть")

STAT_HAVE = Text("complete", "есть")
STAT_PART = Text("partial, {pct}", "частично, {pct}")
STAT_DIFF = Text("other size", "другой размер")

SUMMARY = Text(
    "{sel} of {total} selected - {size} to fetch",
    "Выбрано {sel} из {total} - скачать {size}",
)
SUMMARY_EMPTY = Text("Nothing loaded yet", "Список ещё не загружен")

LBL_FOLDER = Text("Folder:", "Папка:")
BTN_BROWSE = Text("Browse...", "Обзор...")
BTN_OPEN_FOLDER = Text("Open", "Открыть")
BTN_FORGET = Text("Forget the list", "Очистить список")
CHK_STRUCTURE = Text(
    "Keep the repository's subfolders", "Сохранять подпапки репозитория"
)
CHK_REPO_FOLDER = Text(
    "Make a subfolder named after the repository",
    "Создавать подпапку с именем репозитория",
)
HINT_REPO_FOLDER = Text("into {name}", "в {name}")
HINT_REPO_FOLDER_WAIT = Text(
    "the name comes from the repository - load its file list",
    "имя берётся из репозитория - загрузите список файлов",
)
LBL_THREADS = Text("At once:", "Одновременно:")
LBL_TOKEN = Text("HF token:", "Токен HF:")
CHK_SHOW_TOKEN = Text("show", "показать")
HINT_TOKEN = Text(
    "only for private or gated repositories on Hugging Face",
    "только для приватных и gated-репозиториев Hugging Face",
)
CHK_NO_VERIFY = Text(
    "Do not check HTTPS certificates (antivirus or proxy in the way)",
    "Не проверять HTTPS-сертификаты (мешает антивирус или прокси)",
)
TITLE_CHOOSE_FOLDER =Text("Where to save the files", "Куда сохранять файлы")

QCOL_FILE = Text("File", "Файл")
QCOL_DONE = Text("Progress", "Прогресс")
QCOL_SIZE = Text("Size", "Размер")
QCOL_SPEED = Text("Speed", "Скорость")
QCOL_ETA = Text("Left", "Осталось")
QCOL_STATE = Text("State", "Статус")

ST_PENDING = Text("waiting", "в очереди")
ST_RUNNING = Text("downloading", "качается")
ST_PAUSED = Text("paused", "пауза")
ST_DONE = Text("done", "готово")
ST_SKIPPED = Text("already there", "уже было")
ST_FAILED = Text("failed", "ошибка")
ST_CANCELLED = Text("stopped", "остановлено")

BTN_START = Text("Download", "Скачать")
BTN_PAUSE = Text("Pause", "Пауза")
BTN_RESUME = Text("Resume", "Продолжить")
BTN_STOP = Text("Stop", "Остановить")
BTN_CLEAR_QUEUE = Text("Clear the list", "Очистить список")

OVERALL_IDLE = Text("No downloads running", "Загрузок нет")
OVERALL = Text(
    "{done} of {total} - {speed} - {eta} left",
    "{done} из {total} - {speed} - осталось {eta}",
)
OVERALL_PAUSED = Text("{done} of {total} - paused", "{done} из {total} - пауза")

MSG_READY = Text("Ready.", "Готов к работе.")
MSG_MIRROR = Text("Mirror: {url}", "Зеркало: {url}")
MSG_MODELSCOPE = Text(
    "ModelScope: {url}. Public repositories only - this program does not sign in "
    "to ModelScope, and the HF token is not sent there.",
    "ModelScope: {url}. Только публичные репозитории - входить в ModelScope "
    "программа не умеет, и токен HF туда не отправляется.",
)
MSG_FETCHING = Text("Reading the file list of {repo}...", "Читаю список файлов {repo}...")
MSG_FETCHED = Text("{repo}: {n} files, {size} in total", "{repo}: {n} файлов, всего {size}")
MSG_NO_FILES = Text(
    "There are no files at this path in the repository.",
    "По этому пути в репозитории файлов нет.",
)
MSG_START = Text("Downloading {n} files, {size}", "Качаю {n} файлов, {size}")
MSG_RESUME_FILE = Text("Resuming {name} from {size}", "Докачиваю {name} с {size}")
MSG_DONE_FILE = Text("Done: {name}", "Готово: {name}")
MSG_SKIP_FILE = Text("Already there: {name}", "Уже на месте: {name}")
MSG_FAIL_FILE = Text("Failed: {name} - {err}", "Ошибка: {name} - {err}")
MSG_PAUSED = Text("Paused.", "Пауза.")
MSG_RESUMED = Text("Carrying on.", "Продолжаю.")
MSG_STOPPED = Text(
    "Stopped. What was downloaded is kept - press Download again to carry on.",
    "Остановлено. Скачанное сохранено - нажмите «Скачать» ещё раз, чтобы продолжить.",
)
MSG_FINISHED = Text(
    "Finished: {ok} downloaded, {skip} already there, {fail} failed.",
    "Завершено: {ok} скачано, {skip} уже было, {fail} с ошибкой.",
)
MSG_NO_VERIFY = Text(
    "Certificate checking is off - connections are not protected from interception.",
    "Проверка сертификатов отключена - соединение не защищено от перехвата.",
)
MSG_LANG_SWITCHED =Text("Language: English", "Язык: русский")
WARN_FLAT_CLASH = Text(
    "{n} files share a name and would overwrite each other - their subfolders "
    "were kept.",
    "У {n} файлов совпадают имена, они бы затёрли друг друга - для них подпапки "
    "сохранены.",
)

ERR_NO_REPO = Text(
    "Type a repository name or paste a link first.",
    "Сначала укажите репозиторий или вставьте ссылку.",
)
ERR_NO_SELECTION = Text("No file is selected.", "Не выбран ни один файл.")
ERR_NO_FOLDER = Text(
    "Choose the folder to save into.", "Выберите папку для сохранения."
)
ERR_BAD_FOLDER = Text(
    "{folder} cannot be created: {err}", "Не удалось создать {folder}: {err}"
)
ERR_BAD_REF = Text(
    "{text} does not look like a repository. Expected owner/name, or a link to "
    "huggingface.co or ModelScope.",
    "{text} не похоже на репозиторий. Нужно owner/name или ссылка на "
    "huggingface.co или ModelScope.",
)
ERR_NOT_FOUND = Text(
    "{repo} was not found. Check the name and the kind - a dataset is not a model.",
    "{repo} не найден. Проверьте имя и тип - датасет не модель.",
)
ERR_BAD_ENDPOINT = Text(
    "{text} is not an address the Mirror field can use. Expected something like "
    "https://hf-mirror.com; leave it empty for huggingface.co.",
    "{text} не годится как адрес в поле «Зеркало». Нужно что-то вроде "
    "https://hf-mirror.com; пустое поле означает huggingface.co.",
)
ERR_OTHER_HOST = Text(
    "{host} is not huggingface.co. If it is a mirror you trust, put it in the "
    "Mirror field first - the token is sent to whatever is there, so a link "
    "cannot choose that by itself.",
    "{host} - это не huggingface.co. Если это зеркало, которому вы доверяете, "
    "сначала впишите его в поле «Зеркало»: токен уходит именно туда, что там "
    "указано, и ссылка не вправе решать это за вас.",
)
ERR_GATED = Text(
    "{repo} is private or gated. Accept its licence on huggingface.co and paste an "
    "access token into the HF token field.",
    "{repo} приватный или gated. Примите его лицензию на huggingface.co и вставьте "
    "токен доступа в поле «Токен HF».",
)
ERR_MS_NOT_FOUND = Text(
    "{repo} was not found on ModelScope. Check the name, the branch and the kind - "
    "a dataset is not a model. A private repository looks exactly the same: only "
    "public ModelScope repositories can be downloaded here.",
    "{repo} не найден на ModelScope. Проверьте имя, ветку и тип - датасет не "
    "модель. Приватный репозиторий выглядит точно так же: с ModelScope здесь "
    "качаются только публичные репозитории.",
)
ERR_MS_PRIVATE = Text(
    "{repo} on ModelScope is private or needs approval. This program does not sign "
    "in to ModelScope, so only public repositories can be downloaded from there.",
    "{repo} на ModelScope приватный или требует одобрения. Входить в ModelScope "
    "программа не умеет, поэтому оттуда качаются только публичные репозитории.",
)
ERR_MS_NO_SPACE = Text(
    "ModelScope studios cannot be downloaded here - only models and datasets.",
    "Студии (studios) ModelScope здесь не качаются - только модели и датасеты.",
)
ERR_MS_LINK = Text(
    "{host} is ModelScope. Pick https://{host} in the Mirror field first, then load "
    "the list again.",
    "{host} - это ModelScope. Сначала выберите https://{host} в поле «Зеркало», "
    "потом загрузите список ещё раз.",
)
ERR_HTTP = Text("HTTP {status} from {url}", "HTTP {status} от {url}")
ERR_NETWORK = Text("Network error: {err}", "Ошибка сети: {err}")
ERR_NOT_URL = Text("Not a URL: {url}", "Это не URL: {url}")
ERR_REDIRECTS = Text(
    "More than {n} redirects starting at {url}",
    "Больше {n} перенаправлений от {url}",
)
ERR_GAVE_UP = Text(
    "gave up after {n} attempts: {err}", "не вышло за {n} попыток: {err}"
)
ERR_SIZE = Text(
    "expected {want} bytes, got {got}", "ожидалось {want} байт, получено {got}"
)
ERR_SPACE = Text(
    "{need} needed on {drive}, {free} free",
    "Нужно {need} на {drive}, свободно {free}",
)
ERR_UNSAFE_NAME = Text(
    "{name} would land outside the chosen folder",
    "{name} оказался бы вне выбранной папки",
)

ASK_CLOSE_TITLE = Text("Downloads are running", "Идёт загрузка")
ASK_CLOSE = Text(
    "Files are still downloading. Close anyway?\n"
    "What is already downloaded stays on disk and can be carried on later.",
    "Файлы ещё качаются. Всё равно закрыть?\n"
    "Скачанное останется на диске, докачать можно потом.",
)
