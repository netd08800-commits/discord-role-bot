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

TICKET_CATEGORY_NAME = "Заявки на роли"

ROLE_OPTIONS = {
    "civilian": {
        "emoji": "👤",
        "label": "Гражданский",
        "role_id": int(get_required_env("ROLE_CIVILIAN")),
        "auto_give": True,
    },
    "state": {
        "emoji": "🛡️",
        "label": "Сотрудник гос. структуры",
        "role_id": int(get_required_env("ROLE_STATE")),
        "auto_give": False,
    },
    "government": {
        "emoji": "🏛️",
        "label": "Сотрудник Правительства",
        "role_id": int(get_required_env("ROLE_GOVERNMENT")),
        "auto_give": False,
    },
    "prosecutor": {
        "emoji": "⚖️",
        "label": "Сотрудник Прокуратуры",
        "role_id": int(get_required_env("ROLE_PROSECUTOR")),
        "auto_give": False,
    },
    "health_minister": {
        "emoji": "🧑‍⚕️",
        "label": "Министр Здравоохранения",
        "role_id": int(get_required_env("ROLE_HEALTH_MINISTER")),
        "auto_give": False,
    },
}

BUTTON_COOLDOWN = timedelta(minutes=30)

# Кулдаун только на создание заявок.
# Гражданский выдаётся автоматом и не блокирует запрос доп. роли.
user_ticket_cooldowns: dict[int, datetime] = {}


def sanitize_channel_name(text: str) -> str:
    text = text.lower()
    text = text.replace(" ", "-")
    text = re.sub(r"[^a-zа-яё0-9\-]", "", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:40] or "request"


def make_ticket_topic(requester_id: int, role_key: str, status: str) -> str:
    return f"role_ticket|requester_id={requester_id}|role_key={role_key}|status={status}"


def parse_ticket_topic(topic: str | None) -> dict[str, str]:
    if not topic or not topic.startswith("role_ticket|"):
        return {}

    data = {}

    for part in topic.split("|")[1:]:
        if "=" not in part:
            continue

        key, value = part.split("=", 1)
        data[key] = value

    return data


def user_is_moderator(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True

    return any(role.id == MOD_ROLE_ID for role in member.roles)


async def get_or_create_ticket_category(guild: discord.Guild) -> discord.CategoryChannel:
    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)

    if category is not None:
        return category

    return await guild.create_category(
        name=TICKET_CATEGORY_NAME,
        reason="Создание категории для заявок на роли"
    )


def find_open_ticket_for_user(
    guild: discord.Guild,
    user_id: int
) -> discord.TextChannel | None:
    for channel in guild.text_channels:
        info = parse_ticket_topic(channel.topic)

        if not info:
            continue

        if info.get("requester_id") != str(user_id):
            continue

        if info.get("status") == "open":
            return channel

    return None


async def set_ticket_status(
    channel: discord.TextChannel,
    requester: discord.Member | None,
    role_key: str,
    status: str
):
    requester_id = None

    info = parse_ticket_topic(channel.topic)
    if info.get("requester_id"):
        requester_id = int(info["requester_id"])

    if requester is not None:
        requester_id = requester.id

        if status == "open":
            await channel.set_permissions(
                requester,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
        else:
            await channel.set_permissions(
                requester,
                view_channel=False,
                send_messages=False,
                read_message_history=False,
                attach_files=False,
                embed_links=False
            )

    if requester_id is not None:
        await channel.edit(
            topic=make_ticket_topic(requester_id, role_key, status)
        )


def create_ticket_embed(
    member: discord.Member,
    role_data: dict[str, str | int | bool]
) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Заявка на получение дополнительной роли",
        description=(
            f"{member.mention}, ваш запрос был успешно создан.\n"
            "Заполните форму ниже, чтобы модерация могла рассмотреть заявку."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🎭 Запрашиваемая роль",
        value=f"**{role_data['emoji']} {role_data['label']}**",
        inline=False
    )

    embed.add_field(
        name="📝 Форма для заполнения",
        value=(
            "```md\n"
            "1. Ваш Ник:\n"
            "2. Ваш Static:\n"
            "3. Ваше служебное удостоверение:\n"
            "   Прикрепите файл прямо в этот канал.\n"
            "```"
        ),
        inline=False
    )

    embed.add_field(
        name="📎 Как прикрепить удостоверение?",
        value=(
            "Можно **не загружать на фотохостинг**.\n"
            "Просто отправьте изображение или файл прямо сюда, в этот канал."
        ),
        inline=False
    )

    embed.add_field(
        name="⏳ Срок рассмотрения",
        value=(
            "Рассмотрение заявки может занять **до 24-х часов**.\n"
            "Модерация старается рассматривать каждый запрос в ближайшее свободное время."
        ),
        inline=False
    )

    embed.add_field(
        name="⚠️ Важно",
        value=(
            "После отправки формы ожидайте ответа модерации.\n\n"
            "**Тема автоматически закрыта.**"
        ),
        inline=False
    )

    embed.set_footer(
        text="Не создавайте повторные заявки без необходимости."
    )

    return embed


def create_auto_role_embed(
    member: discord.Member,
    role_data: dict[str, str | int | bool]
) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Роль успешно выдана",
        description=(
            f"{member.mention}, вам автоматически выдана роль:\n\n"
            f"**{role_data['emoji']} {role_data['label']}**"
        ),
        color=discord.Color.green()
    )

    embed.set_footer(
        text="Если нужна дополнительная роль — нажмите соответствующую кнопку."
    )

    return embed


async def give_auto_role(
    interaction: discord.Interaction,
    member: discord.Member,
    role_data: dict[str, str | int | bool]
):
    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "Эта кнопка работает только на сервере.",
            ephemeral=True
        )
        return

    role = guild.get_role(int(role_data["role_id"]))

    if role is None:
        await interaction.response.send_message(
            "Роль не найдена. Проверь ID роли в Railway Variables.",
            ephemeral=True
        )
        return

    if role in member.roles:
        await interaction.response.send_message(
            f"У вас уже есть роль **{role_data['emoji']} {role_data['label']}**.",
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

    if role >= bot_member.top_role:
        await interaction.response.send_message(
            "Я не могу выдать эту роль. Подними роль бота выше выдаваемых ролей.",
            ephemeral=True
        )
        return

    try:
        await member.add_roles(
            role,
            reason="Автоматическая выдача роли Гражданский"
        )

        embed = create_auto_role_embed(member, role_data)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "Я не смог выдать роль. Проверь права и порядок ролей.",
            ephemeral=True
        )

    except discord.HTTPException:
        await interaction.response.send_message(
            "Discord не дал выдать роль. Попробуйте позже.",
            ephemeral=True
        )


async def handle_ticket_action(
    interaction: discord.Interaction,
    action: str
):
    if interaction.guild is None:
        await interaction.response.send_message(
            "Эта кнопка работает только на сервере.",
            ephemeral=True
        )
        return

    guild = interaction.guild
    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "Эта кнопка работает только в текстовом канале заявки.",
            ephemeral=True
        )
        return

    moderator = interaction.user

    if not isinstance(moderator, discord.Member):
        moderator = guild.get_member(interaction.user.id)

    if moderator is None or not user_is_moderator(moderator):
        await interaction.response.send_message(
            "Эти кнопки доступны только модерации.",
            ephemeral=True
        )
        return

    ticket_info = parse_ticket_topic(channel.topic)

    if not ticket_info:
        await interaction.response.send_message(
            "Не удалось определить данные заявки.",
            ephemeral=True
        )
        return

    requester_id = int(ticket_info["requester_id"])
    role_key = ticket_info["role_key"]

    role_data = ROLE_OPTIONS.get(role_key)

    if role_data is None:
        await interaction.response.send_message(
            "Не удалось определить запрашиваемую роль.",
            ephemeral=True
        )
        return

    requester = guild.get_member(requester_id)

    await interaction.response.defer(ephemeral=False)

    if action == "approve":
        if requester is None:
            await interaction.followup.send(
                "Не удалось найти участника на сервере. Возможно, он вышел."
            )
            return

        role = guild.get_role(int(role_data["role_id"]))

        if role is None:
            await interaction.followup.send(
                "Роль не найдена. Проверь ID роли в Railway Variables."
            )
            return

        bot_member = guild.me

        if bot_member is None:
            await interaction.followup.send(
                "Не удалось проверить права бота."
            )
            return

        if role >= bot_member.top_role:
            await interaction.followup.send(
                "Я не могу выдать эту роль. Подними роль бота выше выдаваемых ролей."
            )
            return

        try:
            await requester.add_roles(
                role,
                reason=f"Заявка одобрена модератором {moderator}"
            )

            await set_ticket_status(
                channel=channel,
                requester=requester,
                role_key=role_key,
                status="approved"
            )

            embed = discord.Embed(
                title="✅ Заявка одобрена",
                description=(
                    f"Пользователю {requester.mention} выдана роль "
                    f"**{role_data['emoji']} {role_data['label']}**.\n\n"
                    "**Тема автоматически закрыта.**"
                ),
                color=discord.Color.green()
            )

            embed.set_footer(
                text=f"Решение принял модератор: {moderator.display_name}"
            )

            await interaction.followup.send(embed=embed)

        except discord.Forbidden:
            await interaction.followup.send(
                "Я не смог выдать роль. Проверь права и порядок ролей."
            )

        except discord.HTTPException:
            await interaction.followup.send(
                "Discord не дал выдать роль. Попробуйте позже."
            )

    elif action == "reject":
        await set_ticket_status(
            channel=channel,
            requester=requester,
            role_key=role_key,
            status="rejected"
        )

        embed = discord.Embed(
            title="❌ Заявка отклонена",
            description=(
                f"Заявка была отклонена модератором {moderator.mention}.\n\n"
                "**Тема автоматически закрыта.**"
            ),
            color=discord.Color.red()
        )

        await interaction.followup.send(embed=embed)

    elif action == "close":
        await set_ticket_status(
            channel=channel,
            requester=requester,
            role_key=role_key,
            status="closed"
        )

        embed = discord.Embed(
            title="🔒 Заявка закрыта",
            description=(
                f"Заявка была закрыта модератором {moderator.mention}.\n\n"
                "**Тема автоматически закрыта.**"
            ),
            color=discord.Color.dark_gray()
        )

        await interaction.followup.send(embed=embed)

    elif action == "open":
        if requester is None:
            await interaction.followup.send(
                "Не удалось открыть заявку: участник не найден на сервере."
            )
            return

        await set_ticket_status(
            channel=channel,
            requester=requester,
            role_key=role_key,
            status="open"
        )

        embed = discord.Embed(
            title="🔓 Заявка открыта",
            description=f"Заявка снова открыта для {requester.mention}.",
            color=discord.Color.blue()
        )

        await interaction.followup.send(embed=embed)


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

        role_data = ROLE_OPTIONS[self.role_key]

        if role_data.get("auto_give") is True:
            await give_auto_role(
                interaction=interaction,
                member=member,
                role_data=role_data
            )
            return

        now = datetime.now(timezone.utc)
        last_click = user_ticket_cooldowns.get(member.id)

        if last_click is not None:
            remaining = BUTTON_COOLDOWN - (now - last_click)

            if remaining.total_seconds() > 0:
                minutes = int(remaining.total_seconds() // 60)
                seconds = int(remaining.total_seconds() % 60)

                await interaction.response.send_message(
                    f"Заявки можно создавать 1 раз в 30 минут. "
                    f"Попробуйте снова через {minutes} мин. {seconds} сек.",
                    ephemeral=True
                )
                return

        existing_ticket = find_open_ticket_for_user(guild, member.id)

        if existing_ticket is not None:
            await interaction.response.send_message(
                f"У вас уже есть открытая заявка: {existing_ticket.mention}",
                ephemeral=True
            )
            return

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

        await interaction.response.defer(ephemeral=True)

        safe_user_name = sanitize_channel_name(member.display_name)
        safe_role_name = sanitize_channel_name(str(role_data["label"]))

        channel_name = f"заявка-{safe_role_name}-{safe_user_name}"

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
            category = await get_or_create_ticket_category(guild)

            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=category,
                topic=make_ticket_topic(
                    requester_id=member.id,
                    role_key=self.role_key,
                    status="open"
                ),
                reason=f"Запрос роли от {member}"
            )

            embed = create_ticket_embed(
                member=member,
                role_data=role_data
            )

            await ticket_channel.send(
                content=f"{member.mention} {moder_role.mention}",
                embed=embed,
                view=TicketActionView(),
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=True,
                    everyone=False
                )
            )

            user_ticket_cooldowns[member.id] = now

            await interaction.followup.send(
                f"Ваш приватный канал заявки создан: {ticket_channel.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "Я не могу создать приватный канал. Проверь права бота.",
                ephemeral=True
            )

        except discord.HTTPException:
            await interaction.followup.send(
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


class TicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Одобрить",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="ticket_action:approve"
    )
    async def approve_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await handle_ticket_action(interaction, "approve")

    @discord.ui.button(
        label="Отказать",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_action:reject"
    )
    async def reject_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await handle_ticket_action(interaction, "reject")

    @discord.ui.button(
        label="Закрыть заявку",
        emoji="🔒",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_action:close"
    )
    async def close_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await handle_ticket_action(interaction, "close")

    @discord.ui.button(
        label="Открыть заявку",
        emoji="🔓",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_action:open"
    )
    async def open_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await handle_ticket_action(interaction, "open")


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
        self.add_view(TicketActionView())

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
    description="Отправить сообщение с кнопками выбора/запроса роли"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_roles(interaction: discord.Interaction):
    message_text = (
        "Приветствую! Я - Бот данного дискорд-сервера, помогаю каждому участнику "
        "в получении необходимой роли.\n\n"
        "Нажмите соответствующую кнопку с эмоджи ниже:\n\n"
        "👤 — Гражданский **выдаётся автоматически**\n"
        "🛡️ — Сотрудник гос. структуры **через заявку**\n"
        "🏛️ — Сотрудник Правительства **через заявку**\n"
        "⚖️ — Сотрудник Прокуратуры **через заявку**\n"
        "🧑‍⚕️ — Министр Здравоохранения **через заявку**\n\n"
        "Дополнительные роли рассматриваются модерацией."
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
