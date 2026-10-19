using Newtonsoft.Json;
using UnityEngine;

namespace Officina.Vfx
{
    // emission.bursts 한 줄. [t, n] 이나 {t, n, cycles, interval} 꼴.
    [JsonConverter(typeof(VfxBurstConverter))]
    public class VfxBurst
    {
        public float Time;
        public float Count;
        public int Cycles = 1;
        public float Interval = 0.01f;

        public ParticleSystem.Burst ToBurst()
        {
            return new ParticleSystem.Burst(Time, new ParticleSystem.MinMaxCurve(Count), Cycles, Interval);
        }
    }
}
