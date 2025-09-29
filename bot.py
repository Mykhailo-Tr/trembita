import logging
import sqlite3
import io
from datetime import datetime, date
import matplotlib.pyplot as plt
import pandas as pd

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters.callback_data import CallbackData

# FSM imports (aiogram v3)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

import settings

API_TOKEN = settings.BOT_API_KEY
DB_PATH = settings.REPORTS_DB_PATH

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN,
          default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())


class ReportCallback(CallbackData, prefix="report"):
    action: str
    report_id: int | None = None
    date_str: str | None = None


# --- FSM states ---
class MonthForm(StatesGroup):
    waiting_for_month = State()


# --- DB utils ---
def get_reports_by_date(target_date: date):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, content, created_at FROM report WHERE DATE(created_at)=?",
            (target_date.isoformat(),),
        )
        rows = cur.fetchall()
    return rows


def get_reports_by_month(target_year: int, target_month: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, content, created_at
            FROM report
            WHERE strftime('%Y', created_at) = ?
              AND strftime('%m', created_at) = ?
            ORDER BY created_at DESC
            """,
            (str(target_year), f"{target_month:02d}"),
        )
        rows = cur.fetchall()
    return rows


def get_all_reports():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, content, created_at FROM report ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
    return rows


def get_report_content(report_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT name, content, created_at FROM report WHERE id=?", (report_id,)
        )
        row = cur.fetchone()
    return row


# --- Handlers ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📅 Звіти за датою",
        callback_data=ReportCallback(action="choose_date").pack(),
    )
    kb.button(
        text="🗓 Звіти за місяць",
        callback_data=ReportCallback(action="choose_month").pack(),
    )
    kb.button(
        text="📋 Всі звіти",
        callback_data=ReportCallback(action="all_reports").pack(),
    )
    kb.adjust(1)
    await message.answer(
        "<b>👋 Вітаю!</b>\n\n"
        "Я бот для роботи зі <b>звітами</b> 📊\n\n"
        "Оберіть одну з опцій нижче ⬇️",
        reply_markup=kb.as_markup(),
    )


# Показати всі звіти
@dp.callback_query(ReportCallback.filter(F.action == "all_reports"))
async def show_all_reports(cb: CallbackQuery):
    await cb.answer()
    reports = get_all_reports()
    if not reports:
        await cb.message.edit_text("❌ <b>Немає звітів у базі.</b>")
        return

    kb = InlineKeyboardBuilder()
    for r_id, name, content, created_at in reports[:20]:
        date_str = created_at[:10]
        kb.button(
            text=f"📄 {name} | 📆 {date_str}",
            callback_data=ReportCallback(
                action="view_report", report_id=r_id
            ).pack(),
        )
    kb.button(
        text="🔙 Назад", callback_data=ReportCallback(action="menu").pack()
    )
    kb.adjust(1)
    await cb.message.edit_text(
        "📋 <b>Доступні звіти:</b>", reply_markup=kb.as_markup()
    )


# Вибір дати
@dp.callback_query(ReportCallback.filter(F.action == "choose_date"))
async def choose_date(cb: CallbackQuery):
    await cb.answer()
    today_str = date.today().isoformat()
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📅 Сьогодні",
        callback_data=ReportCallback(
            action="view_by_date", date_str=today_str
        ).pack(),
    )
    kb.button(
        text="🔍 Ввести дату вручну (YYYY-MM-DD)",
        callback_data=ReportCallback(action="enter_date").pack(),
    )
    kb.button(
        text="🔙 Назад", callback_data=ReportCallback(action="menu").pack()
    )
    kb.adjust(1)
    await cb.message.edit_text(
        "📆 <b>Оберіть дату:</b>", reply_markup=kb.as_markup()
    )


# Перегляд звітів за датою
@dp.callback_query(ReportCallback.filter(F.action == "view_by_date"))
async def view_by_date(cb: CallbackQuery, callback_data: ReportCallback):
    await cb.answer()
    try:
        dt = datetime.fromisoformat(callback_data.date_str).date()
    except Exception:
        await cb.message.edit_text("⚠️ <b>Невірний формат дати.</b>")
        return

    reports = get_reports_by_date(dt)
    if not reports:
        await cb.message.edit_text(f"❌ <b>Звітів за {dt} немає.</b>")
        return

    kb = InlineKeyboardBuilder()
    for r_id, name, content, created_at in reports:
        kb.button(
            text=f"📄 {name} | 📆 {created_at[:10]}",
            callback_data=ReportCallback(
                action="view_report", report_id=r_id
            ).pack(),
        )
    kb.button(
        text="🔙 Назад", callback_data=ReportCallback(action="menu").pack()
    )
    kb.adjust(1)
    await cb.message.edit_text(
        f"📊 <b>Звіти за {dt}:</b>", reply_markup=kb.as_markup()
    )


# Вибір місяця
@dp.callback_query(ReportCallback.filter(F.action == "choose_month"))
async def choose_month(cb: CallbackQuery):
    await cb.answer()
    today = date.today()
    current_month_str = today.strftime("%Y-%m")
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🗓 Поточний місяць",
        callback_data=ReportCallback(
            action="view_by_month", date_str=current_month_str
        ).pack(),
    )
    kb.button(
        text="🔍 Ввести місяць вручну (YYYY-MM)",
        callback_data=ReportCallback(action="enter_month").pack(),
    )
    kb.button(
        text="🔙 Назад", callback_data=ReportCallback(action="menu").pack()
    )
    kb.adjust(1)
    await cb.message.edit_text(
        "🗓 <b>Оберіть місяць:</b>", reply_markup=kb.as_markup()
    )


@dp.callback_query(ReportCallback.filter(F.action == "view_by_month"))
async def view_by_month(cb: CallbackQuery, callback_data: ReportCallback):
    await cb.answer()
    try:
        year_part, month_part = callback_data.date_str.split("-")
        year = int(year_part)
        month = int(month_part)
        if not (1 <= month <= 12):
            raise ValueError("Невірний місяць")
    except Exception:
        await cb.message.edit_text("⚠️ <b>Невірний формат місяця.</b>")
        return

    reports = get_reports_by_month(year, month)
    if not reports:
        await cb.message.edit_text(f"❌ <b>Звітів за {year}-{month:02d} немає.</b>")
        return

    kb = InlineKeyboardBuilder()
    for r_id, name, content, created_at in reports:
        kb.button(
            text=f"📄 {name} | 📆 {created_at[:10]}",
            callback_data=ReportCallback(action="view_report", report_id=r_id).pack(),
        )

    kb.button(text="🔙 Назад", callback_data=ReportCallback(action="choose_month").pack())
    kb.adjust(1)

    await cb.message.edit_text(
        f"📊 <b>Звіти за {year}-{month:02d}:</b>",
        reply_markup=kb.as_markup(),
    )


# Обробник: користувач обирає "ввести місяць вручну" — переключаємось в FSM
@dp.callback_query(ReportCallback.filter(F.action == "enter_month"))
async def enter_month_cb(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    # Просимо ввести місяць у форматі YYYY-MM
    await cb.message.edit_text(
        "🔍 Введіть місяць у форматі <code>YYYY-MM</code> (наприклад <code>2025-09</code>).\n"
        "Або відправте /cancel для відміни."
    )
    await state.set_state(MonthForm.waiting_for_month)


# Обробник для текстового введення місяця (FSM)
@dp.message(MonthForm.waiting_for_month)
async def month_input(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ Пусте повідомлення. Введіть місяць у форматі <code>YYYY-MM</code> або /cancel.")
        return

    if text.lower().strip() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer("❌ Дію скасовано.")
        await cmd_start(message)
        return

    # Парсимо рік і місяць
    try:
        year_part, month_part = text.split("-")
        year = int(year_part)
        month = int(month_part)
        if not (1 <= month <= 12):
            raise ValueError("Невірний місяць")
    except Exception:
        await message.answer(
            "⚠️ Невірний формат. Будь ласка введіть місяць у форматі <code>YYYY-MM</code>, "
            "наприклад <code>2025-09</code> або /cancel."
        )
        return

    # Отримуємо звіти
    reports = get_reports_by_month(year, month)
    if not reports:
        await message.answer(f"❌ <b>Звітів за {year}-{month:02d} немає.</b>")
        await state.clear()
        return

    kb = InlineKeyboardBuilder()
    for r_id, name, content, created_at in reports:
        kb.button(
            text=f"📄 {name} | 📆 {created_at[:10]}",
            callback_data=ReportCallback(action="view_report", report_id=r_id).pack(),
        )

    kb.button(text="🔙 Назад", callback_data=ReportCallback(action="choose_month").pack())
    kb.adjust(1)

    await message.answer(
        f"📊 <b>Звіти за {year}-{month:02d}:</b>",
        reply_markup=kb.as_markup(),
    )
    await state.clear()


# Перегляд звіту
@dp.callback_query(ReportCallback.filter(F.action == "view_report"))
async def view_report(cb: CallbackQuery, callback_data: ReportCallback):
    await cb.answer()
    row = get_report_content(callback_data.report_id)
    if not row:
        await cb.message.edit_text("❌ <b>Звіт не знайдено.</b>")
        return

    name, content, created_at = row
    df = pd.read_csv(io.StringIO(content))

    # додаємо колонку "№"
    df.insert(0, "№", range(1, len(df) + 1))

    # малюємо таблицю
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis("off")

    table = ax.table(
        cellText=df.head(15).values,
        colLabels=df.columns,
        cellLoc="center",
        loc="center",
    )

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.2, 1.2)

    for (row_idx, col_idx), cell in table.get_celld().items():
        if row_idx == 0:  # заголовки
            cell.set_text_props(weight="bold", color="white")
            cell.set_facecolor("#2E86C1")
        elif row_idx % 2 == 0:
            cell.set_facecolor("#F8F9F9")
        else:
            cell.set_facecolor("white")

    plt.title(f"{name}\n Створенно: {created_at[:10]}", fontsize=14, weight="bold")
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format="PNG", bbox_inches="tight", dpi=200)
    plt.close(fig)
    img_buf.seek(0)

    # фото як BufferedInputFile
    image = BufferedInputFile(img_buf.read(), filename=f"{name}.png")
    await cb.message.answer_photo(
        photo=image,
        caption=f"<b>📄 {name}</b>\n🗓 <i>{created_at[:10]}</i>\n\n📂 Файл CSV у вкладенні ⬇️",
    )

    # CSV як BufferedInputFile
    csv_buf = io.BytesIO(content.encode())
    csv_file = BufferedInputFile(csv_buf.read(), filename=f"{name}.csv")
    await cb.message.answer_document(document=csv_file)

    # --- НОВА ЧАСТИНА: розділення на основні та підсумкові ---
    numeric_cols = df.select_dtypes(include="number").columns

    if len(numeric_cols) > 0:
        # Основні рядки (без nan у числових колонках)
        main_df = df.dropna(subset=numeric_cols, how="any")
        # Підсумкові рядки (там де nan у числових колонках)
        totals_df = df[df[numeric_cols].isna().any(axis=1)]

        # --- Основний графік ---
        if not main_df.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            x_labels = main_df[main_df.columns.to_list()[1]].astype(str).tolist()
            x_labels = [f"{i+1}. {label}" for i, label in enumerate(x_labels)]

            main_df[numeric_cols].plot(kind="bar", ax=ax)

            ax.set_xticks(range(len(x_labels)))
            ax.set_xticklabels(x_labels, rotation=45, ha="right")

            plt.title("Основний графік по числових даних", fontsize=12, weight="bold")
            plt.tight_layout()
            chart_buf = io.BytesIO()
            plt.savefig(chart_buf, format="PNG", dpi=200)
            plt.close(fig)
            chart_buf.seek(0)

            chart = BufferedInputFile(chart_buf.read(), filename=f"{name}_main_chart.png")
            await cb.message.answer_photo(photo=chart)

        # --- Окремий графік для підсумків ---
        if not totals_df.empty:
            fig, ax = plt.subplots(figsize=(8, 4))
            totals_df = totals_df.reset_index(drop=True).get("Тара (kg)")

            # перетворюємо у словник, де ключі - назви показників
            summary_data = {
                "Брутто завезено": totals_df[0],
                "Брутто вивезено": totals_df[1],
                "Нетто завезено": totals_df[2],
                "Нетто вивезено": totals_df[3],
                "Загальний залишок": totals_df[4],
            }

            labels = list(summary_data.keys())
            values = list(summary_data.values())

            bars = ax.bar(labels, values, color=["#4CAF50", "#F44336", "#2196F3", "#FF9800", "#9C27B0"])

            # підписуємо значення над стовпчиками
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, height,
                        f"{height:,.0f} кг",
                        ha="center", va="bottom", fontsize=9, weight="bold")

            ax.set_ylabel("Кількість (кг)")
            ax.set_title("Підсумкові значення", fontsize=12, weight="bold")

            plt.tight_layout()
            totals_buf = io.BytesIO()
            plt.savefig(totals_buf, format="PNG", dpi=200)
            plt.close(fig)
            totals_buf.seek(0)

            totals_chart = BufferedInputFile(
                totals_buf.read(), filename=f"{name}_totals_chart.png"
            )
            await cb.message.answer_photo(photo=totals_chart)

    # меню
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Меню", callback_data=ReportCallback(action="menu").pack())
    kb.button(
        text="🔙 Назад",
        callback_data=ReportCallback(action="all_reports").pack(),
    )
    kb.adjust(2)
    await cb.message.answer(
        "⬆️ <b>Оберіть наступну дію:</b>", reply_markup=kb.as_markup()
    )

# Повернення в меню
@dp.callback_query(ReportCallback.filter(F.action == "menu"))
async def back_to_menu(cb: CallbackQuery):
    await cb.answer()
    await cmd_start(cb.message)


# Глобальна команда /cancel — тільки коли користувач в стані
@dp.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("❌ Дію скасовано.")
        await cmd_start(message)
    else:
        await message.answer("Немає активної операції, яку потрібно скасувати.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(dp.start_polling(bot))
