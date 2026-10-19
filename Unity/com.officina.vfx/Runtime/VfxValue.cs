using System.Collections.Generic;
using Newtonsoft.Json;
using UnityEngine;

namespace Officina.Vfx
{
    // resolved.json 의 숫자 칸 하나. 숫자 · random · curve · random_curve 넷을 MinMaxCurve 로 옮긴다.
    [JsonConverter(typeof(VfxValueConverter))]
    public class VfxValue
    {
        public VfxValueMode Mode;
        public float Constant;
        public float Min;
        public float Max;
        public List<Vector2> Keys = new List<Vector2>();
        public List<Vector2> MaxKeys = new List<Vector2>();
        public float Mult = 1f;
        public bool Step;

        public static VfxValue Of(float value)
        {
            return new VfxValue { Mode = VfxValueMode.Constant, Constant = value };
        }

        public ParticleSystem.MinMaxCurve ToMinMaxCurve()
        {
            switch (Mode)
            {
                case VfxValueMode.TwoConstants:
                    return new ParticleSystem.MinMaxCurve(Min, Max);
                case VfxValueMode.Curve:
                    return new ParticleSystem.MinMaxCurve(Mult, BuildCurve(Keys, Step));
                case VfxValueMode.TwoCurves:
                    return new ParticleSystem.MinMaxCurve(Mult, BuildCurve(Keys, Step), BuildCurve(MaxKeys, Step));
                default:
                    return new ParticleSystem.MinMaxCurve(Constant);
            }
        }

        // 같은 모드의 0. velocityOverLifetime 의 x·y·z 는 모드가 같아야 해서 빈 축을 이걸로 채운다.
        public ParticleSystem.MinMaxCurve ToZeroLike()
        {
            AnimationCurve zero = AnimationCurve.Constant(0f, 1f, 0f);
            switch (Mode)
            {
                case VfxValueMode.TwoConstants:
                    return new ParticleSystem.MinMaxCurve(0f, 0f);
                case VfxValueMode.Curve:
                    return new ParticleSystem.MinMaxCurve(0f, zero);
                case VfxValueMode.TwoCurves:
                    return new ParticleSystem.MinMaxCurve(0f, zero, AnimationCurve.Constant(0f, 1f, 0f));
                default:
                    return new ParticleSystem.MinMaxCurve(0f);
            }
        }

        // step 이면 탄젠트 무한 = 계단. 아니면 자동 평활.
        private static AnimationCurve BuildCurve(List<Vector2> keys, bool step)
        {
            var frames = new Keyframe[keys.Count];
            for (int i = 0; i < keys.Count; i++)
            {
                frames[i] = new Keyframe(keys[i].x, keys[i].y);
                if (step)
                {
                    frames[i].inTangent = float.PositiveInfinity;
                    frames[i].outTangent = float.PositiveInfinity;
                }
            }

            var curve = new AnimationCurve(frames);
            if (step) { return curve; }

            for (int i = 0; i < curve.length; i++)
            {
                curve.SmoothTangents(i, 0f);
            }
            return curve;
        }
    }
}
