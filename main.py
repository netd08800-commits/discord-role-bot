import os
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or value.strip() == "":
        raise RuntimeError(f"Не найдена переменная окружения: {name}")

    return value.strip()


TOKEN = get_required_env("DISCORD_TOKEN")
GUILD_ID = int(get_required_env("GUILD_ID"))

MOD_ROLE_ID = int(get_required_env("MOD_ROLE_ID"))

ROLE_OPTIONS = {
    "civilian": {
        "emoji": "👤",
        "label": "Гражданский",
        "role_id": int(get_required_env("ROLE_CIVILIAN")),
    },
    "state": {
        "emoji": "🛡️",
        "label": "Сотрудник гос. структуры",
        "role_id": int(get_required_env("ROLE_STATE")),
    },
    "government": {
        "emoji": "🏛️",
        "label": "Сотрудник Правительства",
        "role_id": int(get_required_env("ROLE_GOVERNMENT")),
    },
    "prosecutor": {
        "emoji": "⚖️",
        "label": "Сотрудник Прокуратуры",
        "role_id": int(get_required_env("ROLE_PROSECUTOR")),
    },
    "health_minister": {
        "emoji": "🧑‍⚕️",
        "label": "Министр Здравоохранения",
        "role_id": int(get_required_env("ROLE_HEALTH_MINISTER")),
    },
}

# Один клик по любой кнопке раз в 30 минут.
BUTTON_COOLDOWN = timedelta(minutes=30)

# Кулдауны хранятся в памяти.
# После полного перезапуска бота кулдаун сбросится.
user_cooldowns: dict[int, datetime] = {}


def sanitize_channel_name(text: str) -> str:
    text = text.lower()
    text = text.replace(" ", "-")
    text = re.sub(r"[^a-zа-яё0-9\-]", "", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:40] or "request"


class RoleRequestButton(discord.ui.Button):
    def __init__(self, emoji: str, role_key: str, custom_id: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            emoji=emoji,
            custom_id=custom_id
        )
        self.role_key = role_key

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Эта кнопка работает только на сервере.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        member = interaction.user

        if not isinstance(member, discord.Member):
            member = guild.get_member(interaction.user.id)

        if member is None:
            await interaction.response.send_message(
                "Не удалось найти участника на сервере.",
                ephemeral=True
            )
            return

        now = datetime.now(timezone.utc)
        last_click = user_cooldowns.get(member.id)

        if last_click is not None:
            remaining = BUTTON_COOLDOWN - (now - last_click)

            if remaining.total_seconds() > 0:
                minutes = int(remaining.total_seconds() // 60)
                seconds = int(remaining.total_seconds() % 60)

                await interaction.response.send_message(
                    f"Кнопки можно нажимать 1 раз в 30 минут. "
                    f"Попробуйте снова через {minutes} мин. {seconds} сек.",
                    ephemeral=True
                )
                return

        role_data = ROLE_OPTIONS[self.role_key]
        moder_role = guild.get_role(MOD_ROLE_ID)

        if moder_role is None:
            await interaction.response.send_message(
                "Роль 💫 Moder не найдена. Проверь MOD_ROLE_ID в Railway Variables.",
                ephemeral=True
            )
            return

        bot_member = guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "Не удалось проверить права бота.",
                ephemeral=True
            )
            return

        safe_user_name = sanitize_channel_name(member.display_name)
        safe_role_name = sanitize_channel_name(role_data["label"])

        channel_name = f"запрос-{safe_role_name}-{safe_user_name}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            moder_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                manage_messages=True
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True
            )
        }

        try:
            category = interaction.channel.category if interaction.channel else None

            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=category,
                reason=f"Запрос роли от {member}"
            )

            request_text = (
                f"{member.mention}, ваш запрос создан.\n"
                f"Запрашиваемая роль: **{role_data['emoji']} {role_data['label']}**\n\n"
                "Для того, чтоб Ваш запрос был направлен Модерации на рассмотрение — "
                "отправьте по следующей форме свой ответ:\n\n"
                "1. Ваш Ник:\n"
                "2. Ваш Static:\n"
                "3. Ваше служебное удостоверение "
                "(можно не на фотохостинг, а прикрепить файлом):\n\n"
                "После составления формы, ожидание ответа Модерации.\n"
                "На рассмотрение Вашего запроса может занять до 24-х часов.\n"
                "Модерация старается рассматривать каждый запрос в ближайшем свободном времени.\n\n"
                "**Тема автоматически закрыта.**"
            )

            await ticket_channel.send(
                content=f"{member.mention} {moder_role.mention}\n\n{request_text}",
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=True,
                    everyone=False
                )
            )

            user_cooldowns[member.id] = now

            await interaction.response.send_message(
                f"Ваш приватный канал создан: {ticket_channel.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "Я не могу создать приватный канал. Проверь право «Управлять каналами» у роли бота.",
                ephemeral=True
            )

        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord не дал создать канал. Попробуйте позже или проверьте права бота.",
                ephemeral=True
            )


class RoleRequestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(RoleRequestButton("👤", "civilian", "role_request:civilian"))
        self.add_item(RoleRequestButton("🛡️", "state", "role_request:state"))
        self.add_item(RoleRequestButton("🏛️", "government", "role_request:government"))
        self.add_item(RoleRequestButton("⚖️", "prosecutor", "role_request:prosecutor"))
        self.add_item(RoleRequestButton("🧑‍⚕️", "health_minister", "role_request:health_minister"))


class RoleBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        self.add_view(RoleRequestView())

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


bot = RoleBot()


@bot.event
async def on_ready():
    print("================================")
    print(f"Бот запущен как {bot.user}")
    print("================================")


@bot.tree.command(
    name="setup_roles",
    description="Отправить сообщение с кнопками запроса роли"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_roles(interaction: discord.Interaction):
    message_text = (
        "Приветствую! Я - Бот данного дискорд-сервера, помогаю каждому участнику "
        "в получении необходимой роли. Нажми соответствующую кнопку с эмоджи ниже, "
        "роль которой вам нужна.\n\n"
        "👤 — Гражданский\n"
        "🛡️ — Сотрудник гос. структуры\n"
        "🏛️ — Сотрудник Правительства\n"
        "⚖️ — Сотрудник Прокуратуры\n"
        "🧑‍⚕️ — Министр Здравоохранения"
    )

    await interaction.channel.send(
        message_text,
        view=RoleRequestView()
    )

    await interaction.response.send_message(
        "Сообщение с кнопками отправлено.",
        ephemeral=True
    )


@setup_roles.error
async def setup_roles_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "Эту команду может использовать только администратор.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"Ошибка при выполнении команды: {error}",
            ephemeral=True
        )


bot.run(TOKEN)
