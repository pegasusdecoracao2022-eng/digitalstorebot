import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Exibe erros importantes nos logs do Railway
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# Pasta onde está o arquivo bot.py
BASE_DIR = Path(__file__).resolve().parent

# Token armazenado nas Variables do Railway
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "A variável BOT_TOKEN não foi configurada no Railway."
    )


# Links de pagamento da Kiwify
LINKS_CHECKOUT = {
    "tati_bronze": "https://pay.kiwify.com.br/mZXVqh5",
    "tati_prata": "https://pay.kiwify.com.br/ncKuUX4",
    "tati_ouro": "https://pay.kiwify.com.br/buZicPn",
}


# Informações dos planos
PLANOS = {
    "tati_bronze": {
        "nome": "🥉 PLANO BRONZE",
        "preco": "19,90",
        "videos": "200 vídeos exclusivos",
        "atualizacao": "Atualizações mensais",
        "imagem": BASE_DIR / "fotos" / "tati maia" / "tati 1.jpg",
    },
    "tati_prata": {
        "nome": "🥈 PLANO PRATA",
        "preco": "39,90",
        "videos": "500 vídeos exclusivos",
        "atualizacao": "Atualizações semanais",
        "imagem": BASE_DIR / "fotos" / "tati maia" / "tati 3.jpg",
    },
    "tati_ouro": {
        "nome": "🥇 PLANO OURO",
        "preco": "59,90",
        "videos": "900 vídeos exclusivos",
        "atualizacao": "Todas as atualizações futuras",
        "imagem": BASE_DIR / "fotos" / "tati maia" / "tati 2.jpg",
    },
}


def teclado_menu_principal() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💃 Danças",
                    callback_data="categoria_dancas",
                )
            ]
        ]
    )


def teclado_modelos() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💃 Tati Maia",
                    callback_data="modelo_tati_maia",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 Menu principal",
                    callback_data="menu_principal",
                )
            ],
        ]
    )


def teclado_planos_tati() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🥉 Bronze",
                    callback_data="tati_bronze",
                )
            ],
            [
                InlineKeyboardButton(
                    "🥈 Prata",
                    callback_data="tati_prata",
                )
            ],
            [
                InlineKeyboardButton(
                    "🥇 Ouro",
                    callback_data="tati_ouro",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Voltar",
                    callback_data="categoria_dancas",
                )
            ],
        ]
    )


async def substituir_por_texto(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    texto: str,
    teclado: InlineKeyboardMarkup,
) -> None:
    """
    Troca a tela atual por uma mensagem de texto.

    Se a tela atual for uma foto, apaga a foto e envia texto.
    Se já for uma mensagem de texto, apenas edita a mensagem.
    """
    query = update.callback_query
    mensagem = query.message
    chat_id = mensagem.chat.id

    if mensagem.photo:
        await mensagem.delete()

        await context.bot.send_message(
            chat_id=chat_id,
            text=texto,
            reply_markup=teclado,
        )
    else:
        await query.edit_message_text(
            text=texto,
            reply_markup=teclado,
        )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message:
        return

    await update.message.reply_text(
        "🛒 Bem-vindo à Digital Store!\n\n"
        "Escolha uma categoria:",
        reply_markup=teclado_menu_principal(),
    )


async def botoes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query

    if not query or not query.message:
        return

    await query.answer()

    # Lista de modelos
    if query.data == "categoria_dancas":
        await substituir_por_texto(
            update=update,
            context=context,
            texto=(
                "💃 DANÇAS\n\n"
                "Escolha uma dançarina:"
            ),
            teclado=teclado_modelos(),
        )

    # Planos da Tati Maia
    elif query.data == "modelo_tati_maia":
        await substituir_por_texto(
            update=update,
            context=context,
            texto=(
                "💃 TATI MAIA\n\n"
                "Escolha um plano:"
            ),
            teclado=teclado_planos_tati(),
        )

    # Tela de um plano
    elif query.data in PLANOS:
        plano = PLANOS[query.data]
        caminho_imagem = plano["imagem"]
        link_pagamento = LINKS_CHECKOUT[query.data]
        chat_id = query.message.chat.id

        teclado = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🛒 Comprar Agora",
                        url=link_pagamento,
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Voltar aos planos",
                        callback_data="modelo_tati_maia",
                    )
                ],
            ]
        )

        texto = (
            f"{plano['nome']}\n\n"
            f"💃 Modelo: Tati Maia\n\n"
            f"💰 Valor: R$ {plano['preco']} por mês\n\n"
            f"📂 Conteúdo\n"
            f"• {plano['videos']}\n\n"
            f"✅ Benefícios\n"
            f"• Acesso após confirmação do pagamento\n"
            f"• {plano['atualizacao']}\n"
            f"• Conteúdo em alta qualidade\n\n"
            f"👇 Clique abaixo para assinar."
        )

        if not caminho_imagem.is_file():
            logger.error(
                "Imagem não encontrada: %s",
                caminho_imagem,
            )

            await query.message.reply_text(
                "❌ Não consegui encontrar a imagem deste plano.\n\n"
                "Verifique o nome e a pasta do arquivo."
            )
            return

        # Remove a tela anterior para não acumular menus
        await query.message.delete()

        with caminho_imagem.open("rb") as foto:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=foto,
                caption=texto,
                reply_markup=teclado,
            )

    # Menu principal
    elif query.data == "menu_principal":
        await substituir_por_texto(
            update=update,
            context=context,
            texto=(
                "🛒 Bem-vindo à Digital Store!\n\n"
                "Escolha uma categoria:"
            ),
            teclado=teclado_menu_principal(),
        )


# Mostra nos logs o ID de canais onde o bot recebe publicações
async def mostrar_id_canal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.channel_post:
        canal = update.channel_post.chat

        logger.info("==============================")
        logger.info("CANAL: %s", canal.title)
        logger.info("ID: %s", canal.id)
        logger.info("==============================")


async def tratar_erro(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.exception(
        "Erro durante o processamento de uma atualização:",
        exc_info=context.error,
    )


def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(botoes))

    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            mostrar_id_canal,
        )
    )

    app.add_error_handler(tratar_erro)

    logger.info("Bot iniciado.")
    logger.info("Checkouts e imagens configurados.")

    app.run_polling()


if __name__ == "__main__":
    main()
