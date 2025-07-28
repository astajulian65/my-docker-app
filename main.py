from binance.client import Client
import pandas as pd
import pandas_ta as ta
from datetime import datetime
import time

# ------------------- API KEYS -------------------
API_KEY = "22jj7Y6jJoBdWA64qzlxoFlfAM2b6UIf7Kva3VbNFNn0VWVvWTQRVb5sKLlunjLv"
API_SECRET = "wHcp9Gke2YzzEFIIBMzY86aSgCADroGIgf2muBAOwe49VfUCyogHYoaulnMv0AWK"
client = Client(API_KEY, API_SECRET)

# ------------------- CONFIG -------------------
SYMBOL = "XRPUSDT"
ENTRY_INTERVAL = "1m"
TREND_INTERVAL = "15m"
ENTRY_LIMIT = 54000      # 1m candles (~37.5 days)
TREND_LIMIT = 18000      # 15m candles (~6 months)

EMA_SHORT = 3
EMA_LONG = 18

STOP_LOSS_BUFFER = 0.02
RISK_REWARD_RATIO = 2.0
MIN_GAP_PERCENT = 0.03


# ------------------- FETCH CANDLES -------------------
def fetch_klines(symbol, interval, total_limit):
    print(f"📥 Fetching {total_limit}x{interval} candles from Binance...")
    all_klines = []
    end_time = None

    while len(all_klines) < total_limit:
        limit = min(1000, total_limit - len(all_klines))
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit, endTime=end_time)
        if not klines:
            break
        all_klines.extend(klines)
        end_time = klines[0][0] - 1  # Go backward
        time.sleep(0.2)

    df = pd.DataFrame(all_klines, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_qav', 'ignore'
    ])
    df['time'] = pd.to_datetime(df['open_time'], unit='ms')
    df['close'] = pd.to_numeric(df['close'])
    df = df.sort_values('time').reset_index(drop=True)
    print(f"✅ Pulled {len(df)} candles for {symbol}")
    return df[['time', 'close']]


# ------------------- EMA -------------------
def apply_ema(df):
    df["EMA_SHORT"] = ta.ema(df["close"], length=EMA_SHORT)
    df["EMA_LONG"] = ta.ema(df["close"], length=EMA_LONG)
    return df


# ------------------- BACKTEST -------------------
def backtest(df_entry, df_trend):
    wins = losses = total = 0
    active_trade = None
    prev_cross = None
    waiting_for_cross = None

    df_entry = apply_ema(df_entry.copy())
    df_trend = apply_ema(df_trend.copy())

    for i in range(max(EMA_LONG, 2), len(df_entry)):
        row = df_entry.iloc[i]
        price = row['close']
        time_now = row['time']
        ema_s, ema_l = row["EMA_SHORT"], row["EMA_LONG"]
        cross = "buy" if ema_s > ema_l else "sell" if ema_s < ema_l else None

        if active_trade:
            typ, entry, slp, tp = active_trade.values()
            if (typ == "buy" and price <= slp) or (typ == "sell" and price >= slp):
                print(f"[{time_now}] 🛑 SL hit {typ.upper()} @ {price}")
                losses += 1
                total += 1
                active_trade = None
            elif (typ == "buy" and price >= tp) or (typ == "sell" and price <= tp):
                print(f"[{time_now}] ✅ TP hit {typ.upper()} @ {price}")
                wins += 1
                total += 1
                active_trade = None

        if not active_trade and cross != prev_cross:
            waiting_for_cross = cross
            prev_cross = cross

            trend_row = df_trend[df_trend["time"] <= time_now]
            if trend_row.empty:
                continue
            trend = trend_row.iloc[-1]
            ts, tl = trend["EMA_SHORT"], trend["EMA_LONG"]

            if waiting_for_cross == "buy" and ts > tl and cross == "buy":
                gap_pct = abs(ema_s - ema_l) / price * 100
                if gap_pct >= MIN_GAP_PERCENT:
                    entry = price
                    slp = entry - STOP_LOSS_BUFFER
                    tp = entry + STOP_LOSS_BUFFER * RISK_REWARD_RATIO
                    active_trade = {"type": "buy", "entry": entry, "sl": slp, "tp": tp}
                    print(f"[{time_now}] 🚀 BUY ENTRY @ {entry:.4f} | SL: {slp:.4f} | TP: {tp:.4f}")
                    waiting_for_cross = None

            elif waiting_for_cross == "sell" and ts < tl and cross == "sell":
                gap_pct = abs(ema_s - ema_l) / price * 100
                if gap_pct >= MIN_GAP_PERCENT:
                    entry = price
                    slp = entry + STOP_LOSS_BUFFER
                    tp = entry - STOP_LOSS_BUFFER * RISK_REWARD_RATIO
                    active_trade = {"type": "sell", "entry": entry, "sl": slp, "tp": tp}
                    print(f"[{time_now}] 🔻 SELL ENTRY @ {entry:.4f} | SL: {slp:.4f} | TP: {tp:.4f}")
                    waiting_for_cross = None

    print(f"\n📊 FINAL BACKTEST STATS:")
    print(f"Total Trades: {total}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win Rate: {wins/total*100:.2f}%" if total > 0 else "No trades executed.")


# ------------------- MAIN -------------------
if __name__ == "__main__":
    df_entry = fetch_klines(SYMBOL, ENTRY_INTERVAL, ENTRY_LIMIT)
    df_trend = fetch_klines(SYMBOL, TREND_INTERVAL, TREND_LIMIT)
    backtest(df_entry, df_trend)
