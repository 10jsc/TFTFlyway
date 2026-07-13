# 🛡️ TFTFlyway — Sistema Anti-Cheat para TFT

**TFTFlyway** é um sistema completo de detecção, rastreamento e catalogação de hackers/cheaters no Teamfight Tactics (TFT). Ele unifica múltiplos canais de comunicação com o jogo e a API da Riot para analisar jogadores em tempo real e gerar scores de suspeição.

---

## ✨ Funcionalidades

### 🕵️ Detecção Anti-Cheat Híbrida
- **Análise Histórica**: Examina partidas anteriores via API Riot (média de 3★, win rate, top 4 rate, dano, streaks)
- **Comportamento em Tempo Real**: Monitora APM (ações por minuto), tempo de reação e consistência
- **Score Híbrido**: Combina ambas as análises em um score de 0 a 100
- **Níveis**: BAIXO → MÉDIO → ALTO → CRÍTICO
- **Detecção de Smurf**: Identifica contas novas com performance anormal

### 📡 Rastreamento Multi-Canal
- **LCU Bridge**: Conexão direta com o cliente do League of Legends
- **Live Client API**: Dados em tempo real durante a partida (gold, level, players)
- **Riot API**: Histórico de partidas, PUUID, summoner data
- **Server Probe**: Sonda o servidor TFT diretamente
- **Data Collector**: Coleta dados de todos os canais simultaneamente

### 💾 Banco de Dados de Suspeitos
- Catálogo persistente com SQLite
- Histórico completo de encontros por jogador
- Métricas e estatísticas ao longo do tempo
- Lista negra de hackers confirmados

### 🌐 Dashboard Web
- Interface responsiva com Bootstrap 5
- Gráficos em tempo real com Chart.js
- Tabela de suspeitos com filtros
- Log de atividades

---

## 🚀 Instalação

### Pré-requisitos
- **Python 3.10+**
- **League of Legends** instalado
- **Riot API Key** (gratuita em [developer.riotgames.com](https://developer.riotgames.com/))
- Opcional: Opção **"Habilitar API de Dados do Cliente ao Vivo"** nas configurações do LoL

### 1. Clone o repositório
```bash
git clone https://github.com/10jsc/TFTFlyway.git
cd TFTFlyway
```

### 2. Instale as dependências
```bash
pip install -r requirements.txt
```

### 3. Configure o .env
Edite o arquivo `.env` com suas informações:
```env
RIOT_ID=SeuNomeDeInvocador
TAGLINE=BR1
REGION_ACCOUNT=americas
REGION_GAME=br1
LOCKFILE_PATH=F:\Riot Games\League of Legends\lockfile
```

### 4. Execute
```bash
python main.py
```

---

## 📖 Como Usar

### Menu Interativo
```bash
python main.py
```
Digite `help` para ver todos os comandos.

### Anti-Cheat / Detecção
| Comando | Descrição |
|---|---|
| `scan` | Escaneia jogadores na sala atual |
| `monitor [N]` | Monitoramento contínuo (N=intervalo em seg) |
| `search <nome>` | Analisa um jogador específico |
| `blacklist` | Lista negra de hackers confirmados |

### Rastreamento
| Comando | Descrição |
|---|---|
| `track [N]` | Rastreia partida em tempo real |
| `probe` | Sonda o servidor TFT diretamente |
| `collect` | Coleta dados de todos os canais |

### Dados
| Comando | Descrição |
|---|---|
| `report` | Relatório da sessão |
| `dashboard [porta]` | Abre dashboard web (default: 8000) |
| `export` | Exporta dados para JSON |

### Sistema
| Comando | Descrição |
|---|---|
| `status` | Status das conexões |
| `quit` / `exit` | Sair |

### Modo Direto
```bash
python main.py scan
python main.py monitor
python main.py dashboard 8080
python main.py search "Jogador#BR1"
python main.py report
```

---

## 🏗️ Estrutura do Projeto

```
TFTFlyway/
├── main.py                      # Orquestrador principal
├── .env                         # Configurações
├── .gitignore                   # Arquivos ignorados
├── requirements.txt             # Dependências
├── README.md                    # Documentação
├── DESCRICAO.txt                # Descrição detalhada
│
├── core/                        # Módulos de conexão
│   ├── lcu_bridge.py            # Conexão LCU (lockfile)
│   ├── live_api.py              # Live Client API (porta 2999)
│   ├── riot_api.py              # Riot API externa
│   ├── collector.py             # Coleta multi-canal
│   └── server_probe.py          # Sonda servidor TFT
│
├── detector/                    # Motor de detecção
│   ├── database.py              # SQLite - catálogo de suspeitos
│   ├── suspect_detector.py      # Detector híbrido
│   └── player_tracker.py        # Rastreador em tempo real
│
├── analytics/                   # Métricas e relatórios
│   └── metrics.py               # Motor de analytics
│
├── web/                         # Dashboard web
│   └── index.html               # Bootstrap 5 + Chart.js
│
└── data/                        # Dados gerados
    └── suspects.db              # Banco SQLite (criado automaticamente)
```

---

## ⚙️ Arquitetura

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  LCU Bridge  │    │  Live API    │    │  Riot API   │
│  (Lockfile)  │    │  (Porta 2999)│    │  (Externa)  │
└──────┬───────┘    └──────┬───────┘    └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                    ┌──────▼───────┐
                    │   Detector   │
                    │   Híbrido    │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼───┐ ┌──────▼───┐ ┌──────▼───┐
       │ Database  │ │ Metrics  │ │ Dashboard│
       │ (SQLite)  │ │ Engine   │ │ (Web)    │
       └───────────┘ └──────────┘ └──────────┘
```

---

## 🤖 Score de Suspeição

O score é calculado com base em múltiplas métricas ponderadas:

| Métrica | Peso | Descrição |
|---|---|---|
| Média de 3★ | 20% | Quantos campeões 3 estrelas por partida |
| Top 4 Rate | 10% | Porcentagem de vezes que fica entre os 4 primeiros |
| Win Rate | 15% | Porcentagem de vitórias (1º lugar) |
| APM | 25% | Ações por minuto durante a partida |
| Tempo de Reação | 10% | Velocidade média de reação |
| Consistência | 5% | Consistência robótica nos cliques |
| Dano Médio | 10% | Dano médio causado por partida |
| Level Speed | 5% | Velocidade de level up |

**Níveis:**
- **0-39**: BAIXO — Jogador normal
- **40-59**: MÉDIO — Possível suspeito, requer observação
- **60-79**: ALTO — Provável hacker 🟠
- **80-100**: CRÍTICO — Hacker confirmado 🔴

---

## 🛠️ Tecnologias

- **Python 3.12** — Core do sistema
- **Requests** — Comunicação HTTP com APIs
- **SQLite** — Banco de dados local
- **Bootstrap 5.3** — Dashboard web
- **Chart.js 4.4** — Gráficos interativos
- **Win32 API** — Integração com processo do jogo

---

## 📌 Roadmap

- [x] Detector híbrido (histórico + comportamento)
- [x] Banco de dados SQLite de suspeitos
- [x] Dashboard web Bootstrap 5
- [x] Coleta multi-canal (LCU, Live API, Riot API)
- [x] Server probe (comunicação direta com servidor)
- [x] Rastreador em tempo real
- [ ] Notificações desktop push
- [ ] Integração com Discord webhook
- [ ] Auto-avoid (evitar partidas com hackers conhecidos)
- [ ] Modo stealth (ocultar janelas automaticamente)

---

## ⚠️ Aviso Legal

Este projeto é **apenas para fins educacionais e de segurança**. O uso de ferramentas de automação em jogos online pode violar os Termos de Serviço da Riot Games. Use por sua conta e risco.

---

## 👤 Autor

**Johnatan Silva Costa** (Titanjsc)
- GitHub: [10jsc](https://github.com/10jsc)
- Site: [10jsc.github.io](https://10jsc.github.io)

---

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo LICENSE para mais detalhes.
