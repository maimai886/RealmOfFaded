//! 隨機數：PCG32，O'Neill 2014 的 pcg32 XSH RR 版本。
//! 常數照 pcg-random.org 的參考實作，同一個種子在任何平台都出一樣的序列，測試可以重現。

const MULTIPLIER: u64 = 6364136223846793005;

#[derive(Clone, Debug)]
pub struct Pcg32 {
    state: u64,
    inc: u64,
}

impl Pcg32 {
    /// seed 是起始狀態，stream 選序列，同一個種子不同序列互不相關
    pub fn new(seed: u64, stream: u64) -> Self {
        let mut rng = Pcg32 { state: 0, inc: (stream << 1) | 1 };
        rng.next_u32();
        rng.state = rng.state.wrapping_add(seed);
        rng.next_u32();
        rng
    }

    pub fn next_u32(&mut self) -> u32 {
        let old = self.state;
        self.state = old.wrapping_mul(MULTIPLIER).wrapping_add(self.inc);
        let xorshifted = (((old >> 18) ^ old) >> 27) as u32;
        let rot = (old >> 59) as u32;
        xorshifted.rotate_right(rot)
    }

    /// 0 以上、bound 以下的整數，拒絕取樣避免偏差；bound 是 0 時回 0
    pub fn below(&mut self, bound: u32) -> u32 {
        if bound == 0 {
            return 0;
        }
        let threshold = bound.wrapping_neg() % bound;
        loop {
            let r = self.next_u32();
            if r >= threshold {
                return r % bound;
            }
        }
    }

    /// low 到 high 之間的整數，兩端都包含
    pub fn range_i32(&mut self, low: i32, high: i32) -> i32 {
        if high <= low {
            return low;
        }
        let span = (high as i64 - low as i64 + 1) as u32;
        (low as i64 + self.below(span) as i64) as i32
    }

    /// 0 以上、1 以下的小數，取高 24 位元，f32 每個值都一樣可能
    pub fn unit_f32(&mut self) -> f32 {
        (self.next_u32() >> 8) as f32 / (1u32 << 24) as f32
    }

    /// 千分比的機率判定，例如爆擊率 125 就是 12.5%
    pub fn chance_per_mille(&mut self, per_mille: i32) -> bool {
        per_mille > 0 && (per_mille >= 1000 || (self.below(1000) as i32) < per_mille)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_the_reference_sequence() {
        // pcg-random.org 的 pcg32-demo 用種子 42、序列 54，前六個數
        let mut rng = Pcg32::new(42, 54);
        let got: Vec<u32> = (0..6).map(|_| rng.next_u32()).collect();
        assert_eq!(got, [0xa15c02b7, 0x7b47f409, 0xba1d3330, 0x83d2f293, 0xbfa4784b, 0xcbed606e]);
    }

    #[test]
    fn range_stays_inside_and_hits_both_ends() {
        let mut rng = Pcg32::new(7, 1);
        let mut seen = [false; 5];
        for _ in 0..1000 {
            let v = rng.range_i32(-2, 2);
            assert!((-2..=2).contains(&v));
            seen[(v + 2) as usize] = true;
        }
        assert!(seen.iter().all(|s| *s));
    }

    #[test]
    fn unit_is_below_one() {
        let mut rng = Pcg32::new(1, 1);
        assert!((0..10_000).all(|_| (0.0..1.0).contains(&rng.unit_f32())));
    }

    #[test]
    fn chance_edges() {
        let mut rng = Pcg32::new(3, 3);
        assert!((0..100).all(|_| !rng.chance_per_mille(0)));
        assert!((0..100).all(|_| rng.chance_per_mille(1000)));
    }
}
