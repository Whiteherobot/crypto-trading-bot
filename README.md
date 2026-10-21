# Bot de trading algorítmico para Binance (testnet)

Bot de trading de criptomonedas en Python que corre contra la **testnet de Binance Spot**, con
dinero ficticio: está bloqueado para producción a propósito. Incluye un motor de backtest,
paper trading en vivo con órdenes reales en la testnet, un dashboard de control y un diario en
SQLite que cruza lo que registra el bot con lo que reporta Binance.

## Qué hay adentro

| Carpeta | Qué hace |
|---|---|
| `strategy/` | Tres estrategias intercambiables desde la configuración (`factory.py`): `ema_rsi` (cruce de EMAs con filtros de RSI, volumen, régimen y volatilidad), `bb_rsi` (reversión a la media con Bandas de Bollinger y RSI) y `regime_switch` (usa una u otra según el régimen del mercado) |
| `backtest/` | Backtest vela a vela con comisiones, stop-loss y trailing, y las métricas: retorno, win rate, drawdown máximo y Sharpe anualizado |
| `live/paper_trade.py` | Operación en vivo: stop-loss real en el exchange, recuperación de la posición tras un reinicio y reconciliación con el saldo |
| `dashboard.py` | Panel en Streamlit: precio con las operaciones, curva de capital, estado del bot y alertas |
| `config/config.py` | Toda la configuración: par, timeframe, indicadores y riesgo |

**Gestión de riesgo:** un 10 % del capital por operación, stop inicial y trailing dinámicos con
ATR (con un techo del 2 %), una pausa de 48 h si los últimos 7 días salen mal, y frenos que
detienen el bot si la pérdida llega al 5 % en un día o al 10 % en la semana.

## Resultados

Backtest sobre BTC/USDT con velas de 15 minutos, alrededor de 13 meses de datos reales
(comisión del 0,1 % por lado):

| Estrategia | Retorno | Sharpe | Operaciones |
|---|---:|---:|---:|
| `ema_rsi` | -1,99 % | -6,14 | 64 |
| `bb_rsi` | -2,53 % | -2,63 | 115 |
| `regime_switch` | -2,80 % | -4,92 | 104 |

**Ninguna estrategia le gana al mercado de forma robusta.** Llegué a eso después de nueve rondas
de optimización: filtros de tendencia, de volumen y de volatilidad, un grid search, otra
estrategia, un análisis de arbitraje de *funding rate* y otro par (DOGE/USDT). Cada ronda se
validó en períodos que no se habían usado para ajustar los parámetros, para no confundir el
sobreajuste con una ventaja real. El detalle, con las tablas y los veredictos de cada ronda,
está en [`docs/historial-optimizacion.md`](docs/historial-optimizacion.md).

Por eso el bot quedó en paper trading supervisado con `ema_rsi`, la configuración con mejor
control del drawdown, para validar la infraestructura (órdenes, stops, reinicios y el
dashboard) y no para ganar dinero.

## Uso

Requiere Python 3.10 a 3.13 y claves de la [testnet de Binance](https://testnet.binance.vision/).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # completar las claves de la testnet
python -m backtest.run_backtest      # métricas y curva de capital en backtest/output/
python -m live.paper_trade           # paper trading en vivo
streamlit run dashboard.py           # panel de control
```

En Windows están `setup.bat`, `run_bot.bat` y `run_dashboard.bat`. La testnet solo conserva
unas semanas de velas, así que un backtest largo necesita el histórico público de Binance.

## Aviso

Es un proyecto educativo. Un resultado de backtest no garantiza resultados futuros, y el código
no está pensado para operar con dinero real.

## Licencia

MIT. Ver [LICENSE](LICENSE).
