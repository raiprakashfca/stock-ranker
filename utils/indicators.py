# Ensure timestamp is datetime and set as index
df['date'] = pd.to_datetime(df['date'])
df.set_index('date', inplace=True)

# Price columns required
if not {'open', 'high', 'low', 'close', 'volume'}.issubset(df.columns):
    return {}

# Trend Indicators
ema8 = ta.ema(df['close'], length=8)
ema21 = ta.ema(df['close'], length=21)
supertrend = ta.supertrend(df['high'], df['low'], df['close'])["SUPERT_7_3.0"]

# Momentum Indicators
macd = ta.macd(df['close'])
rsi = ta.rsi(df['close'])
adx = ta.adx(df['high'], df['low'], df['close'])

# Volume Indicators
obv = ta.obv(df['close'], df['volume'])
mfi = ta.mfi(df['high'], df['low'], df['close'], df['volume'])

# Latest values
close = df['close'].iloc[-1]
latest_ema8 = ema8.iloc[-1]
latest_ema21 = ema21.iloc[-1]
latest_supertrend = supertrend.iloc[-1]
latest_macd = macd['MACD_12_26_9'].iloc[-1]
latest_signal = macd['MACDs_12_26_9'].iloc[-1]
latest_rsi = rsi.iloc[-1]
latest_adx = adx['ADX_14'].iloc[-1]
obv_diff = obv.diff().iloc[-1]
latest_mfi = mfi.iloc[-1]

# Decision Tree Logic

# Trend Check
if latest_ema8 > latest_ema21 and close > latest_supertrend:
    trend = 'Strong'
elif latest_ema8 > latest_ema21 or close > latest_supertrend:
    trend = 'Moderate'
else:
    trend = 'Weak'

# Momentum Check
momentum_checks = sum([
    latest_macd > latest_signal,
    latest_rsi > 55,
    latest_adx > 20
])
if momentum_checks == 3:
    momentum = 'Strong'
elif momentum_checks == 2:
    momentum = 'Moderate'
else:
    momentum = 'Weak'

# Volume Check
volume_checks = sum([
    obv_diff > 0,
    latest_mfi > 55
])
if volume_checks == 2:
    volume = 'Strong'
elif volume_checks == 1:
    volume = 'Moderate'
else:
    volume = 'Weak'

# Rule-Based TMV Scoring
if trend == 'Strong' and momentum == 'Strong':
    tmv_score = 1.0
elif trend == 'Moderate' and momentum == 'Strong' and volume == 'Strong':
    tmv_score = 0.9
elif (trend == 'Moderate' or momentum == 'Moderate') and volume == 'Strong':
    tmv_score = 0.7
elif trend == 'Weak' and momentum == 'Weak':
    tmv_score = 0.2
else:
    tmv_score = 0.5

# Final TMV Score and qualitative direction
scores['TMV Score'] = round(tmv_score, 2)
scores['Trend Direction'] = (
    'Bullish' if tmv_score >= 0.8 else
    'Neutral' if tmv_score >= 0.5 else
    'Bearish'
)

# Reversal Probability (based on RSI oversold/overbought zones)
recent_rsi = rsi.iloc[-5:]
reversal = ((recent_rsi < 30) | (recent_rsi > 70)).sum() / 5
scores['Reversal Probability'] = round(reversal, 2)

return scores
