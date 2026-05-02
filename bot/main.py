"""
🎫 Ticket King Charts - Bot com Gráficos Visuais
Painéis persistentes, estatísticas com imagens
"""
import os
import asyncio
import datetime
from typing import Optional
import io

import discord
from discord import app_commands, SelectOption, ButtonStyle, File
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select

from database import SessionLocal, GuildConfig, Panel, Ticket, StaffStats
from charts.generator import (
    generate_volume_chart, generate_resolution_chart, generate_team_ranking,
    generate_closure_rate_chart, generate_panel_distribution, generate_hourly_heatmap
)

TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID = os.environ.get("GUILD_ID")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN não encontrado!")
if GUILD_ID:
    GUILD_ID = int(GUILD_ID)

def get_db():
    return SessionLocal()


async def painel_autocomplete(interaction, current: str):
    try:
        db = get_db()
        paineis = db.query(Panel).filter(
            Panel.guild_id == interaction.guild.id
        ).all()

        return [
            app_commands.Choice(
                name=panel.name,
                value=str(panel.id)
            )
            for panel in paineis
            if current.lower() in panel.name.lower()
        ][:25]

    except Exception:
        return []


STYLE_MAP = {
    "primary": ButtonStyle.primary,
    "secondary": ButtonStyle.secondary,
    "success": ButtonStyle.success,
    "danger": ButtonStyle.danger,
    "blurple": ButtonStyle.primary,
    "grey": ButtonStyle.secondary,
    "gray": ButtonStyle.secondary,
    "green": ButtonStyle.success,
    "red": ButtonStyle.danger,
}

# ==================== MODALS ====================
class TicketReasonModal(Modal, title="🎫 Abrir Ticket"):
    def __init__(self, bot, panel_id):
        super().__init__()
        self.bot = bot
        self.panel_id = panel_id
        self.reason = TextInput(
            label="Motivo do ticket",
            placeholder="Descreva como podemos ajudar...",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        db = get_db()

        panel = db.query(Panel).filter_by(id=self.panel_id, is_active=True).first()
        if not panel:
            db.close()
            return await interaction.followup.send("❌ Painel não encontrado.", ephemeral=True)

        # Anti-spam
        existing = db.query(Ticket).filter_by(guild_id=guild.id, user_id=user.id, status="open").first()
        if existing:
            ch = guild.get_channel(existing.channel_id)
            if ch:
                db.close()
                return await interaction.followup.send(f"❌ Você já tem um ticket: {ch.mention}", ephemeral=True)

        # Incrementa contador
        config = db.query(GuildConfig).filter_by(guild_id=guild.id).first()
        if not config:
            config = GuildConfig(guild_id=guild.id, ticket_counter=0)
            db.add(config)
            db.commit()
        config.ticket_counter += 1
        db.commit()
        panel.total_tickets += 1
        db.commit()

        category = guild.get_channel(panel.category_id)
        staff_role = guild.get_role(panel.staff_role_id) if panel.staff_role_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ticket_ch = await guild.create_text_channel(
            name=f"ticket-{config.ticket_counter:04d}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket #{config.ticket_counter} | {user.name} | {panel.name}"
        )

        ticket = Ticket(
            guild_id=guild.id,
            channel_id=ticket_ch.id,
            user_id=user.id,
            panel_id=panel.id,
            reason=self.reason.value,
            status="open"
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        color_int = int(panel.color, 16) if panel.color else 0x5865F2
        embed = discord.Embed(
            title=f"{panel.emoji or '🎫'} Ticket #{config.ticket_counter:04d} - {panel.name}",
            description=f"Bem-vindo, {user.mention}!\n\n"
                       f"**Motivo:**\n```{self.reason.value}```\n\n"
                       f"{panel.welcome_message or 'Um membro da equipe irá atendê-lo.'}\n\n"
                       f"⏳ Aguarde um staff **Claim** o ticket.",
            color=color_int,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"ID: {user.id}")
        embed.set_thumbnail(url=user.display_avatar.url)

        view = TicketControlView(self.bot, ticket.id)
        msg = await ticket_ch.send(content=user.mention, embed=embed, view=view)
        await msg.pin()

        # Log
        if panel.log_channel_id:
            log_ch = guild.get_channel(panel.log_channel_id)
            if log_ch:
                log_embed = discord.Embed(title="🟢 Ticket Aberto", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
                log_embed.add_field(name="Usuário", value=f"{user.mention} (`{user.id}`)", inline=False)
                log_embed.add_field(name="Categoria", default=panel.name, inline=True)
                log_embed.add_field(name="Canal", value=ticket_ch.mention, inline=True)
                log_embed.add_field(name="Motivo", value=self.reason.value[:1000], inline=False)
                await log_ch.send(embed=log_embed)

        await interaction.followup.send(f"✅ Ticket criado: {ticket_ch.mention}", ephemeral=True)
        db.close()

class RenameModal(Modal, title="✏️ Renomear Ticket"):
    def __init__(self):
        super().__init__()
        self.name = TextInput(label="Novo nome", placeholder="ticket-ajuda", max_length=100)
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.edit(name=self.name.value.replace(" ", "-").lower())
        await interaction.response.send_message(f"✅ Renomeado para `{self.name.value}`.", ephemeral=True)

class AddUserModal(Modal, title="➕ Adicionar Usuário"):
    def __init__(self):
        super().__init__()
        self.uid = TextInput(label="ID do Usuário", placeholder="123456789012345678")
        self.add_item(self.uid)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user = interaction.guild.get_member(int(self.uid.value))
            if not user:
                return await interaction.response.send_message("❌ Usuário não encontrado.", ephemeral=True)
            await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
            await interaction.response.send_message(f"✅ {user.mention} adicionado.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ ID inválido.", ephemeral=True)

class RemoveUserModal(Modal, title="➖ Remover Usuário"):
    def __init__(self):
        super().__init__()
        self.uid = TextInput(label="ID do Usuário", placeholder="123456789012345678")
        self.add_item(self.uid)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user = interaction.guild.get_member(int(self.uid.value))
            if not user:
                return await interaction.response.send_message("❌ Usuário não encontrado.", ephemeral=True)
            await interaction.channel.set_permissions(user, overwrite=None)
            await interaction.response.send_message(f"✅ {user.mention} removido.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ ID inválido.", ephemeral=True)

class EditPanelModal(Modal, title="✏️ Editar Painel"):
    def __init__(self, panel):
        super().__init__()
        self.panel_id = panel.id
        self.name = TextInput(label="Nome", default=panel.name, max_length=100)
        self.desc = TextInput(label="Descrição", default=panel.description or "", max_length=200, required=False)
        self.color = TextInput(label="Cor (hex)", default=panel.color or "5865F2", max_length=6)
        self.emoji = TextInput(label="Emoji", default=panel.emoji or "🎫", max_length=50)
        self.welcome = TextInput(label="Mensagem de boas-vindas", default=panel.welcome_message or "", style=discord.TextStyle.paragraph, max_length=500, required=False)
        self.add_item(self.name)
        self.add_item(self.desc)
        self.add_item(self.color)
        self.add_item(self.emoji)
        self.add_item(self.welcome)

    async def on_submit(self, interaction: discord.Interaction):
        db = get_db()
        panel = db.query(Panel).filter_by(id=self.panel_id).first()
        if panel:
            panel.name = self.name.value
            panel.description = self.desc.value or None
            panel.color = self.color.value.replace("#", "")
            panel.emoji = self.emoji.value
            panel.welcome_message = self.welcome.value or None
            db.commit()
        db.close()
        await interaction.response.send_message(f"✅ Painel `{self.name.value}` atualizado!", ephemeral=True)

# ==================== VIEWS ====================
class PanelButtonView(View):
    def __init__(self, bot, panel_id, button_style, button_label, button_emoji):
        super().__init__(timeout=None)
        self.bot = bot
        self.panel_id = panel_id
        style = STYLE_MAP.get(button_style, ButtonStyle.primary)
        self.add_item(PanelButton(bot, panel_id, style, button_label, button_emoji))

class PanelButton(Button):
    def __init__(self, bot, panel_id, style, label, emoji):
        super().__init__(style=style, label=label, emoji=emoji, custom_id=f"panel_btn:{panel_id}")
        self.bot = bot
        self.panel_id = panel_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketReasonModal(self.bot, self.panel_id))

class PanelSelectView(View):
    def __init__(self, bot, panels):
        super().__init__(timeout=None)
        self.bot = bot
        if panels:
            self.add_item(PanelSelect(bot, panels))

class PanelSelect(Select):
    def __init__(self, bot, panels):
        options = []
        for p in panels[:25]:
            options.append(SelectOption(
                label=p.name[:25],
                description=(p.description or "Clique para abrir")[:50],
                value=str(p.id),
                emoji=p.emoji or "🎫"
            ))
        super().__init__(placeholder="📂 Escolha uma categoria...", options=options, custom_id="panel_select")
        self.bot = bot
        self.panels = {str(p.id): p for p in panels}

    async def callback(self, interaction: discord.Interaction):
        panel = self.panels.get(self.values[0])
        if not panel:
            return await interaction.response.send_message("❌ Painel não encontrado.", ephemeral=True)
        await interaction.response.send_modal(TicketReasonModal(self.bot, panel.id))

class TicketControlView(View):
    def __init__(self, bot, ticket_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_id = ticket_id

    @discord.ui.button(label="🙋 Claim", style=ButtonStyle.success, custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: Button):
        db = get_db()
        ticket = db.query(Ticket).filter_by(id=self.ticket_id).first()
        if not ticket or ticket.status != "open":
            db.close()
            return await interaction.response.send_message("❌ Ticket inválido.", ephemeral=True)

        if ticket.claimed_by:
            claimer = interaction.guild.get_member(ticket.claimed_by)
            db.close()
            return await interaction.response.send_message(
                f"❌ Já foi assumido por {claimer.mention if claimer else 'alguém'}.", ephemeral=True
            )

        ticket.claimed_by = interaction.user.id
        ticket.claimed_at = datetime.datetime.utcnow()
        db.commit()

        stats = db.query(StaffStats).filter_by(guild_id=interaction.guild_id, user_id=interaction.user.id).first()
        if not stats:
            stats = StaffStats(guild_id=interaction.guild_id, user_id=interaction.user.id)
            db.add(stats)
        stats.tickets_claimed += 1
        db.commit()
        db.close()

        embed = discord.Embed(
            description=f"🙋 **{interaction.user.mention}** assumiu este ticket.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        button.disabled = True
        button.label = f"Claimed by {interaction.user.name[:20]}"
        await interaction.message.edit(view=self)

    @discord.ui.button(label="🔒 Fechar", style=ButtonStyle.danger, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: Button):
        db = get_db()
        ticket = db.query(Ticket).filter_by(id=self.ticket_id).first()
        if not ticket:
            db.close()
            return await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)

        await interaction.response.defer()

        transcript_lines = [f"=== TRANSCRIPT: {interaction.channel.name} ===\n"]
        async for msg in interaction.channel.history(limit=None, oldest_first=True):
            time = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = msg.content or "[Embed/Attachment]"
            transcript_lines.append(f"[{time}] {msg.author.name}: {content}\n")
        transcript = "".join(transcript_lines)

        ticket.status = "closed"
        ticket.closed_at = datetime.datetime.utcnow()
        ticket.transcript = transcript

        if ticket.claimed_at:
            ticket.resolved_at = datetime.datetime.utcnow()
            resolution_time = (ticket.resolved_at - ticket.claimed_at).total_seconds()
            if ticket.claimed_by:
                stats = db.query(StaffStats).filter_by(guild_id=interaction.guild_id, user_id=ticket.claimed_by).first()
                if stats:
                    stats.tickets_closed += 1
                    stats.total_resolution_time += resolution_time
                    db.commit()

        db.commit()

        user = interaction.guild.get_member(ticket.user_id)
        if user:
            await interaction.channel.set_permissions(user, view_channel=False)

        embed = discord.Embed(
            title="🔒 Ticket Fechado",
            description=f"Fechado por {interaction.user.mention}.\nCanal será deletado em 10 segundos...",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.followup.send(embed=embed)

        if user:
            try:
                view = RatingView(ticket.id)
                dm_embed = discord.Embed(
                    title="⭐ Como foi o atendimento?",
                    description=f"Seu ticket em **{interaction.guild.name}** foi fechado.\nClique para avaliar!",
                    color=discord.Color.gold()
                )
                await user.send(embed=dm_embed, view=view)
            except:
                pass

        panel = db.query(Panel).filter_by(id=ticket.panel_id).first()
        if panel and panel.log_channel_id:
            log_ch = interaction.guild.get_channel(panel.log_channel_id)
            if log_ch:
                log_embed = discord.Embed(title="🔴 Ticket Fechado", color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
                log_embed.add_field(name="Ticket", value=f"#{ticket.id}", inline=True)
                log_embed.add_field(name="Fechado por", value=interaction.user.mention, inline=True)
                file = File(io.StringIO(transcript), filename=f"transcript-{ticket.id}.txt")
                await log_ch.send(embed=log_embed, file=file)

        db.close()
        await asyncio.sleep(10)
        await interaction.channel.delete()

    @discord.ui.button(label="✏️ Renomear", style=ButtonStyle.secondary, custom_id="ticket:rename")
    async def rename(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RenameModal())

    @discord.ui.button(label="➕ Add", style=ButtonStyle.secondary, custom_id="ticket:add")
    async def add_user(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AddUserModal())

    @discord.ui.button(label="➖ Remove", style=ButtonStyle.secondary, custom_id="ticket:remove")
    async def remove_user(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RemoveUserModal())

    @discord.ui.button(label="🧵 Thread", style=ButtonStyle.secondary, custom_id="ticket:thread")
    async def create_thread(self, interaction: discord.Interaction, button: Button):
        db = get_db()
        ticket = db.query(Ticket).filter_by(id=self.ticket_id).first()
        db.close()
        if not ticket:
            return await interaction.response.send_message("❌ Ticket inválido.", ephemeral=True)

        thread = await interaction.channel.create_thread(name=f"Staff-{interaction.channel.name}", type=discord.ChannelType.private_thread)

        db = get_db()
        panel = db.query(Panel).filter_by(id=ticket.panel_id).first()
        if panel and panel.staff_role_id:
            role = interaction.guild.get_role(panel.staff_role_id)
            if role:
                for member in role.members:
                    await thread.add_user(member)
        db.close()

        await interaction.response.send_message(f"✅ Thread staff criada: {thread.mention}", ephemeral=True)

class RatingView(View):
    def __init__(self, ticket_id):
        super().__init__(timeout=300)
        self.ticket_id = ticket_id

    @discord.ui.button(label="⭐", style=ButtonStyle.secondary, custom_id="rate:1")
    async def r1(self, interaction: discord.Interaction, button: Button):
        await self.save(interaction, 1)
    @discord.ui.button(label="⭐⭐", style=ButtonStyle.secondary, custom_id="rate:2")
    async def r2(self, interaction: discord.Interaction, button: Button):
        await self.save(interaction, 2)
    @discord.ui.button(label="⭐⭐⭐", style=ButtonStyle.secondary, custom_id="rate:3")
    async def r3(self, interaction: discord.Interaction, button: Button):
        await self.save(interaction, 3)
    @discord.ui.button(label="⭐⭐⭐⭐", style=ButtonStyle.secondary, custom_id="rate:4")
    async def r4(self, interaction: discord.Interaction, button: Button):
        await self.save(interaction, 4)
    @discord.ui.button(label="⭐⭐⭐⭐⭐", style=ButtonStyle.secondary, custom_id="rate:5")
    async def r5(self, interaction: discord.Interaction, button: Button):
        await self.save(interaction, 5)

    async def save(self, interaction: discord.Interaction, stars: int):
        db = get_db()
        ticket = db.query(Ticket).filter_by(id=self.ticket_id).first()
        if ticket:
            ticket.rating = stars
            db.commit()
            if ticket.claimed_by:
                stats = db.query(StaffStats).filter_by(guild_id=ticket.guild_id, user_id=ticket.claimed_by).first()
                if stats:
                    stats.rating_count += 1
                    stats.avg_rating = ((stats.avg_rating * (stats.rating_count - 1)) + stars) / stats.rating_count
                    db.commit()
        db.close()
        await interaction.response.send_message(f"Obrigado! {'⭐' * stars}", ephemeral=True)
        self.stop()

class PanelManagementView(View):
    def __init__(self, bot, panel_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.panel_id = panel_id

    @discord.ui.button(label="✏️ Editar", style=ButtonStyle.primary, custom_id="panel:edit")
    async def edit(self, interaction: discord.Interaction, button: Button):
        db = get_db()
        panel = db.query(Panel).filter_by(id=self.panel_id).first()
        db.close()
        if panel:
            await interaction.response.send_modal(EditPanelModal(panel))

    @discord.ui.button(label="📤 Enviar", style=ButtonStyle.success, custom_id="panel:send")
    async def send(self, interaction: discord.Interaction, button: Button):
        db = get_db()
        panel = db.query(Panel).filter_by(id=self.panel_id).first()
        if not panel:
            db.close()
            return await interaction.response.send_message("❌ Painel não encontrado.", ephemeral=True)

        color_int = int(panel.color, 16) if panel.color else 0x5865F2
        embed = discord.Embed(
            title=f"{panel.emoji} {panel.name}",
            description=panel.description or "Clique abaixo para abrir um ticket.",
            color=color_int
        )

        if panel.panel_type == "buttons":
            view = PanelButtonView(self.bot, panel.id, panel.button_style, panel.button_label, panel.button_emoji)
            msg = await interaction.channel.send(embed=embed, view=view)
        elif panel.panel_type == "select":
            panels = db.query(Panel).filter_by(guild_id=interaction.guild_id, panel_type="select", is_active=True).all()
            view = PanelSelectView(self.bot, panels)
            msg = await interaction.channel.send(embed=embed, view=view)
        else:
            msg = await interaction.channel.send(embed=embed)

        panel.channel_id = interaction.channel_id
        panel.message_id = msg.id
        db.commit()
        db.close()
        await interaction.response.send_message(f"✅ Painel enviado neste canal!", ephemeral=True)

    @discord.ui.button(label="🗑️ Desativar", style=ButtonStyle.danger, custom_id="panel:deactivate")
    async def deactivate(self, interaction: discord.Interaction, button: Button):
        db = get_db()
        panel = db.query(Panel).filter_by(id=self.panel_id).first()
        if panel:
            panel.is_active = False
            db.commit()
        db.close()
        await interaction.response.send_message(f"✅ Painel desativado. Use `/ticket ativar` para reativar.", ephemeral=True)

# ==================== BOT ====================
class TicketKingBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        db = get_db()
        panels = db.query(Panel).filter_by(is_active=True).all()

        for p in panels:
            if p.panel_type == "buttons":
                self.add_view(PanelButtonView(self, p.id, p.button_style, p.button_label, p.button_emoji))

        guilds = {}
        for p in panels:
            if p.panel_type == "select":
                guilds.setdefault(p.guild_id, []).append(p)
        for guild_id, gps in guilds.items():
            self.add_view(PanelSelectView(self, gps))

        open_tickets = db.query(Ticket).filter_by(status="open").all()
        for t in open_tickets:
            self.add_view(TicketControlView(self, t.id))

        db.close()

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        print(f"🚀 Ticket King Charts online como {self.user}")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="tickets | /ticket"))

bot = TicketKingBot()

# ==================== COMANDOS TICKET ====================
ticket_group = app_commands.Group(name="ticket", description="Sistema de tickets")

@ticket_group.command(name="painel", description="Cria painel de tickets")
@app_commands.describe(
    nome="Nome do painel",
    tipo="Tipo: buttons, select, links",
    categoria="Categoria dos tickets",
    cargo_staff="Cargo da equipe",
    canal_logs="Canal de logs",
    descricao="Descrição",
    cor="Cor hex",
    emoji="Emoji do painel",
    estilo_botao="primary, secondary, success, danger",
    label_botao="Texto do botão",
    emoji_botao="Emoji do botão"
)
@app_commands.checks.has_permissions(administrator=True)
async def ticket_painel(
    interaction: discord.Interaction,
    nome: str,
    tipo: str,
    categoria: discord.CategoryChannel,
    cargo_staff: discord.Role,
    canal_logs: discord.TextChannel,
    descricao: Optional[str] = None,
    cor: Optional[str] = "5865F2",
    emoji: Optional[str] = "🎫",
    estilo_botao: Optional[str] = "primary",
    label_botao: Optional[str] = "Abrir Ticket",
    emoji_botao: Optional[str] = None
):
    db = get_db()
    panel = Panel(
        guild_id=interaction.guild_id,
        name=nome,
        description=descricao,
        category_id=categoria.id,
        staff_role_id=cargo_staff.id,
        log_channel_id=canal_logs.id,
        panel_type=tipo.lower(),
        color=cor.replace("#", ""),
        emoji=emoji,
        button_style=estilo_botao.lower(),
        button_label=label_botao,
        button_emoji=emoji_botao
    )
    db.add(panel)
    db.commit()
    db.refresh(panel)

    color_int = int(panel.color, 16) if panel.color else 0x5865F2
    embed = discord.Embed(
        title=f"{panel.emoji} {panel.name}",
        description=panel.description or "Clique abaixo para abrir um ticket.",
        color=color_int
    )

    if panel.panel_type == "buttons":
        view = PanelButtonView(bot, panel.id, panel.button_style, panel.button_label, panel.button_emoji)
        msg = await interaction.channel.send(embed=embed, view=view)
    elif panel.panel_type == "select":
        panels = db.query(Panel).filter_by(guild_id=interaction.guild_id, panel_type="select", is_active=True).all()
        view = PanelSelectView(bot, panels)
        msg = await interaction.channel.send(embed=embed, view=view)
    else:
        msg = await interaction.channel.send(embed=embed)

    panel.channel_id = interaction.channel_id
    panel.message_id = msg.id
    db.commit()
    db.close()
    await interaction.response.send_message(f"✅ Painel `{nome}` criado!", ephemeral=True)

@ticket_group.command(name="gerenciar", description="Gerencia painel existente")
@app_commands.describe(painel="ID ou nome do painel")
@app_commands.autocomplete(painel=painel_autocomplete)
@app_commands.checks.has_permissions(administrator=True)
async def ticket_gerenciar(interaction: discord.Interaction, painel: str):
    db = get_db()
    try:
        panel_id = int(painel)
        panel = db.query(Panel).filter_by(id=panel_id, guild_id=interaction.guild_id).first()
    except ValueError:
        panel = db.query(Panel).filter_by(name=painel, guild_id=interaction.guild_id).first()

    if not panel:
        db.close()
        return await interaction.response.send_message("❌ Painel não encontrado.", ephemeral=True)

    color_int = int(panel.color, 16) if panel.color else 0x5865F2
    embed = discord.Embed(
        title=f"✏️ Gerenciar: {panel.name}",
        description=f"Tipo: {panel.panel_type} | Status: {'Ativo' if panel.is_active else 'Inativo'} | Tickets: {panel.total_tickets}",
        color=color_int
    )
    view = PanelManagementView(bot, panel.id)
    db.close()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@ticket_group.command(name="ativar", description="Reativa painel desativado")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_ativar(interaction: discord.Interaction, painel: int):
    db = get_db()
    panel = db.query(Panel).filter_by(id=painel, guild_id=interaction.guild_id).first()
    if not panel:
        db.close()
        return await interaction.response.send_message("❌ Painel não encontrado.", ephemeral=True)
    panel.is_active = True
    db.commit()
    db.close()
    await interaction.response.send_message(f"✅ Painel `{panel.name}` reativado!", ephemeral=True)

@ticket_group.command(name="mover", description="Move painel para outro canal")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_mover(interaction: discord.Interaction, painel: int, canal: discord.TextChannel):
    db = get_db()
    panel = db.query(Panel).filter_by(id=painel, guild_id=interaction.guild_id).first()
    if not panel:
        db.close()
        return await interaction.response.send_message("❌ Painel não encontrado.", ephemeral=True)

    if panel.channel_id and panel.message_id:
        old_ch = interaction.guild.get_channel(panel.channel_id)
        if old_ch:
            try:
                old_msg = await old_ch.fetch_message(panel.message_id)
                await old_msg.delete()
            except:
                pass

    color_int = int(panel.color, 16) if panel.color else 0x5865F2
    embed = discord.Embed(
        title=f"{panel.emoji} {panel.name}",
        description=panel.description or "Clique abaixo para abrir um ticket.",
        color=color_int
    )

    if panel.panel_type == "buttons":
        view = PanelButtonView(bot, panel.id, panel.button_style, panel.button_label, panel.button_emoji)
        msg = await canal.send(embed=embed, view=view)
    elif panel.panel_type == "select":
        panels = db.query(Panel).filter_by(guild_id=interaction.guild_id, panel_type="select", is_active=True).all()
        view = PanelSelectView(bot, panels)
        msg = await canal.send(embed=embed, view=view)
    else:
        msg = await canal.send(embed=embed)

    panel.channel_id = canal.id
    panel.message_id = msg.id
    db.commit()
    db.close()
    await interaction.response.send_message(f"✅ Painel movido para {canal.mention}!", ephemeral=True)

@ticket_group.command(name="lista", description="Lista todos os painéis")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_lista(interaction: discord.Interaction):
    db = get_db()
    panels = db.query(Panel).filter_by(guild_id=interaction.guild_id).all()
    db.close()
    if not panels:
        return await interaction.response.send_message("❌ Nenhum painel.", ephemeral=True)
    embed = discord.Embed(title="📋 Painéis", color=0x5865F2)
    for p in panels:
        status = "🟢" if p.is_active else "🔴"
        embed.add_field(name=f"{status} {p.name} (ID: {p.id})", value=f"Tipo: {p.panel_type} | Tickets: {p.total_tickets}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@ticket_group.command(name="config", description="Configurações gerais")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_config(interaction: discord.Interaction, cargo_staff: discord.Role, canal_logs: discord.TextChannel):
    db = get_db()
    config = db.query(GuildConfig).filter_by(guild_id=interaction.guild_id).first()
    if not config:
        config = GuildConfig(guild_id=interaction.guild_id)
        db.add(config)
    config.staff_role_id = cargo_staff.id
    config.log_channel_id = canal_logs.id
    db.commit()
    db.close()
    await interaction.response.send_message("✅ Config salva!", ephemeral=True)

@ticket_group.command(name="fechar", description="Fecha ticket atual")
async def ticket_fechar(interaction: discord.Interaction):
    db = get_db()
    ticket = db.query(Ticket).filter_by(channel_id=interaction.channel_id, status="open").first()
    db.close()
    if not ticket:
        return await interaction.response.send_message("❌ Não é um ticket aberto.", ephemeral=True)
    view = TicketControlView(bot, ticket.id)
    await view.close.callback(interaction)

@ticket_group.command(name="claim", description="Assume ticket")
async def ticket_claim(interaction: discord.Interaction):
    db = get_db()
    ticket = db.query(Ticket).filter_by(channel_id=interaction.channel_id, status="open").first()
    db.close()
    if not ticket:
        return await interaction.response.send_message("❌ Não é um ticket.", ephemeral=True)
    view = TicketControlView(bot, ticket.id)
    await view.claim.callback(interaction)

@ticket_group.command(name="unclaim", description="Desiste do ticket")
async def ticket_unclaim(interaction: discord.Interaction):
    db = get_db()
    ticket = db.query(Ticket).filter_by(channel_id=interaction.channel_id, status="open").first()
    if not ticket:
        db.close()
        return await interaction.response.send_message("❌ Não é um ticket.", ephemeral=True)
    if ticket.claimed_by != interaction.user.id:
        db.close()
        return await interaction.response.send_message("❌ Você não assumiu este ticket.", ephemeral=True)
    ticket.claimed_by = None
    ticket.claimed_at = None
    db.commit()
    db.close()
    await interaction.response.send_message("✅ Você desistiu do ticket.")

@ticket_group.command(name="add", description="Adiciona usuário")
async def ticket_add(interaction: discord.Interaction, usuario: discord.Member):
    db = get_db()
    ticket = db.query(Ticket).filter_by(channel_id=interaction.channel_id, status="open").first()
    db.close()
    if not ticket:
        return await interaction.response.send_message("❌ Não é um ticket.", ephemeral=True)
    await interaction.channel.set_permissions(usuario, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"✅ {usuario.mention} adicionado.")

@ticket_group.command(name="remove", description="Remove usuário")
async def ticket_remove(interaction: discord.Interaction, usuario: discord.Member):
    db = get_db()
    ticket = db.query(Ticket).filter_by(channel_id=interaction.channel_id, status="open").first()
    db.close()
    if not ticket:
        return await interaction.response.send_message("❌ Não é um ticket.", ephemeral=True)
    await interaction.channel.set_permissions(usuario, overwrite=None)
    await interaction.response.send_message(f"✅ {usuario.mention} removido.")

@ticket_group.command(name="rename", description="Renomeia ticket")
async def ticket_rename(interaction: discord.Interaction, nome: str):
    db = get_db()
    ticket = db.query(Ticket).filter_by(channel_id=interaction.channel_id).first()
    db.close()
    if not ticket:
        return await interaction.response.send_message("❌ Não é um ticket.", ephemeral=True)
    await interaction.channel.edit(name=nome.replace(" ", "-").lower())
    await interaction.response.send_message(f"✅ Renomeado.")

@ticket_group.command(name="thread", description="Cria thread staff")
async def ticket_thread(interaction: discord.Interaction):
    db = get_db()
    ticket = db.query(Ticket).filter_by(channel_id=interaction.channel_id, status="open").first()
    db.close()
    if not ticket:
        return await interaction.response.send_message("❌ Não é um ticket.", ephemeral=True)
    view = TicketControlView(bot, ticket.id)
    await view.create_thread.callback(interaction)

@ticket_group.command(name="transcript", description="Mostra transcript")
async def ticket_transcript(interaction: discord.Interaction):
    db = get_db()
    ticket = db.query(Ticket).filter_by(channel_id=interaction.channel_id).first()
    if not ticket or not ticket.transcript:
        db.close()
        return await interaction.response.send_message("❌ Sem transcript.", ephemeral=True)
    file = File(io.StringIO(ticket.transcript), filename=f"transcript-{ticket.id}.txt")
    await interaction.response.send_message(file=file)
    db.close()

@ticket_group.command(name="avaliar", description="Avalia ticket (DM)")
async def ticket_avaliar(interaction: discord.Interaction):
    db = get_db()
    ticket = db.query(Ticket).filter_by(user_id=interaction.user.id, status="closed").order_by(Ticket.closed_at.desc()).first()
    if not ticket:
        db.close()
        return await interaction.response.send_message("❌ Sem tickets para avaliar.", ephemeral=True)
    if ticket.rating:
        db.close()
        return await interaction.response.send_message("❌ Já avaliou.", ephemeral=True)
    view = RatingView(ticket.id)
    embed = discord.Embed(title="⭐ Avalie", description=f"Ticket #{ticket.id}", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed, view=view)
    db.close()

bot.tree.add_command(ticket_group)

# ==================== COMANDOS STATS COM GRÁFICOS ====================
stats_group = app_commands.Group(name="stats", description="Estatísticas com gráficos visuais")

@stats_group.command(name="volume", description="📊 Volume de tickets por dia")
async def stats_volume(interaction: discord.Interaction, dias: Optional[int] = 7):
    await interaction.response.defer()
    buf = generate_volume_chart(interaction.guild_id, dias)
    file = File(buf, filename="volume.png")
    embed = discord.Embed(title="📊 Volume de Tickets", color=0x5865F2)
    await interaction.followup.send(embed=embed, file=file)

@stats_group.command(name="equipe", description="🏆 Desempenho da equipe com gráfico")
async def stats_equipe(interaction: discord.Interaction):
    await interaction.response.defer()
    buf = generate_team_ranking(interaction.guild_id)
    if not buf:
        return await interaction.followup.send("❌ Sem dados da equipe ainda.", ephemeral=True)
    file = File(buf, filename="equipe.png")
    embed = discord.Embed(title="🏆 Ranking da Equipe", color=0x5865F2)
    await interaction.followup.send(embed=embed, file=file)

@stats_group.command(name="resolucao", description="⏱️ Tempo médio de resolução")
async def stats_resolucao(interaction: discord.Interaction):
    await interaction.response.defer()
    buf = generate_resolution_chart(interaction.guild_id)
    if not buf:
        return await interaction.followup.send("❌ Sem dados de resolução.", ephemeral=True)
    file = File(buf, filename="resolucao.png")
    embed = discord.Embed(title="⏱️ Tempo de Resolução", color=0x5865F2)
    await interaction.followup.send(embed=embed, file=file)

@stats_group.command(name="fechamento", description="📈 Taxa de fechamento ao longo do tempo")
async def stats_fechamento(interaction: discord.Interaction, dias: Optional[int] = 30):
    await interaction.response.defer()
    buf = generate_closure_rate_chart(interaction.guild_id, dias)
    file = File(buf, filename="fechamento.png")
    embed = discord.Embed(title="📈 Taxa de Fechamento", color=0x5865F2)
    await interaction.followup.send(embed=embed, file=file)

@stats_group.command(name="categorias", description="📊 Distribuição por categoria")
async def stats_categorias(interaction: discord.Interaction):
    await interaction.response.defer()
    buf = generate_panel_distribution(interaction.guild_id)
    if not buf:
        return await interaction.followup.send("❌ Sem dados de categorias.", ephemeral=True)
    file = File(buf, filename="categorias.png")
    embed = discord.Embed(title="📊 Distribuição por Categoria", color=0x5865F2)
    await interaction.followup.send(embed=embed, file=file)

@stats_group.command(name="pico", description="🕐 Horário de pico")
async def stats_pico(interaction: discord.Interaction):
    await interaction.response.defer()
    buf = generate_hourly_heatmap(interaction.guild_id)
    file = File(buf, filename="pico.png")
    embed = discord.Embed(title="🕐 Horário de Pico", color=0x5865F2)
    await interaction.followup.send(embed=embed, file=file)

@stats_group.command(name="geral", description="📊 Dashboard completo com todos os gráficos")
async def stats_geral(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_id = interaction.guild_id

    files = []

    # Volume
    buf1 = generate_volume_chart(guild_id, 7)
    files.append(File(buf1, filename="1_volume.png"))

    # Fechamento
    buf2 = generate_closure_rate_chart(guild_id, 30)
    files.append(File(buf2, filename="2_fechamento.png"))

    # Categorias
    buf3 = generate_panel_distribution(guild_id)
    if buf3:
        files.append(File(buf3, filename="3_categorias.png"))

    # Pico
    buf4 = generate_hourly_heatmap(guild_id)
    files.append(File(buf4, filename="4_pico.png"))

    # Equipe
    buf5 = generate_team_ranking(guild_id)
    if buf5:
        files.append(File(buf5, filename="5_equipe.png"))

    # Resolução
    buf6 = generate_resolution_chart(guild_id)
    if buf6:
        files.append(File(buf6, filename="6_resolucao.png"))

    embed = discord.Embed(
        title="📊 Dashboard Completo - Ticket King",
        description="Análises abrangentes de volume e resolução de chamados\n"
                   "Acompanhamento do desempenho da equipe e rankings\n"
                   "Relatórios baseados em períodos de tempo\n"
                   "Gráficos interativos e visualização de dados\n"
                   "Análise e tendências da taxa de fechamento\n"
                   "Rastreamento de tempo de resolução média",
        color=0x5865F2,
        timestamp=datetime.datetime.utcnow()
    )

    await interaction.followup.send(embed=embed, files=files)

bot.tree.add_command(stats_group)

# ==================== ERROS ====================
@ticket_painel.error
@ticket_config.error
@ticket_gerenciar.error
@ticket_ativar.error
@ticket_mover.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Administrador apenas.", ephemeral=True)

def run_bot():
    bot.run(TOKEN)

if __name__ == "__main__":
    run_bot()
