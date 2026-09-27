"""
技能放出來和詠唱的音效，全部用程式合成，輸出到 assets/audio/skills/*.wav
2026-09-27 使用者：施放技能的音效很鳥、現在都同一個，要照技能的特性播適合的音效。
專案裡的 Kenney 三包只有打擊、介面、布料和刀子，沒有魔法類的聲音，所以依技能的性質自己合成：
喝止、衝步、魔力彈、符文、雷、風、聖光、治療、增益、印記、瞬移、暗、詠唱；
2026-09-27 使用者同意下載 TomMusic 免費奇幻音效包之後，刀光、重揮、突刺、崩岩、岩膚、引爆、火、冰、弓改用裡面的錄音
哪一招用哪一個寫在 data/vfx.json 每一招的 sound，事件的音量音高寫在 src/audio/sound_map.gd
用法：python art_pipeline/audio/skill_sfx.py，只需要 numpy
"""
import math
import os
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "assets", "audio", "skills")
RATE = 44100
# 固定亂數種子，每次產出一模一樣，版本庫才不會一直出現差異
rng = np.random.default_rng(20260927)


def t_axis(duration):
    return np.arange(int(duration * RATE)) / RATE


def noise(duration):
    return rng.uniform(-1.0, 1.0, int(duration * RATE))


def lowpass(signal, cutoff):
    """一階低通；cutoff 可以是一個數字或每個樣本一個數字，拿來做掃頻"""
    cut = np.broadcast_to(np.asarray(cutoff, dtype=float), signal.shape)
    alpha = 1.0 - np.exp(-2.0 * math.pi * cut / RATE)
    out = np.empty_like(signal)
    y = 0.0
    for i in range(signal.size):
        y += alpha[i] * (signal[i] - y)
        out[i] = y
    return out


def highpass(signal, cutoff):
    return signal - lowpass(signal, cutoff)


def bandpass(signal, center, q):
    """二階帶通，中心頻率可以逐樣本改變，掃頻的呼嘯聲靠這個"""
    c = np.broadcast_to(np.asarray(center, dtype=float), signal.shape)
    out = np.empty_like(signal)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(signal.size):
        w0 = 2.0 * math.pi * min(c[i], RATE * 0.45) / RATE
        alpha = math.sin(w0) / (2.0 * q)
        cos = math.cos(w0)
        a0 = 1.0 + alpha
        b0 = alpha / a0
        b2 = -alpha / a0
        a1 = -2.0 * cos / a0
        a2 = (1.0 - alpha) / a0
        x0 = signal[i]
        y0 = b0 * x0 + b2 * x2 - a1 * y1 - a2 * y2
        out[i] = y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return out


def sweep(f0, f1, duration, curve="exp"):
    t = t_axis(duration)
    k = t / max(duration, 1e-6)
    return f0 * (f1 / f0) ** k if curve == "exp" else f0 + (f1 - f0) * k


def tone(freq, duration, phase=0.0):
    """freq 可以是逐樣本的頻率，積分成相位，掃頻不會有斷點"""
    f = np.broadcast_to(np.asarray(freq, dtype=float), (int(duration * RATE),))
    return np.sin(phase + 2.0 * math.pi * np.cumsum(f) / RATE)


def env(duration, attack, decay, hold=0.0):
    """起音線性上升、之後指數衰減；decay 是掉到大約 5% 的秒數"""
    t = t_axis(duration)
    up = np.clip(t / max(attack, 1e-4), 0.0, 1.0)
    down = np.where(t < attack + hold, 1.0, np.exp(-3.0 * (t - attack - hold) / max(decay, 1e-4)))
    return up * down


def swell(duration, peak):
    """先慢慢變大、在 peak 那個比例最響、再收掉，像東西從旁邊掃過去"""
    k = t_axis(duration) / duration
    return np.where(k < peak, np.sin(0.5 * math.pi * k / peak) ** 2,
                    np.clip(np.cos(0.5 * math.pi * np.clip((k - peak) / (1.0 - peak), 0.0, 1.0)), 0.0, 1.0) ** 1.5)


def pad(signal, duration):
    out = np.zeros(int(duration * RATE))
    n = min(out.size, signal.size)
    out[:n] = signal[:n]
    return out


def mix(duration, *layers):
    """每層是 (起點秒, 訊號, 音量)，全部疊在同一條上"""
    out = np.zeros(int(duration * RATE))
    for start, signal, gain in layers:
        i = int(start * RATE)
        n = min(signal.size, out.size - i)
        if n > 0:
            out[i:i + n] += signal[:n] * gain
    return out


def reverb(signal, length=0.8, amount=0.3, tone_cut=5000.0):
    """衰減的噪音當殘響，用 FFT 摺積，聖光和冰這種要空間感的才加"""
    ir_noise = lowpass(noise(length), tone_cut)
    ir = ir_noise * np.exp(-4.0 * t_axis(length) / length)
    ir[0] = 0.0
    n = signal.size + ir.size
    size = 1 << (n - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(signal, size) * np.fft.rfft(ir, size), size)[:n]
    wet /= max(np.max(np.abs(wet)), 1e-9)
    dry = np.concatenate([signal, np.zeros(ir.size)])
    return dry + wet * amount * np.max(np.abs(signal))


def crackle(duration, rate, center, decay_s, shape=1.0):
    """一顆一顆的碎裂聲：隨機時間點放很短的噪音爆點，密度照 shape 往後變稀"""
    out = np.zeros(int(duration * RATE))
    count = int(rate * duration)
    for _ in range(count):
        at = (rng.random() ** shape) * duration
        length = rng.uniform(0.003, 0.012)
        grain = noise(length) * np.exp(-np.arange(int(length * RATE)) / (length * RATE * 0.3))
        i = int(at * RATE)
        n = min(grain.size, out.size - i)
        out[i:i + n] += grain[:n] * rng.uniform(0.3, 1.0) * math.exp(-3.0 * at / decay_s)
    return bandpass(out, center, 0.9)


def bell(freq, duration, partials=(1.0, 2.0, 3.0, 4.2), decay=0.8):
    t_len = duration
    out = np.zeros(int(t_len * RATE))
    for index, ratio in enumerate(partials):
        out += tone(freq * ratio, t_len) * env(t_len, 0.002, decay / (1.0 + index * 0.6)) / (1.0 + index)
    return out



def whoosh(duration, f0, f1, q=1.2, peak=0.35):
    return bandpass(noise(duration), sweep(f0, f1, duration), q) * swell(duration, peak)


# ---- 各種聲音 ----






def shout():
    """喝止：往前推出去的一團低頻衝擊波"""
    d = 0.7
    wave_ = tone(sweep(160, 50, 0.6) * (1.0 + 0.03 * np.sin(2 * math.pi * 22 * t_axis(0.6))), 0.6)
    wave_ *= env(0.6, 0.01, 0.5)
    air = lowpass(noise(0.5), sweep(1800, 300, 0.5)) * env(0.5, 0.005, 0.4)
    air /= max(np.max(np.abs(air)), 1e-9)
    return mix(d, (0.0, wave_, 1.0), (0.0, air, 0.6))


def dash():
    """衝步：蹬地的一下加上短促的風"""
    d = 0.35
    kick = tone(sweep(140, 60, 0.12), 0.12) * env(0.12, 0.002, 0.1)
    return mix(d, (0.0, kick, 0.8), (0.02, whoosh(0.25, 900, 2800, 1.4, 0.4), 1.0))


def arcane():
    """魔力彈：往上揚的魔力啾聲，帶一點閃爍的泛音和空氣感"""
    d = 0.55
    f = np.concatenate([sweep(320, 1250, 0.12), np.full(int(0.38 * RATE), 1250.0)])
    f = f * (1.0 + 0.02 * np.sin(2 * math.pi * 11 * t_axis(0.5)))
    body = tone(f, 0.5) * env(0.5, 0.01, 0.4)
    sparkle = sum(tone(f * r, 0.5) for r in (2.01, 2.99)) * env(0.5, 0.01, 0.25)
    sparkle *= 0.5 + 0.5 * np.sin(2 * math.pi * 31 * t_axis(0.5))
    air = highpass(noise(0.5), 3500) * env(0.5, 0.02, 0.3)
    return reverb(mix(d, (0.0, body, 0.7), (0.0, sparkle, 0.2), (0.0, air, 0.15)), 0.5, 0.25)


def glyph():
    """符文：畫在地上的法陣，一串玻璃般的閃爍加上底下低低的共鳴"""
    d = 0.9
    t = t_axis(0.8)
    shimmer = np.zeros(t.size)
    for f in rng.uniform(1500, 4500, 7):
        shimmer += np.sin(2 * math.pi * f * t) * (0.5 + 0.5 * np.sin(2 * math.pi * rng.uniform(6, 18) * t + rng.uniform(0, 6)))
    shimmer *= env(0.8, 0.15, 0.6) / 7.0
    hum = (tone(110, 0.8) + 0.6 * tone(165, 0.8)) * env(0.8, 0.1, 0.7)
    return reverb(mix(d, (0.0, shimmer, 0.8), (0.0, hum, 0.35)), 0.7, 0.35)





def thunder():
    """雷：劈啪亂跳的電流聲，接一段悶雷"""
    d = 1.1
    t = t_axis(0.5)
    gate = (np.sin(2 * math.pi * (40 + 30 * rng.random()) * t + 6 * np.sin(2 * math.pi * 7 * t)) > 0.2).astype(float)
    zap = bandpass(noise(0.5), 3200, 0.8) * gate * env(0.5, 0.001, 0.35)
    zap /= max(np.max(np.abs(zap)), 1e-9)
    crack = highpass(noise(0.05), 1500) * env(0.05, 0.0005, 0.04)
    boom = lowpass(noise(1.0), 120) * env(1.0, 0.03, 0.9)
    boom /= max(np.max(np.abs(boom)), 1e-9)
    return mix(d, (0.0, crack, 0.8), (0.0, zap, 0.7), (0.08, boom, 0.8))


def wind():
    """風：帶音高的呼嘯往上捲再落下"""
    d = 0.95
    k = t_axis(0.9) / 0.9
    center = 500 + 1500 * np.sin(math.pi * k) ** 1.5
    a = bandpass(noise(0.9), center, 5.0)
    b = bandpass(noise(0.9), center * 1.6, 6.0)
    howl = (a + 0.5 * b) * swell(0.9, 0.45)
    howl /= max(np.max(np.abs(howl)), 1e-9)
    return mix(d, (0.0, howl, 1.0))


def holy():
    """聖光：往上爬的四個鐘音，長長的殘響"""
    d = 1.3
    notes = (1046.5, 1318.5, 1568.0, 2093.0)
    layers = [(i * 0.06, bell(f, 0.9, (1.0, 2.0, 3.0, 4.2), 0.8), 0.3) for i, f in enumerate(notes)]
    glow = sum(tone(f * 0.5, 1.0) for f in notes[:3]) * swell(1.0, 0.3) / 3.0
    layers.append((0.0, glow, 0.25))
    return reverb(mix(d, *layers), 1.2, 0.5, 6000)


def heal():
    """治療：一串輕輕往上的亮音，底下一層暖暖的和弦"""
    d = 1.1
    notes = (784.0, 880.0, 1046.5, 1174.7, 1318.5, 1568.0)
    layers = [(i * 0.045, bell(f, 0.4, (1.0, 2.0, 3.0), 0.3), 0.22) for i, f in enumerate(notes)]
    chord = (tone(392.0, 0.9) + tone(493.9, 0.9) + tone(587.3, 0.9)) * swell(0.9, 0.35) / 3.0
    layers.append((0.0, chord, 0.3))
    return reverb(mix(d, *layers), 0.9, 0.45, 5500)


def buff():
    """增益：力量灌進身體，往上爬的音加一層亮亮的沙沙聲"""
    d = 0.7
    f = sweep(220, 660, 0.55)
    body = (tone(f, 0.55) + 0.5 * tone(f * 2, 0.55) + 0.25 * tone(f * 3, 0.55)) * swell(0.55, 0.7)
    shine = highpass(noise(0.55), 4000) * swell(0.55, 0.8)
    return reverb(mix(d, (0.0, body, 0.6), (0.0, shine, 0.25)), 0.5, 0.25)



def mark():
    """印記：叮叮兩聲金屬輕響，第二聲高一點"""
    d = 0.4
    a = bell(2600, 0.25, (1.0, 2.76, 5.4), 0.18)
    b = bell(3300, 0.25, (1.0, 2.76, 5.4), 0.18)
    pop = lowpass(noise(0.03), 1500) * env(0.03, 0.001, 0.025)
    return mix(d, (0.0, pop, 0.4), (0.0, a, 0.5), (0.07, b, 0.45))


def warp():
    """瞬移：吸進去的聲音越來越高、啪地收掉，接一聲小亮音"""
    d = 0.5
    rise = bandpass(noise(0.3), sweep(600, 3200, 0.3), 2.5) * np.linspace(0.0, 1.0, int(0.3 * RATE)) ** 2
    rise /= max(np.max(np.abs(rise)), 1e-9)
    ping = bell(2400, 0.2, (1.0, 2.0), 0.15)
    return mix(d, (0.0, rise, 0.9), (0.29, ping, 0.4))


def dark():
    """暗：兩個差一點點的低音互相拍打，往下沉的滑音"""
    d = 0.9
    drone = (tone(55, 0.85) + tone(58.5, 0.85)) * swell(0.85, 0.3) * 0.5
    fall = tone(sweep(420, 70, 0.6), 0.6) * env(0.6, 0.02, 0.5)
    murk = lowpass(noise(0.85), 400) * swell(0.85, 0.3)
    murk /= max(np.max(np.abs(murk)), 1e-9)
    return mix(d, (0.0, drone, 0.9), (0.0, fall, 0.4), (0.0, murk, 0.3))


def chant():
    """詠唱：輕輕的和弦慢慢浮起來，帶一點空氣感，音高在 sound_map 依屬性調"""
    d = 1.0
    t = t_axis(0.95)
    trem = 0.8 + 0.2 * np.sin(2 * math.pi * 5.5 * t)
    chord = (tone(330, 0.95) + 0.7 * tone(495, 0.95) + 0.4 * tone(660, 0.95)) * trem
    chord *= swell(0.95, 0.35)
    air = highpass(noise(0.95), 3000) * swell(0.95, 0.4)
    return reverb(mix(d, (0.0, chord, 0.4), (0.0, air, 0.12)), 0.7, 0.35)


SOUNDS = { "shout": shout,
    "dash": dash, "arcane": arcane, "glyph": glyph,
    "thunder": thunder, "wind": wind, "holy": holy, "heal": heal, "buff": buff,
    "mark": mark, "warp": warp, "dark": dark, "chant": chant,
}


def write(name, signal):
    # 頭尾各淡 5 毫秒免得爆音，峰值壓在 -1 dBFS，和 Kenney 素材同一個基準
    fade = int(0.005 * RATE)
    assert np.all(np.isfinite(signal)), name
    signal = signal.copy()
    signal[:fade] *= np.linspace(0.0, 1.0, fade)
    signal[-fade:] *= np.linspace(1.0, 0.0, fade)
    peak = max(np.max(np.abs(signal)), 1e-9)
    signal = signal / peak * 10 ** (-1.0 / 20.0)
    data = (signal * 32767).astype("<i2").tobytes()
    path = os.path.join(OUT_DIR, name + ".wav")
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(data)
    return path


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, make in SOUNDS.items():
        write(name, make())
    print("[audio/skills] 輸出 %d 個到 %s" % (len(SOUNDS), OUT_DIR))


if __name__ == "__main__":
    main()
