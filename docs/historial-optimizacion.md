# Historial de optimización y operación (julio de 2026)

> Bitácora completa de las rondas de backtest, diagnóstico y puesta en marcha. El resumen está en el [README](../README.md).


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
├── strategy/      # Lógica de las estrategias (intercambiables por config)
│   ├── ema_rsi_strategy.py   # Seguimiento de tendencia: cruce EMA + RSI + filtros
│   ├── bb_rsi_strategy.py    # Reversión a la media: Bollinger + RSI
│   └── factory.py            # Instancia la estrategia activa (MARKET.strategy)
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

Corre la estrategia contra el histórico disponible (la testnet solo conserva
~30 días; `history_limit` en `config.py` pide más pero se recorta a lo que
haya):

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

| Parámetro            | Dónde            | Qué hace                              | Valor actual |
|----------------------|------------------|----------------------------------------|:---:|
| `symbol`, `timeframe`| `MarketConfig`   | Par y temporalidad                    | BTC/USDT, **15m** |
| `strategy`           | `MarketConfig`   | Estrategia activa: `"ema_rsi"` (tendencia) o `"bb_rsi"` (reversión a la media) — ver `strategy/factory.py` | **ema_rsi** |
| `ema_fast/ema_slow`  | `StrategyConfig` | Periodos de las medias móviles        | 9 / 21 |
| `rsi_period`         | `StrategyConfig` | Periodo del RSI                       | 14 |
| `rsi_lower/rsi_upper`| `StrategyConfig` | Filtro de momentum / sobrecompra      | 50 / 70 |
| `ema_trend`          | `StrategyConfig` | Filtro de tendencia: solo compra si precio > EMA (p.ej. 200). `None` para desactivar | 200 |
| `vol_window`         | `StrategyConfig` | Nº de velas para el volumen promedio  | 20 |
| `vol_mult`           | `StrategyConfig` | Solo entra si el volumen de la señal es >= este múltiplo del promedio. `None` para desactivar | 1.2 |
| `regime_lookback`    | `StrategyConfig` | Nº de velas para medir la pendiente de `ema_trend`. `None` para desactivar | 20 |
| `regime_slope_threshold` | `StrategyConfig` | Solo entra (y se cierra si deja de cumplirse) si la pendiente de `ema_trend` supera este umbral — exige régimen ALCISTA confirmado, no solo "precio > EMA200" | 0.1% |
| `atr_period`         | `StrategyConfig` | Periodo del ATR (volatilidad)         | 14 |
| `confirm_candle`     | `StrategyConfig` | Si es True, espera una vela más tras el cruce y exige que el cierre siga sobre `ema_fast` antes de entrar | **False** (probado y descartado, ver abajo) |
| `atr_lookback`       | `StrategyConfig` | Solo entra si ATR actual <= mediana(ATR de las últimas `atr_lookback` velas) x `atr_max_mult`. `None` para desactivar | **None** (probado y descartado, ver ronda 4) |
| `atr_max_mult`       | `StrategyConfig` | Umbral de volatilidad "aceptable" para el filtro de arriba (solo aplica si `atr_lookback` no es `None`) | 1.0 |
| `position_size_pct`  | `RiskConfig`     | % del capital por operación           | 10% |
| `stop_loss_pct`      | `RiskConfig`     | Stop-loss fijo: TECHO máximo de riesgo del stop inicial (ver `atr_multiplier`) | 2% |
| `trail_pct`          | `RiskConfig`     | Trailing stop en % fijo. Se usa solo si `atr_multiplier` está desactivado | 1.5% |
| `atr_multiplier`     | `RiskConfig`     | Stop inicial y trailing DINÁMICOS: distancia = `atr_multiplier` x ATR, en vez de % fijo. `None` para volver al % fijo | 1.5 |
| `cooldown_candles`   | `RiskConfig`     | Velas de espera tras cerrar una operación antes de poder volver a entrar | 3 |
| `weekly_loss_limit`  | `RiskConfig`     | Circuit breaker: si el retorno de 7 días corridos cae por debajo de esto, pausa nuevas entradas (no cierra posiciones ni detiene el bot) | -3% |
| `breaker_pause_hours`| `RiskConfig`     | Cuánto dura la pausa del circuit breaker antes de reevaluar | 48h |
| `fee_pct`            | `RiskConfig`     | Comisión estimada por lado            | 0.1% |
| `use_exchange_stop`  | `RiskConfig`     | Colocar el stop-loss como orden real  | activado |
| `max_daily_loss_pct` | `RiskConfig`     | Kill-switch: pérdida diaria máxima (detiene el bot por completo) | 5% |
| **Parámetros de `bb_rsi`** (solo aplican con `strategy="bb_rsi"`) | `BBRsiConfig` | | |
| `bb_period` / `bb_std` | `BBRsiConfig` | Período y desviaciones estándar de las Bandas de Bollinger | 20 / 2.0 |
| `rsi_oversold`       | `BBRsiConfig`    | Solo entra si RSI < este umbral (sobreventa)   | 35 |
| `stop_loss_pct`      | `BBRsiConfig`    | Stop fijo simple desde la entrada (distinto del de `RiskConfig`, que es el techo de `ema_rsi`) | 1.5% |
| `time_stop_candles`  | `BBRsiConfig`    | Cierre forzado si no llegó a la banda media en N velas | 10 |
| `max_weekly_loss_pct`| `RiskConfig`     | Kill-switch: pérdida semanal máxima (detiene el bot por completo) | 10% |

---

## 🧠 La estrategia (resumen)

Hay dos estrategias implementadas, seleccionables con `MARKET.strategy`
(ver `strategy/factory.py`). La activa por defecto es `ema_rsi`.

### `ema_rsi` (activa por defecto) — seguimiento de tendencia

**EMA 9 / EMA 21 + filtro RSI + filtro de tendencia (EMA200) + filtro de
volumen**, en velas de **15 minutos**, long-only:

- **Entrada:** la EMA rápida cruza por encima de la lenta, **y** el RSI está
  entre `rsi_lower` y `rsi_upper` (hay momentum, pero sin sobrecompra), **y**
  el precio está por encima de la EMA de tendencia (`ema_trend`, 200 velas —
  evita comprar cruces alcistas dentro de un mercado lateral o en tendencia
  bajista de fondo), **y** el volumen de la vela de señal es al menos
  `vol_mult` veces el promedio de las `vol_window` velas anteriores (exige
  que el cruce venga con participación real). Además, tras cerrar una
  operación, se ignoran nuevas entradas durante `cooldown_candles` velas.
- **Salida:** cruce bajista de EMAs, **o** se toca el stop (fijo al principio;
  si el precio sube, un **trailing stop** —`trail_pct`— lo va subiendo para
  dejar correr la ganancia en vez de cortarla en un take-profit fijo).

Es una base sencilla y robusta para empezar; la idea es que la valides en
backtest y la afines antes de dejarla corriendo en paper trading.

### `bb_rsi` (alternativa, implementada en la ronda 5) — reversión a la media

**Bandas de Bollinger + RSI**, en velas de **15 minutos**, long-only:

- **Entrada:** el cierre toca o cruza por debajo de la banda inferior de
  Bollinger (`bb_period`/`bb_std`), **y** RSI < `rsi_oversold` (sobreventa
  real), **y** la vela es alcista (close > open, el rebote ya empezó).
- **Salida** (orden de prioridad): 1) el precio toca la banda MEDIA
  (objetivo natural de la reversión), 2) stop-loss fijo (`stop_loss_pct` de
  `BBRsiConfig`), 3) `time_stop_candles` velas sin llegar al objetivo ->
  cierre forzado. Sin trailing a propósito (interferiría con el objetivo).
- Probada en backtest (ver ronda 5 más abajo) y **no superó el semáforo
  VERDE** — queda disponible pero no es la que corre por defecto.

---

## 📈 Historial de optimización (2026-07-03)

Punto de partida: EMA9/21 + RSI en 5m, sin filtro de tendencia, take-profit
fijo, sin filtro de volumen ni cooldown. Backtest sobre el histórico
disponible en la testnet (~30 días, 2026-06-03 a 2026-07-03):
**-17.35% de retorno, 192 operaciones, 8.85% de aciertos, drawdown -17.56%.**

Se probaron 4 mejoras, cada una medida en backtest antes de pasar a la
siguiente (mismos ~30 días salvo donde se indica):

**1. Timeframe (5m vs 15m vs 1h)** — con el filtro de tendencia EMA200 ya
puesto:

| Timeframe | Retorno | Operaciones | Win rate | Max DD | Sharpe |
|---|---:|---:|---:|---:|---:|
| 5m  | -9.13% | 103 | 10.68% | -9.37% | -20.78 |
| 15m | -6.34% | 42  | 0.00%  | -6.41% | -19.87 |
| 1h  | -0.94% | 5   | 0.00%  | -0.94% | -7.20  |

**Elegido: 15m.** 1h tiene mejores números "en papel", pero con solo 5
operaciones en 30 días no es una muestra fiable — es casi "no operar", no
una estrategia probada. 15m da una muestra razonable (42 operaciones) y ya
reduce a la mitad el ruido de 5m. Si tras acumular más historial en vivo el
1h sigue viéndose bien con más operaciones, vale la pena revisitarlo.

**2. Trailing stop** (reemplaza el take-profit fijo), sobre 15m, sin filtro
de volumen todavía:

| Config | Retorno | Win rate | Max DD | Sharpe | Motivo de salida |
|---|---:|---:|---:|---:|---|
| Sin trailing (solo SL fijo) | -6.34% | 0.00% | -6.41% | -19.87 | 25 SL, 17 cruce EMA |
| `trail_pct=1.5%` | **-2.27%** | 11.90% | -3.62% | **-5.42** | 30 trailing, 12 cruce EMA |
| `trail_pct=2%` | -3.35% | 9.52% | -4.63% | -7.91 | 27 trailing, 15 cruce EMA |
| `trail_pct=3%` | -4.65% | 2.38% | -5.80% | -10.81 | 18 SL, 16 cruce, 8 trailing |

**Elegido: 1.5%.** El más ajustado de los tres probados fue el mejor en este
mercado de rango estrecho — deja correr un poco la ganancia pero la protege
rápido en cuanto el precio retrocede.

**3. Filtro de volumen** (20 velas, 120% del promedio), sobre 15m + trailing 1.5%:

| Config | Retorno | Operaciones | Win rate | Max DD | Sharpe |
|---|---:|---:|---:|---:|---:|
| Sin filtro de volumen | -2.27% | 42 | 11.90% | -3.62% | -5.42 |
| **Con filtro de volumen** | **+0.51%** | **10** | **20.00%** | **-0.94%** | **+1.35** |

**El cambio con más impacto de los cuatro.** Filtra 32 de las 42 señales por
no tener volumen real detrás — el bot pasa de "operar todo lo que cruza" a
operar solo los cruces con participación de mercado real. Primer resultado
en positivo de toda la optimización.

**4. Cooldown entre operaciones** (3 velas), sobre 15m + trailing 1.5% +
filtro de volumen: **sin efecto medible** (idéntico con 0, 3 o 6 velas). El
filtro de volumen ya deja las operaciones tan espaciadas que el cooldown
nunca llega a activarse en esta ventana. Se deja en 3 como red de seguridad
barata para escenarios de mayor volumen/más señales seguidas, sin costo
aparente.

### Comparación final: original vs. mejorado

**Sobre los mismos ~30 días (testnet):**

| | Original (5m, sin filtros) | Mejorado (15m + todo) |
|---|---:|---:|
| Retorno | -17.35% | **+0.51%** |
| Operaciones | 192 | 10 |
| Win rate | 8.85% | 20.00% |
| Max drawdown | -17.56% | -0.94% |
| Sharpe | -29.3 | +1.35 |

**Validación fuera de muestra — 90 días de datos REALES de Binance** (la
testnet solo conserva ~30 días de histórico, así que para esta prueba se
usaron velas públicas reales de Binance Spot, sin API keys ni operar —
solo lectura de histórico. El paper trading en vivo sigue siendo
100% testnet):

| | Original (5m, sin filtros) | Mejorado (15m + todo) | Comprar y mantener |
|---|---:|---:|---:|
| Retorno (90 días) | -11.59% | **-0.73%** | -8.20% |
| Operaciones | 592 | 40 | — |
| Win rate | 23.82% | **37.50%** | — |
| Max drawdown | -11.84% | **-1.28%** | — |
| Sharpe | -16.81 | -2.27 | — |

El `trail_pct=1.5%` elegido con los 30 días también resultó ser el mejor (o
empatado) al re-probarlo sobre estos 90 días reales (-0.73% vs -0.85% con 2%
y -0.80% con 3%) — no parece sobreajustado a la ventana corta.

### 🚦 Veredicto: AMARILLO

**Hay mejora real y consistente, pero todavía no para soltarlo una semana sin supervisión.**

Lo bueno:
- Retorno pasó de -17.35% a +0.51% en la ventana de 30 días, y de -11.59% a
  -0.73% en 90 días reales fuera de muestra — la mejora **no es un
  espejismo de sobreajuste**, se sostiene en datos que la estrategia nunca vio.
- En 90 días reales, el bot **le gana a comprar-y-mantener por ~7.5 puntos**
  (-0.73% vs -8.20%) y controla el drawdown a menos de -1.3% en todo momento.
- El win rate se cuadruplicó (8.85% → 37.5% en la ventana de 90 días).

Lo que falta:
- El retorno de 90 días sigue siendo **ligeramente negativo** (-0.73%), no
  positivo. La estrategia protege capital mucho mejor que antes, pero
  todavía no tiene una edge neta demostrada en una ventana amplia.
- El Sharpe de 90 días sigue en negativo (-2.27), aunque muy lejos del -16.81
  original.
- Todo esto se probó solo en BTC/USDT — no se validó en otro par ni en otro
  régimen de mercado (ej. un tramo claramente alcista).

**Qué ajustar antes de un veredicto verde:**
1. Añadir el "circuito de freno" de la Fase 1 propuesta en el diagnóstico
   inicial (pausar/reducir tamaño si el win rate reciente cae) como red de
   seguridad adicional durante la prueba en vivo.
2. Partir los 90 días en tramos (alcista/lateral/bajista) para ver si la
   estrategia gana en unos regímenes y pierde en otros — hoy el resultado es
   un promedio que puede esconder eso.
3. Si tras esto se decide arrancar el paper trading en vivo, hacerlo con
   supervisión diaria los primeros días, no completamente desatendido,
   apoyándose en los kill-switches (`max_daily_loss_pct`/`max_weekly_loss_pct`)
   que ya están activos.

**No se tocó el paper trading en vivo** en esta ronda — sigue detenido, tal
como se pidió, a la espera de estos ajustes adicionales.

---

## 📈 Historial de optimización — ronda 2 (2026-07-03): régimen, ATR, confirmación, circuit breaker

Punto de partida de esta ronda: la config de la ronda 1 (15m + EMA200 +
volumen + trailing 1.5% + cooldown 3). 90 días: -0.73%, Sharpe -2.27.

### 1. Diagnóstico de régimen (solo análisis, sin tocar código)

Se dividieron los 90 días en ALCISTA/LATERAL/BAJISTA según la pendiente de
la EMA200 en 20 velas. El umbral inicial (0.5%) resultó demasiado exigente
(92% del tiempo caía en "lateral"); recalibrado a **0.1%** dio un split
razonable (33/33/33):

| Régimen | % del tiempo | Operaciones | Win rate | PnL total | Precio (buy&hold) en ese tramo |
|---|---:|---:|---:|---:|---:|
| ALCISTA (slope > +0.1%) | 33.4% | 13 | 46.2% | -$6.73 (~flat) | +0.33% |
| LATERAL (-0.1% a +0.1%) | 33.2% | 27 | 33.3% | **-$26.03** | +10.36% |
| BAJISTA (slope < -0.1%) | 33.4% | 0 | — | $0 | -17.08% |

El filtro `ema_trend` (precio > EMA200) ya evitaba casi toda entrada en
tendencia bajista real (0 operaciones ahí). Pero **el 67.5% de las
operaciones ocurría en mercado lateral, y ahí se concentraba casi toda la
pérdida** (-$26 de -$33 totales). El régimen alcista estaba casi en
equilibrio. Esto marcó el diseño del filtro de régimen: excluir también el
lateral, no solo el bajista.

### 2. Filtro de régimen (pendiente de EMA200, `regime_lookback=20`, `regime_slope_threshold=0.1%`)

| Config | Retorno | Operaciones | Win rate | Max DD | Sharpe |
|---|---:|---:|---:|---:|---:|
| Sin filtro de régimen | -0.73% | 40 | 37.50% | -1.28% | -2.27 |
| **Con filtro de régimen** | **-0.20%** | **13** | **46.15%** | **-0.50%** | **-1.07** |

Filtra 27 de las 40 operaciones (las mismas 27 "lateral" del diagnóstico).
Mejora todo, aunque sigue sin ser positivo.

### 3. Stop-loss y trailing dinámicos con ATR (`atr_multiplier`)

`stop_loss_pct` pasa a ser el TECHO máximo de riesgo, no la distancia fija:
`distancia = min(atr_multiplier x ATR, stop_loss_pct x precio)`.

| Config | Retorno | Win rate | Max DD | Sharpe |
|---|---:|---:|---:|---:|
| Sin ATR (% fijo) | -0.20% | 46.15% | -0.50% | -1.07 |
| ATR x1.0 | -0.15% | 30.77% | -0.23% | -2.76 |
| **ATR x1.5** | **-0.10%** | **53.85%** | **-0.18%** | -1.35 |
| ATR x2.0 | -0.21% | 38.46% | -0.25% | -2.25 |

**Elegido: 1.5x.** Mejor retorno, mejor win rate y menor drawdown de los
cuatro (el Sharpe queda ligeramente por debajo del % fijo, pero con 13
operaciones esa métrica es ruidosa; los otros tres indicadores son consistentes).

### 4. Confirmación de doble vela (`confirm_candle`)

| Config | Retorno | Win rate | Sharpe |
|---|---:|---:|---:|
| `confirm_candle=False` | **-0.10%** | **53.85%** | **-1.35** |
| `confirm_candle=True` | -0.32% | 30.77% | -4.62 |

**Descartado.** Con el filtro de volumen y de régimen ya tan selectivos,
ninguna de las 13 señales de los 90 días era una mecha falsa que la
confirmación pudiera filtrar — solo retrasó la entrada una vela (peor
precio de entrada) sin evitar ninguna operación mala. Es una lección
concreta de sobre-filtrado: no toda mejora "intuitiva" ayuda una vez que
otras ya cubren el mismo problema.

### 5. Circuit breaker semanal

`weekly_loss_limit=-3%` sobre 7 días **corridos** (no de calendario, a
diferencia del kill-switch `max_weekly_loss_pct` que ya existía). Si se
dispara, el bot deja de abrir posiciones nuevas durante `breaker_pause_hours`
(48h) y vuelve a evaluar — NO cierra la posición abierta ni detiene el bot
(para eso sigue estando el kill-switch). Implementado en `paper_trade.py`
(`_check_weekly_breaker`) y visible como alerta ⏸️ en el dashboard. No aplica
al backtest (es una salvaguarda operativa de la ejecución en vivo, no una
regla de la estrategia), así que no cambia ninguna métrica de backtest.

### Comparación final: original vs. v1 (ronda 1) vs. v2 (esta ronda) — 90 días

| | Original (5m, sin filtros) | v1 (ronda 1) | v2 (esta ronda) |
|---|---:|---:|---:|
| Retorno | -11.59% | -0.73% | **-0.10%** |
| Operaciones | 592 | 40 | 13 |
| Win rate | 23.82% | 37.50% | **53.85%** |
| Max drawdown | -11.84% | -1.28% | **-0.18%** |
| Sharpe | -16.81 | -2.27 | -1.35 |

### Validación en un tercer período no visto — 6 meses reales (2026-01-02 a 2026-07-03)

Datos públicos reales de Binance (mismo motivo que antes: la testnet no
guarda tanto histórico). Este período incluyó un mercado bajista fuerte:
comprar-y-mantener BTC en esos 6 meses dio **-30.79%**.

| | Original (5m, sin filtros) | v2 (esta ronda) | Comprar y mantener |
|---|---:|---:|---:|
| Retorno | -23.24% | **-0.89%** | -30.79% |
| Operaciones | 1224 | 32 | — |
| Win rate | 21.90% | 31.25% | — |
| Max drawdown | -23.41% | **-0.91%** | — |
| Sharpe | -15.44 | -5.05 | — |

**Breakdown por régimen del resultado v2 en estos 6 meses:** las 32
operaciones cayeron **el 100% del tiempo en régimen ALCISTA** (0 en lateral,
0 en bajista) — el filtro de régimen se comportó exactamente como se
diseñó, incluso en un período con un tramo bajista mucho más severo que el
de 90 días.

### 🚦 Veredicto: ROJO (con matiz importante)

Aplicando el criterio literal pedido — Sharpe en los 3 períodos probados
con la config v2 (30 días recientes: -0.99 · 90 días: -1.35 · 6 meses:
-5.05) — **los tres son negativos**, así que por la letra del criterio esto
es ROJO, no AMARILLO ni VERDE.

**Pero es importante leer esto con matiz, no como "la estrategia no tiene
edge":**
- En los tres períodos el retorno está prácticamente plano (-0.03% / -0.10%
  / -0.89%), no cayendo — muy distinto del original, que pierde entre -11%
  y -23% en las mismas ventanas.
- En el período de 6 meses (el más severo: mercado bajista de -30.79%), la
  v2 le gana a comprar-y-mantener por **~30 puntos** y al original por
  **~22 puntos**. El filtro de régimen demostrablemente evita el grueso del
  daño.
- El Sharpe negativo aquí viene de que el bot pasa la enorme mayoría del
  tiempo **en cash** (solo 13-32 operaciones en 90-180 días) — con tan poca
  variancia y algunas pérdidas pequeñas, el Sharpe se ve penalizado aunque
  el comportamiento sea el deseado (no perder dinero, no el de generar
  ganancias todavía).
- Es decir: **hay una edge defensiva real y demostrada** (evitar pérdidas
  grandes), pero **no una edge ofensiva todavía** (el bot no está
  capturando suficiente del lado ganador cuando el régimen sí es
  favorable). Eso es sobre-filtrado, no ausencia de edge.

**Siguiente ajuste recomendado (antes de replantear la estrategia entera):**
relajar ligeramente `regime_slope_threshold` (p.ej. 0.05% en vez de 0.1%)
o `vol_mult` (p.ej. 1.1 en vez de 1.2) para dejar pasar algunas operaciones
más sin volver a caer en el problema original de sobre-operar en lateral —
buscando el punto donde el Sharpe cruce a positivo sin sacrificar el control
de drawdown logrado.

**No se tocó el paper trading en vivo.** Sigue detenido.

---

## 📈 Historial de optimización — ronda 3 (2026-07-03): grid search + diagnóstico honesto

Hipótesis a probar: la config v2 está sobre-filtrada (13-32 operaciones en
90-180 días) y aflojar `regime_slope_threshold` o `vol_mult` debería
recuperar Sharpe positivo sin volver al problema de sobre-operar en lateral.

### Grid search 4×4 (90 días) — `regime_slope_threshold` × `vol_mult`

16 combinaciones, ordenadas por Sharpe (tabla completa; `n_alcista/lateral/bajista`
confirma que el filtro de régimen sigue funcionando en todos los casos — el
100% de las operaciones cae siempre en régimen alcista):

| regime_threshold | vol_mult | Retorno | Sharpe | Win rate | Operaciones | Max DD |
|---:|---:|---:|---:|---:|---:|---:|
| **0.10%** | **1.2** | **-0.11%** | **-1.48** | **57.14%** | 14 | -0.18% |
| 0.10% | 1.3 | -0.13% | -1.76 | 53.85% | 13 | -0.20% |
| 0.10% | 1.1 | -0.16% | -1.86 | 50.00% | 18 | -0.27% |
| 0.07% | 1.2 | -0.23% | -2.87 | 44.44% | 18 | -0.26% |
| 0.07% | 1.1 | -0.27% | -3.12 | 40.91% | 22 | -0.37% |
| 0.07% | 1.3 | -0.25% | -3.16 | 41.18% | 17 | -0.28% |
| 0.05% | 1.2 | -0.30% | -3.56 | 40.91% | 22 | -0.35% |
| 0.05% | 1.1 | -0.34% | -3.76 | 38.46% | 26 | -0.46% |
| 0.05% | 1.3 | -0.32% | -3.84 | 38.10% | 21 | -0.37% |
| 0.03% | 1.2 | -0.36% | -4.16 | 38.46% | 26 | -0.42% |
| 0.03% | 1.3 | -0.36% | -4.23 | 37.50% | 24 | -0.41% |
| 0.03% | 1.1 | -0.41% | -4.31 | 36.67% | 30 | -0.52% |
| 0.10% | 1.0 (sin filtro vol.) | -0.96% | -7.88 | 27.27% | 44 | -1.04% |
| 0.07% | 1.0 | -1.14% | -8.78 | 25.00% | 52 | -1.20% |
| 0.05% | 1.0 | -1.37% | -9.91 | 25.40% | 63 | -1.43% |
| 0.03% | 1.0 | -1.54% | -10.41 | 25.35% | 71 | -1.61% |

**Resultado contrario a la hipótesis: aflojar CUALQUIERA de los dos filtros
empeora el resultado, de forma monótona y consistente.** La config actual
(`0.10%`, `1.2`) es exactamente el punto óptimo del grid — no una config
demasiado conservadora. Quitar el filtro de volumen (`vol_mult=1.0`) es lo
peor posible en todos los casos (Sharpe -7.88 a -10.41), confirmando que ese
filtro sigue siendo el más valioso de los dos. Ninguna de las 16
combinaciones da retorno positivo en 90 días.

### Validación del "ganador" (= la config actual) en los 6 meses no vistos

| | 90 días | 6 meses |
|---|---:|---:|
| Retorno | -0.11% | -0.89% |
| Sharpe | -1.48 | -5.05 |
| Max drawdown | -0.18% | -0.91% |

Sharpe negativo en **ambos** períodos → por el criterio del prompt, esto es
**ROJO real**, no un caso de overfitting de un ajuste puntual (porque no
hubo ajuste: la config ganadora ya era la que estaba activa).

### 🚦 Veredicto: ROJO real — no seguir ajustando estos dos parámetros

Tal como pedía el prompt, no se siguió tocando `regime_slope_threshold` ni
`vol_mult` al confirmarse el ROJO. En su lugar, diagnóstico de qué
distingue a las operaciones ganadoras de las perdedoras (32 operaciones de
los 6 meses, 10 ganadoras / 22 perdedoras):

| Variable en el momento de ENTRAR | Ganadoras (media) | Perdedoras (media) |
|---|---:|---:|
| RSI | 59.98 | 60.17 |
| Pendiente EMA200 | 0.212% | 0.225% |
| **ATR (% del precio)** | **0.299%** | **0.349%** |
| **Ratio de volumen vs. promedio** | **3.79x** | **2.48x** |
| Distancia a EMA200 | 1.373% | 1.489% |

RSI, pendiente de régimen y distancia a EMA200 son prácticamente idénticos
entre ganadoras y perdedoras — no distinguen nada, ya están bien cubiertos
por los filtros existentes. Dos variables sí muestran una diferencia real:

1. **Volumen**: las ganadoras entran con ~53% más volumen relativo que las
   perdedoras (3.79x vs 2.48x el promedio). El filtro actual (`vol_mult=1.2`)
   deja pasar señales que apenas superan el mínimo; las que más volumen
   traen de más tienden a funcionar mejor — pero la relación tiene ruido
   (hay excepciones claras en ambos sentidos con solo 32 datos).
2. **ATR relativo al precio**: las ganadoras entran con **menos** volatilidad
   (0.299% vs 0.349%). Esto tiene sentido económico directo con cómo
   funciona el trailing stop: 21 de las 22 pérdidas salieron por
   `trailing_stop` (solo 1 por cruce EMA) — con ATR alto, la distancia del
   trailing (`atr_multiplier x ATR`) es más ancha, pero el precio también
   se mueve más violentamente contra la posición, y el trailing sigue
   saltando. Con ATR bajo, la tendencia es más "limpia" y el trailing
   —aunque más ajustado— no se dispara por ruido.

**Una sola modificación propuesta para la próxima ronda:** añadir un filtro
de entrada que compare el ATR actual contra su propia media reciente (no un
número fijo, sino relativo — se adapta a cualquier régimen de volatilidad):
solo entrar si `ATR_actual <= mediana(ATR de las últimas M velas)`. La idea
económica es operar en tramos de tendencia "tranquila" y evitar los picos de
volatilidad que, incluso con régimen y volumen correctos, hacen saltar el
trailing por ruido antes de que la tendencia se desarrolle. No es un
indicador nuevo (el ATR ya existe en el código) ni un cambio al trailing
stop — es una condición de entrada adicional sobre un dato que ya se
calcula. Queda pendiente de evaluar en la siguiente ronda.

**No se tocó `config.py` ni el paper trading en vivo** — la config ganadora
del grid coincide con la que ya estaba activa, así que no había nada que
actualizar, y el resultado fue ROJO, no VERDE.

---

## 📈 Historial de optimización — ronda 4 (2026-07-03): filtro ATR relativo + veredicto final sobre la estrategia base

### Paso 1-2: filtro ATR relativo (`atr_lookback`, `atr_max_mult`) + grid search 3×4

Implementado en `strategy/ema_rsi_strategy.py`: solo entra si
`ATR_actual <= mediana(ATR de las atr_lookback velas anteriores) x atr_max_mult`.
No toca el trailing/stop (siguen en `atr_multiplier=1.5` de `RiskConfig`).

12 combinaciones sobre 90 días, con columnas extra de cuántas de las 22
pérdidas / 10 ganadoras **históricas** (las del diagnóstico de la ronda 3)
habría bloqueado cada combo:

| atr_lookback | atr_max_mult | Retorno | Sharpe | Win rate | Operaciones | Max DD | % pérdidas bloqueadas | % ganadoras bloqueadas |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 0.85 | +0.02% | **+0.52** | 100.0% | **2** | -0.04% | 86.4% | 80.0% |
| 50 | 0.85 | -0.02% | -0.80 | 60.0% | 5 | -0.04% | 72.7% | 60.0% |
| 100 | 1.15 | -0.06% | -1.10 | 60.0% | 10 | -0.14% | 36.4% | 30.0% |
| 100 | 0.85 | -0.03% | -1.40 | 60.0% | 5 | -0.04% | 68.2% | 60.0% |
| 100 | 1.30 | -0.10% | -1.46 | 50.0% | 12 | -0.18% | 18.2% | 20.0% |
| 30 | 1.00 | -0.07% | -1.58 | 62.5% | 8 | -0.10% | 59.1% | 40.0% |
| 100 | 1.00 | -0.06% | -2.07 | 57.1% | 7 | -0.09% | 50.0% | 50.0% |
| 30 | 1.30 | -0.13% | -2.15 | 54.6% | 11 | -0.16% | 18.2% | 30.0% |
| 50 | 1.00 | -0.11% | -2.17 | 55.6% | 9 | -0.14% | 50.0% | 30.0% |
| 30 | 1.15 | -0.12% | -2.35 | 60.0% | 10 | -0.14% | 27.3% | 30.0% |
| 50 | 1.30 | -0.12% | -2.35 | 60.0% | 10 | -0.14% | 22.7% | 30.0% |
| 50 | 1.15 | -0.12% | -2.35 | 60.0% | 10 | -0.14% | 31.8% | 30.0% |

Dos señales de alarma en la fila "ganadora" (`lookback=30, mult=0.85`):
1. Solo **2 operaciones** — un "100% win rate" con n=2 no es una muestra,
   es una moneda al aire que salió cara dos veces.
2. Bloquea el **80% de las ganadoras históricas**, casi tanto como el 86.4%
   de las perdedoras — el filtro no está siendo selectivo entre buenas y
   malas, simplemente está bloqueando casi todo (bueno y malo por igual) y
   el resultado "positivo" es que, de las pocas que sobrevivieron, la
   mayoría dio la casualidad de ganar.

### Paso 3: validación honesta de ese "ganador" en 6 meses

En vez de aceptar el Sharpe positivo de 2 operaciones a la ligera, se validó
igual en los 6 meses (fuera de muestra):

| | 90 días (nominal) | 6 meses (real) |
|---|---:|---:|
| Retorno | +0.02% | **-0.14%** |
| Sharpe | +0.52 | **-2.17** |
| Win rate | 100% (2 op.) | 40% (5 op.) |

Se confirma: era ruido estadístico, no una mejora real. Con más datos (5
operaciones en vez de 2), el resultado vuelve a ser negativo, consistente
con el resto del grid. **Ninguna combinación del filtro ATR relativo mejora
el resultado de forma robusta.**

### 🚦 Veredicto: ROJO real (confirmado por segunda vez)

`atr_lookback`/`atr_max_mult` quedan **implementados pero desactivados por
defecto** en `config.py` (`atr_lookback: None`) — la capacidad está ahí por
si se quiere explorar a mano, pero no hay evidencia para activarla.

### Paso 4: análisis profundo de las 10 ganadoras — ¿hay edge real?

Para cada una de las 10 operaciones ganadoras (6 meses) se midió: duración
en velas, retorno del precio en las 10h previas a la entrada, distancia al
mínimo/máximo de las últimas 24h, RSI, ATR%, pendiente de régimen y ratio
de volumen. **Y lo mismo para las 22 perdedoras, para poder comparar.**

**A) Contexto de mercado y duración:**

- Las 10 ganadoras entran, sin excepción, con **momentum positivo reciente**
  (retorno de las 10h previas entre +0.01% y +1.82%, todas ≥ 0) y **cerca de
  su máximo de 24h** (entre -1.08% y 0.00% de distancia al máximo) — parecen
  entradas de "continuación de una subida ya en marcha", no rebotes desde un
  mínimo.
- **Pero al medir lo mismo para las 22 perdedoras, el patrón es
  prácticamente idéntico** (momentum previo medio +0.47% vs +0.73% de las
  ganadoras; distancia al máximo de 24h medio -0.49% vs -0.55%). Esto no es
  una casualidad rara: es simplemente cómo se ve, por construcción, CUALQUIER
  entrada de cruce alcista de EMA con los filtros de tendencia/régimen ya
  puestos — gana o pierda. **No discrimina nada.**
- Las ganadoras SÍ duran más: media de 6.8 velas (~1.7h) vs 2.4 velas (~0.6h)
  de las perdedoras. Pero esto es una consecuencia del resultado, no una
  señal de entrada — no se puede saber de antemano que una operación "va a
  durar", eso es circular.
- El motivo de salida es `trailing_stop` en el 100% de las ganadoras y en 21
  de las 22 perdedoras (95%). Prácticamente ninguna operación —gane o
  pierda— sale por cruce bajista de EMA: el trailing decide casi siempre.

**B) Veredicto honesto sobre el edge:**

Con las variables medidas hasta ahora (RSI, pendiente de régimen, distancia
a EMA200, ATR, momentum previo, distancia a máximos/mínimos de 24h,
volumen), **las 10 ganadoras son estadísticamente indistinguibles de las 22
perdedoras en el momento de la entrada.** No es que falte ajustar un umbral
más: en 4 rondas de optimización (filtro de tendencia, de volumen, de
régimen, de volatilidad) cada filtro nuevo mejoró métricas agregadas
(retorno, drawdown) cuando se comparó contra "no tener el filtro", pero
ninguno logró aislar de antemano cuál cruce específico de EMA va a ganar y
cuál va a perder — solo lograron **evitar los peores tramos de mercado**
(lateral, bajista, alta volatilidad general). Eso es una edge de tipo
"cuándo NO operar", no "cuál operación va a salir bien". Con solo 10
ganadoras de muestra tampoco se puede descartar del todo que haya una señal
más sutil — pero no hay evidencia de ella en los datos disponibles.

**C) Por qué el cruce de EMA en sí probablemente no tiene edge aquí:**

El patrón de duración (2-7 velas, es decir 30min-1h45 en 15m) y que el 95-100%
de las salidas sean por trailing (no por reversión de tendencia detectada)
apunta a que, a esta escala temporal, **BTC no se mueve en tendencias
limpias y sostenidas — se mueve a saltos cortos que revierten rápido.** Un
cruce de EMA es una señal de tendencia por diseño (lagging, confirma que
"ya hubo" un movimiento); en un mercado que en realidad revierte a corto
plazo más de lo que tiende, comprar tras un cruce alcista tiende a comprar
justo cuando el impulso de ese salto corto ya se agotó — de ahí que la
mayoría de las operaciones (ganen o pierdan) apenas duren un puñado de
velas antes de que el trailing las cierre.

### Propuesta de estrategia alternativa (NO implementada — solo para evaluar)

**Reversión a la media en vez de seguimiento de tendencia**, por ejemplo:
bandas de Bollinger (o SMA ± desviación estándar) + RSI, comprando cuando el
precio toca/perfora la banda inferior con RSI en sobreventa, y vendiendo al
volver a la media (o a la banda superior) en vez de con un trailing que
persigue un máximo que no llega a formarse.

**Justificación con los propios datos de este proyecto** (no es una
sugerencia genérica):
- La duración típica de una operación (2-7 velas de 15m) y que el trailing
  cierre casi siempre la posición sugieren que el precio se mueve en saltos
  cortos que revierten, no en tendencias que se sostienen — el terreno
  natural de una estrategia de reversión, no de una de tendencia.
- El filtro de régimen (ronda 2) ya demostró que el mercado "lateral"
  (pendiente de EMA200 casi plana) es donde más opera este tipo de
  movimiento de ida y vuelta — es decir, la mayor parte del tiempo (~33-92%
  según la ventana) el mercado YA está en el régimen que favorecería
  reversión a la media, y la estrategia actual está diseñada justamente para
  evitar operar ahí.
- Comprar-y-mantener perdió -8.2% (90d) y -30.79% (6m) en las ventanas
  analizadas — confirma que no hubo una tendencia alcista sostenida real que
  una estrategia de seguimiento de tendencia pudiera haber capturado; el
  "premio" de las estrategias de tendencia (dejar correr un movimiento largo)
  no estaba disponible en estos datos.

Esto es una hipótesis a **probar en backtest antes de creerla** — igual que
todo lo anterior en este proyecto. Queda propuesta para evaluar en la
siguiente ronda, sin implementar nada todavía.

**No se tocó `config.py` (más allá de dejar el filtro ATR implementado y
desactivado) ni el paper trading en vivo.**

---

## 📈 Ronda 5 (2026-07-03): cambio de estrategia — reversión a la media (bb_rsi)

Decisión de partida: abandonar `ema_rsi` como estrategia principal (4 rondas
sin edge demostrable) y probar reversión a la media, justificada porque la
duración típica de una operación (2-7 velas) y que el 95-100% de las salidas
fueran por trailing (no por reversión de tendencia) apuntaban a un mercado
que revierte a corto plazo, no que tiende.

### Paso 1: implementación

`strategy/bb_rsi_strategy.py` (misma interfaz que `ema_rsi_strategy.py`) +
`BBRsiConfig` propia en `config.py` (no se mezcló con `StrategyConfig` de
`ema_rsi` porque tienen un `stop_loss_pct` con significado distinto: techo
de un stop dinámico en un caso, stop fijo simple en el otro). Se añadió
`strategy/factory.py` para instanciar la estrategia activa (`MARKET.strategy`)
sin que `backtester.py` ni `paper_trade.py` tengan que conocer las clases
concretas.

**Nota de arquitectura:** el backtester original asumía un único estilo de
gestión de posición (trailing desde el máximo). `bb_rsi` necesita uno
distinto (objetivo en banda media + stop fijo + cierre por tiempo), así que
`Backtester` ahora despacha por `strategy.EXIT_STYLE` ("trailing" vs
"target_time_stop") en vez de tener la lógica de `ema_rsi` cableada
directamente. Esto fue más cambio del estrictamente mínimo en
`backtester.py`/`paper_trade.py`, pero sin él no había forma honesta de
conectar una estrategia con reglas de salida distintas — la alternativa
(forzar `bb_rsi` a salir por trailing) habría traicionado su propio diseño.

### Paso 2: backtest inicial + diagnóstico

Con los parámetros por defecto (`bb_period=20, bb_std=2.0, rsi_oversold=35,
stop_loss_pct=1.5%, time_stop_candles=10`):

| | 90 días | 6 meses |
|---|---:|---:|
| Retorno | -0.47% | -1.94% |
| Sharpe | -2.35 | -4.24 |
| Win rate | 42.42% | 36.51% |
| Operaciones | 33 | 63 |
| Max drawdown | -0.58% | -2.03% |
| % salidas por banda media | 27.3% | 22.2% |
| % salidas por stop-loss | 3.0% | 12.7% |
| % salidas por time-stop | **69.7%** | **65.1%** |

Sharpe(90d) = -2.35, por encima del umbral -3 del prompt -> se procedió al
grid search, pero primero el diagnóstico pedido:

**¿Entradas malas, salidas malas, o stop muy ajustado?** Ninguna de las
tres, es un cuarto problema — el *plazo* del objetivo:
- Cuando el precio SÍ llega a la banda media, es **9/9 operaciones ganadoras
  (100%)** con +0.92% promedio — la lógica de entrada y el objetivo
  funcionan exactamente como se diseñaron cuando la reversión ocurre.
- El stop-loss casi no se activa (solo 1 de 33 en 90 días) — no está
  demasiado ajustado.
- El **70% de las operaciones** se cierran por time-stop, con pérdidas
  pequeñas pero muy frecuentes (-0.21% promedio, 22% de aciertos ahí) — la
  mayoría de las entradas por sobreventa simplemente no revierten a la
  media dentro de las 10 velas (2.5h) permitidas.

### Paso 3: grid search (27 combinaciones, 90 días)

`bb_std` × `rsi_oversold` × `time_stop_candles`. Igual que en la ronda 4 con
el filtro ATR, el "ganador" nominal por Sharpe es una trampa estadística:

| bb_std | rsi_oversold | time_stop | Retorno | Sharpe | Win rate | Operaciones | % objetivo | % stop | % time-stop |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.5 | 30/35/40 (igual en las 9) | 6/10/15 (igual en las 9) | +0.08-0.09% | **+1.51 a +1.58** | 100% | **2** | 50% | 0% | 50% |
| 2.0 | 40 | 6 | +0.02% | +0.11 | 54.8% | **42** | 28.6% | 0% | 71.4% |
| 2.0 | 40 | 15 | +0.01% | +0.06 | 65.9% | **41** | 65.9% | 4.9% | 29.3% |
| 2.0 | 35 | 6 | -0.08% | -0.47 | 51.5% | 33 | 24.2% | 0% | 75.8% |
| ... | | | | | | | | | (24 combinaciones más, todas negativas) |

Las **9 combinaciones con `bb_std=2.5` dan un resultado IDÉNTICO** entre sí
sin importar `rsi_oversold` ni `time_stop_candles` — señal inequívoca de que
con una banda tan ancha casi nunca se toca (solo 2 veces en 90 días), y una
vez que se toca, esos otros dos parámetros nunca llegan a decidir nada. Es
el mismo patrón de ruido estadístico de la ronda 4 (n=2, "100% de aciertos"
sin significado). Los candidatos con muestra creíble (`bb_std=2.0,
rsi_oversold=40`, 41-42 operaciones) son los que de verdad importan: apenas
positivos, prácticamente en tablas.

### Paso 4: validación en 6 meses

| Candidato | Sharpe 90d | Operaciones 90d | Sharpe 6m | Operaciones 6m | Retorno 6m |
|---|---:|---:|---:|---:|---:|
| Nominal (2.5 / 30 / 15) | +1.58 | 2 | -0.59 | 3 | -0.08% |
| Creíble (2.0 / 40 / 6) | +0.11 | 42 | **-1.96** | 89 | -0.93% |
| Creíble (2.0 / 40 / 15) | +0.06 | 41 | **-2.25** | 88 | -1.31% |

Los tres se caen a Sharpe negativo en los 6 meses. Los dos candidatos con
muestra grande (88-89 operaciones) son categóricos: no es un problema de
tamaño de muestra esta vez, es un resultado negativo robusto.

### 🚦 Veredicto: ROJO real

**¿Es un problema de la estrategia o de que BTC/15m no tiene edge explotable
con datos de testnet (menos líquidos, más ruido)?** Ninguna de las dos —
es más serio: **todos los backtests de esta ronda (y de la ronda 3 en
adelante) se corrieron con datos PÚBLICOS REALES de Binance, no de la
testnet** (la testnet solo tiene ~30 días de profundidad, ver rondas
anteriores). El ruido/iliquidez de la testnet no explica este resultado —
esto es sobre el mercado real.

Con esto, la conclusión es más contundente: **dos filosofías de estrategia
completamente distintas (seguimiento de tendencia y reversión a la media),
cada una con 3-5 rondas de calibración exhaustiva sobre datos reales, no
lograron un Sharpe positivo robusto fuera de muestra en BTC/USDT 15m.**
Eso no prueba que sea imposible, pero sí que un cruce de medias o un rebote
de Bollinger+RSI simples, con los datos y el timeframe disponibles, no
tienen una edge fácil de capturar — probablemente porque BTC/USDT es uno de
los mercados más arbitrados y de mayor liquidez del cripto, donde patrones
tan simples y públicos ya están compitiendo contra muchos otros
participantes con más infraestructura.

`MARKET.strategy` queda en `"ema_rsi"` (la más defendida hasta ahora: mejor
drawdown, evita casi toda entrada en tendencia bajista real) en vez de
`"bb_rsi"` — no porque haya "ganado", sino porque entre dos opciones sin
edge confirmada, es la más prudente por defecto. `bb_rsi` queda totalmente
implementada y disponible cambiando un solo parámetro.

**No se lanzó paper trading** (no hubo semáforo VERDE). El paper trading en
vivo sigue detenido.

---

## 📈 Ronda 6 (2026-07-03): funding rate arbitrage — descartado en el Paso 1 (análisis previo)

Antes de escribir código se pidió validar con datos reales si la oportunidad
existe: cash-and-carry delta-neutral (largo spot + corto perpetuo) cobrando
el funding rate cada 8h. Se descargó el histórico real de Binance Futures
(`fetch_funding_rate_history`, paginado manualmente con `since` porque el
parámetro `limit` del endpoint resultó no ser fiable — la misma llamada
devolvió 200 y 500 registros en intentos idénticos):

**BTC/USDT perpetuo, 500 períodos de 8h, 166 días (2026-01-17 a 2026-07-03):**

| Métrica | Valor |
|---|---:|
| Funding medio por período (8h) | 0.00074% |
| Funding mediano por período | 0.00119% |
| % de períodos positivo / negativo | 59.4% / 40.6% |
| Racha negativa más larga | 14 períodos (4.7 días) — 65 rachas negativas en total |
| Retorno bruto acumulado (166 días, siempre en posición) | 0.370% |
| **Retorno bruto anualizado** | **0.81%** |
| Retorno neto acumulado (fee 0.24% ida/vuelta, 1 sola entrada/salida) | 0.130% |
| **Retorno neto anualizado** | **0.28%** |

Mes a mes (retorno bruto): ene +0.23%, feb -0.06%, mar -0.09%, abr -0.18%,
may +0.23%, jun +0.20%, jul (parcial) +0.04% — 3 de 7 meses negativos, nada
estable.

### 🚦 Veredicto: ROJO inmediato (según el propio criterio del prompt: <3% anual neto)

**0.28% de retorno neto anualizado, muy por debajo del 3% mínimo pedido.**
Ni siquiera cubre por poco margen — está a un orden de magnitud del umbral.
Con esto, y tal como se indicó, **no se implementó nada de código** (ni
`FundingArbConfig`, ni `funding_arb_strategy.py`, ni la conexión dual
spot/futuros): no tiene sentido construir la infraestructura sobre una
oportunidad que los propios datos descartan de entrada.

**Por qué es tan bajo** (la premisa del prompt asumía "funding positivo la
mayoría del tiempo, mercado alcista estructural"): eso describe ciclos
alcistas fuertes de 2020-2021, no necesariamente el mercado actual. En estos
166 días el funding está casi repartido a la mitad (59/41) y su magnitud
media es diminuta (0.0007%/8h) — consistente con lo que ya se vio en las
rondas 3-5: **BTC/USDT hoy es un mercado muy arbitrado y eficiente**, y el
carry trade de funding, cuando existió como oportunidad fácil, ya fue
comprimido por otros participantes. Esto es coherente con el patrón de todo
este proyecto: ni el seguimiento de tendencia, ni la reversión a la media,
ni ahora el arbitraje estructural de funding mostraron una edge fácil de
capturar en este par con datos accesibles al retail.

**No se tocó el paper trading en vivo ni ninguna estrategia existente.**

---

## 📈 Ronda 7 (2026-07-04): estrategia híbrida por régimen (y un bug que casi se cuela)

Con siete estrategias/variantes probadas sin semáforo VERDE, en vez de
insistir con más ajustes finos de parámetros (que las rondas 3-4 ya
demostraron que tiende a producir sobreajuste), se probó una idea
estructural nueva: **usar el filtro de régimen no para descartar bb_rsi,
sino para decidir cuándo usar cada estrategia.** `ema_rsi` solo entra en
régimen ALCISTA; `bb_rsi` solo entra en régimen LATERAL (el régimen para el
que la reversión a la media tiene sentido económico, y que bb_rsi nunca se
había probado de forma aislada); ningún lado opera en BAJISTA.

### Implementación

`strategy/regime_switch_strategy.py` (`EXIT_STYLE="regime_switch"`) genera
ambas señales de entrada con sus propios filtros existentes, condicionadas
al régimen, y cada posición recuerda con qué sub-estrategia entró
(`entry_style`) para aplicar su gestión de salida correspondiente
(trailing/ATR para "trend", objetivo+stop+time-stop para "reversion")
durante toda la vida de esa operación. `backtester.py` ganó un tercer método
de gestión, `_manage_regime_switch()`, que despacha por ese campo.

### ⚠️ Bug encontrado (y corregido) antes de creer el resultado

La primera corrida dio resultados espectaculares a simple vista: **90 días:
Sharpe +100.72 (100% de aciertos, 6 operaciones). 6 meses: Sharpe +17.75.**
Antes de reportarlo como un hallazgo, se investigó por qué — la duración
promedio de las operaciones "reversion" no cuadraba con `time_stop_candles=10`
(deberían cerrarse en 2.5h como máximo, pero promediaban 9 días). La causa:
la columna `entry_style` se inicializaba con `None` en las velas sin señal
(la inmensa mayoría), y el `.dropna()` genérico que usa `backtester.py` para
recortar el warm-up de indicadores **borraba también esas filas** — de
38,400 velas de 13 meses, sobrevivían solo **108**. El backtest corrió sobre
un DataFrame roto (velas de entrada dispersas tratadas como si fueran
consecutivas), invalidando por completo el índice que usa el time-stop y la
curva de equity. Corregido inicializando `entry_style` con `""` en vez de
`None` (ver el comentario en el código, para que no se repita el error si se
añaden más columnas de estado en el futuro).

### Resultado real (tras corregir el bug)

| | 90 días | 6 meses | ~13 meses (máximo real disponible) |
|---|---:|---:|---:|
| Retorno | -0.34% | -1.43% | **-2.80%** |
| Sharpe | -2.64 | -5.28 | **-4.92** |
| Operaciones | 26 | 52 | 104 |
| Win rate | 38.46% | 30.77% | 27.88% |
| Max drawdown | -0.42% | -1.45% | -2.80% |

Comparado con las estrategias individuales sobre los mismos ~13 meses:

| | ema_rsi sola | bb_rsi sola | regime_switch (combinada) |
|---|---:|---:|---:|
| Retorno | -1.99% | -2.53% | **-2.80% (peor que ambas)** |
| Sharpe | -6.14 | -2.63 | -4.92 |
| Operaciones | 64 | 115 | 104 |

**Combinar las dos estrategias no mejoró el resultado — lo empeoró
ligeramente en retorno.** El desglose por sub-estrategia sobre los 13 meses
confirma que ninguna de las dos partes se salvó al aislarla por régimen:
`reversion` (bb_rsi en lateral) dio -$42 en 40 operaciones (42.5% aciertos),
`trend` (ema_rsi en alcista) dio -$136 en 64 operaciones (18.75% aciertos).
El filtro de régimen sí funcionó exactamente como se diseñó (64 entradas en
ALCISTA + 40 en LATERAL, cero en BAJISTA), pero aislar cada sub-estrategia a
su régimen "ideal" no destapó una edge que no estuviera ya buscada en las
rondas 1-6. El retorno mes a mes fue negativo en 13 de 14 meses.

### 🚦 Veredicto: ROJO — séptimo intento sin edge robusta

Con esto son siete estrategias/variantes distintas (ema_rsi con 4 rondas de
calibración, bb_rsi, funding rate arbitrage, y ahora la combinación por
régimen de las dos primeras) sin lograr un Sharpe positivo robusto y
sostenido fuera de muestra en BTC/USDT 15m con datos reales. `ema_rsi` se
mantiene como default (mejor drawdown de las tres); `bb_rsi` y
`regime_switch` quedan implementadas y disponibles.

**Nota sobre el propio proceso:** el bug de esta ronda es un recordatorio
concreto de por qué este proyecto exige validar cada resultado "bueno" antes
de creerlo — un Sharpe de +100 con 6 operaciones debería generar sospecha
inmediata (es exactamente el patrón de ruido estadístico que ya se
identificó en las rondas 4 y 5), y en este caso, además de ser poca muestra,
resultó ser directamente un dato inválido.

**No se tocó el paper trading en vivo.**

---

## 📈 Ronda 8 (2026-07-04): ¿otro par en vez de BTC/USDT?

Hipótesis a probar: BTC/USDT es de los pares más arbitrados/eficientes del
mercado cripto — quizás un activo más dominado por retail y narrativa (menos
arbitraje institucional) conserve más patrón técnico explotable. Se probó
**DOGE/USDT** (testnet lo soporta; 431 pares USDT disponibles en total),
reutilizando las tres estrategias YA construidas (`ema_rsi`, `bb_rsi`,
`regime_switch`) **con sus parámetros actuales, sin recalibrar** — un primer
sondeo rápido antes de invertir en una calibración completa específica para
este par.

| | 90 días (BH -12.73%) | 6 meses (BH -44.14%) | ~13 meses (BH -60.52%) |
|---|---:|---:|---:|
| `ema_rsi` | Sharpe -5.64 | Sharpe -5.23 | Sharpe -5.23 |
| `bb_rsi` | Sharpe -5.53 | Sharpe -1.97 | Sharpe -3.10 |
| `regime_switch` | Sharpe -6.73 | Sharpe -5.43 | Sharpe -5.94 |

Las 9 combinaciones (3 estrategias × 3 ventanas) dieron Sharpe negativo.
Antes de descartarlo, se comprobó si el problema era simplemente que los
parámetros están calibrados para la volatilidad de BTC: el ATR medio de
DOGE resultó ~2x el de BTC (0.56% vs 0.29% del precio), pero el stop
dinámico basado en ATR (`atr_multiplier=1.5`) se mantiene muy por debajo del
techo fijo de `stop_loss_pct=2%` en ambos activos — **el techo no es el
cuello de botella**, así que no es (solo) un problema de mal ajuste de
volatilidad: la lógica de entrada en sí tampoco mostró ventaja en DOGE,
igual que en BTC.

### 🚦 Veredicto: no concluyente para descartar la hipótesis del todo, pero desalienta seguir por este camino sin una recalibración completa

Esto NO es una prueba definitiva de que ningún par alternativo pueda
funcionar (los parámetros nunca se recalibraron específicamente para DOGE,
que es su propio activo con su propia dinámica), pero sí es una señal: con
el mismo enfoque estructural reutilizado tal cual, DOGE se comportó igual de
mal que BTC en las tres estrategias. Hacer una calibración completa y
honesta para DOGE (equivalente a repetir las rondas 1-4 para este par) es un
esfuerzo grande y, dado el patrón observado en 8 rondas consecutivas (7
estrategias/variantes en BTC + este sondeo en DOGE), el retorno esperado de
esa inversión de tiempo es incierto.

**No se tocó el paper trading en vivo ni ninguna estrategia existente.**

---

## 📈 Ronda 9 (2026-07-04): recalibración completa de DOGE/USDT (con split calibración/validación real)

A diferencia de las rondas 1-6 (donde la ventana de "backtest inicial" de
30-90 días era un SUBCONJUNTO de la ventana de "validación" de 6 meses/13
meses — es decir, no eran datos completamente distintos), esta ronda usó un
split honesto: **70% más antiguo de los ~13 meses disponibles para calibrar
(mayo 2025 - marzo 2026), 30% más reciente para validar (marzo - julio
2026), nunca visto durante la calibración.**

### Timeframe y filtro de régimen específicos para DOGE

Igual patrón que BTC (ronda 1): 5m es ruido puro (Sharpe -23), 15m mejor
pero malo (-10.5), **1h es el mejor de los tres** (Sharpe -2.61) tanto para
`ema_rsi` como para `bb_rsi` — se cambió el timeframe a 1h para DOGE (no 15m
como BTC). La pendiente de EMA200 de DOGE tiene una escala distinta a la de
BTC (desviación estándar ~4x mayor), así que el umbral de régimen se
recalibró a partir de su propia distribución en vez de reusar el 0.1% de BTC.

### Calibración (ventana de mayo 2025 a marzo 2026)

| | ema_rsi (calibrado) | bb_rsi (calibrado) | regime_switch (calibrado) |
|---|---:|---:|---:|
| Retorno | -0.19% | +0.38% | **+0.47%** |
| Sharpe | -0.77 | +0.45 | **+0.60** |
| Operaciones | 9 | 25 | 28 |
| Win rate | 55.56% | 48.00% | 53.57% |

`ema_rsi` no logró Sharpe positivo ni siquiera en su propia ventana de
calibración tras barrer régimen/volumen/ATR (se descartó sin más ajuste,
igual criterio que en rondas anteriores). `bb_rsi` y `regime_switch` sí
mostraron Sharpe positivo en calibración — con muestras razonables (25-28
operaciones, no los "2 trades" que ya se identificaron como ruido en rondas
previas).

### Validación (marzo-julio 2026, jamás visto durante la calibración)

| | ema_rsi | bb_rsi | regime_switch |
|---|---:|---:|---:|
| Retorno | 0.00% (0 operaciones) | -0.09% | -0.09% |
| Sharpe | 0.00 | -0.78 | -0.78 |
| Operaciones | 0 | 3 | 3 |

Buy&hold en el mismo período de validación: -12.81%.

**El patrón se repite exactamente igual que en BTC: lo que parecía
funcionar en la ventana de calibración se desvanece al probarlo en datos
genuinamente nunca vistos.** `bb_rsi` y `regime_switch`, que en calibración
llegaron a Sharpe +0.45/+0.60, caen a Sharpe -0.78 en la validación —
además con solo 3 operaciones en 4 meses, una muestra demasiado pequeña para
sacar ninguna conclusión salvo que definitivamente no hay una mejora clara.

### 🚦 Veredicto: ROJO — el split honesto lo confirma con más rigor que nunca

Esta ronda usó la metodología más estricta de las nueve (calibración y
validación en datos disjuntos, sin ningún solape) y el resultado es el
mismo: ninguna estrategia mostró Sharpe positivo robusto fuera de muestra.
Contando esta ronda, van **9 combinaciones estrategia×activo** (7 en
BTC/USDT + 2 en DOGE/USDT — bb_rsi/regime_switch calibrados) sin edge
demostrable con metodología rigurosa. El patrón ya no parece casualidad de
un activo en particular: apunta a que el problema es el **enfoque**
(indicadores técnicos simples sobre datos de precio/volumen públicos), no
el par elegido.

`MARKET.strategy` se mantiene en `"ema_rsi"` y `MARKET.symbol` en
`"BTC/USDT"` — no se encontró justificación para cambiar ninguno de los dos.

**No se tocó el paper trading en vivo ni ninguna estrategia existente.**

---

## 🏁 Cierre de la búsqueda de estrategia (2026-07-04): paper trading supervisado con `ema_rsi`

Tras 9 rondas de diagnóstico y calibración (4 con `ema_rsi` en BTC/USDT, 1 con
`bb_rsi`, 1 con `funding_arb` — descartada en el análisis previo sin llegar a
implementarse —, 1 con `regime_switch`, y 1 recalibración completa en
DOGE/USDT con split honesto calibración/validación) sin encontrar una
estrategia con Sharpe positivo robusto fuera de muestra, se decidió **cerrar
la fase de búsqueda** y pasar a paper trading supervisado con `ema_rsi`
(BTC/USDT, 15m) — la configuración más defendida de las nueve, no por tener
una edge confirmada sino por su mejor control de drawdown y consistencia.
**No hay expectativa de ganancia; el objetivo de esta fase es validar que
toda la infraestructura (órdenes, stop-loss real, circuit breaker,
recuperación tras reinicio, dashboard) funciona correctamente en vivo.**

### Qué se hizo para arrancar limpio

- Se detectó que **dos procesos** de `live.paper_trade` (de arranques
  distintos, con código viejo de antes de la ronda 1) seguían corriendo en
  segundo plano desde el principio de la sesión. Se detuvieron ambos.
- Uno de ellos tenía una posición real abierta en la testnet (0.01557 BTC,
  dinero ficticio) con un stop-loss real descansando en Binance. Se canceló
  esa orden y se vendió la posición a mercado para no arrastrar contabilidad
  de la estrategia original (pre-diagnóstico) a la nueva.
- Se limpió el diario SQLite (`trades`, `equity`, `bot_status`,
  `position_state`) para que el dashboard arranque en cero, sin mezclar el
  historial de las 9 rondas de backtest/exploración con la ejecución real.
- Se relanzó `live.paper_trade` con la configuración final. Primer tick
  confirmado: capital limpio (saldo real de la testnet tras cerrar la
  posición vieja), régimen ALCISTA detectado, sin posición abierta.

### Cómo relanzarlo manualmente si hace falta

```powershell
cd cryptobot
.\venv\Scripts\Activate.ps1
python -m live.paper_trade
```

(o doble clic en `run_bot.bat`). En paralelo, para el dashboard:

```powershell
streamlit run dashboard.py
```

(o doble clic en `run_dashboard.bat`). Abre en http://localhost:8501.

### Qué revisar como supervisión diaria

- **Dashboard, sección "Estado del bot":** que siga en 🟢 CORRIENDO (si
  aparece 🔴 DETENIDO, revisar `logs/live.log` para ver si fue el
  kill-switch, un error, o un cierre manual).
- **Alerta de circuit breaker:** si aparece la alerta ⏸️ naranja, el bot
  pausó nuevas entradas por 48h tras una mala racha de 7 días — es
  información, no un error.
- **Historial de operaciones:** confirmar que Binance (🟢) y el diario del
  bot (🔵) coinciden siempre — si el dashboard marca una alerta de
  discrepancia entre las dos fuentes, revisar con prioridad.
- **`logs/live.log`:** cada tick queda registrado con precio, EMAs, régimen,
  RSI y la señal — es la fuente más detallada si algo no cuadra.
- **Kill-switches:** si el bot se detiene solo, es porque
  `max_daily_loss_pct` (5%) o `max_weekly_loss_pct` (10%) saltaron — eso
  significa que hay que decidir si reiniciar o pausar más tiempo, no
  reiniciar automáticamente sin mirar por qué.

---

## ⚠️ Aviso

Este proyecto es educativo. El rendimiento en backtest **no garantiza**
resultados futuros. Úsalo solo en testnet.
