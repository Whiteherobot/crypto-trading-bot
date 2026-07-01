# 🤖 Cryptobot — Bot de trading algorítmico (Binance Testnet)

Bot modular de trading de criptomonedas en Python, pensado para correr **100%
local** sobre la **Testnet de Binance Spot** (dinero ficticio). Incluye
backtesting con métricas + gráfico de equity y paper trading en vivo.

> ⚠️ **Solo testnet.** El bot está bloqueado para producción a propósito.
> Nunca arriesga capital real.

---

## 📁 Estructura del proyecto

```
cryptobot/
├── config/        # Configuración central (par, indicadores, riesgo) + .env
│   └── config.py
├── data/          # Datos OHLCV (paginación) + diario SQLite del bot
│   ├── data_fetcher.py
│   └── journal.py        # Fuente B: trades/equity/estado para el dashboard
├── strategy/      # Lógica de la estrategia (EMA cross + RSI)
│   └── ema_rsi_strategy.py
├── backtest/      # Motor de backtest + script de ejecución
│   ├── backtester.py
│   └── run_backtest.py
├── live/          # Paper trading en vivo contra la Testnet
│   └── paper_trade.py
├── utils/         # Conexión al exchange, logger, indicadores
│   ├── exchange.py
│   ├── indicators.py
│   └── logger.py
├── logs/          # Archivos de log generados
├── dashboard.py   # Front de control local (streamlit run dashboard.py)
├── requirements.txt
├── .env.example   # Plantilla de credenciales (copiar a .env)
└── README.md
```

---

## 🚀 Puesta en marcha

> Requiere **Python 3.10–3.13** (no 3.14 aún: numpy<2/numba sin wheels).

### 1. Clonar e instalar

**🪟 Windows (PowerShell)**
```powershell
git clone <URL-DE-TU-REPO> cryptobot
cd cryptobot
py -3.11 -m venv venv            # o: python -m venv venv  (si tu python ya es 3.11)
.\venv\Scripts\Activate.ps1      # cmd.exe:  venv\Scripts\activate.bat
pip install -r requirements.txt
```
> Si PowerShell bloquea el script de activación, ejecuta una vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
> Atajo: hay scripts `setup.bat`, `run_bot.bat` y `run_dashboard.bat` (doble clic).

**🐧 Linux / 🍎 macOS**
```bash
git clone <URL-DE-TU-REPO> cryptobot
cd cryptobot
python3.11 -m venv venv
source venv/bin/activate          # fish: source venv/bin/activate.fish
pip install -r requirements.txt
```

### 2. Generar las API keys de la Testnet

1. Entra a **https://testnet.binance.vision/**
2. Pulsa **"Log In with GitHub"** (la testnet usa tu cuenta de GitHub).
3. En el panel, pulsa **"Generate HMAC_SHA256 Key"**.
4. Copia la **API Key** y el **Secret Key** (el secret solo se muestra una vez).
5. La cuenta de prueba ya viene con saldo ficticio (USDT, BTC, etc.). Si te
   quedas sin fondos, ahí mismo puedes resetear/pedir más.

> Estas claves **solo** sirven para la testnet: no tienen ningún poder sobre
> dinero real. Cada PC necesita su propio `.env` (no se sube al repo).

### 3. Configurar el `.env`

```
Windows:  copy .env.example .env
Linux:    cp .env.example .env
```

Edita `.env` y pega tus claves:

```
BINANCE_TESTNET_API_KEY=xxxxxxxx
BINANCE_TESTNET_API_SECRET=xxxxxxxx
TRADING_MODE=testnet
```

### 4. Probar la conexión

```bash
python -m utils.exchange
```

Debe imprimir el balance de tu cuenta de prueba. Si ves un error de
credenciales, revisa el `.env`.

---

## 📊 Backtesting

Corre la estrategia contra el histórico (1-2 años según `config.py`):

```bash
python -m backtest.run_backtest
```

Salida:
- Métricas por consola: **retorno total, win rate, drawdown máximo, Sharpe,
  nº de operaciones**.
- Gráfico de la **curva de equity** en `backtest/output/equity_*.png`.

---

## 🟢 Paper trading en vivo (Testnet)

```bash
python -m live.paper_trade
```

- Revisa el mercado cada 60 s, calcula la señal y ejecuta órdenes de mercado
  **reales en la testnet**.
- **Stop-loss REAL en Binance:** al abrir posición coloca una orden
  `STOP_LOSS_LIMIT` que queda descansando en el exchange, así te protege
  **aunque el bot se apague**. El take-profit y el cruce bajista se gestionan por
  sondeo (cancelando antes el stop real). Si el exchange rechazara el stop,
  hay un respaldo interno por sondeo.
- **Contabilidad limpia:** la estrategia lleva su propia posición y efectivo,
  **separados** del resto de saldos de la cuenta. Nunca vende monedas que no
  compró y su tamaño es siempre `position_size_pct` del capital.
- **Kill-switch de pérdida:** si la estrategia pierde más de
  `max_daily_loss_pct` en el día o `max_weekly_loss_pct` en la semana, **cierra
  la posición y detiene el bot** automáticamente.
- **Recuperación tras reinicio:** el estado de la posición se persiste en
  `data/cryptobot.db`. Si el bot se reinicia (crash, reboot), retoma la posición
  y detecta si el stop-loss real se ejecutó mientras estuvo caído.
- Cada decisión queda registrada en `logs/live.log` (precio, indicadores,
  motivo de entrada/salida, hora) y en el diario SQLite que alimenta el dashboard.
- Maneja caídas de red y rate limits con reintentos y backoff exponencial.
- Pársalo con **Ctrl+C**.

---

## 🖥️ Dashboard de control (Streamlit)

Front local de supervisión y verificación. Corre en **otra terminal**, en
paralelo al bot:

```bash
source venv/bin/activate
streamlit run dashboard.py
```

Se abre en el navegador (http://localhost:8501) y se **auto-refresca** cada N
segundos (configurable en la barra lateral). Secciones:

- **Estado del bot**: corriendo/detenido (por heartbeat), EMA9/EMA21/RSI
  actuales y cercanía a la próxima señal.
- **Resumen de cuenta** (🟢 en vivo desde Binance): saldos USDT/BTC, posición
  abierta con precio de entrada y PnL no realizado.
- **Historial de operaciones**: tabla que **reconcilia** las órdenes de Binance
  (🟢 verdad oficial) con el diario del bot (🔵 motivo de cada decisión). Si una
  orden aparece en una fuente y no en la otra, lo marca como **alerta**.
- **Gráficas**: curva de equity 🔵 **estrategia** vs 🟢 **comprar-y-mantener**
  (para ver si la estrategia le gana a solo HODLear), velas con EMAs y
  marcadores de compra/venta, y drawdown de la estrategia.

> **Dos fuentes, siempre etiquetadas:** 🟢 = API de Binance Testnet (lo que
> realmente se ejecutó) · 🔵 = diario local del bot (el porqué de cada orden).

El dashboard es de **solo lectura**: no opera, solo observa. Funciona aunque el
bot no esté corriendo (muestra el último estado guardado) e incluso sin `.env`
(muestra solo la Fuente B).

---

## ⚙️ Ajustar la estrategia

Todo se cambia en **`config/config.py`** (no hay números mágicos en el código):

| Parámetro            | Dónde            | Qué hace                              |
|----------------------|------------------|---------------------------------------|
| `symbol`, `timeframe`| `MarketConfig`   | Par y temporalidad                    |
| `ema_fast/ema_slow`  | `StrategyConfig` | Periodos de las medias móviles        |
| `rsi_period`         | `StrategyConfig` | Periodo del RSI                       |
| `rsi_lower/rsi_upper`| `StrategyConfig` | Filtro de momentum / sobrecompra      |
| `position_size_pct`  | `RiskConfig`     | % del capital por operación           |
| `stop_loss_pct`      | `RiskConfig`     | Stop-loss                             |
| `take_profit_pct`    | `RiskConfig`     | Take-profit                           |
| `fee_pct`            | `RiskConfig`     | Comisión estimada por lado            |
| `use_exchange_stop`  | `RiskConfig`     | Colocar el stop-loss como orden real  |
| `max_daily_loss_pct` | `RiskConfig`     | Kill-switch: pérdida diaria máxima    |
| `max_weekly_loss_pct`| `RiskConfig`     | Kill-switch: pérdida semanal máxima   |

---

## 🧠 La estrategia (resumen)

**EMA 9 / EMA 21 + filtro RSI**, long-only:

- **Entrada:** la EMA rápida cruza por encima de la lenta **y** el RSI está
  entre `rsi_lower` y `rsi_upper` (hay momentum, pero sin sobrecompra).
- **Salida:** cruce bajista de EMAs, **o** se toca el stop-loss / take-profit.

Es una base sencilla y robusta para empezar; la idea es que la valides en
backtest y la afines antes de dejarla corriendo en paper trading.

---

## ⚠️ Aviso

Este proyecto es educativo. El rendimiento en backtest **no garantiza**
resultados futuros. Úsalo solo en testnet.
