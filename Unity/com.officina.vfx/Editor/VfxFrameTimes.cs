using System;
using System.Collections.Generic;
using UnityEngine;

namespace Officina.Vfx.Editor
{
    // 렌더 쪽 순수 셈 — 프레임 시각 · 정사영 크기 · 그림 크기 · 파일 이름. 엔진 없이 시험된다.
    // 프레임 시각은 Python 이 job.frames 로 주는 게 원칙이고, 비었을 때만 여기서 설계 6-2 식으로 셈한다.
    public static class VfxFrameTimes
    {
        public const int MaxFrames = 48;

        // one-shot : t_i = (i - 0.5)/fps, N = ceil((duration + 최대 startDelay + 최대 startLifetime) × fps), 상한 48.
        // loop : 한 바퀴 돈 뒤 t_i = duration + (i - 0.5)/fps, N = ceil(duration × fps). t=0 은 안 뽑는다.
        // 칸 가운데를 찍는 까닭 : i/fps 는 fps 12 플립북 칸 경계와 딱 겹쳐 float 내림 오차로 칸이 빠졌고,
        // (i + 0.5)/fps 는 첫 장이 1번 칸이라 플립북 0번 칸이 안 찍혔다. (i - 0.5)/fps 면 N 장이 0~N-1 칸을 하나씩 덮는다.
        public static List<VfxJobFrame> Compute(VfxRecipe recipe)
        {
            int fps = Math.Max(1, recipe.Fps);
            var frames = new List<VfxJobFrame>();
            if (recipe.Loop)
            {
                int loopCount = Math.Min(MaxFrames, RequiredCount(recipe));
                for (int i = 1; i <= loopCount; i++)
                {
                    frames.Add(new VfxJobFrame { I = i, T = recipe.Duration + (i - 0.5f) / fps });
                }
                return frames;
            }

            int count = Math.Min(MaxFrames, RequiredCount(recipe));
            for (int i = 1; i <= count; i++)
            {
                frames.Add(new VfxJobFrame { I = i, T = (i - 0.5f) / fps });
            }
            return frames;
        }

        // 상한 없이 셈한 프레임 수. MaxFrames 를 넘으면 렌더가 render.frames_capped 로 알린다.
        public static int RequiredCount(VfxRecipe recipe)
        {
            int fps = Math.Max(1, recipe.Fps);
            if (recipe.Loop) { return (int)Math.Ceiling(recipe.Duration * fps - 1e-4); }
            float span = recipe.Duration + MaxOverLayers(recipe, true) + MaxOverLayers(recipe, false);
            return (int)Math.Ceiling(span * fps - 1e-4);
        }

        // orthographicSize = 텍셀 높이 / 2 / ppu (설계 5-2).
        public static float OrthoSize(VfxRecipe recipe)
        {
            return CanvasTexels(recipe).y / 2f / Math.Max(1, recipe.Ppu);
        }

        // 그림 픽셀 = 텍셀 × scale.
        public static Vector2Int PixelSize(VfxRecipe recipe)
        {
            Vector2Int texels = CanvasTexels(recipe);
            int scale = 4;
            if (recipe.Canvas != null && recipe.Canvas.Scale > 0) { scale = recipe.Canvas.Scale; }
            return new Vector2Int(texels.x * scale, texels.y * scale);
        }

        // f001.png · 흑백 짝은 f001_k.png · f001_w.png.
        public static string FileName(int index, string suffix)
        {
            return $"f{index:000}{suffix}.png";
        }

        private static Vector2Int CanvasTexels(VfxRecipe recipe)
        {
            bool ok = recipe.Canvas != null && recipe.Canvas.Texels != null && recipe.Canvas.Texels.Length == 2;
            if (!ok) { return new Vector2Int(64, 64); }
            return new Vector2Int(recipe.Canvas.Texels[0], recipe.Canvas.Texels[1]);
        }

        private static float MaxOverLayers(VfxRecipe recipe, bool delay)
        {
            float max = 0f;
            foreach (VfxLayer layer in recipe.Layers)
            {
                if (layer.Main == null) { continue; }
                VfxValue value = layer.Main.StartLifetime;
                if (delay) { value = layer.Main.StartDelay; }
                max = Math.Max(max, MaxOf(value));
            }
            return max;
        }

        private static float MaxOf(VfxValue value)
        {
            if (value == null) { return 0f; }
            switch (value.Mode)
            {
                case VfxValueMode.TwoConstants:
                    return Math.Max(value.Min, value.Max);
                case VfxValueMode.Curve:
                    return MaxKey(value.Keys) * value.Mult;
                case VfxValueMode.TwoCurves:
                    return Math.Max(MaxKey(value.Keys), MaxKey(value.MaxKeys)) * value.Mult;
                default:
                    return value.Constant;
            }
        }

        private static float MaxKey(List<Vector2> keys)
        {
            float max = 0f;
            foreach (Vector2 key in keys)
            {
                max = Math.Max(max, key.y);
            }
            return max;
        }
    }
}
