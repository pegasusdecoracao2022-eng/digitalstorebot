import asyncio
import hashlib
import hmac
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from flask import Flask, jsonify, request
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)


# ============================================================
# LOGS
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "A variável BOT_TOKEN não foi configurada no Railway."
    )

# Chave que protegerá o endereço do webhook
KIWIFY_WEBHOOK_SECRET = os.getenv("KIWIFY_WEBHOOK_SECRET")

# Porta fornecida automaticamente pelo Railway
PORT = int(os.getenv("PORT", "8080"))

# IDs dos canais privados
CANAIS_PLANOS = {
    "tati_bronze": -1004361035516,
    "tati_prata": -1004438900351,
    "tati_ouro": -1004397041536,
}


# ============================================================
# FLASK — SERVIDOR QUE RECEBERÁ A KIWIFY
# ============================================================

servidor = Flask(__name__)


@servidor.get("/")
def pagina_inicial():
    """
    Usada para verificar se o servidor está online.
    """
    return jsonify(
        {
            "status": "online",
            "servico": "Digital Store Bot",
            "webhook": "ativo",
        }
    ), 200


@servidor.get("/health")
def health():
    """
    Rota de verificação do Railway.
    """
    return jsonify({"status": "ok"}), 200


def procurar_valor(
    dados: Any,
    nomes_possiveis: set[str],
) -> Any:
    """
    Procura recursivamente uma informação dentro do JSON.

    Isso ajuda porque os dados da Kiwify podem estar organizados
    em diferentes níveis do objeto recebido.
    """
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            chave_normalizada = str(chave).lower()

            if chave_normalizada in nomes_possiveis:
                return valor

        for valor in dados.values():
            resultado = procurar_valor(
                valor,
                nomes_possiveis,
            )

            if resultado is not None:
                return resultado

    elif isinstance(dados, list):
        for item in dados:
            resultado = procurar_valor(
                item,
                nomes_possiveis,
            )

            if resultado is not None:
                return resultado

    return None


def identificar_plano(
    dados: dict[str, Any],
) -> str | None:
    """
    Tenta identificar qual plano foi comprado.

    Primeiro procura o parâmetro s1 enviado pelo checkout.
    Depois procura pelo nome do produto.
    """
    parametro_s1 = procurar_valor(
        dados,
        {
            "s1",
            "tracking_s1",
        },
    )

    if parametro_s1:
        plano = str(parametro_s1).lower().strip()

        if plano in PLANOS:
            return plano

    nome_produto = procurar_valor(
        dados,
        {
            "product_name",
            "produto",
            "nome_produto",
            "product",
        },
    )

    if nome_produto:
        nome = str(nome_produto).lower()

        if "bronze" in nome:
            return "tati_bronze"

        if "prata" in nome:
            return "tati_prata"

        if "ouro" in nome:
            return "tati_ouro"

    return None


def identificar_chat_id(
    dados: dict[str, Any],
) -> int | None:
    """
    Extrai o ID do Telegram enviado no parâmetro src.

    Formato usado:
    tg_123456789
    """
    parametro_src = procurar_valor(
        dados,
        {
            "src",
            "tracking_src",
            "source",
        },
    )

    if not parametro_src:
        return None

    valor = str(parametro_src).strip()

    if valor.startswith("tg_"):
        valor = valor.removeprefix("tg_")

    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


async def enviar_acesso_telegram(
    plano: str,
    chat_id: int,
) -> str:
    """
    Cria um convite individual e envia ao comprador.

    O convite aceita apenas uma entrada e expira em 24 horas.
    """
    canal_id = CANAIS_PLANOS.get(plano)

    if canal_id is None:
        raise ValueError(
            f"Não existe canal configurado para o plano {plano}."
        )

    expira_em = datetime.now(timezone.utc) + timedelta(hours=24)

    async with Bot(TOKEN) as bot:
        convite = await bot.create_chat_invite_link(
            chat_id=canal_id,
            name=f"{plano}-{chat_id}",
            expire_date=expira_em,
            member_limit=1,
            creates_join_request=False,
        )

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ Pagamento confirmado!\n\n"
                "Seu acesso foi liberado. Clique no link abaixo "
                "para entrar no canal do seu plano:\n\n"
                f"{convite.invite_link}\n\n"
                "Este convite permite apenas uma entrada e expira "
                "em 24 horas."
            ),
        )

    return convite.invite_link


def processar_entrega_acesso(
    plano: str,
    chat_id: int,
) -> str:
    """
    Executa a função assíncrona do Telegram dentro da rota Flask.
    """
    return asyncio.run(
        enviar_acesso_telegram(
            plano=plano,
            chat_id=chat_id,
        )
    )


def assinatura_kiwify_valida() -> bool:
    """
    Valida a assinatura enviada pela Kiwify.

    A Kiwify envia a assinatura na URL:
    /webhook/kiwify?signature=...

    A assinatura é comparada com um HMAC-SHA1 do corpo original
    usando o token salvo em KIWIFY_WEBHOOK_SECRET.
    """
    assinatura_recebida = request.args.get(
        "signature",
        "",
    ).strip().lower()

    if not assinatura_recebida:
        logger.warning(
            "Webhook recebido sem o parâmetro signature."
        )
        return False

    corpo_original = request.get_data(cache=True)

    assinatura_calculada = hmac.new(
        KIWIFY_WEBHOOK_SECRET.encode("utf-8"),
        corpo_original,
        hashlib.sha1,
    ).hexdigest().lower()

    return hmac.compare_digest(
        assinatura_recebida,
        assinatura_calculada,
    )


@servidor.post("/webhook/kiwify")
def webhook_kiwify():
    """
    Recebe e valida os eventos enviados pela Kiwify.
    """
    if not KIWIFY_WEBHOOK_SECRET:
        logger.error(
            "A variável KIWIFY_WEBHOOK_SECRET não foi configurada."
        )

        return jsonify(
            {
                "status": "erro",
                "mensagem": "Webhook não configurado.",
            }
        ), 500

    if not assinatura_kiwify_valida():
        logger.warning(
            "Webhook recebido com assinatura inválida."
        )

        return jsonify(
            {
                "status": "negado",
                "mensagem": "Assinatura inválida.",
            }
        ), 401

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        logger.warning(
            "A Kiwify enviou uma requisição sem JSON válido."
        )

        return jsonify(
            {
                "status": "erro",
                "mensagem": "JSON inválido.",
            }
        ), 400

    evento = procurar_valor(
        dados,
        {
            "webhook_event_type",
            "event",
            "evento",
            "event_type",
            "type",
            "status",
            "order_status",
        },
    )

    plano = identificar_plano(dados)
    chat_id = identificar_chat_id(dados)

    pedido_id = procurar_valor(
        dados,
        {
            "order_id",
            "order_ref",
            "pedido_id",
            "transaction_id",
            "sale_id",
        },
    )

    logger.info("========================================")
    logger.info("WEBHOOK DA KIWIFY RECEBIDO E VALIDADO")
    logger.info("Evento/status: %s", evento)
    logger.info("Plano identificado: %s", plano)
    logger.info("Telegram chat_id: %s", chat_id)
    logger.info("Pedido/transação: %s", pedido_id)
    logger.info("========================================")

    evento_normalizado = str(evento or "").strip().lower()
    eventos_aprovados = {
        "paid",
        "approved",
        "order_approved",
        "compra aprovada",
    }

    acesso_enviado = False

    if evento_normalizado in eventos_aprovados:
        if plano is None or chat_id is None:
            logger.warning(
                "Compra aprovada sem plano ou chat_id. "
                "Nenhum acesso foi enviado."
            )
        else:
            try:
                link_convite = processar_entrega_acesso(
                    plano=plano,
                    chat_id=chat_id,
                )

                acesso_enviado = True

                logger.info(
                    "Acesso enviado ao Telegram %s para o plano %s.",
                    chat_id,
                    plano,
                )
                logger.info(
                    "Convite criado com sucesso: %s",
                    link_convite,
                )
            except Exception:
                logger.exception(
                    "Falha ao criar ou enviar o convite do Telegram."
                )

                return jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Falha ao entregar o acesso.",
                    }
                ), 500

    return jsonify(
        {
            "status": "recebido",
            "evento": evento,
            "plano": plano,
            "chat_id_encontrado": chat_id is not None,
            "acesso_enviado": acesso_enviado,
        }
    ), 200


def iniciar_servidor_flask() -> None:
    """
    Inicia o Flask em uma thread separada.

    Assim o servidor da Kiwify e o bot do Telegram
    funcionam ao mesmo tempo.
    """
    logger.info(
        "Servidor Flask iniciado na porta %s.",
        PORT,
    )

    servidor.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False,
    )


# ============================================================
# CHECKOUTS E PLANOS
# ============================================================

LINKS_CHECKOUT = {
    "tati_bronze": "https://pay.kiwify.com.br/9yfHOUk",
    "tati_prata": "https://pay.kiwify.com.br/ncKuUX4",
    "tati_ouro": "https://pay.kiwify.com.br/buZicPn",
}


PLANOS = {
    "tati_bronze": {
        "nome": "🥉 PLANO BRONZE",
        "preco": "19,90",
        "videos": "200 vídeos exclusivos",
        "atualizacao": "Atualizações mensais",
        "imagem": (
            BASE_DIR
            / "fotos"
            / "tati maia"
            / "tati 1.jpg"
        ),
    },
    "tati_prata": {
        "nome": "🥈 PLANO PRATA",
        "preco": "39,90",
        "videos": "500 vídeos exclusivos",
        "atualizacao": "Atualizações semanais",
        "imagem": (
            BASE_DIR
            / "fotos"
            / "tati maia"
            / "tati 3.jpg"
        ),
    },
    "tati_ouro": {
        "nome": "🥇 PLANO OURO",
        "preco": "59,90",
        "videos": "900 vídeos exclusivos",
        "atualizacao": "Todas as atualizações futuras",
        "imagem": (
            BASE_DIR
            / "fotos"
            / "tati maia"
            / "tati 2.jpg"
        ),
    },
}


def criar_link_checkout(
    plano: str,
    chat_id: int,
) -> str:
    """
    Cria um checkout personalizado para cada usuário.

    src identifica o usuário do Telegram.
    s1 identifica o plano escolhido.
    """
    link_base = LINKS_CHECKOUT[plano]

    parametros = urlencode(
        {
            "src": f"tg_{chat_id}",
            "s1": plano,
        }
    )

    separador = "&" if "?" in link_base else "?"

    return f"{link_base}{separador}{parametros}"


# ============================================================
# TECLADOS
# ============================================================

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


# ============================================================
# FUNÇÕES DO TELEGRAM
# ============================================================

async def substituir_por_texto(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    texto: str,
    teclado: InlineKeyboardMarkup,
) -> None:
    """
    Troca a tela atual por uma mensagem de texto.

    Se a tela atual for foto, apaga a foto e envia texto.
    Se for texto, edita a mensagem atual.
    """
    query = update.callback_query

    if not query or not query.message:
        return

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

    elif query.data in PLANOS:
        plano_id = query.data
        plano = PLANOS[plano_id]
        caminho_imagem = plano["imagem"]
        chat_id = query.message.chat.id

        link_pagamento = criar_link_checkout(
            plano=plano_id,
            chat_id=chat_id,
        )

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

        await query.message.delete()

        with caminho_imagem.open("rb") as foto:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=foto,
                caption=texto,
                reply_markup=teclado,
            )

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


async def mostrar_id_canal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.info("===================================")
    logger.info("ATUALIZAÇÃO RECEBIDA: %s", update)
    logger.info("===================================")

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


# ============================================================
# INICIALIZAÇÃO
# ============================================================

def main() -> None:
    thread_flask = threading.Thread(
        target=iniciar_servidor_flask,
        daemon=True,
        name="servidor-flask",
    )

    thread_flask.start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            botoes,
        )
    )

    app.add_handler(
        TypeHandler(
            Update,
            mostrar_id_canal,
        ),
        group=1,
    )

    app.add_error_handler(tratar_erro)

    logger.info("Bot iniciado.")
    logger.info("Checkouts e imagens configurados.")
    logger.info("Servidor da Kiwify configurado.")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
