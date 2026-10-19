using System.Collections.Generic;
using UnityEngine;

namespace Officina.Vfx
{
    // 수명 색 하나. 색 키 · 알파 키는 각각 8개까지(Unity 한도), 넘는 검사는 Python check 몫이다.
    public class VfxGradient
    {
        public List<GradientColorKey> ColorKeys = new List<GradientColorKey>();
        public List<GradientAlphaKey> AlphaKeys = new List<GradientAlphaKey>();
        public GradientMode Mode = GradientMode.Fixed;

        public Gradient ToGradient()
        {
            var gradient = new Gradient { mode = Mode };
            List<GradientColorKey> colors = ColorKeys;
            if (colors.Count == 0)
            {
                colors = new List<GradientColorKey> { new GradientColorKey(Color.white, 0f) };
            }
            List<GradientAlphaKey> alphas = AlphaKeys;
            if (alphas.Count == 0)
            {
                alphas = new List<GradientAlphaKey> { new GradientAlphaKey(1f, 0f) };
            }
            if (Mode == GradientMode.Fixed)
            {
                colors = ShiftColorKeys(colors);
                alphas = ShiftAlphaKeys(alphas);
            }
            gradient.SetKeys(colors.ToArray(), alphas.ToArray());
            return gradient;
        }

        // 레시피의 fixed 키 [t, v] 는 「t 부터 다음 키까지 v」 다(설계 2-6 「알파는 0.8 에서 끊긴다」).
        // Unity Fixed 는 「t 에서 t 이상인 첫 키의 값」 이라(실측 2026-10-15), 키 i 의 값을 다음 키 시각으로, 끝 키는 1 로 옮긴다.
        private static List<GradientColorKey> ShiftColorKeys(List<GradientColorKey> keys)
        {
            var shifted = new List<GradientColorKey>(keys.Count);
            for (int i = 0; i < keys.Count; i++)
            {
                shifted.Add(new GradientColorKey(keys[i].color, NextTime(keys.Count, i, k => keys[k].time)));
            }
            return shifted;
        }

        private static List<GradientAlphaKey> ShiftAlphaKeys(List<GradientAlphaKey> keys)
        {
            var shifted = new List<GradientAlphaKey>(keys.Count);
            for (int i = 0; i < keys.Count; i++)
            {
                shifted.Add(new GradientAlphaKey(keys[i].alpha, NextTime(keys.Count, i, k => keys[k].time)));
            }
            return shifted;
        }

        private static float NextTime(int count, int index, System.Func<int, float> timeAt)
        {
            if (index + 1 < count) { return timeAt(index + 1); }
            return 1f;
        }
    }
}
