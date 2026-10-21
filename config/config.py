"""
config/config.py
================
Punto único de configuración del bot. TODO lo que quieras ajustar
(par, timeframe, periodos de indicadores, gestión de riesgo) vive aquí,
no disperso por el código.

- Las CLAVES de API se leen del archivo .env (nunca se escriben aquí).
- Los PARÁMETROS de estrategia/riesgo son dataclasses fáciles de editar.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Carga el .env que está en la raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# ----------------------------------------------------------------------
# 1) Credenciales y modo (se leen del entorno / .env)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class ExchangeConfig:
    api_key: str = os.getenv("BINANCE_TESTNET_API_KEY", "")
    api_secret: str = os.getenv("BINANCE_TESTNET_API_SECRET", "")
    mode: str = os.getenv("TRADING_MODE", "testnet").lower()  # "testnet" | "live"

    @property
    def is_testnet(self) -> bool:
        return self.mode != "live"


# ----------------------------------------------------------------------
# 2) Mercado a operar
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class MarketConfig:
    symbol: str = "BTC/USDT"   # par (formato ccxt: BASE/QUOTE)
    # 15m elegido tras comparar 5m/15m/1h en backtest (ver README, sección
    # "Timeframe"): 5m es puro ruido y 1h deja muestra insuficiente (5
    # operaciones en 30 días). 1m, 5m, 15m, 1h, 4h, 1d ...
    timeframe: str = "15m"
    # Cuántas VELAS pedir como historial para el backtest (no es tiempo fijo:
    # el rango real = history_limit * timeframe). La testnet de Binance solo
    # conserva ~30 días de histórico real independientemente de este número.
    history_limit: int = 24 * 365 * 2

    # --- Selector de estrategia ---
    # "ema_rsi"      : cruce de EMAs + filtros (seguimiento de tendencia).
    # "bb_rsi"       : reversión a la media con Bandas de Bollinger + RSI.
    # "regime_switch": combina las dos anteriores usando el propio filtro de
    #                  régimen — ema_rsi en régimen ALCISTA, bb_rsi en
    #                  régimen LATERAL, nada en BAJISTA (ronda 7).
    # Ninguna de las tres alcanzó semáforo VERDE (ver README). "regime_switch"
    # en particular dio -2.80% / Sharpe -4.92 en ~13 meses reales: PEOR que
    # ema_rsi sola (-1.99%) y que bb_rsi sola (-2.53%) en retorno — combinar
    # las dos estrategias no mejoró el resultado, lo empeoró ligeramente.
    # Se deja "ema_rsi" como default por ser la más defendida en drawdown;
    # las otras dos quedan implementadas y disponibles para seguir explorando.
    strategy: str = "ema_rsi"


# ----------------------------------------------------------------------
# 3) Parámetros de la estrategia (EMA cross + filtro RSI)
#    Cambia estos números para "tunear" la estrategia sin tocar la lógica.
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class StrategyConfig:
    ema_fast: int = 9          # EMA rápida
    ema_slow: int = 21         # EMA lenta
    rsi_period: int = 14       # periodo del RSI
    rsi_lower: float = 50.0    # solo COMPRAR si RSI > rsi_lower (hay momentum)
    rsi_upper: float = 70.0    # evitar comprar si RSI > rsi_upper (sobrecompra)

    # --- Filtro de tendencia de fondo ---
    # Solo se permite ENTRAR si el precio de cierre está por encima de esta EMA
    # (en el mismo timeframe). Evita comprar cruces alcistas dentro de un
    # mercado lateral o bajista de fondo. Para desactivarlo, poner en None.
    ema_trend: int | None = 200

    # --- Filtro de volumen ---
    # Solo se permite ENTRAR si el volumen de la vela de señal es >= vol_mult
    # veces el volumen promedio de las vol_window velas ANTERIORES (sin mirar
    # la propia vela de señal, para no hacer lookahead). Evita cruces de EMA
    # sin fuerza real detrás. Para desactivarlo, poner vol_mult en None.
    vol_window: int = 20
    vol_mult: float | None = 1.2

    # --- Filtro de régimen de mercado (pendiente de la EMA de tendencia) ---
    # slope = (ema_trend_actual - ema_trend_hace_N_velas) / ema_trend_hace_N_velas
    # Solo se permite ENTRAR si slope > regime_slope_threshold (régimen
    # ALCISTA confirmado). Si ya hay una posición abierta y el régimen deja
    # de ser alcista (slope <= threshold, sea plano o bajista), se CIERRA de
    # inmediato aunque no haya cruce bajista de EMAs ni se haya tocado el
    # stop. Diagnóstico (ver README): en 90 días reales el régimen "lateral"
    # (slope entre -0.1% y +0.1%) concentró casi toda la pérdida (-$26 de
    # -$33 totales) mientras que "alcista" estaba casi en equilibrio y
    # "bajista" ya quedaba evitado por el filtro ema_trend. Requiere
    # ema_trend activo. Para desactivarlo, poner regime_lookback en None.
    regime_lookback: int | None = 20
    regime_slope_threshold: float = 0.001

    # --- ATR (volatilidad), para el stop-loss/trailing dinámicos de RiskConfig ---
    atr_period: int = 14

    # --- Filtro de ATR relativo (volatilidad "anormal" en el momento de entrar) ---
    # Solo se permite ENTRAR si ATR_actual <= mediana(ATR de las atr_lookback
    # velas ANTERIORES) * atr_max_mult. Hipótesis (ver README): 21 de 22
    # pérdidas salían por trailing_stop, y las ganadoras entraban con ATR más
    # bajo (0.299% del precio) que las perdedoras (0.349%). PROBADO por grid
    # search (12 combos, 90 días + validación en 6 meses): ninguna combinación
    # con tamaño de muestra razonable mejora el Sharaje/retorno; la única
    # celda con Sharpe>0 en 90d (2 operaciones, 100% win rate) resultó ruido
    # estadístico -> Sharpe -2.17 al validarla en 6 meses. La diferencia de
    # ATR entre ganadoras/perdedoras no era una relación causal explotable,
    # solo una correlación débil en una muestra de 32 operaciones. Queda
    # implementado (por si se quiere explorar a mano) pero DESACTIVADO por
    # defecto: no demostró mejorar el resultado de forma robusta.
    atr_lookback: int | None = None
    atr_max_mult: float = 1.0

    # --- Confirmación de entrada con doble vela ---
    # Si es True, la entrada NO se toma en la misma vela del cruce alcista:
    # se espera una vela más y solo se entra si el cierre de esa vela
    # siguiente sigue por encima de ema_fast (confirma que el cruce no fue
    # una mecha temporal que se revierte enseguida).
    # Probado en backtest (ver README) y dejado en False: con el resto de
    # filtros (volumen + régimen) ya tan selectivos, ninguna de las 13
    # señales de los 90 días era una mecha falsa -> la confirmación solo
    # retrasaba la entrada a un peor precio, empeorando el resultado
    # (-0.10% -> -0.32%, win rate 53.85% -> 30.77%).
    confirm_candle: bool = False


# ----------------------------------------------------------------------
# 3b) Parámetros de la estrategia alternativa: reversión a la media
#     (Bandas de Bollinger + RSI). Config separada de StrategyConfig a
#     propósito: son parámetros de una estrategia distinta (con su propio
#     `stop_loss_pct`, que aquí es un stop fijo simple, NO el mismo concepto
#     que RiskConfig.stop_loss_pct que actúa como techo del stop dinámico de
#     ema_rsi) — mezclarlos en una sola clase habría sido confuso.
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class BBRsiConfig:
    bb_period: int = 20         # período de la media móvil de Bollinger
    bb_std: float = 2.0         # nº de desviaciones estándar para las bandas
    rsi_period: int = 14
    rsi_oversold: int = 35      # solo COMPRAR si RSI < rsi_oversold (sobreventa real)
    stop_loss_pct: float = 0.015    # stop fijo simple desde la entrada (1.5%)
    time_stop_candles: int = 10     # cierre forzado si no llegó a la banda media en N velas


# ----------------------------------------------------------------------
# 4) Gestión de riesgo y capital
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class RiskConfig:
    initial_capital: float = 10_000.0   # capital inicial (solo para backtest)
    position_size_pct: float = 0.10     # % del capital por operación (10%)
    stop_loss_pct: float = 0.02         # stop-loss FIJO 2%: TECHO máximo de riesgo (ver atr_multiplier)
    fee_pct: float = 0.001              # comisión estimada por lado (0.1% taker)

    # --- Trailing stop (reemplaza al take-profit fijo) ---
    # Una vez abierta la posición se registra el precio máximo alcanzado
    # ("peak"). El stop efectivo es max(stop fijo, peak - distancia_trailing):
    # nunca es más laxo que el stop fijo, pero sube a medida que sube el
    # precio, dejando correr la ganancia en vez de cortarla en un TP fijo.
    # Para desactivarlo (volver a un TP fijo clásico), poner en None.
    # Se usa como % SOLO si atr_multiplier está desactivado (ver abajo).
    # 1.5% elegido tras comparar 1.5/2/3% en backtest (ver README): fue el
    # que mejor retorno y Sharpe dio en este mercado de rango estrecho.
    trail_pct: float | None = 0.015

    # --- Stop-loss / trailing DINÁMICOS por volatilidad (ATR) ---
    # Si atr_multiplier no es None, sustituye tanto el stop inicial como el
    # trailing por distancias basadas en el ATR del momento (en vez de un %
    # fijo): distancia = atr_multiplier * ATR. Con poca volatilidad el stop
    # queda más ajustado que un % fijo; con mucha, más amplio (evita que te
    # saquen antes de que la operación madure). stop_loss_pct sigue actuando
    # como TECHO: el stop inicial nunca arriesga más que ese % pase lo que
    # pase, aunque el ATR sea muy amplio. Para desactivarlo y volver al
    # stop/trailing en % fijo, poner en None.
    atr_multiplier: float | None = 1.5

    # --- Cooldown entre operaciones ---
    # Tras CERRAR una posición, el bot ignora nuevas señales de entrada
    # durante este número de velas. Evita "entrar - perder - re-entrar" en
    # el mismo tramo bajista. 0 = desactivado.
    cooldown_candles: int = 3

    # --- Stop-loss REAL en el exchange (no solo lógica interna) ---
    use_exchange_stop: bool = True      # coloca una orden STOP_LOSS_LIMIT que queda en Binance
    stop_limit_buffer_pct: float = 0.005  # el precio límite se pone 0.5% por debajo del stop

    # --- Kill-switch: detiene el bot POR COMPLETO si la pérdida supera estos límites ---
    max_daily_loss_pct: float = 0.05    # -5% en el día -> cierra y detiene
    max_weekly_loss_pct: float = 0.10   # -10% en la semana -> cierra y detiene

    # --- Circuit breaker semanal: PAUSA temporal, no detiene el bot ---
    # Si el retorno de los últimos 7 días CORRIDOS (no de calendario, como el
    # kill-switch de arriba) cae por debajo de este umbral, el bot deja de
    # abrir posiciones nuevas durante `breaker_pause_hours` y vuelve a
    # evaluar. Una posición ya abierta NO se cierra por esto (para eso está
    # el kill-switch); solo se bloquean entradas nuevas. Es la primera pieza
    # del "circuito de freno" del diagnóstico original: reaccionar a una
    # mala racha reciente antes de que escale a la pérdida semanal completa.
    weekly_loss_limit: float = -0.03    # -3% en 7 días corridos -> pausa
    breaker_pause_hours: float = 48.0


# ----------------------------------------------------------------------
# Instancias listas para importar:  from config.config import STRATEGY, RISK ...
# ----------------------------------------------------------------------
EXCHANGE = ExchangeConfig()
MARKET = MarketConfig()
STRATEGY = StrategyConfig()
BB_STRATEGY = BBRsiConfig()
RISK = RiskConfig()
