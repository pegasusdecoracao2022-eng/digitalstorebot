from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# TOKEN DO BOT
TOKEN = "8688800056:AAGJTmlPJiaPckAu-ab1UFMbYvQBVyU2wKI"


# Links de pagamento da Kiwify
LINKS_CHECKOUT = {
    "bronze": "https://pay.kiwify.com.br/mZXVqh5",
    "prata": "https://pay.kiwify.com.br/ncKuUX4",
    "ouro": "https://pay.kiwify.com.br/buZicPn",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = [
        [InlineKeyboardButton("💃 Danças", callback_data="dancas")]
    ]

    await update.message.reply_text(
        "🛒 Bem-vindo à Digital Store!\n\n"
        "Escolha uma categoria:",
        reply_markup=InlineKeyboardMarkup(teclado),
    )


async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Menu principal da Tati Maia
    if query.data == "dancas":
        teclado = [
            [
                InlineKeyboardButton(
                    "🥉 Tati Maia - Bronze",
                    callback_data="bronze",
                )
            ],
            [
                InlineKeyboardButton(
                    "🥈 Tati Maia - Prata",
                    callback_data="prata",
                )
            ],
            [
                InlineKeyboardButton(
                    "🥇 Tati Maia - Ouro",
                    callback_data="ouro",
                )
            ],
        ]

        await query.edit_message_text(
            "💃 TATI MAIA\n\nEscolha um plano:",
            reply_markup=InlineKeyboardMarkup(teclado),
        )

    # Informações dos planos
    elif query.data in ["bronze", "prata", "ouro"]:
        planos = {
            "bronze": {
                "nome": "🥉 PLANO BRONZE",
                "preco": "19,90",
                "videos": "200 vídeos exclusivos",
                "atualizacao": "Atualizações mensais",
            },
            "prata": {
                "nome": "🥈 PLANO PRATA",
                "preco": "39,90",
                "videos": "600 vídeos exclusivos",
                "atualizacao": "Atualizações semanais",
            },
            "ouro": {
                "nome": "🥇 PLANO OURO",
                "preco": "59,90",
                "videos": "Todo o acervo",
                "atualizacao": "Todas as atualizações futuras",
            },
        }

        plano = planos[query.data]
        link_pagamento = LINKS_CHECKOUT[query.data]

        teclado = [
            [
                InlineKeyboardButton(
                    "🛒 Comprar Agora",
                    url=link_pagamento,
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Voltar",
                    callback_data="dancas",
                )
            ],
        ]

        texto = (
            f"{plano['nome']}\n\n"
            f"💰 Valor: R$ {plano['preco']} por mês\n\n"
            f"📂 Conteúdo\n"
            f"• {plano['videos']}\n\n"
            f"✅ Benefícios\n"
            f"• Acesso após confirmação do pagamento\n"
            f"• {plano['atualizacao']}\n"
            f"• Conteúdo em alta qualidade\n\n"
            f"👇 Clique abaixo para assinar."
        )

        await query.edit_message_text(
            texto,
            reply_markup=InlineKeyboardMarkup(teclado),
        )


# Mostra no terminal o ID dos canais onde o bot é administrador
async def mostrar_id_canal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.channel_post:
        canal = update.channel_post.chat

        print("\n==============================")
        print(f"CANAL: {canal.title}")
        print(f"ID: {canal.id}")
        print("==============================\n")


# Inicialização do bot
app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(botoes))

app.add_handler(
    MessageHandler(
        filters.UpdateType.CHANNEL_POST,
        mostrar_id_canal,
    )
)

print("✅ Bot iniciado...")
print("✅ Checkouts da Kiwify configurados.")

app.run_polling()
