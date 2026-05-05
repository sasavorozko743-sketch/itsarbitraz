import asyncio
import os
import requests
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 7458769714, 1772108483 # сюди свій Telegram ID

ASSET = "USDT"
FIAT = "UAH"

settings = {
    "amount": 1000,
    "pay_type": "Monobank",
    "custom_limit": 41.99,
    "monitoring": False,
    "last_alert_time": 0,
    "alert_cooldown": 300,  # 5 хвилин
}

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


def keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Перевірити ціну", callback_data="check")],
        [InlineKeyboardButton(text="▶️ Моніторинг ON", callback_data="mon_on"),
         InlineKeyboardButton(text="⏸ Моніторинг OFF", callback_data="mon_off")],
        [InlineKeyboardButton(text="💰 Ліміт 41.99", callback_data="limit_41_99"),
         InlineKeyboardButton(text="💰 Ліміт 41.50", callback_data="limit_41_50")],
        [InlineKeyboardButton(text="💰 Ліміт 41.00", callback_data="limit_41_00"),
         InlineKeyboardButton(text="💰 Ліміт 40.00", callback_data="limit_40_00")],
        [InlineKeyboardButton(text="💰 Ліміт 39.00", callback_data="limit_39_00")],
        [InlineKeyboardButton(text="🏦 Monobank", callback_data="bank_mono"),
         InlineKeyboardButton(text="🏦 PrivatBank", callback_data="bank_privat")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")]
    ])


def get_p2p_ads(trade_type: str):
    """
    trade_type:
    BUY  = вкладка купити USDT
    SELL = вкладка продати USDT
    """

    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

    payload = {
        "asset": ASSET,
        "fiat": FIAT,
        "tradeType": trade_type,
        "page": 1,
        "rows": 10,
        "payTypes": [settings["pay_type"]] if settings["pay_type"] else [],
        "publisherType": None,
        "transAmount": str(settings["amount"])
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.post(url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()

    data = r.json().get("data", [])

    ads = []

    for item in data:
        adv = item["adv"]
        advertiser = item["advertiser"]

        price = float(adv["price"])
        min_limit = float(adv["minSingleTransAmount"])
        max_limit = float(adv["maxSingleTransAmount"])

        ads.append({
            "price": price,
            "min": min_limit,
            "max": max_limit,
            "nick": advertiser.get("nickName", "Unknown"),
            "orders": advertiser.get("monthOrderCount", 0),
            "rate": advertiser.get("monthFinishRate", 0),
        })

    return ads


def format_ads(title, ads):
    if not ads:
        return f"{title}\nНемає оголошень під твої фільтри.\n"

    text = f"{title}\n"

    for i, ad in enumerate(ads[:5], start=1):
        text += (
            f"{i}. {ad['price']} грн | {ad['nick']}\n"
            f"   Ліміт: {ad['min']:.0f}–{ad['max']:.0f} грн | "
            f"Угоди: {ad['orders']} | Завершення: {ad['rate']}%\n"
        )

    return text


async def check_price(send_to_user=True):
    try:
        buy_ads = get_p2p_ads("BUY")
        sell_ads = get_p2p_ads("SELL")

        best_buy = buy_ads[0]["price"] if buy_ads else None
        best_sell = sell_ads[0]["price"] if sell_ads else None

        text = (
            f"📊 Binance P2P {ASSET}/{FIAT}\n\n"
            f"Сума: {settings['amount']} грн\n"
            f"Банк: {settings['pay_type']}\n"
            f"Твій ліміт алерту: {settings['custom_limit']}\n\n"
        )

        text += format_ads("🟢 Купити USDT:", buy_ads)
        text += "\n"
        text += format_ads("🔴 Продати USDT:", sell_ads)

        if best_buy and best_sell:
            spread = best_sell - best_buy
            text += f"\n📌 Спред: {spread:.2f} грн"

        if send_to_user:
            await bot.send_message(ADMIN_ID, text)

        return best_buy, best_sell

    except Exception as e:
        if send_to_user:
            await bot.send_message(ADMIN_ID, f"Помилка перевірки: {e}")
        return None, None


async def monitor_loop():
    while True:
        if settings["monitoring"]:
            best_buy, best_sell = await check_price(send_to_user=False)

            if best_buy:
                now = time.time()

                # Алерт на твій ручний ліміт
                if best_buy <= settings["custom_limit"]:
                    if now - settings["last_alert_time"] > settings["alert_cooldown"]:
                        await bot.send_message(
                            ADMIN_ID,
                            f"🚨 ЦІНА ДОЙШЛА ДО ЛІМІТУ\n\n"
                            f"Купити USDT: {best_buy} грн\n"
                            f"Твій ліміт: {settings['custom_limit']}\n"
                            f"Сума: {settings['amount']} грн\n"
                            f"Банк: {settings['pay_type']}"
                        )
                        settings["last_alert_time"] = now

                # Окремий коридор 41.99 → 39.00
                if 39.00 <= best_buy <= 41.99:
                    if now - settings["last_alert_time"] > settings["alert_cooldown"]:
                        await bot.send_message(
                            ADMIN_ID,
                            f"🔥 ЦІНА В КОРИДОРІ 39–41.99\n\n"
                            f"Зараз купити USDT: {best_buy} грн"
                        )
                        settings["last_alert_time"] = now

        await asyncio.sleep(20)


@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Доступ закритий.")
        return

    await message.answer(
        "P2P-бот запущений.\n\n"
        "Команди:\n"
        "/amount 1000 — змінити суму\n"
        "/limit 41.33 — змінити ліміт\n"
        "/bank Monobank — змінити банк",
        reply_markup=keyboard()
    )


@dp.message(F.text.startswith("/amount"))
async def set_amount(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        amount = float(message.text.split()[1])
        settings["amount"] = amount
        await message.answer(f"Суму змінено: {amount} грн", reply_markup=keyboard())
    except:
        await message.answer("Формат: /amount 1000")


@dp.message(F.text.startswith("/limit"))
async def set_limit(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        limit = float(message.text.split()[1])
        settings["custom_limit"] = limit
        await message.answer(f"Ліміт змінено: {limit}", reply_markup=keyboard())
    except:
        await message.answer("Формат: /limit 41.33")


@dp.message(F.text.startswith("/bank"))
async def set_bank(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        bank = message.text.split(maxsplit=1)[1]
        settings["pay_type"] = bank
        await message.answer(f"Банк змінено: {bank}", reply_markup=keyboard())
    except:
        await message.answer("Формат: /bank Monobank")


@dp.callback_query(F.data == "check")
async def cb_check(callback: CallbackQuery):
    await callback.answer()
    await check_price(send_to_user=True)


@dp.callback_query(F.data == "mon_on")
async def cb_mon_on(callback: CallbackQuery):
    settings["monitoring"] = True
    await callback.answer("Моніторинг увімкнено")
    await callback.message.answer("Моніторинг увімкнено.", reply_markup=keyboard())


@dp.callback_query(F.data == "mon_off")
async def cb_mon_off(callback: CallbackQuery):
    settings["monitoring"] = False
    await callback.answer("Моніторинг вимкнено")
    await callback.message.answer("Моніторинг вимкнено.", reply_markup=keyboard())


@dp.callback_query(F.data.startswith("limit_"))
async def cb_limits(callback: CallbackQuery):
    value = callback.data.replace("limit_", "").replace("_", ".")
    settings["custom_limit"] = float(value)

    await callback.answer(f"Ліміт: {value}")
    await callback.message.answer(
        f"Новий ліміт алерту: {value}",
        reply_markup=keyboard()
    )


@dp.callback_query(F.data == "bank_mono")
async def cb_bank_mono(callback: CallbackQuery):
    settings["pay_type"] = "Monobank"
    await callback.answer("Monobank")
    await callback.message.answer("Банк: Monobank", reply_markup=keyboard())


@dp.callback_query(F.data == "bank_privat")
async def cb_bank_privat(callback: CallbackQuery):
    settings["pay_type"] = "PrivatBank"
    await callback.answer("PrivatBank")
    await callback.message.answer("Банк: PrivatBank", reply_markup=keyboard())


@dp.callback_query(F.data == "status")
async def cb_status(callback: CallbackQuery):
    await callback.answer()

    text = (
        f"⚙️ Налаштування\n\n"
        f"Моніторинг: {'ON' if settings['monitoring'] else 'OFF'}\n"
        f"Сума: {settings['amount']} грн\n"
        f"Банк: {settings['pay_type']}\n"
        f"Ліміт: {settings['custom_limit']}\n"
        f"Перевірка кожні: 20 сек\n"
        f"Антиспам: {settings['alert_cooldown']} сек"
    )

    await callback.message.answer(text, reply_markup=keyboard())


async def main():
    asyncio.create_task(monitor_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
