import logging
import random
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ====== НАСТРОЙКИ ======
BOT_TOKEN     = "8859847824:AAEfH__UkQuvOVNZyV-hGRXfCvxgUFVHckc"
CRYPTO_TOKEN  = "592962:AAbQZKwcihOajR7rjTjICHGnHY1MexUiJoQ"   # @CryptoBot → Pay → My Apps → Create App
CRYPTO_API    = "https://pay.crypt.bot/api"

# ====== ТОВАРЫ ======
PRODUCTS = [
    {"name": "Саморег Кляйз", "available": True, "price": 8},
]

# ====== ХРАНИЛИЩЕ В ПАМЯТИ ======
user_data_store = {}

# ====== КАПЧА ======
CAPTCHA_POOL = [
    (2, 3, 5), (3, 5, 8), (4, 4, 8), (6, 2, 8),
    (1, 7, 8), (5, 4, 9), (3, 6, 9), (7, 2, 9),
    (4, 3, 7), (2, 6, 8), (1, 5, 6), (3, 3, 6),
    (8, 1, 9), (5, 5, 10), (4, 6, 10), (2, 4, 6),
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ====== УТИЛИТЫ ======
def get_store(user_id: int) -> dict:
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "balance": 0,
            "orders": [],
            "favorites": [],
            "verified": False,
            "topup_history": [],
        }
    return user_data_store[user_id]


def main_menu():
    kb = [
        [KeyboardButton("📚 Все категории"), KeyboardButton("📦 Товары")],
        [KeyboardButton("📜 Правила"), KeyboardButton("👤 Мой профиль"), KeyboardButton("⚠️ Внимание")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def generate_captcha(context) -> str:
    a, b, answer = random.choice(CAPTCHA_POOL)
    context.user_data["captcha_answer"] = answer
    return f"🔐 Подтверди, что ты не робот!\n\nРеши пример: <b>{a} + {b} = ?</b>\n\nОтправь ответ числом:"


# ====== CRYPTOBOT API ======
async def create_invoice(amount: float) -> dict | None:
    """Создаёт инвойс в CryptoBot. Возвращает dict с pay_url и invoice_id."""
    headers = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
    payload = {
        "currency_type": "fiat",
        "fiat": "USD",
        "accepted_assets": "USDT,TON,BTC,ETH,LTC",
        "amount": str(amount),
        "description": "Пополнение баланса магазина",
        "expires_in": 3600,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTO_API}/createInvoice",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    inv = data["result"]
                    return {"invoice_id": inv["invoice_id"], "pay_url": inv["pay_url"]}
    except Exception as e:
        logger.error(f"CryptoBot createInvoice error: {e}")
    return None


async def check_invoice(invoice_id: int) -> str:
    """Проверяет статус инвойса. Возвращает: 'paid', 'active', 'expired', 'error'."""
    headers = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
    params = {"invoice_ids": invoice_id}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CRYPTO_API}/getInvoices",
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    items = data["result"].get("items", [])
                    if items:
                        return items[0]["status"]   # paid / active / expired
    except Exception as e:
        logger.error(f"CryptoBot getInvoices error: {e}")
    return "error"


# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    store = get_store(user.id)
    name = user.first_name or user.username or "друг"

    if store["verified"]:
        await update.message.reply_text(
            f"👋 С возвращением, {name}!",
            reply_markup=main_menu()
        )
        return

    context.user_data["waiting_captcha"] = True
    await update.message.reply_text(
        f"👋 Привет, <b>{name}</b>!\n\n"
        f"Добро пожаловать в наш магазин. Рады видеть тебя здесь!\n\n"
        + generate_captcha(context),
        parse_mode="HTML"
    )


# ====== Alle Kategorien ======
async def alle_kategorien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton("Аккаунты", callback_data="cat_accounts")]]
    await update.message.reply_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(buttons))


async def cat_accounts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    buttons = []
    for i, p in enumerate(PRODUCTS):
        if p["available"]:
            label = f"✅  {p['name']}  —  {p['price']}$"
            cb = f"buy_{i}"
        else:
            label = "Товар закончился"
            cb = f"sold_{i}"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_cats")])

    await query.edit_message_text(
        "Категория: Аккаунты\n\nВыберите товар:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def back_to_cats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [[InlineKeyboardButton("Аккаунты", callback_data="cat_accounts")]]
    await query.edit_message_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(buttons))


async def sold_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Товар закончился. Заказ отменён.")


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[1])
    p = PRODUCTS[idx]
    store = get_store(query.from_user.id)

    if store["balance"] >= p["price"]:
        store["balance"] -= p["price"]
        store["orders"].append(p["name"])
        await query.edit_message_text(
            f"✅ Покупка прошла успешно!\n\n"
            f"Товар: {p['name']}\n"
            f"Сумма: {p['price']}$\n"
            f"Остаток: {store['balance']}$"
        )
    else:
        await query.edit_message_text(
            f"Недостаточно средств.\n\n"
            f"Цена: {p['price']}$  |  Ваш баланс: {store['balance']}$\n\n"
            f"Пополните баланс в разделе 👤 Мой профиль."
        )


# ====== Artikel ======
async def artikel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = []
    for p in PRODUCTS:
        if p["available"]:
            lines.append(f"<b>{p['name']}</b>\nЦена: {p['price']}$\nСтатус: в наличии")
        else:
            lines.append(f"<b>{p['name']}</b>\nСтатус: товар закончился")
    await update.message.reply_text(
        "Актуальные товары:\n\n" + "\n\n".join(lines),
        parse_mode="HTML"
    )


# ====== Regeln ======
async def regeln(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 <b>Правила магазина</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🔄 <b>Замена товара</b>\n"
        "Замена осуществляется <u>только</u> в следующих случаях:\n"
        "✅ Невалид при покупке — <b>только при наличии видеозаписи</b> (в течение 10 минут после покупки)\n\n"
        "❌ <b>Замена НЕ предоставляется при:</b>\n"
        "• Бане аккаунта\n"
        "• Не заливе\n"
        "• Волне сноса\n"
        "• Наличии двухфакторной аутентификации (2FA) — это ахтунг с вашей стороны\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💸 <b>Вывод средств</b>\n"
        "Мы <b>никогда</b> не осуществляем вывод средств с баланса магазина на кошелёк клиента.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📌 По всем вопросам: @Lexsavvs | @Tonnyliver"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ====== Meins ======
async def meins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    store = get_store(user.id)
    name = user.first_name or user.username or "Пользователь"

    text = (
        f"Имя: <b>{name}</b>\n"
        f"ID: <code>{user.id}</code>\n"
        f"Баланс: <b>{store['balance']} $</b>"
    )
    buttons = [
        [InlineKeyboardButton("История заказов", callback_data="orders")],
        [InlineKeyboardButton("Активировать купон", callback_data="coupon")],
        [InlineKeyboardButton("Избранное", callback_data="favorites")],
        [
            InlineKeyboardButton("Пополнить баланс", callback_data="topup"),
            InlineKeyboardButton("История пополнений", callback_data="topup_history"),
        ],
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def orders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    store = get_store(query.from_user.id)
    count = len(store["orders"])

    if count == 0:
        text = "История заказов\n\nПокупок пока нет."
    else:
        items = "\n".join(f"• {o}" for o in store["orders"])
        text = f"История заказов\n\nКуплено аккаунтов: <b>{count}</b>\n\n{items}"

    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_meins")]]))


async def favorites_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    store = get_store(query.from_user.id)

    if not store["favorites"]:
        store["favorites"] = ["Саморег Кляйз"]

    items = "\n".join(f"— {f}" for f in store["favorites"])
    await query.edit_message_text(
        f"Избранное:\n\n{items}", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_meins")]]))


async def coupon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["waiting_coupon"] = True
    await query.edit_message_text(
        "Активация купона\n\nОтправьте ваш купон-код в чат:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_meins")]]))


async def topup_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    store = get_store(query.from_user.id)
    history = store.get("topup_history", [])

    if not history:
        text = "История пополнений\n\nПополнений не найдено."
    else:
        lines = "\n".join(f"• {h['amount']}$ — {h['date']}" for h in history[-10:])
        text = f"История пополнений:\n\n{lines}"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_meins")]]))


async def topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["waiting_topup"] = True
    await query.edit_message_text("💳 Укажите сумму пополнения баланса (в $):")


# ====== Проверка оплаты (реальная) ======
async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Проверяю оплату...", show_alert=False)

    invoice_id = context.user_data.get("invoice_id")
    amount = context.user_data.get("pending_amount", 0)
    store = get_store(query.from_user.id)

    if not invoice_id:
        await query.edit_message_text("Инвойс не найден. Попробуйте пополнить баланс заново.")
        return

    status = await check_invoice(invoice_id)

    if status == "paid":
        # Деньги поступили
        store["balance"] += amount
        from datetime import datetime
        store["topup_history"].append({
            "amount": amount,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        })
        context.user_data["pending_amount"] = 0
        context.user_data["invoice_id"] = None
        await query.edit_message_text(
            f"✅ <b>Оплата прошла успешно!</b>\n\n"
            f"Зачислено: <b>{amount}$</b>\n"
            f"Ваш баланс: <b>{store['balance']}$</b>",
            parse_mode="HTML"
        )

    elif status == "expired":
        context.user_data["invoice_id"] = None
        await query.edit_message_text(
            "⌛ Время оплаты истекло.\n\n"
            "Создайте новый счёт через кнопку «Пополнить баланс»."
        )

    elif status == "active":
        # Ещё не оплачено
        await query.edit_message_text(
            "⏳ Оплата пока не поступила.\n\n"
            "Убедитесь, что вы завершили платёж в CryptoBot, и попробуйте снова.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить снова", callback_data="check_payment")]
            ])
        )

    else:
        await query.edit_message_text(
            "❌ Ошибка при проверке оплаты.\n\n"
            "Попробуйте ещё раз или обратитесь в поддержку: @Lexsavvs",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить снова", callback_data="check_payment")]
            ])
        )


async def back_meins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    store = get_store(user.id)
    name = user.first_name or user.username or "Пользователь"

    text = (
        f"Имя: <b>{name}</b>\n"
        f"ID: <code>{user.id}</code>\n"
        f"Баланс: <b>{store['balance']} $</b>"
    )
    buttons = [
        [InlineKeyboardButton("История заказов", callback_data="orders")],
        [InlineKeyboardButton("Активировать купон", callback_data="coupon")],
        [InlineKeyboardButton("Избранное", callback_data="favorites")],
        [
            InlineKeyboardButton("Пополнить баланс", callback_data="topup"),
            InlineKeyboardButton("История пополнений", callback_data="topup_history"),
        ],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


# ====== Achtung ======
async def achtung(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ <b>Внимание</b>\n\n"
        "По всем вопросам (возврат, замена, реклама, сотрудничество):\n\n"
        "👤 @Lexsavvs\n"
        "👤 @Tonnyliver",
        parse_mode="HTML"
    )


# ====== Обработчик текстовых сообщений ======
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    store = get_store(user.id)

    # --- КАПЧА ---
    if context.user_data.get("waiting_captcha"):
        correct = context.user_data.get("captcha_answer")
        try:
            answer = int(text)
        except ValueError:
            await update.message.reply_text("Введи число — например: 5")
            return

        if answer == correct:
            context.user_data["waiting_captcha"] = False
            store["verified"] = True
            name = user.first_name or user.username or "друг"
            await update.message.reply_text(
                f"✅ Проверка пройдена!\n\nДобро пожаловать, <b>{name}</b>. Выбери раздел в меню ниже.",
                parse_mode="HTML",
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text(
                "Неверно. Попробуй ещё раз:\n\n" + generate_captcha(context),
                parse_mode="HTML"
            )
        return

    # Блок незарегистрированных
    if not store["verified"]:
        await update.message.reply_text("Сначала пройди проверку. Напиши /start")
        return

    # --- МЕНЮ ---
    if text == "📚 Все категории":
        await alle_kategorien(update, context)
    elif text == "📦 Товары":
        await artikel(update, context)
    elif text == "📜 Правила":
        await regeln(update, context)
    elif text == "👤 Мой профиль":
        await meins(update, context)
    elif text == "⚠️ Внимание":
        await achtung(update, context)

    # --- ПОПОЛНЕНИЕ: получаем сумму и создаём инвойс ---
    elif context.user_data.get("waiting_topup"):
        try:
            amount = float(text.replace(",", "."))
            if amount <= 0:
                raise ValueError

            context.user_data["waiting_topup"] = False

            # Создаём реальный инвойс в CryptoBot
            await update.message.reply_text("⏳ Создаю счёт для оплаты...")
            invoice = await create_invoice(amount)

            if invoice:
                context.user_data["pending_amount"] = amount
                context.user_data["invoice_id"] = invoice["invoice_id"]

                buttons = [
                    [InlineKeyboardButton("💳 Оплатить через CryptoBot", url=invoice["pay_url"])],
                    [InlineKeyboardButton("✅ Проверить оплату", callback_data="check_payment")],
                ]
                await update.message.reply_text(
                    f"Сумма к оплате: <b>{amount}$</b>\n\n"
                    f"Перейдите по кнопке ниже и завершите оплату в CryptoBot.\n"
                    f"После оплаты нажмите <b>«Проверить оплату»</b>.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            else:
                await update.message.reply_text(
                    "❌ Не удалось создать счёт. Проверьте настройки CryptoBot или попробуйте позже."
                )
        except ValueError:
            await update.message.reply_text("Введите корректную сумму, например: 8")

    # --- КУПОН ---
    elif context.user_data.get("waiting_coupon"):
        context.user_data["waiting_coupon"] = False
        await update.message.reply_text(
            "Купон не найден или уже был использован.",
            reply_markup=main_menu()
        )

    else:
        await update.message.reply_text("Используй кнопки меню.", reply_markup=main_menu())


# ====== MAIN ======
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(cat_accounts_callback,  pattern="^cat_accounts$"))
    app.add_handler(CallbackQueryHandler(back_to_cats_callback,  pattern="^back_to_cats$"))
    app.add_handler(CallbackQueryHandler(sold_callback,          pattern=r"^sold_\d+$"))
    app.add_handler(CallbackQueryHandler(buy_callback,           pattern=r"^buy_\d+$"))
    app.add_handler(CallbackQueryHandler(orders_callback,        pattern="^orders$"))
    app.add_handler(CallbackQueryHandler(favorites_callback,     pattern="^favorites$"))
    app.add_handler(CallbackQueryHandler(coupon_callback,        pattern="^coupon$"))
    app.add_handler(CallbackQueryHandler(topup_callback,         pattern="^topup$"))
    app.add_handler(CallbackQueryHandler(topup_history_callback, pattern="^topup_history$"))
    app.add_handler(CallbackQueryHandler(check_payment_callback, pattern="^check_payment$"))
    app.add_handler(CallbackQueryHandler(back_meins_callback,    pattern="^back_meins$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Бот запущен.")
    app.run_polling()


if __name__ == "__main__":
    main()