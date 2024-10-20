# Step 1: Авторизация через Google аккаунт и интеграция с Telegram Mini App (TMA)

# Чтобы реализовать авторизацию через Google, можно использовать библиотеку OAuth 2.0 и Google API Python Client.
# Ниже приведен пример использования Flask и библиотеки "google-auth" для авторизации через Google аккаунт.

# Установите необходимые библиотеки перед началом разработки:
# pip install Flask google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-telegram-bot pyyaml

from flask import Flask, request, redirect
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os
import logging
import json
from google.oauth2.credentials import Credentials

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка констант из переменных окружения
SECRET_KEY = os.getenv('SECRET_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
REDIRECT_URI = os.getenv('REDIRECT_URI')
MY_DOMAIN = os.getenv('MY_DOMAIN')
CLIENT_SECRETS_JSON = os.getenv('CLIENT_SECRETS_FILE')

# Настройка Flask приложения
app = Flask(__name__)
app.secret_key = SECRET_KEY  # Замените на ваш собственный секретный ключ

# Настройка Telegram Bot
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Установите свой CLIENT_ID и CLIENT_SECRET от Google Developer Console
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Только для локального тестирования

# Проверка текущей рабочей директории
logger.info("Текущая рабочая директория: %s", os.getcwd())

# Создание Flow для аутентификации
client_secrets = json.loads(CLIENT_SECRETS_JSON)
flow = Flow.from_client_config(
    client_secrets,
    scopes=["https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_uri=REDIRECT_URI
)

# Хранение состояния авторизации (временное хранилище)
auth_states = {}

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
        auth_states[query.from_user.id] = state
        await query.edit_message_text(text=f"Пожалуйста, перейдите по следующей ссылке для авторизации: {authorization_url}")

application.add_handler(CallbackQueryHandler(button))

# Обработка редиректа после успешной авторизации
@app.route("/api/callback")
def callback():
    try:
        logger.info("Получение токена через callback")
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        logger.error(f"Ошибка при получении токена: {str(e)}")
        return f"Ошибка при получении токена: {str(e)}"

    user_id = request.args.get("state")
    if user_id not in auth_states or auth_states[user_id] != request.args.get("state"):
        logger.error("Ошибка: Неверное состояние.")
        return "Ошибка: Неверное состояние."

    credentials = flow.credentials
    auth_states[user_id] = credentials_to_dict(credentials)
    logger.info("Авторизация успешна, вернитесь в Telegram для продолжения.")
    return "Авторизация успешна! Вернитесь в Telegram, чтобы продолжить."

# Получение событий из Google Календаря через Telegram бота
async def calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    credentials_dict = auth_states.get(update.message.from_user.id)
    if not credentials_dict:
        await update.message.reply_text("Вам нужно авторизоваться через Google. Используйте /start для начала.")
        return

    credentials = build_credentials_from_dict(credentials_dict)
    service = build('calendar', 'v3', credentials=credentials)

    # Получение списка событий из основного календаря пользователя
    try:
        events_result = service.events().list(
            calendarId='primary',
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
    except Exception as e:
        logger.error(f"Ошибка при получении событий из календаря: {str(e)}")
        await update.message.reply_text("Ошибка при получении событий из календаря.")
        return

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
@app.route("/api/subscribe")
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
    return Credentials(
        token=credentials_dict['token'],
        refresh_token=credentials_dict['refresh_token'],
        token_uri=credentials_dict['token_uri'],
        client_id=credentials_dict['client_id'],
        client_secret=credentials_dict['client_secret'],
        scopes=credentials_dict['scopes']
    )

# Установка вебхука для Telegram бота
@app.route(f"/api/webhook/{TELEGRAM_TOKEN}", methods=['POST'])
def telegram_webhook():
    update = Update.de_json(request.get_json(), application.bot)
    application.update_queue.put_nowait(update)
    return "", 200

logger.info("Финишная настройка завершена, готово к работе с Vercel")
