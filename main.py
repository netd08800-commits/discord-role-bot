import os
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

ROLE_IDS = {
    "civilian": int(get_required_env("ROLE_CIVILIAN")),
    "state": int(get_required_env("ROLE_STATE")),
    "government": int(get_required_env("ROLE_GOVERNMENT")),
    "prosecutor": int(get_required_env("ROLE_PROSECUTOR")),
    "health_minister": int(get_required_env("ROLE_HEALTH_MINISTER")),
}

# True = у человека будет только одна роль из этих пяти.
# False = роли будут просто добавляться.
ONE_ROLE_ONLY = True


class RoleButton(discord.ui.Button):
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

        member = interaction.user

        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(interaction.user.id)

        if member is None:
            await interaction.response.send_message(
                "Не удалось найти участника на сервере.",
                ephemeral=True
            )
            return

        role_id = ROLE_IDS[self.role_key]
        role = interaction.guild.get_role(role_id)

        if role is None:
            await interaction.response.send_message(
                "Роль не найдена. Проверь ID роли в Railway Variables.",
                ephemeral=True
            )
            return

        bot_member = interaction.guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "Не удалось проверить права бота.",
                ephemeral=True
            )
            return

        if role >= bot_member.top_role:
            await interaction.response.send_message(
                "Я не могу выдать эту роль. Подними роль бота выше нужных ролей.",
                ephemeral=True
            )
            return

        try:
            if ONE_ROLE_ONLY:
                old_roles = [
                    interaction.guild.get_role(rid)
                    for rid in ROLE_IDS.values()
                ]

                old_roles = [
                    old_role
                    for old_role in old_roles
                    if old_role is not None and old_role in member.roles
                ]

                if old_roles:
                    await member.remove_roles(
                        *old_roles,
                        reason="Смена роли через кнопки"
                    )

            await member.add_roles(
                role,
                reason="Выбор роли через кнопки"
            )

            await interaction.response.send_message(
                "Готово. Роль успешно выдана.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "У меня нет прав на выдачу этой роли. Проверь право «Управлять ролями» и порядок ролей.",
                ephemeral=True
            )

        except discord.HTTPException:
            await interaction.response.send_message(
                "Произошла ошибка Discord. Попробуй позже.",
                ephemeral=True
            )


class RoleSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(RoleButton("👤", "civilian", "role_button:civilian"))
        self.add_item(RoleButton("🛡️", "state", "role_button:state"))
        self.add_item(RoleButton("🏛️", "government", "role_button:government"))
        self.add_item(RoleButton("⚖️", "prosecutor", "role_button:prosecutor"))
        self.add_item(RoleButton("🧑‍⚕️", "health_minister", "role_button:health_minister"))


class RoleBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        self.add_view(RoleSelectView())

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


bot = RoleBot()


@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user}")


@bot.tree.command(
    name="setup_roles",
    description="Отправить сообщение с кнопками выбора роли"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_roles(interaction: discord.Interaction):
    message_text = (
        "Приветствую! Я - Бот данного дискорд-сервера, помогаю каждому участнику "
        "в получении необходимой роли. Нажми соответствующую кнопку с эмоджи ниже, "
        "роль которой вам нужна.\n\n"
        "👤  🛡️  🏛️  ⚖️  🧑‍⚕️"
    )

    await interaction.channel.send(
        message_text,
        view=RoleSelectView()
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
