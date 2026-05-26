from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Главное меню
main_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🆘 Помощь", callback_data="help"),
            InlineKeyboardButton(text="🚀 Начать работу", callback_data="start_work"),
        ]
    ]
)

# Меню помощи
help_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ]
)

# Меню начала работы
start_work_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔌 Подключиться к агенту", callback_data="connect_to_agent"
            )
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")],
    ]
)

# Меню отключения
disconnect_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔌 Отключиться от агента", callback_data="disconnect"
            )
        ]
    ]
)

# Меню отмены подключения
connect_cancel_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="❌ Отменить подключение", callback_data="cancel_connect"
            )
        ]
    ]
)
