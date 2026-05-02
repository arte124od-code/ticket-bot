"""Gera gráficos visuais para estatísticas"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import discord
from datetime import datetime, timedelta
from database import SessionLocal, Ticket, Panel, StaffStats

def generate_volume_chart(guild_id, period_days=7):
    """Gráfico de volume de tickets por dia"""
    db = SessionLocal()
    now = datetime.utcnow()

    dates = []
    counts = []
    for i in range(period_days-1, -1, -1):
        date = now - timedelta(days=i)
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59)
        count = db.query(Ticket).filter_by(guild_id=guild_id).filter(
            Ticket.opened_at >= start, Ticket.opened_at <= end
        ).count()
        dates.append(date.strftime("%d/%m"))
        counts.append(count)

    db.close()

    plt.figure(figsize=(10, 5))
    plt.bar(dates, counts, color='#5865F2', edgecolor='white', linewidth=1.5)
    plt.title('📊 Volume de Tickets por Dia', fontsize=16, fontweight='bold', color='white')
    plt.xlabel('Data', fontsize=12, color='white')
    plt.ylabel('Quantidade', fontsize=12, color='white')
    plt.xticks(rotation=45, color='white')
    plt.yticks(color='white')
    plt.gca().set_facecolor('#2b2d31')
    plt.gcf().set_facecolor('#1e1f22')
    plt.grid(axis='y', alpha=0.3, color='gray')
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def generate_resolution_chart(guild_id):
    """Gráfico de tempo médio de resolução por staff"""
    db = SessionLocal()
    stats = db.query(StaffStats).filter_by(guild_id=guild_id).filter(StaffStats.tickets_closed > 0).all()

    if not stats:
        db.close()
        return None

    names = []
    times = []
    for s in stats[:10]:
        avg = s.total_resolution_time / s.tickets_closed if s.tickets_closed > 0 else 0
        names.append(f"Staff {s.user_id % 10000}")
        times.append(avg / 60)  # em minutos

    db.close()

    plt.figure(figsize=(10, 5))
    colors = ['#3ba55d' if t < 30 else '#faa81a' if t < 60 else '#ed4245' for t in times]
    plt.barh(names, times, color=colors, edgecolor='white', linewidth=1)
    plt.title('⏱️ Tempo Médio de Resolução (min)', fontsize=16, fontweight='bold', color='white')
    plt.xlabel('Minutos', fontsize=12, color='white')
    plt.ylabel('Staff', fontsize=12, color='white')
    plt.xticks(color='white')
    plt.yticks(color='white')
    plt.gca().set_facecolor('#2b2d31')
    plt.gcf().set_facecolor('#1e1f22')
    plt.grid(axis='x', alpha=0.3, color='gray')
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def generate_team_ranking(guild_id):
    """Gráfico de ranking da equipe"""
    db = SessionLocal()
    stats = db.query(StaffStats).filter_by(guild_id=guild_id).order_by(StaffStats.tickets_closed.desc()).all()

    if not stats:
        db.close()
        return None

    names = []
    claims = []
    closed = []
    for s in stats[:8]:
        names.append(f"ID:{s.user_id % 10000}")
        claims.append(s.tickets_claimed)
        closed.append(s.tickets_closed)

    db.close()

    x = range(len(names))
    width = 0.35

    plt.figure(figsize=(10, 5))
    plt.bar([i - width/2 for i in x], claims, width, label='🙋 Claims', color='#5865F2', edgecolor='white')
    plt.bar([i + width/2 for i in x], closed, width, label='🔒 Fechados', color='#3ba55d', edgecolor='white')
    plt.title('🏆 Desempenho da Equipe', fontsize=16, fontweight='bold', color='white')
    plt.xlabel('Staff', fontsize=12, color='white')
    plt.ylabel('Quantidade', fontsize=12, color='white')
    plt.xticks(x, names, rotation=45, color='white')
    plt.yticks(color='white')
    plt.legend(facecolor='#2b2d31', edgecolor='white', labelcolor='white')
    plt.gca().set_facecolor('#2b2d31')
    plt.gcf().set_facecolor('#1e1f22')
    plt.grid(axis='y', alpha=0.3, color='gray')
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def generate_closure_rate_chart(guild_id, period_days=30):
    """Gráfico de taxa de fechamento ao longo do tempo"""
    db = SessionLocal()
    now = datetime.utcnow()

    dates = []
    rates = []
    for i in range(period_days-1, -1, -1):
        date = now - timedelta(days=i)
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59)
        total = db.query(Ticket).filter_by(guild_id=guild_id).filter(
            Ticket.opened_at >= start, Ticket.opened_at <= end
        ).count()
        closed = db.query(Ticket).filter_by(guild_id=guild_id, status="closed").filter(
            Ticket.closed_at >= start, Ticket.closed_at <= end
        ).count()
        rate = (closed / total * 100) if total > 0 else 0
        dates.append(date.strftime("%d/%m"))
        rates.append(rate)

    db.close()

    plt.figure(figsize=(10, 5))
    plt.plot(dates, rates, color='#faa81a', linewidth=2.5, marker='o', markersize=6, markerfacecolor='white')
    plt.fill_between(dates, rates, alpha=0.3, color='#faa81a')
    plt.title('📈 Taxa de Fechamento (%)', fontsize=16, fontweight='bold', color='white')
    plt.xlabel('Data', fontsize=12, color='white')
    plt.ylabel('Taxa %', fontsize=12, color='white')
    plt.xticks(rotation=45, color='white')
    plt.yticks(color='white')
    plt.ylim(0, 105)
    plt.gca().set_facecolor('#2b2d31')
    plt.gcf().set_facecolor('#1e1f22')
    plt.grid(alpha=0.3, color='gray')
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def generate_panel_distribution(guild_id):
    """Gráfico de pizza - distribuição por categoria"""
    db = SessionLocal()
    panels = db.query(Panel).filter_by(guild_id=guild_id, is_active=True).all()

    if not panels:
        db.close()
        return None

    names = []
    values = []
    for p in panels:
        count = db.query(Ticket).filter_by(panel_id=p.id).count()
        if count > 0:
            names.append(p.name[:15])
            values.append(count)

    db.close()

    if not values:
        return None

    colors = ['#5865F2', '#3ba55d', '#ed4245', '#faa81a', '#eb459e', '#00b0f4']

    plt.figure(figsize=(8, 8))
    plt.pie(values, labels=names, autopct='%1.1f%%', startangle=90, colors=colors[:len(values)],
            textprops={'color': 'white', 'fontsize': 11}, wedgeprops={'edgecolor': '#1e1f22', 'linewidth': 2})
    plt.title('📊 Distribuição por Categoria', fontsize=16, fontweight='bold', color='white')
    plt.gcf().set_facecolor('#1e1f22')
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def generate_hourly_heatmap(guild_id):
    """Gráfico de horário de pico"""
    db = SessionLocal()
    tickets = db.query(Ticket).filter_by(guild_id=guild_id).all()

    hours = {h: 0 for h in range(24)}
    for t in tickets:
        if t.opened_at:
            hours[t.opened_at.hour] += 1

    db.close()

    labels = [f"{h:02d}h" for h in range(24)]
    values = [hours[h] for h in range(24)]

    plt.figure(figsize=(12, 4))
    colors = ['#5865F2' if v > 0 else '#404249' for v in values]
    plt.bar(labels, values, color=colors, edgecolor='white', linewidth=0.5)
    plt.title('🕐 Horário de Pico', fontsize=16, fontweight='bold', color='white')
    plt.xlabel('Hora do Dia', fontsize=12, color='white')
    plt.ylabel('Tickets', fontsize=12, color='white')
    plt.xticks(rotation=45, color='white', fontsize=8)
    plt.yticks(color='white')
    plt.gca().set_facecolor('#2b2d31')
    plt.gcf().set_facecolor('#1e1f22')
    plt.grid(axis='y', alpha=0.3, color='gray')
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf
