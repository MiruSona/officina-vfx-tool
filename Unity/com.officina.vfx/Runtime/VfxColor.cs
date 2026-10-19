using Newtonsoft.Json;
using UnityEngine;

namespace Officina.Vfx
{
    // resolved.json 의 색 칸 하나. hex · random · gradient · random_gradient 넷을 MinMaxGradient 로 옮긴다.
    [JsonConverter(typeof(VfxColorConverter))]
    public class VfxColor
    {
        public VfxColorMode Mode;
        public Color Color = Color.white;
        public Color ColorMax = Color.white;
        public VfxGradient Gradient;
        public VfxGradient GradientMax;

        public ParticleSystem.MinMaxGradient ToMinMaxGradient()
        {
            switch (Mode)
            {
                case VfxColorMode.TwoColors:
                    return new ParticleSystem.MinMaxGradient(Color, ColorMax);
                case VfxColorMode.Gradient:
                    return new ParticleSystem.MinMaxGradient(Gradient.ToGradient());
                case VfxColorMode.TwoGradients:
                    return new ParticleSystem.MinMaxGradient(Gradient.ToGradient(), GradientMax.ToGradient());
                default:
                    return new ParticleSystem.MinMaxGradient(Color);
            }
        }
    }
}
