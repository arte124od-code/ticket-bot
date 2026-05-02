# 🎫 Ticket King Charts

Bot de tickets com gráficos visuais e estatísticas avançadas.

## ✨ Funcionalidades

### Painéis
- 🎨 Botões, Select Menu, Links
- 💾 Salvos no banco (reativáveis, movíveis, editáveis)
- ✏️ Edição em tempo real

### Tickets
- 🙋 Claim/Unclaim
- 🔒 Fechar com transcript
- ➕ Add/Remove/Rename/Thread
- ⭐ Avaliação 1-5 estrelas

### Estatísticas com Gráficos (`/stats`)
- `/stats volume` - 📊 Gráfico de barras: tickets por dia
- `/stats equipe` - 🏆 Gráfico comparativo: desempenho staff
- `/stats resolucao` - ⏱️ Gráfico horizontal: tempo médio de resolução
- `/stats fechamento` - 📈 Gráfico de linha: taxa de fechamento (%)
- `/stats categorias` - 📊 Gráfico de pizza: distribuição por categoria
- `/stats pico` - 🕐 Gráfico de barras: horário de pico (24h)
- `/stats geral` - 📊 Todos os gráficos de uma vez (dashboard completo)

## 🚀 Deploy

### Variáveis (Railway)
| Variável | Descrição |
|---|---|
| `DISCORD_TOKEN` | Token do bot |
| `GUILD_ID` | ID do servidor (opcional) |

### Comandos Admin
- `/ticket painel` - Cria painel
- `/ticket gerenciar` - Edita painel
- `/ticket ativar` - Reativa painel
- `/ticket mover` - Move painel
- `/ticket lista` - Lista painéis
- `/ticket config` - Configurações

### Comandos Staff
- `/ticket claim/unclaim/fechar/add/remove/rename/thread/transcript`

### Comandos Stats
- `/stats volume/equipe/resolucao/fechamento/categorias/pico/geral`
