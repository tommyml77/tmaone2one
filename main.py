# Step 1: Авторизация через Google аккаунт и интеграция с Telegram Mini App (TMA)

# Чтобы реализовать авторизацию через Google, можно использовать библиотеку OAuth 2.0 и Google API Python Client.
# Ниже приведен пример использования Flask и библиотеки "google-auth" для авторизации через Google аккаунт.

# Установите необходимые библиотеки перед началом разработки:
# pip install Flask google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-telegram-bot pyyaml

from flask import Flask, request, session as flask_session, redirect
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os
import yaml

# Загрузка констант из файла consts.yaml
with open(os.path.join(os.path.dirname(__file__), 'secrs', 'consts.yaml'), 'r') as file:
    config = yaml.safe_load(file)

# Настройка Flask приложения
app = Flask(__name__)
app.secret_key = config['SECRET_KEY']  # Замените на ваш собственный секретный ключ

# Настройка Telegram Bot
TELEGRAM_TOKEN = config['TELEGRAM_TOKEN']
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Установите свой CLIENT_ID и CLIENT_SECRET от Google Developer Console
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Только для локального тестирования
CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(__file__), "secrs", "client_secrets.json")
REDIRECT_URI = config['REDIRECT_URI']
MY_DOMAIN = config['MY_DOMAIN']

# Проверка текущей рабочей директории и абсолютного пути к файлу client_secrets.json
print("Текущая рабочая директория:", os.getcwd())
print("Абсолютный путь к client_secrets.json:", os.path.abspath(CLIENT_SECRETS_FILE))

# Изменение текущей рабочей директории на директорию скрипта
os.chdir(os.path.dirname(__file__))

# Создание Flow для аутентификации
flow = Flow.from_client_secrets_file(
    CLIENT_SECRETS_FILE,
    scopes=["https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_uri=REDIRECT_URI
)

# Команда /start для Telegram бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("Авторизоваться через Google", callback_data='authorize')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Добро пожаловать в TMA! Пожалуйста, авторизуйтесь:', reply_markup=reply_markup)

application.add_handler(CommandHandler("start", start))

# Обработка нажатия на кнопку авторизации
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == 'authorize':
        authorization_url, state = flow.authorization_url()
        flask_session["state"] = state
        await query.edit_message_text(text=f"Пожалуйста, перейдите по следующей ссылке для авторизации: {authorization_url}")

application.add_handler(CallbackQueryHandler(button))

# Обработка редиректа после успешной авторизации
@app.route("/callback")
def callback():
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        return f"Ошибка при получении токена: {str(e)}"

    if "state" not in flask_session or flask_session["state"] != request.args.get("state"):
        return "Ошибка: Неверное состояние."

    credentials = flow.credentials
    flask_session['credentials'] = credentials_to_dict(credentials)
    return "Авторизация успешна! Вернитесь в Telegram, чтобы продолжить."

# Получение событий из Google Календаря через Telegram бота
async def calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    credentials = flask_session.get('credentials')
    if not credentials:
        await update.message.reply_text("Вам нужно авторизоваться через Google. Используйте /start для начала.")
        return

    credentials = build_credentials_from_dict(credentials)
    service = build('calendar', 'v3', credentials=credentials)

    # Получение списка событий из основного календаря пользователя
    events_result = service.events().list(
        calendarId='primary',
        maxResults=10,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    if not events:
        await update.message.reply_text('Нет предстоящих событий.')
        return

    events_list = "Предстоящие события:\n"
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        events_list += f"{start} - {event['summary']}\n"

    await update.message.reply_text(events_list)

application.add_handler(CommandHandler("calendar", calendar))

# Подключение к TON Connect для подписки
@app.route("/subscribe")
def subscribe():
    return "<h2>Интеграция с TON Connect в процессе разработки. Скоро здесь появится возможность подписки через TON Wallet.</h2>"

# Конвертация данных авторизации в словарь
def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

# Создание объекта Credentials из словаря
def build_credentials_from_dict(credentials_dict):
    from google.oauth2.credentials import Credentials
    return Credentials(
        token=credentials_dict['token'],
        refresh_token=credentials_dict['refresh_token'],
        token_uri=credentials_dict['token_uri'],
        client_id=credentials_dict['client_id'],
        client_secret=credentials_dict['client_secret'],
        scopes=credentials_dict['scopes']
    )

# Установка вебхука для Telegram бота
@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=['POST'])
def telegram_webhook():
    update = Update.de_json(request.get_json(), application.bot)
    application.update_queue.put_nowait(update)
    return "", 200

if __name__ == "__main__":
    # Устанавливаем вебхук для Telegram
    application.run_webhook(
        listen="0.0.0.0",
        port=5000,
        url_path=f"/webhook/{TELEGRAM_TOKEN}",
        webhook_url=f"https://{MY_DOMAIN}/webhook/{TELEGRAM_TOKEN}"
    )
    # Запуск Flask приложения для обработки Google OAuth callback и Telegram webhook
    app.run("0.0.0.0", port=5000, debug=True)
