using UnityEngine;

namespace Officina.Vfx.Editor
{
    // 수명 모듈 여섯 (velocity · color · size · rotation · noise · textureSheet). 모듈 하나 = 함수 하나.
    // 레시피에 안 적은 모듈은 끈다.
    public static class VfxLifetimeModules
    {
        // x · y · z 는 Unity 가 같은 모드를 요구한다. 빈 축은 적힌 축과 같은 모드의 0 으로 채운다.
        public static void ApplyVelocity(ParticleSystem ps, VfxLayer layer, VfxResult result)
        {
            var velocity = ps.velocityOverLifetime;
            VfxVelocityOverLifetimeModule m = layer.VelocityOverLifetime;
            velocity.enabled = m != null;
            if (m == null) { return; }
            VfxModules.ReportExtra(result, layer.Name, "velocityOverLifetime.", m.Extra);

            VfxValue reference = m.X;
            if (reference == null) { reference = m.Y; }
            if (reference != null)
            {
                if (m.X != null && m.Y != null && m.X.Mode != m.Y.Mode)
                {
                    result.Issue("build.mixed_modes", layer.Name, $"velocityOverLifetime.x={m.X.Mode} · y={m.Y.Mode}");
                }
                velocity.x = AxisOrZero(m.X, reference);
                velocity.y = AxisOrZero(m.Y, reference);
                velocity.z = reference.ToZeroLike();
            }
            if (m.OrbitalZ != null)
            {
                velocity.orbitalX = m.OrbitalZ.ToZeroLike();
                velocity.orbitalY = m.OrbitalZ.ToZeroLike();
                velocity.orbitalZ = m.OrbitalZ.ToMinMaxCurve();
            }
            if (m.Radial != null) { velocity.radial = m.Radial.ToMinMaxCurve(); }
            if (m.Space != null)
            {
                velocity.space = VfxModules.ParseSpace(m.Space, layer.Name, "velocityOverLifetime.space", result);
            }
        }

        public static void ApplyColor(ParticleSystem ps, VfxLayer layer, VfxResult result)
        {
            var color = ps.colorOverLifetime;
            VfxColorOverLifetimeModule m = layer.ColorOverLifetime;
            color.enabled = m != null;
            if (m == null) { return; }
            VfxModules.ReportExtra(result, layer.Name, "colorOverLifetime.", m.Extra);
            if (m.Color == null) { return; }
            // 수명 색은 시간에 따라 바뀌는 값이라 gradient · random_gradient 만 받는다. hex · random 은 startColor 몫.
            if (m.Color.Mode != VfxColorMode.Gradient && m.Color.Mode != VfxColorMode.TwoGradients)
            {
                result.Issue("build.bad_value", layer.Name, $"colorOverLifetime.color={m.Color.Mode} — gradient 만 받는다, 끔");
                color.enabled = false;
                return;
            }
            color.color = m.Color.ToMinMaxGradient();
        }

        public static void ApplySize(ParticleSystem ps, VfxLayer layer, VfxResult result)
        {
            var size = ps.sizeOverLifetime;
            VfxSizeOverLifetimeModule m = layer.SizeOverLifetime;
            size.enabled = m != null;
            if (m == null) { return; }
            VfxModules.ReportExtra(result, layer.Name, "sizeOverLifetime.", m.Extra);
            size.separateAxes = false;
            if (m.Size != null) { size.size = m.Size.ToMinMaxCurve(); }
        }

        public static void ApplyRotation(ParticleSystem ps, VfxLayer layer, VfxResult result)
        {
            var rotation = ps.rotationOverLifetime;
            VfxRotationOverLifetimeModule m = layer.RotationOverLifetime;
            rotation.enabled = m != null;
            if (m == null) { return; }
            VfxModules.ReportExtra(result, layer.Name, "rotationOverLifetime.", m.Extra);
            rotation.separateAxes = false;
            if (m.Z != null) { rotation.z = m.Z.ToMinMaxCurve(); }
        }

        public static void ApplyNoise(ParticleSystem ps, VfxLayer layer, VfxResult result)
        {
            var noise = ps.noise;
            VfxNoiseModule m = layer.Noise;
            noise.enabled = m != null;
            if (m == null) { return; }
            VfxModules.ReportExtra(result, layer.Name, "noise.", m.Extra);

            noise.separateAxes = false;
            if (m.Strength != null) { noise.strength = m.Strength.ToMinMaxCurve(); }
            if (m.Frequency.HasValue) { noise.frequency = m.Frequency.Value; }
            if (m.ScrollSpeed != null) { noise.scrollSpeed = m.ScrollSpeed.ToMinMaxCurve(); }
            if (m.Octaves.HasValue) { noise.octaveCount = m.Octaves.Value; }
            if (m.Quality != null)
            {
                if (TryParseQuality(m.Quality, out ParticleSystemNoiseQuality quality)) { noise.quality = quality; }
                else { result.Issue("build.bad_value", layer.Name, $"noise.quality={m.Quality}"); }
            }
        }

        // 격자 시트 · FPS 시간. row 없으면 시트 전체, 있으면 한 줄만. Frame Blending 은 정점 스트림(AnimBlend)을 안 넣어 꺼진다.
        public static void ApplyTextureSheet(ParticleSystem ps, VfxLayer layer, VfxResult result)
        {
            var sheet = ps.textureSheetAnimation;
            VfxTextureSheetModule m = layer.TextureSheet;
            sheet.enabled = m != null;
            if (m == null) { return; }
            VfxModules.ReportExtra(result, layer.Name, "textureSheet.", m.Extra);

            sheet.mode = ParticleSystemAnimationMode.Grid;
            sheet.animation = ParticleSystemAnimationType.WholeSheet;
            sheet.timeMode = ParticleSystemAnimationTimeMode.FPS;
            if (m.Tiles != null && m.Tiles.Length == 2)
            {
                sheet.numTilesX = m.Tiles[0];
                sheet.numTilesY = m.Tiles[1];
            }
            else if (m.Tiles != null)
            {
                result.Issue("build.bad_value", layer.Name, "textureSheet.tiles 는 [x, y] 두 칸");
            }
            // 줄은 tiles 를 넣은 뒤에 고른다 — 범위 검사가 numTilesY 를 본다.
            if (m.Row != null) { ApplyRow(sheet, m.Row, layer.Name, result); }
            if (m.Fps.HasValue) { sheet.fps = m.Fps.Value; }
            if (m.StartFrame != null) { sheet.startFrame = ToNormalizedFrame(m.StartFrame, FramesInAnimation(sheet)); }
            if (m.Cycles.HasValue) { sheet.cycleCount = m.Cycles.Value; }
        }

        // 틀린 꼴 · 범위 밖 줄은 issue 를 남기고 시트 전체(WholeSheet)로 둔다 — 없는 줄을 고르면 빈 칸이 그려진다.
        private static void ApplyRow(ParticleSystem.TextureSheetAnimationModule sheet, VfxRow row, string layer, VfxResult result)
        {
            if (row.IsBad)
            {
                result.Issue("build.bad_value", layer, $"textureSheet.row={row.Bad} — 0 이상 정수나 \"random\" 만, 시트 전체로 둠");
                return;
            }
            if (!row.IsRandom && row.Index >= sheet.numTilesY)
            {
                result.Issue("build.texture_sheet_row", layer, $"textureSheet.row={row.Index} — 줄은 {sheet.numTilesY}개(0 ~ {sheet.numTilesY - 1}), 시트 전체로 둠");
                return;
            }
            sheet.animation = ParticleSystemAnimationType.SingleRow;
            if (row.IsRandom)
            {
                sheet.rowMode = ParticleSystemAnimationRowMode.Random;
                return;
            }
            sheet.rowMode = ParticleSystemAnimationRowMode.Custom;
            sheet.rowIndex = row.Index;
        }

        // 한 애니메이션이 도는 칸 수. Single Row 는 한 줄 길이(numTilesX)다 — 실측 2026-10-15(VfxTextureSheetRowTests) :
        // 4×2 시트 SingleRow 에서 startFrame 0.25 → 1번 칸. 시트 전체(8칸)로 나눴다면 0번 칸이 나왔다.
        private static int FramesInAnimation(ParticleSystem.TextureSheetAnimationModule sheet)
        {
            if (sheet.animation == ParticleSystemAnimationType.SingleRow) { return sheet.numTilesX; }
            return sheet.numTilesX * sheet.numTilesY;
        }

        // 레시피 startFrame 은 프레임 번호(0 부터). API 는 0~1 비율이라 칸 수로 나눈다 — 실측 2026-10-15 :
        // 2×2 시트에서 0.25 → 1번 · 0.5 → 2번 · 1 이상 → 끝 칸(1 로 잘림). 칸 = floor(v) 라 고른 random 은 [0, 칸 수].
        private static ParticleSystem.MinMaxCurve ToNormalizedFrame(VfxValue frame, int tiles)
        {
            ParticleSystem.MinMaxCurve curve = frame.ToMinMaxCurve();
            if (tiles <= 1) { return curve; }
            float scale = 1f / tiles;
            // MinMaxCurve.constant 는 constantMax 와 같은 칸이라 모드별로 한 번씩만 곱한다.
            switch (curve.mode)
            {
                case ParticleSystemCurveMode.Constant:
                    curve.constant *= scale;
                    break;
                case ParticleSystemCurveMode.TwoConstants:
                    curve.constantMin *= scale;
                    curve.constantMax *= scale;
                    break;
                default:
                    curve.curveMultiplier *= scale;
                    break;
            }
            return curve;
        }

        private static ParticleSystem.MinMaxCurve AxisOrZero(VfxValue axis, VfxValue reference)
        {
            if (axis == null) { return reference.ToZeroLike(); }
            return axis.ToMinMaxCurve();
        }

        private static bool TryParseQuality(string name, out ParticleSystemNoiseQuality quality)
        {
            switch (name)
            {
                case "Low": quality = ParticleSystemNoiseQuality.Low; return true;
                case "Medium": quality = ParticleSystemNoiseQuality.Medium; return true;
                case "High": quality = ParticleSystemNoiseQuality.High; return true;
                default: quality = ParticleSystemNoiseQuality.High; return false;
            }
        }
    }
}
